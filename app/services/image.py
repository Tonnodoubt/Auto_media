import asyncio
import base64
import hashlib
import ipaddress
import logging
import mimetypes
import re
import socket
import time
import httpx
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse
from fastapi import HTTPException

from app.core.config import settings
from app.core.api_keys import mask_key, inject_art_style
from app.prompts.character import build_character_prompt

MEDIA_DIR = Path("media")
IMAGE_DIR = Path("media/images")
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

CHARACTER_DIR = Path("media/characters")
CHARACTER_DIR.mkdir(parents=True, exist_ok=True)

EPISODE_DIR = Path("media/episodes")
EPISODE_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "black-forest-labs/FLUX.1-schnell"
IMAGE_SIZE = "1280x720"
CHARACTER_SIZE = "1024x1024"
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
    return "volces.com" in base_url or "volcengine" in base_url


def _versioned_media_name(stem: str, suffix: str) -> str:
    token = hashlib.md5(f"{stem}:{time.time_ns()}".encode()).hexdigest()[:8]
    safe_stem = re.sub(r"[^A-Za-z0-9_-]", "_", stem)
    safe_stem = re.sub(r"_+", "_", safe_stem).strip("_") or "asset"
    return f"{safe_stem}_{token}{suffix}"


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
        resolved = candidate.resolve() if candidate.is_absolute() else (Path.cwd() / candidate).resolve()
        media_root = MEDIA_DIR.resolve()
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
    negative_prompt: str = "",
    reference_images: Optional[list[Any]] = None,
    output_dir: Optional[Path] = None,
    url_prefix: str = "/media/images",
    timeout_seconds: float = 60,
) -> dict:
    """Generate image for a single shot. Returns { shot_id, image_path, image_url }."""
    base_url = image_base_url or settings.siliconflow_base_url
    if image_base_url and not image_api_key:
        raise HTTPException(status_code=400, detail="提供自定义 image_base_url 时必须同时提供 image_api_key")
    image_api_key = image_api_key or settings.siliconflow_api_key
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

        async def _submit(request_payload: dict) -> httpx.Response:
            return await client.post(
                f"{base_url}/images/generations",
                headers={"Authorization": f"Bearer {image_api_key}"},
                json=request_payload,
            )

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
            print(f"[IMAGE][RETRY_NO_REFERENCE] status={resp.status_code} key={mask_key(image_api_key)} base={base_url}")
            logger.warning(
                "Image provider retry without reference_images finished. shot_id=%s status=%s key=%s provider_rejection=1 response_bytes=%s",
                shot_id,
                resp.status_code,
                mask_key(image_api_key),
                len(resp.content or b""),
            )
        if not resp.is_success:
            raise RuntimeError(f"图片生成 API 错误 {resp.status_code}: {resp.text[:200]}")
        image_url = _extract_image_url(resp)

        # Download and save locally
        img_resp = await client.get(image_url)
        img_resp.raise_for_status()

    target_dir = output_dir or IMAGE_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = _versioned_media_name(shot_id, ".png")
    output_path = target_dir / filename
    output_path.write_bytes(img_resp.content)

    return {
        "shot_id": shot_id,
        "image_path": str(output_path),
        "image_url": f"{url_prefix.rstrip('/')}/{filename}",
    }


async def generate_images_batch(shots: list[dict], model: str = DEFAULT_MODEL, image_api_key: str = "", image_base_url: str = "", art_style: str = "") -> list[dict]:
    """Generate images for all shots concurrently.

    Phase 4:
    - 仅生成主镜头首帧图片（image_url）
    - 不再为普通 shot 生成 last_frame_url
    """
    def _prompt(shot: dict) -> str:
        p = shot.get("image_prompt") or shot.get("visual_prompt") or shot.get("final_video_prompt", "")
        if not p or not p.strip():
            raise ValueError(f"shot {shot.get('shot_id', '?')} has no image_prompt / visual_prompt / final_video_prompt")
        return inject_art_style(p, art_style)

    tasks = [
        generate_image(
            _prompt(shot),
            shot["shot_id"],
            model,
            image_api_key,
            image_base_url,
            shot.get("negative_prompt", ""),
            shot.get("reference_images"),
        )
        for shot in shots
    ]

    results = await asyncio.gather(*tasks)

    return [
        {
            "shot_id": shot["shot_id"],
            "image_path": result["image_path"],
            "image_url": result["image_url"],
        }
        for shot, result in zip(shots, results)
    ]


async def generate_character_image(
    character_name: str,
    role: str,
    description: str,
    story_id: str,
    model: str = DEFAULT_MODEL,
    image_api_key: str = "",
    image_base_url: str = "",
    art_style: str = "",
) -> dict:
    """Generate a standard three-view character sheet. Returns { character_name, image_path, image_url, prompt }."""
    prompt = build_character_prompt(character_name, role, description, art_style=art_style)
    base_url = image_base_url or settings.siliconflow_base_url
    if image_base_url and not image_api_key:
        raise HTTPException(status_code=400, detail="提供自定义 image_base_url 时必须同时提供 image_api_key")
    image_api_key = image_api_key or settings.siliconflow_api_key
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

        async def _submit(request_payload: dict) -> httpx.Response:
            return await client.post(
                f"{base_url}/images/generations",
                headers={"Authorization": f"Bearer {image_api_key}"},
                json=request_payload,
            )

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

        img_resp = await client.get(image_url)
        img_resp.raise_for_status()

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
