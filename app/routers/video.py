from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from typing import List, Optional
from app.services.video import generate_videos_batch, DEFAULT_MODEL
from app.core.api_keys import video_config_dep

router = APIRouter(prefix="/api/v1/video", tags=["video"])


class VideoRequest(BaseModel):
    shots: List[dict]
    model: Optional[str] = DEFAULT_MODEL


class VideoResult(BaseModel):
    shot_id: str
    video_url: str


@router.post("/{project_id}/generate", response_model=List[VideoResult])
async def generate_videos(project_id: str, request: Request, body: VideoRequest, video_config: dict = Depends(video_config_dep)):
    base_url = str(request.base_url).rstrip("/")
    try:
        results = await generate_videos_batch(body.shots, base_url=base_url, model=body.model or DEFAULT_MODEL, **video_config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"视频生成失败: {e}")
    return results
