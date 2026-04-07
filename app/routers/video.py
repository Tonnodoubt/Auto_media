import logging

from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from typing import List, Optional
from app.services.video import generate_videos_batch
from app.core.api_keys import video_config_dep, get_art_style, llm_config_dep
from app.core.model_defaults import resolve_video_model
from app.core.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.story_context import build_generation_payload
from app.services import story_repository as repo
from app.services.storyboard_state import (
    load_storyboard_generation_state,
    persist_generated_files_to_pipeline,
    persist_storyboard_generation_state,
)
from app.services.quality import run_quality_guarded_runtime_payload
from app.services.story_context_service import prepare_story_context

router = APIRouter(prefix="/api/v1/video", tags=["video"])
logger = logging.getLogger(__name__)


class VideoRequest(BaseModel):
    shots: List[dict]
    model: Optional[str] = None
    story_id: Optional[str] = None
    pipeline_id: Optional[str] = None


class VideoResult(BaseModel):
    shot_id: str
    video_url: str


@router.post("/{project_id}/generate", response_model=List[VideoResult])
async def generate_videos(
    project_id: str,
    request: Request,
    body: VideoRequest,
    video_config: dict = Depends(video_config_dep),
    llm: dict = Depends(llm_config_dep),
    db: AsyncSession = Depends(get_db),
):
    base_url = str(request.base_url).rstrip("/")
    art_style = get_art_style(request)
    effective_model = resolve_video_model(body.model or "", video_config.get("video_provider", ""))
    story = None
    story_context = None
    effective_pipeline_id = str(body.pipeline_id or "").strip()
    generation_payload_quality: dict[str, dict[str, object]] = {}
    try:
        if body.story_id:
            story, story_context = await prepare_story_context(
                db,
                body.story_id,
                provider=llm["provider"],
                model=llm["model"],
                api_key=llm["api_key"],
                base_url=llm["base_url"],
            )
            if not effective_pipeline_id and story:
                generation_state = load_storyboard_generation_state(story)
                effective_pipeline_id = str(generation_state.get("pipeline_id", "")).strip()
        prepared_shots = []
        for shot in body.shots:
            payload, quality = await run_quality_guarded_runtime_payload(
                provider=llm["provider"],
                model=llm["model"],
                api_key=llm["api_key"],
                base_url=llm["base_url"],
                base_payload_builder=lambda shot=shot: build_generation_payload(
                    shot,
                    story_context,
                    art_style=art_style,
                    story=story,
                ),
                telemetry_context={
                    "operation": "router.video.build_generation_payload",
                    "project_id": project_id,
                    "story_id": str(body.story_id or "").strip(),
                    "shot_id": str(shot.get("shot_id", "")).strip(),
                },
            )
            prepared_shots.append(
                {
                    **shot,
                    "final_video_prompt": payload["final_video_prompt"],
                    "negative_prompt": payload.get("negative_prompt", ""),
                    "reference_images": payload.get("reference_images", []),
                }
            )
            if quality.get("enabled") or quality.get("warnings"):
                generation_payload_quality[str(payload.get("shot_id", "")).strip()] = {"quality": quality}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Video payload build failed for project=%s story_id=%s", project_id, body.story_id)
        detail = str(e).strip() or repr(e) or e.__class__.__name__
        raise HTTPException(status_code=500, detail=f"视频生成失败: {detail}") from e

    try:
        results = await generate_videos_batch(
            prepared_shots,
            base_url=base_url,
            model=effective_model,
            art_style=art_style,
            **video_config,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Video generation failed for project=%s story_id=%s", project_id, body.story_id)
        detail = str(e).strip() or repr(e) or e.__class__.__name__
        raise HTTPException(status_code=500, detail=f"视频生成失败: {detail}") from e

    generated_files = {
        "videos": {result["shot_id"]: result for result in results},
    }
    if generation_payload_quality:
        generated_files["generation_payloads"] = generation_payload_quality
    invalidated_shot_ids = [
        str(result.get("shot_id", "")).strip()
        for result in results
        if str(result.get("shot_id", "")).strip()
    ]
    if body.story_id and story:
        try:
            await persist_storyboard_generation_state(
                db,
                story_id=body.story_id,
                story=story,
                shots=body.shots,
                partial_shots=True,
                generated_files=generated_files,
                pipeline_id=effective_pipeline_id,
                project_id=project_id,
                prune_generated_files_to_shots=True,
                invalidate_shot_ids=invalidated_shot_ids,
                clear_final_video=True,
            )
        except Exception:
            logger.exception(
                "Video storyboard persistence failed project=%s story_id=%s pipeline_id=%s generated_files=%s",
                project_id,
                body.story_id,
                effective_pipeline_id,
                generated_files,
            )
    if effective_pipeline_id:
        pipeline_story_id = str(body.story_id or "").strip()
        try:
            if not pipeline_story_id:
                existing_pipeline = await repo.get_pipeline(db, effective_pipeline_id)
                pipeline_story_id = str(existing_pipeline.get("story_id", "")).strip()
            if pipeline_story_id:
                await persist_generated_files_to_pipeline(
                    db,
                    project_id=project_id,
                    pipeline_id=effective_pipeline_id,
                    story_id=pipeline_story_id,
                    generated_files=generated_files,
                    prune_generated_files_to_shots=True,
                    invalidate_shot_ids=invalidated_shot_ids,
                    clear_final_video=True,
                )
        except Exception:
            logger.exception(
                "Video pipeline persistence failed project=%s story_id=%s pipeline_id=%s generated_files=%s",
                project_id,
                pipeline_story_id or body.story_id,
                effective_pipeline_id,
                generated_files,
            )
    return results
