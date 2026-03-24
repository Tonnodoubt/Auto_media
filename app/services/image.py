import asyncio
import hashlib
import re
import time
import httpx
from pathlib import Path
from fastapi import HTTPException

from app.core.config import settings
from app.core.api_keys import mask_key
from app.prompts.character import build_character_prompt

IMAGE_DIR = Path("media/images")
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

CHARACTER_DIR = Path("media/characters")
CHARACTER_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_MODEL = "black-forest-labs/FLUX.1-schnell"
IMAGE_SIZE = "1280x720"
CHARACTER_SIZE = "1024x1024"

# 火山方舟要求最少 3,686,400 像素（SiliconFlow 无此限制）
ARK_IMAGE_SIZE = "2560x1440"
ARK_CHARACTER_SIZE = "1920x1920"


def _is_ark(base_url: str) -> bool:
    return "volces.com" in base_url or "volcengine" in base_url


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


async def generate_image(visual_prompt: str, shot_id: str, model: str = DEFAULT_MODEL, image_api_key: str = "", image_base_url: str = "") -> dict:
    """Generate image for a single shot. Returns { shot_id, image_path, image_url }."""
    base_url = image_base_url or settings.siliconflow_base_url
    if image_base_url and not image_api_key:
        raise HTTPException(status_code=400, detail="提供自定义 image_base_url 时必须同时提供 image_api_key")
    image_api_key = image_api_key or settings.siliconflow_api_key
    size = ARK_IMAGE_SIZE if _is_ark(base_url) else IMAGE_SIZE
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{base_url}/images/generations",
            headers={"Authorization": f"Bearer {image_api_key}"},
            json={"model": model, "prompt": visual_prompt, "n": 1, "size": size, "response_format": "url"},
        )
        print(f"[IMAGE] status={resp.status_code} key={mask_key(image_api_key)} base={base_url}")
        if not resp.is_success:
            raise RuntimeError(f"图片生成 API 错误 {resp.status_code}: {resp.text[:200]}")
        image_url = _extract_image_url(resp)

        # Download and save locally
        img_resp = await client.get(image_url)
        img_resp.raise_for_status()

    output_path = IMAGE_DIR / f"{shot_id}.png"
    output_path.write_bytes(img_resp.content)

    return {
        "shot_id": shot_id,
        "image_path": str(output_path),
        "image_url": f"/media/images/{shot_id}.png",
    }


async def generate_images_batch(shots: list[dict], model: str = DEFAULT_MODEL, image_api_key: str = "", image_base_url: str = "") -> list[dict]:
    """Generate images for all shots concurrently."""
    tasks = [generate_image(shot["visual_prompt"], shot["shot_id"], model, image_api_key, image_base_url) for shot in shots]
    return list(await asyncio.gather(*tasks))


async def generate_character_image(
    character_name: str,
    role: str,
    description: str,
    story_id: str,
    model: str = DEFAULT_MODEL,
    image_api_key: str = "",
    image_base_url: str = "",
) -> dict:
    """Generate character design image. Returns { character_name, image_path, image_url, prompt }."""
    prompt = build_character_prompt(character_name, role, description)
    base_url = image_base_url or settings.siliconflow_base_url
    if image_base_url and not image_api_key:
        raise HTTPException(status_code=400, detail="提供自定义 image_base_url 时必须同时提供 image_api_key")
    image_api_key = image_api_key or settings.siliconflow_api_key
    size = ARK_CHARACTER_SIZE if _is_ark(base_url) else CHARACTER_SIZE

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{base_url}/images/generations",
            headers={"Authorization": f"Bearer {image_api_key}"},
            json={"model": model, "prompt": prompt, "n": 1, "size": size, "response_format": "url"},
        )
        print(f"[CHARACTER IMAGE] status={resp.status_code} key={mask_key(image_api_key)} base={base_url} for {character_name}")
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
) -> list[dict]:
    """Generate character design images for all characters concurrently."""
    tasks = [
        generate_character_image(
            char["name"], char.get("role", ""), char.get("description", ""),
            story_id, model, image_api_key, image_base_url
        )
        for char in characters
    ]
    raw = await asyncio.gather(*tasks, return_exceptions=True)
    return [
        result if not isinstance(result, Exception)
        else {"character_name": characters[i]["name"], "error": str(result)}
        for i, result in enumerate(raw)
    ]
