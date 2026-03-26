import logging
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_keys import (
    extract_api_keys,
    get_art_style,
    image_config_dep,
    llm_config_dep,
    resolve_image_key,
    resolve_llm_config,
    validate_user_base_url,
    video_config_dep,
)
from app.core.config import settings as _cfg
from app.core.database import AsyncSessionLocal, get_db
from app.core.pipeline_runtime import get_runtime_strategy_note, resolve_tracking_story_id
from app.core.story_context import build_generation_payload
from app.schemas.pipeline import (
    AutoGenerateRequest,
    AutoGenerateResponse,
    ConcatRequest,
    ConcatResponse,
    GenerationStrategy,
    PipelineActionResponse,
    PipelineStatus,
    PipelineStatusResponse,
    StoryboardRequest,
)
from app.schemas.storyboard import Storyboard
from app.services import story_repository as repo
from app.services.pipeline_executor import PipelineExecutor
from app.services.story_context_service import prepare_story_context
from app.services.storyboard import parse_script_to_storyboard

router = APIRouter(prefix="/api/v1/pipeline", tags=["pipeline"])
logger = logging.getLogger(__name__)

_DEFAULT_STEP = "Waiting to start"

def _default_pipeline_record(*, project_id: str, story_id: str | None = None) -> dict:
    return {
        "id": None,
        "story_id": story_id or project_id,
        "status": PipelineStatus.PENDING,
        "progress": 0,
        "current_step": _DEFAULT_STEP,
        "error": None,
        "progress_detail": None,
        "generated_files": None,
    }


def _serialize_shot(shot) -> dict:
    if hasattr(shot, "model_dump"):
        return shot.model_dump(mode="json")
    if hasattr(shot, "dict"):
        return shot.dict()
    return dict(shot)


def _normalize_optional_id(value: str | None) -> str | None:
    if value is None or not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


async def _load_pipeline_record(
    db: AsyncSession,
    *,
    project_id: str,
    pipeline_id: str,
    story_id: str,
) -> dict:
    record = await repo.get_pipeline(db, pipeline_id)
    if not record:
        record = _default_pipeline_record(project_id=project_id, story_id=story_id)
    record["id"] = pipeline_id
    record["story_id"] = story_id
    return record


def _build_pipeline_status_response(project_id: str, pipeline: dict) -> PipelineStatusResponse:
    generated_files = pipeline.get("generated_files")
    note = None
    if isinstance(generated_files, dict):
        meta = generated_files.get("meta")
        if isinstance(meta, dict):
            note = meta.get("note")

    return PipelineStatusResponse(
        project_id=project_id,
        pipeline_id=pipeline.get("id"),
        story_id=pipeline.get("story_id"),
        status=pipeline.get("status", PipelineStatus.PENDING),
        progress=pipeline.get("progress", 0),
        current_step=pipeline.get("current_step", _DEFAULT_STEP),
        error=pipeline.get("error"),
        progress_detail=pipeline.get("progress_detail"),
        generated_files=generated_files,
        note=note,
    )


async def _persist_manual_pipeline_state(
    db: AsyncSession,
    *,
    project_id: str,
    pipeline_id: str,
    story_id: str,
    updates: dict,
    merge_generated_files: bool = False,
) -> dict:
    pipeline = await _load_pipeline_record(
        db,
        project_id=project_id,
        pipeline_id=pipeline_id,
        story_id=story_id,
    )

    if merge_generated_files:
        existing_generated_files = pipeline.get("generated_files")
        new_generated_files = updates.get("generated_files")
        if isinstance(existing_generated_files, dict) and isinstance(new_generated_files, dict):
            merged_generated_files = dict(existing_generated_files)
            merged_generated_files.update(new_generated_files)
            updates = {**updates, "generated_files": merged_generated_files}

    pipeline.update(updates)

    await repo.save_pipeline(db, pipeline_id, story_id, pipeline)
    return pipeline


async def _load_story_context(
    db: AsyncSession,
    story_id: str | None,
    *,
    provider: str = "",
    model: str = "",
    api_key: str = "",
    base_url: str = "",
):
    story, story_context = await prepare_story_context(
        db,
        story_id,
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
    )
    return story or None, story_context


@router.post("/{project_id}/auto-generate", response_model=AutoGenerateResponse)
async def auto_generate(
    project_id: str,
    req: AutoGenerateRequest,
    background_tasks: BackgroundTasks,
    request: Request,
):
    pipeline_id = str(uuid4())
    tracking_story_id = resolve_tracking_story_id(project_id, req.story_id)
    runtime_note = get_runtime_strategy_note(req.strategy) or None

    keys = extract_api_keys(request)
    resolved_llm = resolve_llm_config(
        keys.llm_api_key or req.llm_api_key or "",
        keys.llm_base_url or req.llm_base_url or "",
        keys.llm_provider or req.provider or "",
        keys.llm_model or req.model or "",
    )
    image_api_key = resolve_image_key(keys.image_api_key or req.image_api_key or "")
    validated_image_base_url = validate_user_base_url(keys.image_base_url)
    if validated_image_base_url and not keys.image_api_key:
        raise HTTPException(
            status_code=400,
            detail="Custom X-Image-Base-URL requires X-Image-API-Key.",
        )
    image_base_url = validated_image_base_url or _cfg.siliconflow_base_url

    video_cfg = video_config_dep(request)
    video_api_key = video_cfg["video_api_key"]
    video_base_url = video_cfg["video_base_url"]
    video_provider = video_cfg["video_provider"]
    art_style = req.art_style or get_art_style(request)

    async def _run_pipeline() -> None:
        async with AsyncSessionLocal() as db_session:
            await repo.save_pipeline(
                db_session,
                pipeline_id,
                tracking_story_id,
                {
                    "status": PipelineStatus.PENDING,
                    "progress": 0,
                    "current_step": "Preparing pipeline",
                    "error": None,
                    "progress_detail": None,
                    "generated_files": None,
                },
            )

            character_info = None
            if tracking_story_id:
                try:
                    story = await repo.get_story(db_session, tracking_story_id)
                    if story:
                        characters = story.get("characters", [])
                        character_images = story.get("character_images", {})
                        if characters:
                            character_info = {
                                "characters": characters,
                                "character_images": character_images or {},
                            }
                except Exception:
                    logger.exception("Failed to load character info for story_id=%s", tracking_story_id)

            executor = PipelineExecutor(
                project_id,
                pipeline_id,
                db_session,
                story_id=tracking_story_id,
            )
            await executor.run_full_pipeline(
                script=req.script,
                strategy=req.strategy,
                provider=resolved_llm["provider"] or req.provider,
                model=resolved_llm["model"] or req.model,
                voice=req.voice,
                image_model=req.image_model,
                video_model=req.video_model,
                base_url=req.base_url,
                llm_api_key=resolved_llm["api_key"],
                llm_base_url=resolved_llm["base_url"],
                image_api_key=image_api_key,
                image_base_url=image_base_url,
                video_api_key=video_api_key,
                video_base_url=video_base_url,
                video_provider=video_provider,
                character_info=character_info,
                art_style=art_style,
                story_id=tracking_story_id,
            )

    background_tasks.add_task(_run_pipeline)

    return AutoGenerateResponse(
        project_id=project_id,
        pipeline_id=pipeline_id,
        story_id=tracking_story_id,
        message=f"Pipeline started (strategy: {req.strategy.value})",
        strategy=req.strategy,
        note=runtime_note,
    )


@router.post("/{project_id}/storyboard", response_model=Storyboard)
async def generate_storyboard(
    project_id: str,
    request: Request,
    req: StoryboardRequest = Body(...),
    llm: dict = Depends(llm_config_dep),
    db: AsyncSession = Depends(get_db),
):
    pipeline_id = str(uuid4())

    script_provider = request.headers.get("X-Script-Provider", "")
    script_api_key = request.headers.get("X-Script-API-Key", "")
    script_base_url = request.headers.get("X-Script-Base-URL", "")
    script_model = request.headers.get("X-Script-Model", "")

    if script_provider or script_api_key or script_base_url or script_model:
        script_llm = resolve_llm_config(script_api_key, script_base_url, script_provider, script_model)
    else:
        script_llm = llm

    provider = script_llm["provider"] or req.provider or "claude"
    tracking_story_id = resolve_tracking_story_id(project_id, req.story_id)

    await repo.save_pipeline(
        db,
        pipeline_id,
        tracking_story_id,
        {
            "status": PipelineStatus.STORYBOARD,
            "progress": 10,
            "current_step": "Parsing storyboard",
        },
    )

    try:
        character_info = None
        story, story_context = await _load_story_context(
            db,
            tracking_story_id,
            provider=provider,
            model=script_llm["model"] or req.model or "",
            api_key=script_llm["api_key"],
            base_url=script_llm["base_url"],
        )
        if story:
            characters = story.get("characters", [])
            character_images = story.get("character_images", {})
            if characters:
                character_info = {
                    "characters": characters,
                    "character_images": character_images or {},
                }

        shots, usage = await parse_script_to_storyboard(
            req.script,
            provider=provider,
            model=script_llm["model"] or req.model,
            api_key=script_llm["api_key"],
            base_url=script_llm["base_url"],
            character_info=character_info,
            character_section_override=story_context.clean_character_section if story_context else None,
        )
    except Exception as exc:
        logger.exception(
            "Storyboard generation failed project_id=%s story_id=%s provider=%s model=%s",
            project_id,
            tracking_story_id,
            provider,
            script_llm["model"] or req.model or "",
        )
        await repo.save_pipeline(
            db,
            pipeline_id,
            tracking_story_id,
            {
                "status": PipelineStatus.FAILED,
                "error": str(exc),
            },
        )
        raise HTTPException(status_code=500, detail=f"Storyboard generation failed: {exc}") from exc

    await repo.save_pipeline(
        db,
        pipeline_id,
        tracking_story_id,
        {
            "progress": 30,
            "current_step": "Storyboard ready",
            "generated_files": {
                "storyboard": {
                    "shots": [_serialize_shot(shot) for shot in shots],
                    "usage": {
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                    },
                },
            },
        },
    )

    return Storyboard(
        pipeline_id=pipeline_id,
        story_id=tracking_story_id,
        shots=shots,
        usage={
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
        },
    )

@router.post("/{project_id}/generate-assets", response_model=PipelineActionResponse)
async def generate_assets(
    project_id: str,
    request: Request,
    storyboard: Storyboard,
    image_config: dict = Depends(image_config_dep),
    llm: dict = Depends(llm_config_dep),
    pipeline_id: str | None = Query(None, description="Optional manual pipeline id"),
    generate_tts: bool = Query(True, description="Whether to generate TTS in this batch run"),
    generate_images: bool = Query(True, description="Whether to generate images in this batch run"),
    voice: str = Query("zh-CN-XiaoxiaoNeural", description="TTS voice"),
    image_model: str = Query("black-forest-labs/FLUX.1-schnell", description="Image model"),
    story_id: str | None = Query(None, description="Stable story id for StoryContext loading"),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db),
):
    from app.services import image, tts

    if not generate_tts and not generate_images:
        raise HTTPException(status_code=400, detail="At least one asset type must be enabled")

    tracking_story_id = resolve_tracking_story_id(
        project_id,
        _normalize_optional_id(story_id) or _normalize_optional_id(storyboard.story_id),
    )
    resolved_pipeline_id = (
        _normalize_optional_id(pipeline_id)
        or _normalize_optional_id(storyboard.pipeline_id)
        or str(uuid4())
    )
    shots = storyboard.shots
    total = len(shots)
    art_style = get_art_style(request)

    initial_pipeline = await _persist_manual_pipeline_state(
        db,
        project_id=project_id,
        pipeline_id=resolved_pipeline_id,
        story_id=tracking_story_id,
        updates={
            "status": PipelineStatus.GENERATING_ASSETS,
            "progress": 30,
            "current_step": "Generating assets",
            "error": None,
            "progress_detail": {
                "step": "assets",
                "current": 0,
                "total": total,
                "message": "Preparing asset generation",
            },
        },
    )

    async def _generate_with_session(db_session: AsyncSession) -> None:
        try:
            _, story_context = await _load_story_context(
                db_session,
                tracking_story_id,
                provider=llm["provider"],
                model=llm["model"],
                api_key=llm["api_key"],
                base_url=llm["base_url"],
            )

            generated_files: dict[str, dict] = {}

            if generate_tts:
                await _persist_manual_pipeline_state(
                    db_session,
                    project_id=project_id,
                    pipeline_id=resolved_pipeline_id,
                    story_id=tracking_story_id,
                    updates={
                        "status": PipelineStatus.GENERATING_ASSETS,
                        "progress": 35,
                        "current_step": "Generating TTS",
                        "progress_detail": {
                            "step": "tts",
                            "current": 0,
                            "total": total,
                            "message": "Generating audio",
                        },
                    },
                )
                tts_results = await tts.generate_tts_batch(
                    shots=[
                        {
                            "shot_id": shot.shot_id,
                            "dialogue": (
                                shot.audio_reference.content
                                if shot.audio_reference
                                and shot.audio_reference.type in ("dialogue", "narration")
                                else None
                            ),
                        }
                        for shot in shots
                    ],
                    voice=voice,
                )
                generated_files["tts"] = {result["shot_id"]: result for result in tts_results}

            if generate_images:
                await _persist_manual_pipeline_state(
                    db_session,
                    project_id=project_id,
                    pipeline_id=resolved_pipeline_id,
                    story_id=tracking_story_id,
                    updates={
                        "status": PipelineStatus.GENERATING_ASSETS,
                        "progress": 45,
                        "current_step": "Generating images",
                        "progress_detail": {
                            "step": "image",
                            "current": 0,
                            "total": total,
                            "message": "Generating images",
                        },
                    },
                )
                image_results = await image.generate_images_batch(
                    shots=[build_generation_payload(shot, story_context, art_style=art_style) for shot in shots],
                    model=image_model,
                    art_style=art_style,
                    **image_config,
                )
                generated_files["images"] = {result["shot_id"]: result for result in image_results}

            completion_parts = []
            if generate_tts:
                completion_parts.append("tts")
            if generate_images:
                completion_parts.append("images")

            await _persist_manual_pipeline_state(
                db_session,
                project_id=project_id,
                pipeline_id=resolved_pipeline_id,
                story_id=tracking_story_id,
                updates={
                    "status": PipelineStatus.GENERATING_ASSETS,
                    "progress": 60,
                    "current_step": f"Assets ready: {', '.join(completion_parts)}",
                    "error": None,
                    "progress_detail": None,
                    "generated_files": generated_files,
                },
                merge_generated_files=True,
            )
        except Exception as exc:
            logger.exception(
                "Manual asset generation failed project_id=%s pipeline_id=%s story_id=%s",
                project_id,
                resolved_pipeline_id,
                tracking_story_id,
            )
            await _persist_manual_pipeline_state(
                db_session,
                project_id=project_id,
                pipeline_id=resolved_pipeline_id,
                story_id=tracking_story_id,
                updates={
                    "status": PipelineStatus.FAILED,
                    "current_step": "Asset generation failed",
                    "error": str(exc),
                    "progress_detail": None,
                },
                merge_generated_files=True,
            )

    async def _run_in_background() -> None:
        async with AsyncSessionLocal() as db_session:
            await _generate_with_session(db_session)

    if background_tasks:
        background_tasks.add_task(_run_in_background)
        return PipelineActionResponse(
            project_id=project_id,
            pipeline_id=resolved_pipeline_id,
            story_id=tracking_story_id,
            message="Asset generation started",
            state=_build_pipeline_status_response(project_id, initial_pipeline),
        )

    await _generate_with_session(db)
    final_pipeline = await _load_pipeline_record(
        db,
        project_id=project_id,
        pipeline_id=resolved_pipeline_id,
        story_id=tracking_story_id,
    )
    return PipelineActionResponse(
        project_id=project_id,
        pipeline_id=resolved_pipeline_id,
        story_id=tracking_story_id,
        message="Asset generation finished",
        state=_build_pipeline_status_response(project_id, final_pipeline),
    )


@router.post("/{project_id}/render-video", response_model=PipelineActionResponse)
async def render_video(
    project_id: str,
    request: Request,
    shots_data: list[dict],
    video_config: dict = Depends(video_config_dep),
    llm: dict = Depends(llm_config_dep),
    base_url: str = Query("http://localhost:8000", description="Backend base url"),
    video_model: str = Query("wan2.6-i2v-flash", description="Video model"),
    pipeline_id: str | None = Query(None, description="Optional manual pipeline id"),
    story_id: str | None = Query(None, description="Stable story id for StoryContext loading"),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db),
):
    from app.services import video

    tracking_story_id = resolve_tracking_story_id(project_id, _normalize_optional_id(story_id))
    resolved_pipeline_id = _normalize_optional_id(pipeline_id) or str(uuid4())
    art_style = get_art_style(request)
    total = len(shots_data)

    initial_pipeline = await _persist_manual_pipeline_state(
        db,
        project_id=project_id,
        pipeline_id=resolved_pipeline_id,
        story_id=tracking_story_id,
        updates={
            "status": PipelineStatus.RENDERING_VIDEO,
            "progress": 65,
            "current_step": "Rendering videos",
            "error": None,
            "progress_detail": {
                "step": "video",
                "current": 0,
                "total": total,
                "message": "Preparing video generation",
            },
        },
        merge_generated_files=True,
    )

    async def _render_with_session(db_session: AsyncSession) -> None:
        try:
            _, story_context = await _load_story_context(
                db_session,
                tracking_story_id,
                provider=llm["provider"],
                model=llm["model"],
                api_key=llm["api_key"],
                base_url=llm["base_url"],
            )

            prepared_shots = []
            for shot in shots_data:
                payload = build_generation_payload(shot, story_context, art_style=art_style)
                prepared_shots.append(
                    {
                        **shot,
                        "final_video_prompt": payload["final_video_prompt"],
                        "negative_prompt": payload.get("negative_prompt", ""),
                    }
                )

            video_results = await video.generate_videos_batch(
                shots=prepared_shots,
                base_url=base_url,
                model=video_model,
                art_style=art_style,
                **video_config,
            )

            await _persist_manual_pipeline_state(
                db_session,
                project_id=project_id,
                pipeline_id=resolved_pipeline_id,
                story_id=tracking_story_id,
                updates={
                    "status": PipelineStatus.RENDERING_VIDEO,
                    "progress": 85,
                    "current_step": f"Videos ready: {len(video_results)} shots",
                    "error": None,
                    "progress_detail": None,
                    "generated_files": {
                        "videos": {result["shot_id"]: result for result in video_results},
                    },
                },
                merge_generated_files=True,
            )
        except Exception as exc:
            logger.exception(
                "Manual video rendering failed project_id=%s pipeline_id=%s story_id=%s",
                project_id,
                resolved_pipeline_id,
                tracking_story_id,
            )
            await _persist_manual_pipeline_state(
                db_session,
                project_id=project_id,
                pipeline_id=resolved_pipeline_id,
                story_id=tracking_story_id,
                updates={
                    "status": PipelineStatus.FAILED,
                    "current_step": "Video rendering failed",
                    "error": str(exc),
                    "progress_detail": None,
                },
                merge_generated_files=True,
            )

    async def _run_in_background() -> None:
        async with AsyncSessionLocal() as db_session:
            await _render_with_session(db_session)

    if background_tasks:
        background_tasks.add_task(_run_in_background)
        return PipelineActionResponse(
            project_id=project_id,
            pipeline_id=resolved_pipeline_id,
            story_id=tracking_story_id,
            message="Video rendering started",
            state=_build_pipeline_status_response(project_id, initial_pipeline),
        )

    await _render_with_session(db)
    final_pipeline = await _load_pipeline_record(
        db,
        project_id=project_id,
        pipeline_id=resolved_pipeline_id,
        story_id=tracking_story_id,
    )
    return PipelineActionResponse(
        project_id=project_id,
        pipeline_id=resolved_pipeline_id,
        story_id=tracking_story_id,
        message="Video rendering finished",
        state=_build_pipeline_status_response(project_id, final_pipeline),
    )

@router.get("/{project_id}/status", response_model=PipelineStatusResponse)
async def get_status(
    project_id: str,
    pipeline_id: str | None = None,
    story_id: str | None = Query(None, description="Stable story id for pipeline lookup"),
    db: AsyncSession = Depends(get_db),
):
    normalized_pipeline_id = _normalize_optional_id(pipeline_id)
    normalized_story_id = _normalize_optional_id(story_id)

    pipeline = None
    if normalized_pipeline_id:
        pipeline = await repo.get_pipeline(db, normalized_pipeline_id)
        if not pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")
    elif normalized_story_id:
        pipeline = await repo.get_pipeline_by_story(db, normalized_story_id)
    else:
        pipeline = await repo.get_pipeline_by_story(db, project_id)

    if not pipeline:
        pipeline = _default_pipeline_record(project_id=project_id, story_id=normalized_story_id)

    if "id" not in pipeline:
        pipeline["id"] = normalized_pipeline_id
    if not pipeline.get("story_id"):
        pipeline["story_id"] = normalized_story_id or project_id

    return _build_pipeline_status_response(project_id, pipeline)


@router.post("/{project_id}/concat", response_model=ConcatResponse)
async def concat_videos(
    project_id: str,
    req: ConcatRequest,
    request: Request,
    pipeline_id: str | None = Query(None, description="Optional manual pipeline id"),
    story_id: str | None = Query(None, description="Stable story id for pipeline lookup"),
    db: AsyncSession = Depends(get_db),
):
    from app.services.ffmpeg import VIDEO_DIR, _url_to_local_path, concat_videos as do_concat

    if not req.video_urls:
        raise HTTPException(status_code=400, detail="Video list is empty")

    normalized_pipeline_id = _normalize_optional_id(pipeline_id)
    tracking_story_id = resolve_tracking_story_id(project_id, _normalize_optional_id(story_id))
    base_url = str(request.base_url).rstrip("/")
    local_paths = [_url_to_local_path(url, base_url) for url in req.video_urls]
    output_path = str(VIDEO_DIR / f"episode_{project_id}.mp4")

    if normalized_pipeline_id:
        await _persist_manual_pipeline_state(
            db,
            project_id=project_id,
            pipeline_id=normalized_pipeline_id,
            story_id=tracking_story_id,
            updates={
                "status": PipelineStatus.STITCHING,
                "progress": 90,
                "current_step": "Concatenating videos",
                "error": None,
                "progress_detail": None,
            },
            merge_generated_files=True,
        )

    try:
        await do_concat(local_paths, output_path)
    except (FileNotFoundError, ValueError) as exc:
        if normalized_pipeline_id:
            await _persist_manual_pipeline_state(
                db,
                project_id=project_id,
                pipeline_id=normalized_pipeline_id,
                story_id=tracking_story_id,
                updates={
                    "status": PipelineStatus.FAILED,
                    "current_step": "Video concat failed",
                    "error": str(exc),
                    "progress_detail": None,
                },
                merge_generated_files=True,
            )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        if normalized_pipeline_id:
            await _persist_manual_pipeline_state(
                db,
                project_id=project_id,
                pipeline_id=normalized_pipeline_id,
                story_id=tracking_story_id,
                updates={
                    "status": PipelineStatus.FAILED,
                    "current_step": "Video concat failed",
                    "error": str(exc),
                    "progress_detail": None,
                },
                merge_generated_files=True,
            )
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    video_url = f"/{output_path}"

    if normalized_pipeline_id:
        await _persist_manual_pipeline_state(
            db,
            project_id=project_id,
            pipeline_id=normalized_pipeline_id,
            story_id=tracking_story_id,
            updates={
                "status": PipelineStatus.COMPLETE,
                "progress": 100,
                "current_step": "Video concat complete",
                "error": None,
                "progress_detail": None,
                "generated_files": {"final_video_url": video_url},
            },
            merge_generated_files=True,
        )

    return ConcatResponse(
        video_url=video_url,
        pipeline_id=normalized_pipeline_id,
        story_id=tracking_story_id,
    )
