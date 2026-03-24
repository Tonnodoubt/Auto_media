import asyncio
import logging
import re
from collections import OrderedDict
from pathlib import Path
from typing import Callable, Optional

import httpx

from app.services.video_providers.factory import get_video_provider
from app.services.ffmpeg import extract_last_frame

logger = logging.getLogger(__name__)

VIDEO_DIR = Path("media/videos")
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_MODEL = "wan2.6-i2v-flash"
DEFAULT_PROVIDER = "dashscope"


async def generate_video(
    image_url: str,
    prompt: str,
    shot_id: str,
    model: str = DEFAULT_MODEL,
    video_api_key: str = "",
    video_base_url: str = "",
    video_provider: str = DEFAULT_PROVIDER,
) -> dict:
    """Generate video for a single shot. Returns { shot_id, video_path, video_url }."""
    provider = get_video_provider(video_provider)
    remote_url = await provider.generate(image_url, prompt, model, video_api_key, video_base_url)

    async with httpx.AsyncClient(timeout=60) as client:
        vid_resp = await client.get(remote_url)
        vid_resp.raise_for_status()

    output_path = VIDEO_DIR / f"{shot_id}.mp4"
    output_path.write_bytes(vid_resp.content)

    return {
        "shot_id": shot_id,
        "video_path": str(output_path),
        "video_url": f"/media/videos/{shot_id}.mp4",
    }


async def generate_videos_batch(
    shots: list[dict],
    base_url: str,
    model: str = DEFAULT_MODEL,
    video_api_key: str = "",
    video_base_url: str = "",
    video_provider: str = DEFAULT_PROVIDER,
) -> list[dict]:
    """
    Generate videos for all shots concurrently.
    Each shot must have: shot_id, image_url (relative), visual_prompt, camera_motion.
    base_url: server base URL to convert relative image_url to absolute.
    """
    tasks = [
        generate_video(
            image_url=f"{base_url}{shot['image_url']}",
            prompt=shot.get("final_video_prompt") or shot.get("visual_prompt", ""),
            shot_id=shot["shot_id"],
            model=model,
            video_api_key=video_api_key,
            video_base_url=video_base_url,
            video_provider=video_provider,
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
    链式视频生成：同一场景内串行（首帧独立生图 → 图到视频 → 提取最后一帧 → 下一帧），
    不同场景之间并行。

    Args:
        shots: 镜头列表，每个 dict 需含 shot_id, visual_prompt, camera_motion
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
        prev_frame_path: Optional[str] = None

        for idx, shot in enumerate(scene_shots):
            shot_id = shot["shot_id"]
            visual_prompt = shot.get("final_video_prompt") or shot.get("visual_prompt", "")

            if on_progress:
                await on_progress(scene_key, idx, len(scene_shots), shot_id)

            # 生成参考图：首帧独立生图，后续帧使用上一镜头的最后一帧
            if prev_frame_path is None:
                # 场景首帧：独立生图
                img_result = await generate_image(
                    visual_prompt=visual_prompt,
                    shot_id=shot_id,
                    model=image_model,
                    image_api_key=image_api_key,
                    image_base_url=image_base_url,
                )
                image_url_for_video = f"{base_url}{img_result['image_url']}"
                local_image_url = img_result["image_url"]
            else:
                # 后续帧：使用上一镜头最后一帧作为参考
                # prev_frame_path 是上一镜头的 lastframe 文件路径
                lastframe_name = Path(prev_frame_path).name
                image_url_for_video = f"{base_url}/media/images/{lastframe_name}"
                # 复制最后一帧为当前 shot 的图片（用于结果展示）
                from shutil import copy2
                lastframe_as_shot = Path("media/images") / f"{shot_id}.png"
                copy2(prev_frame_path, lastframe_as_shot)
                local_image_url = f"/media/images/{shot_id}.png"

            # 图到视频
            video_result = await generate_video(
                image_url=image_url_for_video,
                prompt=visual_prompt,
                shot_id=shot_id,
                model=model,
                video_api_key=video_api_key,
                video_base_url=video_base_url,
                video_provider=video_provider,
            )

            # 提取最后一帧供下一镜头使用
            try:
                prev_frame_path = await extract_last_frame(
                    video_result["video_path"], shot_id
                )
            except (FileNotFoundError, RuntimeError) as exc:
                logger.warning("提取最后一帧失败 (%s)，下一镜头将独立生图: %s", shot_id, exc)
                prev_frame_path = None

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
