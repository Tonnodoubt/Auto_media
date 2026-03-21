from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.api_keys import image_config_dep
from app.services.image import generate_character_image, generate_character_images_batch, DEFAULT_MODEL
from app.services import story_repository as repo

router = APIRouter(prefix="/api/v1/character", tags=["character"])


class CharacterImageRequest(BaseModel):
    story_id: str
    character_name: str
    role: str
    description: str
    model: Optional[str] = DEFAULT_MODEL


class BatchCharacterRequest(BaseModel):
    story_id: str
    characters: List[dict]
    model: Optional[str] = DEFAULT_MODEL


class CharacterImageResult(BaseModel):
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
async def generate_single(body: CharacterImageRequest, image_config: dict = Depends(image_config_dep), db: AsyncSession = Depends(get_db)):
    """Generate character design image for a single character."""
    try:
        result = await generate_character_image(
            character_name=body.character_name,
            role=body.role,
            description=body.description,
            story_id=body.story_id,
            model=body.model or DEFAULT_MODEL,
            **image_config,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"角色人设图生成失败: {e}")

    story = await repo.get_story(db, body.story_id)
    character_images = story.get("character_images", {})
    character_images[body.character_name] = {
        "image_url": result["image_url"],
        "image_path": result["image_path"],
        "prompt": result["prompt"],
    }
    await repo.save_story(db, body.story_id, {"character_images": character_images})

    return CharacterImageResult(
        character_name=result["character_name"],
        image_url=result["image_url"],
        prompt=result["prompt"],
    )


@router.post("/generate-all", response_model=BatchCharacterResponse)
async def generate_all(body: BatchCharacterRequest, image_config: dict = Depends(image_config_dep), db: AsyncSession = Depends(get_db)):
    """Generate character design images for all characters."""
    try:
        raw_results = await generate_character_images_batch(
            characters=body.characters,
            story_id=body.story_id,
            model=body.model or DEFAULT_MODEL,
            **image_config,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"批量角色人设图生成失败: {e}")

    story = await repo.get_story(db, body.story_id)
    character_images = story.get("character_images", {})
    valid_results = []
    errors = []

    for i, result in enumerate(raw_results):
        char_name = body.characters[i]["name"] if i < len(body.characters) else "unknown"
        if isinstance(result, Exception):
            errors.append(CharacterImageError(character_name=char_name, error=str(result)))
            continue

        character_images[char_name] = {
            "image_url": result["image_url"],
            "image_path": result["image_path"],
            "prompt": result["prompt"],
        }
        valid_results.append(CharacterImageResult(
            character_name=result["character_name"],
            image_url=result["image_url"],
            prompt=result["prompt"],
        ))

    if not valid_results:
        raise HTTPException(status_code=500, detail=f"所有角色人设图生成失败: {errors[0].error if errors else '未知错误'}")

    await repo.save_story(db, body.story_id, {"character_images": character_images})
    return BatchCharacterResponse(results=valid_results, errors=errors)


@router.get("/{story_id}/images")
async def get_images(story_id: str, db: AsyncSession = Depends(get_db)):
    """Get stored character images for a story."""
    story = await repo.get_story(db, story_id)
    return {"character_images": story.get("character_images", {})}
