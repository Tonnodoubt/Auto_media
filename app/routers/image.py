import logging

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import List, Optional
from app.services.image import generate_images_batch
from app.core.api_keys import image_config_dep, get_art_style, inject_art_style, llm_config_dep
from app.core.model_defaults import resolve_image_model
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

router = APIRouter(prefix="/api/v1/image", tags=["image"])
logger = logging.getLogger(__name__)


class ImageRequest(BaseModel):
    shots: List[dict]
    model: Optional[str] = None
    story_id: Optional[str] = None
    pipeline_id: Optional[str] = None


class ImageResult(BaseModel):
    shot_id: str
    image_url: str


def _build_basic_payload(shot: dict, art_style: str) -> dict:
    image_prompt = (
        str(shot.get("image_prompt", "")).strip()
        or str(shot.get("visual_prompt", "")).strip()
        or str(shot.get("final_video_prompt", "")).strip()
    )
    if not image_prompt:
        raise ValueError(f"shot {shot.get('shot_id', '?')} 缺少 image_prompt/final_video_prompt")

    payload = {
        "shot_id": str(shot.get("shot_id", "")),
        "image_prompt": inject_art_style(image_prompt, art_style),
    }
    negative_prompt = str(shot.get("negative_prompt", "")).strip()
    if negative_prompt:
        payload["negative_prompt"] = negative_prompt
    reference_images = shot.get("reference_images")
    if isinstance(reference_images, list) and reference_images:
        payload["reference_images"] = reference_images
    return payload


@router.post("/{project_id}/generate", response_model=List[ImageResult])
async def generate_images(
    project_id: str,
    request: Request,
    body: ImageRequest,
    image_config: dict = Depends(image_config_dep),
    llm: dict = Depends(llm_config_dep),
    db: AsyncSession = Depends(get_db),
):
    art_style = get_art_style(request)
    effective_model = resolve_image_model(body.model or "", image_config.get("image_base_url", ""))
    story = None
    story_context = None
    effective_pipeline_id = str(body.pipeline_id or "").strip()
    generation_payload_quality: dict[str, dict[str, object]] = {}

    async def _persist_generated_images(generated_files: dict) -> None:
        pipeline_story_id = str(body.story_id or "").strip()
        invalidated_shot_ids = [
            str(result.get("shot_id", "")).strip()
            for result in (generated_files.get("images") or {}).values()
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
                    clear_videos_for_invalidated_shots=True,
                    clear_final_video=True,
                )
            except Exception:
                logger.exception(
                    "Image storyboard persistence failed project=%s story_id=%s pipeline_id=%s generated_files=%s",
                    project_id,
                    body.story_id,
                    effective_pipeline_id,
                    generated_files,
                )

        if not effective_pipeline_id:
            return

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
                    clear_videos_for_invalidated_shots=True,
                    clear_final_video=True,
                )
            else:
                logger.warning(
                    "Skipping image pipeline persistence because story_id is unavailable. project=%s pipeline_id=%s",
                    project_id,
                    effective_pipeline_id,
                )
        except Exception:
            logger.exception(
                "Image pipeline persistence failed project=%s story_id=%s pipeline_id=%s generated_files=%s",
                project_id,
                pipeline_story_id or body.story_id,
                effective_pipeline_id,
                generated_files,
            )
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
        payloads = []
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
                    "operation": "router.image.build_generation_payload",
                    "project_id": project_id,
                    "story_id": str(body.story_id or "").strip(),
                    "shot_id": str(shot.get("shot_id", "")).strip(),
                },
            )
            payloads.append(payload)
            if bool(quality.get("enabled")) or list(quality.get("warnings") or []):
                generation_payload_quality[str(payload.get("shot_id", "")).strip()] = {"quality": quality}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Enhanced image payload build failed for project=%s story_id=%s", project_id, body.story_id)
        if body.story_id:
            try:
                effective_pipeline_id = str(body.pipeline_id or "").strip()
                story, _ = await prepare_story_context(
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
                fallback_results = await generate_images_batch(
                    [_build_basic_payload(shot, art_style) for shot in body.shots],
                    model=effective_model,
                    art_style=art_style,
                    **image_config,
                )
                generated_files = {
                    "images": {result["shot_id"]: result for result in fallback_results},
                }
                await _persist_generated_images(generated_files)
                return fallback_results
            except HTTPException:
                raise
            except Exception:
                logger.exception("Fallback image generation also failed for project=%s story_id=%s", project_id, body.story_id)
        detail = str(e).strip() or repr(e) or e.__class__.__name__
        raise HTTPException(status_code=500, detail=f"图片生成失败: {detail}") from e

    try:
        results = await generate_images_batch(
            payloads,
            model=effective_model,
            art_style=art_style,
            **image_config,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Image generation failed for project=%s story_id=%s", project_id, body.story_id)
        detail = str(e).strip() or repr(e) or e.__class__.__name__
        raise HTTPException(status_code=500, detail=f"图片生成失败: {detail}") from e

    generated_files = {
        "images": {result["shot_id"]: result for result in results},
    }
    if generation_payload_quality:
        generated_files["generation_payloads"] = generation_payload_quality
    await _persist_generated_images(generated_files)
    return results
