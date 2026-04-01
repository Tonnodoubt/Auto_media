import asyncio
import hashlib
import logging
import re
import time
from collections import OrderedDict
from typing import Any, Callable, Optional
from urllib.parse import urlparse

import httpx

from app.core.api_keys import inject_art_style
from app.paths import VIDEO_DIR
from app.services.video_providers.factory import get_video_provider

logger = logging.getLogger(__name__)

VIDEO_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_MODEL = "wan2.6-i2v-flash"
DEFAULT_PROVIDER = "dashscope"
DUAL_FRAME_PROVIDERS = {"doubao"}


def _versioned_media_name(stem: str, suffix: str) -> str:
    token = hashlib.md5(f"{stem}:{time.time_ns()}".encode()).hexdigest()[:8]
    safe_stem = re.sub(r"[^A-Za-z0-9_-]", "_", stem)
    safe_stem = re.sub(r"_+", "_", safe_stem).strip("_") or "asset"
    return f"{safe_stem}_{token}{suffix}"


def _collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _merge_reference_images(*sources: Any) -> list[Any]:
    merged: list[Any] = []
    seen: set[tuple[str, ...]] = set()

    for source in sources:
        if not isinstance(source, list):
            continue
        for item in source:
            if isinstance(item, dict):
                image_url = _collapse_spaces(str(item.get("image_url", "")))
                image_path = _collapse_spaces(str(item.get("image_path", "")))
                identity = ("mapping", image_url, image_path)
                if not image_url and not image_path:
                    fallback_identity = _collapse_spaces(str(item.get("id", ""))) or _collapse_spaces(str(item.get("kind", "")))
                    if not fallback_identity:
                        continue
                    identity = ("mapping-fallback", fallback_identity)
                normalized_item = dict(item)
            else:
                raw_value = _collapse_spaces(str(item))
                if not raw_value:
                    continue
                identity = ("raw", raw_value)
                normalized_item = item
            if identity in seen:
                continue
            seen.add(identity)
            merged.append(normalized_item)

    return merged


def _previous_shot_reference(previous_result: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not previous_result:
        return []

    image_url = _collapse_spaces(str(previous_result.get("image_url", "")))
    image_path = _collapse_spaces(str(previous_result.get("image_path", "")))
    if not image_url and not image_path:
        return []

    return [
        {
            "kind": "previous_shot_image",
            "image_url": image_url,
            "image_path": image_path,
            "weight": 0.38,
        }
    ]


async def _generate_remote_video(
    provider,
    image_url: str,
    prompt: str,
    model: str,
    video_api_key: str,
    video_base_url: str,
    last_frame_url: str,
    negative_prompt: str,
    duration_seconds: int | None,
) -> str:
    return await provider.generate(
        image_url,
        prompt,
        model,
        video_api_key,
        video_base_url,
        last_frame_url,
        negative_prompt,
        duration_seconds=duration_seconds,
    )


def _sanitize_remote_url(remote_url: str) -> str:
    parsed = urlparse(remote_url or "")
    if not parsed.scheme and not parsed.netloc:
        return remote_url
    sanitized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}" if parsed.scheme else f"{parsed.netloc}{parsed.path}"
    return sanitized or remote_url


async def _download_video_with_retry(remote_url: str, shot_id: str) -> bytes:
    attempts = 3
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                vid_resp = await client.get(remote_url)
                vid_resp.raise_for_status()
                return vid_resp.content
        except (httpx.ReadError, httpx.ConnectError, httpx.RemoteProtocolError, httpx.HTTPStatusError) as exc:
            last_exc = exc
            logger.warning(
                "Video download transient failure for shot_id=%s attempt=%s/%s remote_url=%s error=%r",
                shot_id,
                attempt,
                attempts,
                _sanitize_remote_url(remote_url),
                exc,
            )
            if attempt == attempts:
                break
            await asyncio.sleep(min(2 * attempt, 5))
    assert last_exc is not None
    raise last_exc


async def generate_video(
    image_url: str,
    prompt: str,
    shot_id: str,
    model: str = DEFAULT_MODEL,
    video_api_key: str = "",
    video_base_url: str = "",
    video_provider: str = DEFAULT_PROVIDER,
    last_frame_url: str = "",
    negative_prompt: str = "",
    duration_seconds: int | None = None,
) -> dict:
    """Generate video for a single shot.

    Args:
        image_url: 首帧图片URL
        prompt: 动作描述
        shot_id: 镜头ID
        model: 视频生成模型
        video_api_key: API密钥
        video_base_url: API基础URL
        video_provider: 视频生成服务商
        last_frame_url: 尾帧图片URL（可选），提供时启用双帧过渡模式

    Returns:
        { shot_id, video_path, video_url }
    """
    provider = get_video_provider(video_provider)
    remote_url = await _generate_remote_video(
        provider,
        image_url=image_url,
        prompt=prompt,
        model=model,
        video_api_key=video_api_key,
        video_base_url=video_base_url,
        last_frame_url=last_frame_url,
        negative_prompt=negative_prompt,
        duration_seconds=duration_seconds,
    )
    video_bytes = await _download_video_with_retry(remote_url, shot_id)

    filename = _versioned_media_name(shot_id, ".mp4")
    output_path = VIDEO_DIR / filename
    output_path.write_bytes(video_bytes)

    return {
        "shot_id": shot_id,
        "video_path": str(output_path),
        "video_url": f"/media/videos/{filename}",
    }


def supports_dual_frame_provider(provider: str) -> bool:
    return (provider or "").strip().lower() in DUAL_FRAME_PROVIDERS


async def generate_transition_video(
    *,
    transition_id: str,
    first_frame_url: str,
    last_frame_url: str,
    prompt: str,
    model: str = DEFAULT_MODEL,
    video_api_key: str = "",
    video_base_url: str = "",
    video_provider: str = DEFAULT_PROVIDER,
    negative_prompt: str = "",
    duration_seconds: int | None = None,
) -> dict:
    if not supports_dual_frame_provider(video_provider):
        raise ValueError(f"provider {video_provider or DEFAULT_PROVIDER} does not support dual-frame transitions")
    if not first_frame_url or not last_frame_url:
        raise ValueError("transition video requires both first_frame_url and last_frame_url")
    return await generate_video(
        image_url=first_frame_url,
        prompt=prompt,
        shot_id=transition_id,
        model=model,
        video_api_key=video_api_key,
        video_base_url=video_base_url,
        video_provider=video_provider,
        last_frame_url=last_frame_url,
        negative_prompt=negative_prompt,
        duration_seconds=duration_seconds,
    )


async def generate_videos_batch(
    shots: list[dict],
    base_url: str,
    model: str = DEFAULT_MODEL,
    video_api_key: str = "",
    video_base_url: str = "",
    video_provider: str = DEFAULT_PROVIDER,
    art_style: str = "",
) -> list[dict]:
    """
    Generate videos for all shots concurrently.

    Each shot must have: shot_id, image_url (relative), final_video_prompt.
    Phase 4 mainline: always use single-frame I2V for normal storyboard shots.

    base_url: server base URL to convert relative image_url to absolute.
    """
    tasks = [
        generate_video(
            image_url=f"{base_url}{shot['image_url']}",
            prompt=inject_art_style(shot.get("final_video_prompt") or shot.get("visual_prompt", ""), art_style),
            shot_id=shot["shot_id"],
            model=model,
            video_api_key=video_api_key,
            video_base_url=video_base_url,
            video_provider=video_provider,
            last_frame_url="",
            negative_prompt=shot.get("negative_prompt", ""),
        )
        for shot in shots
        if shot.get("image_url")
    ]
    return list(await asyncio.gather(*tasks))


def group_shots_by_scene(shots: list[dict]) -> OrderedDict:
    """
    按 shot_id 中的 scene 前缀分组。

    shot_id 格式约定: scene{N}_shot{M}，例如 scene1_shot1, scene1_shot2, scene2_shot1
    返回 OrderedDict[str, list[dict]]，保持场景顺序。
    """
    groups: OrderedDict[str, list[dict]] = OrderedDict()
    for shot in shots:
        match = re.match(r"(scene\d+)", shot["shot_id"])
        scene_key = match.group(1) if match else "scene0"
        groups.setdefault(scene_key, []).append(shot)
    return groups


async def generate_videos_chained(
    shots: list[dict],
    base_url: str,
    model: str = DEFAULT_MODEL,
    video_api_key: str = "",
    video_base_url: str = "",
    video_provider: str = DEFAULT_PROVIDER,
    image_model: str = "black-forest-labs/FLUX.1-schnell",
    image_api_key: str = "",
    image_base_url: str = "",
    on_progress: Optional[Callable] = None,
) -> list[dict]:
    """
    Phase 4:
    按场景分组执行，但主镜头统一走单首帧 I2V。
    不再提取上一镜头尾帧，也不再把 last-frame 传给下一镜头。

    Args:
        shots: 镜头列表，每个 dict 需含 shot_id, final_video_prompt，可选 image_prompt
        base_url: 服务器地址，用于拼接本地文件 URL
        model: 视频生成模型
        image_model: 图片生成模型
        on_progress: 可选回调 (scene_key, current_index, total, shot_id)

    Returns:
        所有镜头的结果列表，每项含 shot_id, image_url, video_url, video_path
    """
    from app.services.image import generate_image

    scene_groups = group_shots_by_scene(shots)

    async def _process_scene(scene_key: str, scene_shots: list[dict]) -> list[dict]:
        results = []
        previous_image_result: dict[str, str] | None = None
        for idx, shot in enumerate(scene_shots):
            shot_id = shot["shot_id"]
            image_prompt = shot.get("image_prompt") or shot.get("visual_prompt") or shot.get("final_video_prompt", "")
            video_prompt = shot.get("final_video_prompt") or shot.get("visual_prompt", "")
            effective_reference_images = _merge_reference_images(
                shot.get("reference_images"),
                _previous_shot_reference(previous_image_result),
            )

            if on_progress:
                await on_progress(scene_key, idx, len(scene_shots), shot_id)

            img_result = await generate_image(
                visual_prompt=image_prompt,
                shot_id=shot_id,
                model=image_model,
                image_api_key=image_api_key,
                image_base_url=image_base_url,
                negative_prompt=shot.get("negative_prompt", ""),
                reference_images=effective_reference_images or None,
            )
            previous_image_result = img_result
            image_url_for_video = f"{base_url}{img_result['image_url']}"
            local_image_url = img_result["image_url"]

            # 图到视频
            video_result = await generate_video(
                image_url=image_url_for_video,
                prompt=video_prompt,
                shot_id=shot_id,
                model=model,
                video_api_key=video_api_key,
                video_base_url=video_base_url,
                video_provider=video_provider,
                negative_prompt=shot.get("negative_prompt", ""),
            )

            results.append({
                "shot_id": shot_id,
                "image_url": local_image_url,
                "video_url": video_result["video_url"],
                "video_path": video_result["video_path"],
            })

        return results

    # 不同场景并行执行
    scene_tasks = [
        _process_scene(scene_key, scene_shots)
        for scene_key, scene_shots in scene_groups.items()
    ]
    scene_results = await asyncio.gather(*scene_tasks)

    # 按原始 shot 顺序展平结果
    shot_order = [s["shot_id"] for s in shots]
    result_map = {}
    for scene_result in scene_results:
        for r in scene_result:
            result_map[r["shot_id"]] = r

    return [result_map[sid] for sid in shot_order if sid in result_map]
