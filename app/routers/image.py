from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from app.services.image import generate_images_batch, DEFAULT_MODEL
from app.core.api_keys import image_config_dep

router = APIRouter(prefix="/api/v1/image", tags=["image"])


class ImageRequest(BaseModel):
    shots: List[dict]
    model: Optional[str] = DEFAULT_MODEL


class ImageResult(BaseModel):
    shot_id: str
    image_url: str


@router.post("/{project_id}/generate", response_model=List[ImageResult])
async def generate_images(project_id: str, body: ImageRequest, image_config: dict = Depends(image_config_dep)):
    try:
        results = await generate_images_batch(body.shots, model=body.model or DEFAULT_MODEL, **image_config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"图片生成失败: {e}")
    return results
