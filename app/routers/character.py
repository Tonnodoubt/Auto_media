import logging

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.api_keys import image_config_dep, get_art_style
from app.core.model_defaults import resolve_image_model
from app.core.story_assets import build_character_asset_record, get_character_asset_entry
from app.services.image import generate_character_image, generate_character_images_batch
from app.services import story_repository as repo

router = APIRouter(prefix="/api/v1/character", tags=["character"])
logger = logging.getLogger(__name__)


class CharacterImageRequest(BaseModel):
    story_id: str
    character_id: Optional[str] = None
    character_name: str
    role: str
    description: str
    model: Optional[str] = None


class BatchCharacterRequest(BaseModel):
    story_id: str
    characters: List[dict]
    model: Optional[str] = None


class CharacterImageResult(BaseModel):
    character_id: Optional[str] = None
    character_name: str
    image_url: str
    prompt: str


class CharacterImageError(BaseModel):
    character_name: str
    error: str


class BatchCharacterResponse(BaseModel):
    results: List[CharacterImageResult]
    errors: List[CharacterImageError]


@router.post("/generate", response_model=CharacterImageResult)
async def generate_single(body: CharacterImageRequest, request: Request, image_config: dict = Depends(image_config_dep), db: AsyncSession = Depends(get_db)):
    """Generate character design image for a single character."""
    if not (body.character_id or "").strip():
        raise HTTPException(status_code=400, detail="character_id 是必填项，禁止按角色名复用或覆盖人设图")
    art_style = get_art_style(request)
    effective_model = resolve_image_model(body.model or "", image_config.get("image_base_url", ""))
    try:
        result = await generate_character_image(
            character_name=body.character_name,
            role=body.role,
            description=body.description,
            story_id=body.story_id,
            model=effective_model,
            art_style=art_style,
            **image_config,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Character image generation failed story_id=%s character_id=%s", body.story_id, body.character_id)
        detail = str(e).strip() or repr(e) or e.__class__.__name__
        raise HTTPException(status_code=500, detail=f"Character image generation failed: {detail}") from e

    story = await repo.get_story(db, body.story_id)
    character_images = story.get("character_images", {}) if story else {}
    character_key = body.character_id
    await repo.upsert_character_images(db, body.story_id, {
        character_key: build_character_asset_record(
            image_url=result["image_url"],
            image_path=result["image_path"],
            prompt=result["prompt"],
            existing=get_character_asset_entry(character_images, character_key, name=body.character_name),
            character_id=body.character_id,
            character_name=body.character_name,
            quality=result.get("quality"),
        )
    })
    if art_style:
        await repo.save_story(db, body.story_id, {"art_style": art_style})

    return CharacterImageResult(
        character_id=body.character_id,
        character_name=result["character_name"],
        image_url=result["image_url"],
        prompt=result["prompt"],
    )


@router.post("/generate-all", response_model=BatchCharacterResponse)
async def generate_all(body: BatchCharacterRequest, request: Request, image_config: dict = Depends(image_config_dep), db: AsyncSession = Depends(get_db)):
    """Generate character design images for all characters."""
    missing_id_names = [str(char.get("name", "未命名角色")) for char in body.characters if not str(char.get("id", "")).strip()]
    if missing_id_names:
        raise HTTPException(
            status_code=400,
            detail=f"以下角色缺少 character_id，已阻止按角色名复用或覆盖人设图: {'、'.join(missing_id_names)}",
        )
    art_style = get_art_style(request)
    effective_model = resolve_image_model(body.model or "", image_config.get("image_base_url", ""))
    try:
        raw_results = await generate_character_images_batch(
            characters=body.characters,
            story_id=body.story_id,
            model=effective_model,
            art_style=art_style,
            **image_config,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Batch character image generation failed story_id=%s count=%s", body.story_id, len(body.characters))
        detail = str(e).strip() or repr(e) or e.__class__.__name__
        raise HTTPException(status_code=500, detail=f"Batch character image generation failed: {detail}") from e

    valid_results = []
    errors = []
    new_images = {}
    story = await repo.get_story(db, body.story_id)
    character_images = story.get("character_images", {}) if story else {}

    for i, result in enumerate(raw_results):
        char = body.characters[i] if i < len(body.characters) else {}
        char_name = char.get("name", "unknown")
        char_id = char.get("id", "")
        if "error" in result:
            errors.append(CharacterImageError(character_name=char_name, error=result["error"]))
            continue

        character_key = char_id
        new_images[character_key] = build_character_asset_record(
            image_url=result["image_url"],
            image_path=result["image_path"],
            prompt=result["prompt"],
            existing=get_character_asset_entry(character_images, character_key, name=char_name),
            character_id=char_id,
            character_name=char_name,
            quality=result.get("quality"),
        )
        valid_results.append(CharacterImageResult(
            character_id=char_id or None,
            character_name=result["character_name"],
            image_url=result["image_url"],
            prompt=result["prompt"],
        ))

    if not valid_results:
        raise HTTPException(status_code=500, detail=f"所有角色人设图生成失败: {errors[0].error if errors else '未知错误'}")

    await repo.upsert_character_images(db, body.story_id, new_images)
    if art_style:
        await repo.save_story(db, body.story_id, {"art_style": art_style})
    return BatchCharacterResponse(results=valid_results, errors=errors)


@router.get("/{story_id}/images")
async def get_images(story_id: str, db: AsyncSession = Depends(get_db)):
    """Get stored character images for a story."""
    story = await repo.get_story(db, story_id)
    return {"character_images": story.get("character_images", {})}
