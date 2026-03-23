import asyncio
import hashlib
import re
import time
import httpx
from pathlib import Path

from app.core.config import settings
from app.core.api_keys import mask_key

IMAGE_DIR = Path("media/images")
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

CHARACTER_DIR = Path("media/characters")
CHARACTER_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_MODEL = "black-forest-labs/FLUX.1-schnell"
IMAGE_SIZE = "1280x720"
CHARACTER_SIZE = "1024x1024"


async def generate_image(visual_prompt: str, shot_id: str, model: str = DEFAULT_MODEL, image_api_key: str = "", image_base_url: str = "") -> dict:
    """Generate image for a single shot. Returns { shot_id, image_path, image_url }."""
    base_url = image_base_url or settings.siliconflow_base_url
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{base_url}/images/generations",
            headers={"Authorization": f"Bearer {image_api_key}"},
            json={"model": model, "prompt": visual_prompt, "n": 1, "image_size": IMAGE_SIZE},
        )
        print(f"[IMAGE] status={resp.status_code} key={mask_key(image_api_key)} base={base_url}")
        if not resp.is_success:
            raise RuntimeError(f"图片生成 API 错误 {resp.status_code}: {resp.text[:200]}")
        image_url = resp.json()["images"][0]["url"]

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


def _build_character_prompt(name: str, role: str, description: str) -> str:
    """Build prompt for character design image."""
    return (
        f"Character portrait of {name}, role: {role}, appearance: {description}, "
        "cinematic portrait, highly detailed, professional character design, "
        "consistent character reference, clean background, studio lighting, "
        "8k resolution, photorealistic"
    )


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
    prompt = _build_character_prompt(character_name, role, description)
    base_url = image_base_url or settings.siliconflow_base_url

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{base_url}/images/generations",
            headers={"Authorization": f"Bearer {image_api_key}"},
            json={"model": model, "prompt": prompt, "n": 1, "image_size": CHARACTER_SIZE},
        )
        print(f"[CHARACTER IMAGE] status={resp.status_code} key={mask_key(image_api_key)} base={base_url} for {character_name}")
        if not resp.is_success:
            raise RuntimeError(f"角色图生成 API 错误 {resp.status_code}: {resp.text[:200]}")
        image_url = resp.json()["images"][0]["url"]

        img_resp = await client.get(image_url)
        img_resp.raise_for_status()

    # Generate unique filename
    hash_input = f"{story_id}_{character_name}_{time.time()}"
    file_hash = hashlib.md5(hash_input.encode()).hexdigest()[:8]
    safe_name = re.sub(r'[^A-Za-z0-9_-]', '_', character_name)
    safe_name = re.sub(r'_+', '_', safe_name).strip('_') or 'character'
    safe_name = safe_name[:64]
    filename = f"{story_id}_{safe_name}_{file_hash}.png"

    output_path = CHARACTER_DIR / filename
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
