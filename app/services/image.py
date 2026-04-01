import asyncio
import base64
import hashlib
import ipaddress
import logging
import mimetypes
import re
import socket
import time
from collections import OrderedDict
import httpx
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse
from fastapi import HTTPException

from app.core.config import settings
from app.core.api_keys import (
    get_default_image_provider,
    get_image_provider_api_key,
    get_image_provider_base_url,
    infer_image_provider,
    inject_art_style,
    mask_key,
)
from app.paths import CHARACTER_DIR, EPISODE_DIR, IMAGE_DIR, MEDIA_DIR
from app.prompts.character import build_character_prompt

IMAGE_DIR.mkdir(parents=True, exist_ok=True)

CHARACTER_DIR.mkdir(parents=True, exist_ok=True)

EPISODE_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "black-forest-labs/FLUX.1-schnell"
IMAGE_SIZE = "1280x720"
CHARACTER_SIZE = "1024x1024"
_TRANSIENT_HTTP_EXCEPTIONS = (
    httpx.ReadError,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
    httpx.TimeoutException,
)
CHARACTER_NEGATIVE_PROMPT = (
    "text, captions, labels, watermark, logo, speech bubble, poster, signboard, "
    "extra props, unrelated objects, foreground obstruction, hands covering face, "
    "cropped body, close-up portrait, half body, missing feet, missing limbs, duplicate person, inconsistent outfit, "
    "inconsistent costume color, inconsistent costume material, inconsistent hairstyle, inconsistent facial features, "
    "style drift, mixed art styles, mixed media rendering, generic fashion model face, glamour beauty makeup, "
    "dramatic action pose, cinematic environment background"
)

# 火山方舟要求最少 3,686,400 像素（SiliconFlow 无此限制）
ARK_IMAGE_SIZE = "2560x1440"
ARK_CHARACTER_SIZE = "1920x1920"


def _is_ark(base_url: str) -> bool:
    normalized = (base_url or "").rstrip("/").lower()
    configured_doubao_urls = {
        (settings.doubao_image_base_url or "").rstrip("/").lower(),
        (settings.doubao_video_base_url or "").rstrip("/").lower(),
        (settings.doubao_base_url or "").rstrip("/").lower(),
    }
    return (
        normalized in {url for url in configured_doubao_urls if url}
        or "volces.com" in normalized
        or "volcengine" in normalized
    )


def _versioned_media_name(stem: str, suffix: str) -> str:
    token = hashlib.md5(f"{stem}:{time.time_ns()}".encode()).hexdigest()[:8]
    safe_stem = re.sub(r"[^A-Za-z0-9_-]", "_", stem)
    safe_stem = re.sub(r"_+", "_", safe_stem).strip("_") or "asset"
    return f"{safe_stem}_{token}{suffix}"


def _sanitize_remote_target(target: str) -> str:
    parsed = urlparse(target or "")
    if not parsed.scheme and not parsed.netloc:
        return target
    sanitized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}" if parsed.scheme else f"{parsed.netloc}{parsed.path}"
    return sanitized or target


async def _request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    log_label: str,
    attempts: int = 3,
    **kwargs,
) -> httpx.Response:
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await client.request(method, url, **kwargs)
        except _TRANSIENT_HTTP_EXCEPTIONS as exc:
            last_exc = exc
            logger.warning(
                "%s transient failure attempt=%s/%s target=%s error=%r",
                log_label,
                attempt,
                attempts,
                _sanitize_remote_target(url),
                exc,
            )
            if attempt == attempts:
                break
            await asyncio.sleep(min(2 * attempt, 5))
    assert last_exc is not None
    raise last_exc


def _format_upstream_http_error(action: str, target: str, exc: Exception) -> str:
    detail = str(exc).strip() or repr(exc) or exc.__class__.__name__
    return f"{action} failed for {_sanitize_remote_target(target)}: {detail}"


def _collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _scene_key_from_shot_id(shot_id: str) -> str:
    match = re.match(r"(scene\d+)", str(shot_id or ""))
    return match.group(1) if match else "scene0"


def _group_shots_by_scene(shots: list[dict]) -> OrderedDict[str, list[tuple[int, dict]]]:
    groups: OrderedDict[str, list[tuple[int, dict]]] = OrderedDict()
    for index, shot in enumerate(shots):
        scene_key = _scene_key_from_shot_id(str(shot.get("shot_id", "")))
        groups.setdefault(scene_key, []).append((index, shot))
    return groups


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


def _set_response_metadata(resp: Any, **fields) -> None:
    extensions = getattr(resp, "extensions", None)
    if not isinstance(extensions, dict):
        extensions = {}
        setattr(resp, "extensions", extensions)
    extensions.update(fields)


def _extract_image_url(resp) -> str:
    """Parse image URL from API response with clear error messages."""
    try:
        body = resp.json()
    except Exception as exc:
        raise RuntimeError(
            f"图片 API 响应非 JSON (status={resp.status_code}): {resp.text[:200]}"
        ) from exc
    if not isinstance(body, dict):
        raise RuntimeError(f"图片 API 响应格式异常 (status={resp.status_code}): {str(body)[:200]}")
    for key in ("images", "data"):
        items = body.get(key)
        if isinstance(items, list) and items and isinstance(items[0], dict) and "url" in items[0]:
            return items[0]["url"]
    raise RuntimeError(
        f"图片 API 响应缺少 url (status={resp.status_code}, keys={list(body.keys())}, body={str(body)[:200]})"
    )


def _data_url_from_bytes(content: bytes, name: str = "", content_type: str = "") -> str:
    mime = (
        (content_type or "").split(";")[0].strip()
        or mimetypes.guess_type(name)[0]
        or "image/png"
    )
    encoded = base64.b64encode(content).decode()
    return f"data:{mime};base64,{encoded}"


def _resolve_allowed_media_path(path_like: str | Path) -> Path | None:
    try:
        candidate = Path(path_like).expanduser()
        resolved = candidate.resolve() if candidate.is_absolute() else (MEDIA_DIR.parent / candidate).resolve()
        media_root = MEDIA_DIR.resolve(strict=False)
        if resolved.is_file() and resolved.is_relative_to(media_root):
            return resolved
    except (OSError, RuntimeError, ValueError):
        return None
    return None


def _safe_media_name(name: str) -> str:
    candidate = Path(str(name or "")).name
    if candidate and re.fullmatch(r"[A-Za-z0-9._-]+", candidate):
        return candidate
    return "image.png"


def _is_private_or_local_host(host: str) -> bool:
    normalized = str(host or "").strip().lower()
    if normalized in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return True
    try:
        ip = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


async def _resolve_hostname_ips(host: str) -> list[str]:
    normalized_host = str(host or "").strip().rstrip(".")
    if not normalized_host:
        return []
    try:
        ipaddress.ip_address(normalized_host)
        return [normalized_host]
    except ValueError:
        pass

    try:
        loop = asyncio.get_running_loop()
        addrinfo = await loop.getaddrinfo(
            normalized_host,
            None,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except OSError:
        logger.warning("Failed to resolve hostname for reference image host=%s", normalized_host)
        return []

    resolved_ips: list[str] = []
    seen: set[str] = set()
    for entry in addrinfo:
        sockaddr = entry[4]
        if not sockaddr:
            continue
        ip = str(sockaddr[0]).strip()
        if not ip or ip in seen:
            continue
        seen.add(ip)
        resolved_ips.append(ip)
    return resolved_ips


async def _resolve_reference_image_value(reference: Any, client: httpx.AsyncClient) -> str:
    if isinstance(reference, str):
        image_url = reference.strip()
        image_path = ""
    elif isinstance(reference, dict):
        image_url = str(reference.get("image_url", "")).strip()
        image_path = str(reference.get("image_path", "")).strip()
    else:
        return ""

    if image_path:
        local_path = _resolve_allowed_media_path(image_path)
        if local_path:
            return _data_url_from_bytes(local_path.read_bytes(), name=local_path.name)

    if image_url.startswith("data:"):
        return image_url

    if image_url.startswith("/"):
        relative_path = _resolve_allowed_media_path(image_url.lstrip("/"))
        if relative_path:
            return _data_url_from_bytes(relative_path.read_bytes(), name=relative_path.name)
        return ""

    parsed = urlparse(image_url)
    if parsed.scheme in ("http", "https"):
        host = str(parsed.hostname or "").strip().rstrip(".")
        if not host:
            return ""
        if _is_private_or_local_host(host):
            if parsed.path.startswith("/media/"):
                local_path = _resolve_allowed_media_path(parsed.path.lstrip("/"))
                if local_path:
                    return _data_url_from_bytes(local_path.read_bytes(), name=_safe_media_name(parsed.path))
            return ""
        resolved_ips = await _resolve_hostname_ips(host)
        if not resolved_ips:
            return ""
        if any(_is_private_or_local_host(ip) for ip in resolved_ips):
            if parsed.path.startswith("/media/"):
                local_path = _resolve_allowed_media_path(parsed.path.lstrip("/"))
                if local_path:
                    return _data_url_from_bytes(local_path.read_bytes(), name=_safe_media_name(parsed.path))
            return ""
        return image_url

    if image_url:
        local_path = _resolve_allowed_media_path(image_url)
        if local_path:
            return _data_url_from_bytes(local_path.read_bytes(), name=local_path.name)

    return ""


async def generate_image(
    visual_prompt: str,
    shot_id: str,
    model: str = DEFAULT_MODEL,
    image_api_key: str = "",
    image_base_url: str = "",
    image_provider: str = "",
    negative_prompt: str = "",
    reference_images: Optional[list[Any]] = None,
    output_dir: Optional[Path] = None,
    url_prefix: str = "/media/images",
    timeout_seconds: float = 60,
) -> dict:
    """Generate image for a single shot. Returns { shot_id, image_path, image_url }."""
    resolved_image_provider = (
        str(image_provider or "").strip().lower()
        or infer_image_provider(image_base_url)
        or get_default_image_provider()
    )
    base_url = image_base_url or get_image_provider_base_url(resolved_image_provider)
    if image_base_url and resolved_image_provider == "custom" and not image_api_key:
        raise HTTPException(status_code=400, detail="提供自定义 image_base_url 时必须同时提供 image_api_key")
    image_api_key = image_api_key or get_image_provider_api_key(resolved_image_provider)
    if not image_api_key:
        raise HTTPException(
            status_code=400,
            detail=f"图片生成 API Key 未配置 (provider={resolved_image_provider or get_default_image_provider()})",
        )
    size = ARK_IMAGE_SIZE if _is_ark(base_url) else IMAGE_SIZE
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        payload = {"model": model, "prompt": visual_prompt, "n": 1, "size": size, "response_format": "url"}
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt
        resolved_reference_images: list[str] = []
        resolved_reference_strengths: list[float] = []
        for reference in reference_images or []:
            resolved = await _resolve_reference_image_value(reference, client)
            if not resolved:
                continue
            resolved_reference_images.append(resolved)
            if isinstance(reference, dict) and reference.get("weight") is not None:
                try:
                    resolved_reference_strengths.append(float(reference["weight"]))
                except (TypeError, ValueError):
                    pass
        if resolved_reference_images:
            payload["reference_images"] = resolved_reference_images
            if len(resolved_reference_strengths) == len(resolved_reference_images):
                payload["reference_strengths"] = resolved_reference_strengths

        submit_url = f"{base_url}/images/generations"

        async def _submit(request_payload: dict) -> httpx.Response:
            try:
                return await _request_with_retry(
                    client,
                    "POST",
                    submit_url,
                    log_label=f"Image generation request shot_id={shot_id}",
                    headers={"Authorization": f"Bearer {image_api_key}"},
                    json=request_payload,
                )
            except httpx.RequestError as exc:
                raise RuntimeError(_format_upstream_http_error("Image generation request", submit_url, exc)) from exc

        effective_payload = dict(payload)
        resp = await _submit(effective_payload)
        print(f"[IMAGE] status={resp.status_code} key={mask_key(image_api_key)} base={base_url}")
        if not resp.is_success and negative_prompt and resp.status_code in (400, 422):
            logger.warning(
                "Image provider rejected negative_prompt; retrying without it. shot_id=%s status=%s key=%s provider_rejection=1 response_bytes=%s",
                shot_id,
                resp.status_code,
                mask_key(image_api_key),
                len(resp.content or b""),
            )
            effective_payload = dict(effective_payload)
            effective_payload.pop("negative_prompt", None)
            resp = await _submit(effective_payload)
            print(f"[IMAGE][RETRY_NO_NEGATIVE] status={resp.status_code} key={mask_key(image_api_key)} base={base_url}")
            logger.warning(
                "Image provider retry without negative_prompt finished. shot_id=%s status=%s key=%s provider_rejection=1 response_bytes=%s",
                shot_id,
                resp.status_code,
                mask_key(image_api_key),
                len(resp.content or b""),
            )
        if not resp.is_success and resolved_reference_images and resp.status_code in (400, 422):
            logger.warning(
                "Image provider rejected reference_images; retrying without them. shot_id=%s status=%s key=%s provider_rejection=1 response_bytes=%s",
                shot_id,
                resp.status_code,
                mask_key(image_api_key),
                len(resp.content or b""),
            )
            effective_payload = dict(effective_payload)
            effective_payload.pop("reference_images", None)
            effective_payload.pop("reference_strengths", None)
            resp = await _submit(effective_payload)
            _set_response_metadata(
                resp,
                reference_images_applied=False,
                dropped_reference_count=len(resolved_reference_images),
            )
            print(f"[IMAGE][RETRY_NO_REFERENCE] status={resp.status_code} key={mask_key(image_api_key)} base={base_url}")
            logger.warning(
                "Image provider retry without reference_images finished. shot_id=%s status=%s key=%s provider_rejection=1 response_bytes=%s",
                shot_id,
                resp.status_code,
                mask_key(image_api_key),
                len(resp.content or b""),
            )
        elif resolved_reference_images:
            _set_response_metadata(
                resp,
                reference_images_applied=True,
                dropped_reference_count=0,
            )
        else:
            _set_response_metadata(
                resp,
                reference_images_applied=False,
                dropped_reference_count=0,
            )
        if not resp.is_success:
            raise RuntimeError(f"图片生成 API 错误 {resp.status_code}: {resp.text[:200]}")
        image_url = _extract_image_url(resp)

        # Download and save locally
        try:
            img_resp = await _request_with_retry(
                client,
                "GET",
                image_url,
                log_label=f"Image download shot_id={shot_id}",
            )
            img_resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(_format_upstream_http_error("Image download", image_url, exc)) from exc

    target_dir = output_dir or IMAGE_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = _versioned_media_name(shot_id, ".png")
    output_path = target_dir / filename
    output_path.write_bytes(img_resp.content)

    return {
        "shot_id": shot_id,
        "image_path": str(output_path),
        "image_url": f"{url_prefix.rstrip('/')}/{filename}",
        "reference_images_applied": bool(getattr(resp, "extensions", {}).get("reference_images_applied", False)),
        "dropped_reference_count": int(getattr(resp, "extensions", {}).get("dropped_reference_count", 0) or 0),
    }


async def generate_images_batch(
    shots: list[dict],
    model: str = DEFAULT_MODEL,
    image_api_key: str = "",
    image_base_url: str = "",
    image_provider: str = "",
    art_style: str = "",
) -> list[dict]:
    """Generate images for all shots.

    Phase 4:
    - 仅生成主镜头首帧图片（image_url）
    - 不再为普通 shot 生成 last_frame_url
    - 同场景内按顺序生成，并把上一张主镜头图作为下一张的额外参考图
    """
    def _prompt(shot: dict) -> str:
        p = shot.get("image_prompt") or shot.get("visual_prompt") or shot.get("final_video_prompt", "")
        if not p or not p.strip():
            raise ValueError(f"shot {shot.get('shot_id', '?')} has no image_prompt / visual_prompt / final_video_prompt")
        return inject_art_style(p, art_style)

    async def _process_scene(scene_entries: list[tuple[int, dict]]) -> list[tuple[int, dict]]:
        previous_result: dict[str, Any] | None = None
        scene_results: list[tuple[int, dict]] = []

        for index, shot in scene_entries:
            effective_reference_images = _merge_reference_images(
                shot.get("reference_images"),
                _previous_shot_reference(previous_result),
            )
            result = await generate_image(
                visual_prompt=_prompt(shot),
                shot_id=shot["shot_id"],
                model=model,
                image_api_key=image_api_key,
                image_base_url=image_base_url,
                image_provider=image_provider,
                negative_prompt=shot.get("negative_prompt", ""),
                reference_images=effective_reference_images or None,
            )
            previous_result = result
            scene_results.append(
                (
                    index,
                    {
                        "shot_id": shot["shot_id"],
                        "image_path": result["image_path"],
                        "image_url": result["image_url"],
                        "reference_images_applied": bool(result.get("reference_images_applied", False)),
                        "dropped_reference_count": int(result.get("dropped_reference_count", 0) or 0),
                    },
                )
            )

        return scene_results

    scene_groups = _group_shots_by_scene(shots)
    grouped_results = await asyncio.gather(*[_process_scene(entries) for entries in scene_groups.values()])

    ordered_results: dict[int, dict] = {}
    for scene_results in grouped_results:
        for index, result in scene_results:
            ordered_results[index] = result

    return [ordered_results[index] for index in range(len(shots)) if index in ordered_results]


async def generate_character_image(
    character_name: str,
    role: str,
    description: str,
    story_id: str,
    model: str = DEFAULT_MODEL,
    image_api_key: str = "",
    image_base_url: str = "",
    image_provider: str = "",
    art_style: str = "",
) -> dict:
    """Generate a standard three-view character sheet. Returns { character_name, image_path, image_url, prompt }."""
    prompt = build_character_prompt(character_name, role, description, art_style=art_style)
    resolved_image_provider = (
        str(image_provider or "").strip().lower()
        or infer_image_provider(image_base_url)
        or get_default_image_provider()
    )
    base_url = image_base_url or get_image_provider_base_url(resolved_image_provider)
    if image_base_url and resolved_image_provider == "custom" and not image_api_key:
        raise HTTPException(status_code=400, detail="提供自定义 image_base_url 时必须同时提供 image_api_key")
    image_api_key = image_api_key or get_image_provider_api_key(resolved_image_provider)
    if not image_api_key:
        raise HTTPException(
            status_code=400,
            detail=f"图片生成 API Key 未配置 (provider={resolved_image_provider or get_default_image_provider()})",
        )
    size = ARK_CHARACTER_SIZE if _is_ark(base_url) else CHARACTER_SIZE

    async with httpx.AsyncClient(timeout=120) as client:
        payload = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "size": size,
            "response_format": "url",
            "negative_prompt": CHARACTER_NEGATIVE_PROMPT,
        }

        submit_url = f"{base_url}/images/generations"

        async def _submit(request_payload: dict) -> httpx.Response:
            try:
                return await _request_with_retry(
                    client,
                    "POST",
                    submit_url,
                    log_label=f"Character image request character={character_name}",
                    headers={"Authorization": f"Bearer {image_api_key}"},
                    json=request_payload,
                )
            except httpx.RequestError as exc:
                raise RuntimeError(_format_upstream_http_error("Character image request", submit_url, exc)) from exc

        resp = await _submit(payload)
        print(f"[CHARACTER IMAGE] status={resp.status_code} key={mask_key(image_api_key)} base={base_url} for {character_name}")
        if not resp.is_success and resp.status_code in (400, 422):
            logger.warning(
                "Character image provider rejected negative_prompt; retrying without it. character=%s status=%s key=%s provider_rejection=1 response_bytes=%s",
                character_name,
                resp.status_code,
                mask_key(image_api_key),
                len(resp.content or b""),
            )
            retry_payload = dict(payload)
            retry_payload.pop("negative_prompt", None)
            resp = await _submit(retry_payload)
            print(f"[CHARACTER IMAGE][RETRY_NO_NEGATIVE] status={resp.status_code} key={mask_key(image_api_key)} base={base_url} for {character_name}")
        if not resp.is_success:
            raise RuntimeError(f"角色图生成 API 错误 {resp.status_code}: {resp.text[:500]}")
        image_url = _extract_image_url(resp)

        try:
            img_resp = await _request_with_retry(
                client,
                "GET",
                image_url,
                log_label=f"Character image download character={character_name}",
            )
            img_resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(_format_upstream_http_error("Character image download", image_url, exc)) from exc

    # Generate unique filename
    hash_input = f"{story_id}_{character_name}_{time.time()}"
    file_hash = hashlib.md5(hash_input.encode()).hexdigest()[:8]
    safe_story_id = re.sub(r'[^A-Za-z0-9_-]', '_', story_id)
    safe_story_id = re.sub(r'_+', '_', safe_story_id).strip('_') or 'story'
    safe_story_id = safe_story_id[:64]
    safe_name = re.sub(r'[^A-Za-z0-9_-]', '_', character_name)
    safe_name = re.sub(r'_+', '_', safe_name).strip('_') or 'character'
    safe_name = safe_name[:64]
    filename = f"{safe_story_id}_{safe_name}_{file_hash}.png"

    output_path = CHARACTER_DIR / filename
    try:
        output_path.resolve().relative_to(CHARACTER_DIR.resolve())
    except ValueError as err:
        raise ValueError(f"Unsafe output path detected: {output_path}") from err
    output_path.write_bytes(img_resp.content)

    return {
        "character_name": character_name,
        "image_path": str(output_path),
        "image_url": f"/media/characters/{filename}",
        "prompt": prompt,
    }


async def generate_character_images_batch(
    characters: list[dict],
    story_id: str,
    model: str = DEFAULT_MODEL,
    image_api_key: str = "",
    image_base_url: str = "",
    image_provider: str = "",
    art_style: str = "",
) -> list[dict]:
    """Generate character design images for all characters concurrently."""
    tasks = [
        generate_character_image(
            character_name=char["name"],
            role=char.get("role", ""),
            description=char.get("description", ""),
            story_id=story_id,
            model=model,
            image_api_key=image_api_key,
            image_base_url=image_base_url,
            image_provider=image_provider,
            art_style=art_style,
        )
        for char in characters
    ]
    raw = await asyncio.gather(*tasks, return_exceptions=True)
    return [
        result if not isinstance(result, Exception)
        else {"character_name": characters[i]["name"], "error": str(result)}
        for i, result in enumerate(raw)
    ]
