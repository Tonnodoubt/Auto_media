import logging
import re
from uuid import uuid4
from pathlib import Path

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
    TransitionGenerateRequest,
    TransitionResult,
)
from app.schemas.storyboard import Storyboard
from app.services import story_repository as repo
from app.services.pipeline_executor import PipelineExecutor
from app.services.storyboard_state import persist_storyboard_generation_state
from app.services.story_context_service import prepare_story_context
from app.services.storyboard import parse_script_to_storyboard
from app.services.storyboard_state import load_storyboard_generation_state

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
    record["story_id"] = _normalize_optional_id(record.get("story_id")) or story_id
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
            merged_generated_files = _merge_generated_files(existing_generated_files, new_generated_files)
            updates = {**updates, "generated_files": merged_generated_files}

    pipeline.update(updates)

    effective_story_id = _normalize_optional_id(pipeline.get("story_id")) or story_id
    await repo.save_pipeline(db, pipeline_id, effective_story_id, pipeline)
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


def _collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _trim_words(text: str, limit: int) -> str:
    normalized = _collapse_spaces(text)
    words = normalized.split()
    if len(words) <= limit:
        return normalized.strip(" ,.;:!?，。；：！？、")
    return " ".join(words[:limit]).strip(" ,.;:!?，。；：！？、")


def _merge_generated_files(existing: dict | None, incoming: dict | None) -> dict:
    merged = dict(existing or {})
    if not isinstance(incoming, dict):
        return merged
    for key, value in incoming.items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            nested = dict(merged.get(key) or {})
            nested.update(value)
            merged[key] = nested
            continue
        merged[key] = value
    return merged


def _serialize_timeline(shots: list[dict], transitions: dict[str, dict] | None) -> list[dict]:
    transition_map = transitions or {}
    timeline: list[dict] = []
    for index, shot in enumerate(shots):
        shot_id = str(shot.get("shot_id", "")).strip()
        if not shot_id:
            continue
        timeline.append({"item_type": "shot", "item_id": shot_id})
        next_shot = shots[index + 1] if index + 1 < len(shots) else None
        if not next_shot:
            continue
        next_shot_id = str(next_shot.get("shot_id", "")).strip()
        transition_id = f"transition_{shot_id}__{next_shot_id}"
        transition = transition_map.get(transition_id) or {}
        if transition.get("video_url"):
            timeline.append({"item_type": "transition", "item_id": transition_id})
    return timeline


def _url_from_local_media_path(path: str) -> str:
    normalized = str(Path(path)).replace("\\", "/").lstrip("/")
    return f"/{normalized}"


def _absolute_media_url(url: str, base_url: str) -> str:
    normalized = str(url or "").strip()
    if not normalized:
        return normalized
    if normalized.startswith(("http://", "https://", "data:")):
        return normalized
    if normalized.startswith("/"):
        return f"{base_url}{normalized}"
    return f"{base_url}/{normalized}"


def _build_transition_prompt(
    *,
    from_shot: dict,
    to_shot: dict,
    from_payload: dict,
    to_payload: dict,
    user_hint: str,
) -> str:
    from_camera = from_shot.get("camera_setup") or {}
    to_camera = to_shot.get("camera_setup") or {}
    from_visuals = from_shot.get("visual_elements") or {}
    to_visuals = to_shot.get("visual_elements") or {}

    def _camera_phrase(camera: dict) -> str:
        shot_size = _collapse_spaces(str(camera.get("shot_size", "")))
        angle = _collapse_spaces(str(camera.get("camera_angle", "")))
        movement = _collapse_spaces(str(camera.get("movement", "")))
        pieces = [piece for piece in (shot_size, angle, movement) if piece]
        return ", ".join(pieces)

    bridge = _trim_words(str(to_shot.get("transition_from_previous", "")), 28)
    from_desc = _trim_words(str(from_shot.get("storyboard_description", "")), 18)
    to_desc = _trim_words(str(to_shot.get("storyboard_description", "")), 18)
    from_frame = _trim_words(str(from_payload.get("image_prompt", "")), 20)
    to_frame = _trim_words(str(to_payload.get("image_prompt", "")), 20)
    from_subject = _trim_words(str((from_shot.get("visual_elements") or {}).get("subject_and_clothing", "")), 12)
    to_subject = _trim_words(str((to_shot.get("visual_elements") or {}).get("subject_and_clothing", "")), 12)
    from_action = _trim_words(str(from_visuals.get("action_and_expression", "")), 16)
    to_action = _trim_words(str(to_visuals.get("action_and_expression", "")), 16)
    from_environment = _trim_words(str(from_visuals.get("environment_and_props", "")), 16)
    to_environment = _trim_words(str(to_visuals.get("environment_and_props", "")), 16)
    from_lighting = _trim_words(str(from_visuals.get("lighting_and_color", "")), 16)
    to_lighting = _trim_words(str(to_visuals.get("lighting_and_color", "")), 16)
    from_camera_phrase = _trim_words(_camera_phrase(from_camera), 10)
    to_camera_phrase = _trim_words(_camera_phrase(to_camera), 10)
    from_prompt = _trim_words(str(from_payload.get("final_video_prompt", "")), 18)
    to_prompt = _trim_words(str(to_payload.get("final_video_prompt", "")), 18)
    hint = _trim_words(user_hint, 18)

    parts = [
        "Short cinematic transition between two adjacent storyboard shots.",
        "Stay inside the same story beat and visual theme.",
        f"Start from the exact ending frame of: {from_desc or from_frame or from_prompt or from_subject}.",
        f"Arrive at the exact opening frame of: {to_desc or to_frame or to_prompt or to_subject}.",
        "Create one smooth, physically plausible bridging motion instead of a hard jump.",
        "Keep identity, outfit, props, environment logic, lighting direction, and camera continuity consistent.",
        "Do not introduce new characters, unrelated props, new locations, costume changes, or off-theme action.",
    ]
    if from_action or to_action:
        parts.append(f"Action bridge: move naturally from {from_action or from_desc or from_prompt} into {to_action or to_desc or to_prompt}.")
    if from_camera_phrase or to_camera_phrase:
        parts.append(f"Camera continuity: begin with {from_camera_phrase or 'the current framing'} and settle into {to_camera_phrase or 'the destination framing'} with smooth motion.")
    if from_environment or to_environment:
        parts.append(
            f"Environment continuity: preserve the visible space and props from {from_environment or from_desc} into {to_environment or to_desc} without abrupt layout changes."
        )
    if from_lighting or to_lighting:
        parts.append(
            f"Lighting continuity: keep the light direction and color stable from {from_lighting or 'the previous frame'} toward {to_lighting or 'the next frame'}."
        )
    if from_subject or to_subject:
        parts.append(f"Subject continuity: keep the same appearance and silhouette from {from_subject or to_subject} to {to_subject or from_subject}.")
    if bridge:
        parts.append(f"Narrative bridge: {bridge}.")
    if hint:
        parts.append(f"User emphasis: {hint}.")
    return _collapse_spaces(" ".join(parts))


def _merge_negative_prompts(*prompts: str) -> str:
    ordered: list[str] = []
    for prompt in prompts:
        normalized = _collapse_spaces(prompt)
        if not normalized:
            continue
        for piece in re.split(r"\s*,\s*", normalized):
            cleaned = piece.strip()
            if not cleaned:
                continue
            lowered = cleaned.casefold()
            if any(existing.casefold() == lowered for existing in ordered):
                continue
            ordered.append(cleaned)
    return ", ".join(ordered)


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
    if tracking_story_id and story:
        await persist_storyboard_generation_state(
            db,
            story_id=tracking_story_id,
            story=story,
            shots=shots,
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
            },
            pipeline_id=pipeline_id,
            project_id=project_id,
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
    resolved_story_id = _normalize_optional_id(initial_pipeline.get("story_id")) or tracking_story_id

    async def _generate_with_session(db_session: AsyncSession) -> None:
        try:
            story, story_context = await _load_story_context(
                db_session,
                resolved_story_id,
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
                    story_id=resolved_story_id,
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
                    story_id=resolved_story_id,
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
                    shots=[
                        build_generation_payload(shot, story_context, art_style=art_style, story=story)
                        for shot in shots
                    ],
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
                story_id=resolved_story_id,
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
            if resolved_story_id and story:
                await persist_storyboard_generation_state(
                    db_session,
                    story_id=resolved_story_id,
                    story=story,
                    shots=shots,
                    partial_shots=False,
                    generated_files=generated_files,
                    pipeline_id=resolved_pipeline_id,
                    project_id=project_id,
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
                story_id=resolved_story_id,
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
            story_id=resolved_story_id,
            message="Asset generation started",
            state=_build_pipeline_status_response(project_id, initial_pipeline),
        )

    await _generate_with_session(db)
    final_pipeline = await _load_pipeline_record(
        db,
        project_id=project_id,
        pipeline_id=resolved_pipeline_id,
        story_id=resolved_story_id,
    )
    return PipelineActionResponse(
        project_id=project_id,
        pipeline_id=resolved_pipeline_id,
        story_id=resolved_story_id,
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
    resolved_story_id = _normalize_optional_id(initial_pipeline.get("story_id")) or tracking_story_id

    async def _render_with_session(db_session: AsyncSession) -> None:
        try:
            story, story_context = await _load_story_context(
                db_session,
                resolved_story_id,
                provider=llm["provider"],
                model=llm["model"],
                api_key=llm["api_key"],
                base_url=llm["base_url"],
            )

            prepared_shots = []
            for shot in shots_data:
                payload = build_generation_payload(shot, story_context, art_style=art_style, story=story)
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
                story_id=resolved_story_id,
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
            if resolved_story_id and story:
                await persist_storyboard_generation_state(
                    db_session,
                    story_id=resolved_story_id,
                    story=story,
                    shots=shots_data,
                    partial_shots=True,
                    generated_files={
                        "videos": {result["shot_id"]: result for result in video_results},
                    },
                    pipeline_id=resolved_pipeline_id,
                    project_id=project_id,
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
                story_id=resolved_story_id,
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
            story_id=resolved_story_id,
            message="Video rendering started",
            state=_build_pipeline_status_response(project_id, initial_pipeline),
        )

    await _render_with_session(db)
    final_pipeline = await _load_pipeline_record(
        db,
        project_id=project_id,
        pipeline_id=resolved_pipeline_id,
        story_id=resolved_story_id,
    )
    return PipelineActionResponse(
        project_id=project_id,
        pipeline_id=resolved_pipeline_id,
        story_id=resolved_story_id,
        message="Video rendering finished",
        state=_build_pipeline_status_response(project_id, final_pipeline),
    )


@router.post("/{project_id}/transitions/generate", response_model=TransitionResult)
async def generate_transition(
    project_id: str,
    request: Request,
    req: TransitionGenerateRequest,
    video_config: dict = Depends(video_config_dep),
    llm: dict = Depends(llm_config_dep),
    db: AsyncSession = Depends(get_db),
):
    from app.services import ffmpeg, video
    from app.services.ffmpeg import url_to_local_path

    normalized_pipeline_id = _normalize_optional_id(req.pipeline_id)
    if not normalized_pipeline_id:
        raise HTTPException(status_code=400, detail="pipeline_id is required")

    if not video.supports_dual_frame_provider(video_config["video_provider"]):
        raise HTTPException(
            status_code=400,
            detail=f"当前 provider={video_config['video_provider']} 不支持双帧过渡，请切换到 doubao。",
        )

    if req.duration_seconds < 1 or req.duration_seconds > 3:
        raise HTTPException(status_code=400, detail="duration_seconds must be between 1 and 3 seconds")

    pipeline = await _load_pipeline_record(
        db,
        project_id=project_id,
        pipeline_id=normalized_pipeline_id,
        story_id=resolve_tracking_story_id(project_id, _normalize_optional_id(req.story_id)),
    )
    tracking_story_id = (
        _normalize_optional_id(req.story_id)
        or _normalize_optional_id(pipeline.get("story_id"))
        or project_id
    )
    generated_files = dict(pipeline.get("generated_files") or {})

    story = await repo.get_story(db, tracking_story_id) if tracking_story_id else None
    stored_state = load_storyboard_generation_state(story)
    stored_generated_files = dict(stored_state.get("generated_files") or {})
    storyboard_payload = generated_files.get("storyboard") or stored_generated_files.get("storyboard") or {}
    storyboard_shots = storyboard_payload.get("shots") if isinstance(storyboard_payload, dict) else None
    if not isinstance(storyboard_shots, list) or not storyboard_shots:
        storyboard_shots = list(stored_state.get("shots") or [])
    if not storyboard_shots:
        raise HTTPException(status_code=400, detail="Storyboard shots are not available for this pipeline")

    shot_order = [str(shot.get("shot_id", "")).strip() for shot in storyboard_shots if str(shot.get("shot_id", "")).strip()]
    try:
        from_index = shot_order.index(req.from_shot_id)
        to_index = shot_order.index(req.to_shot_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Transition shots not found in storyboard") from exc

    if to_index != from_index + 1:
        raise HTTPException(status_code=400, detail="Only adjacent shots can create a transition")

    from_shot = dict(storyboard_shots[from_index])
    to_shot = dict(storyboard_shots[to_index])

    videos_map = dict(stored_generated_files.get("videos") or {})
    videos_map.update(generated_files.get("videos") or {})
    images_map = dict(stored_generated_files.get("images") or {})
    images_map.update(generated_files.get("images") or {})
    from_video_entry = videos_map.get(req.from_shot_id) or {"video_url": from_shot.get("video_url", "")}
    to_video_entry = videos_map.get(req.to_shot_id) or {"video_url": to_shot.get("video_url", "")}
    from_image_entry = images_map.get(req.from_shot_id) or {"image_url": from_shot.get("image_url", "")}
    to_image_entry = images_map.get(req.to_shot_id) or {"image_url": to_shot.get("image_url", "")}
    from_video_url = str(from_video_entry.get("video_url", "")).strip()
    to_video_url = str(to_video_entry.get("video_url", "")).strip()
    from_image_url = str(from_image_entry.get("image_url", "") or from_shot.get("image_url", "")).strip()
    to_image_url = str(to_image_entry.get("image_url", "") or to_shot.get("image_url", "")).strip()
    if not from_video_url or not to_video_url:
        missing = []
        if not from_video_url:
            missing.append(req.from_shot_id)
        if not to_video_url:
            missing.append(req.to_shot_id)
        raise HTTPException(
            status_code=400,
            detail=f"Transition requires both adjacent shot videos to be generated first. Missing video for: {', '.join(missing)}",
        )

    story, story_context = await _load_story_context(
        db,
        tracking_story_id,
        provider=llm["provider"],
        model=llm["model"],
        api_key=llm["api_key"],
        base_url=llm["base_url"],
    )
    art_style = get_art_style(request)
    from_payload = build_generation_payload(from_shot, story_context, art_style=art_style, story=story)
    to_payload = build_generation_payload(to_shot, story_context, art_style=art_style, story=story)
    transition_prompt = _build_transition_prompt(
        from_shot=from_shot,
        to_shot=to_shot,
        from_payload=from_payload,
        to_payload=to_payload,
        user_hint=req.transition_prompt or "",
    )
    negative_prompt = _merge_negative_prompts(
        str(from_payload.get("negative_prompt", "")),
        str(to_payload.get("negative_prompt", "")),
    )

    transition_id = f"transition_{req.from_shot_id}__{req.to_shot_id}"
    base_url = str(request.base_url).rstrip("/")
    from_video_path = url_to_local_path(from_video_url, base_url)
    to_video_path = url_to_local_path(to_video_url, base_url)
    try:
        try:
            from_frame_path = await ffmpeg.extract_last_frame(
                from_video_path,
                req.from_shot_id,
                output_name=f"{transition_id}_from_last.png",
            )
            from_frame_url = _url_from_local_media_path(from_frame_path)
        except (FileNotFoundError, RuntimeError) as exc:
            if not from_image_url:
                raise
            logger.warning(
                "Transition %s 前镜抽帧失败，回退到分镜图 %s: %s",
                transition_id,
                req.from_shot_id,
                exc,
            )
            from_frame_url = from_image_url

        try:
            to_frame_path = await ffmpeg.extract_first_frame(
                to_video_path,
                req.to_shot_id,
                output_name=f"{transition_id}_to_first.png",
            )
            to_frame_url = _url_from_local_media_path(to_frame_path)
        except (FileNotFoundError, RuntimeError) as exc:
            if not to_image_url:
                raise
            logger.warning(
                "Transition %s 后镜抽帧失败，回退到分镜图 %s: %s",
                transition_id,
                req.to_shot_id,
                exc,
            )
            to_frame_url = to_image_url

        transition_video = await video.generate_transition_video(
            transition_id=transition_id,
            # Provider-side parameter names are fixed: first_frame is the ending frame of from_shot,
            # last_frame is the opening frame of to_shot for this transition bridge.
            first_frame_url=_absolute_media_url(from_frame_url, base_url),
            last_frame_url=_absolute_media_url(to_frame_url, base_url),
            prompt=transition_prompt,
            model=req.model or "doubao-seedance-1-5-pro-251215",
            video_api_key=video_config["video_api_key"],
            video_base_url=video_config["video_base_url"],
            video_provider=video_config["video_provider"],
            negative_prompt=negative_prompt,
            duration_seconds=req.duration_seconds,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=f"过渡视频生成失败，缺少本地素材文件: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"过渡视频生成失败: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"过渡视频生成失败: {exc}") from exc

    result = {
        "transition_id": transition_id,
        "from_shot_id": req.from_shot_id,
        "to_shot_id": req.to_shot_id,
        "prompt": transition_prompt,
        "duration_seconds": req.duration_seconds,
        "video_url": transition_video["video_url"],
        "first_frame_source": {
            "shot_id": req.from_shot_id,
            "video_url": from_video_url,
            "frame_role": "from_last",
            "extracted_image_url": from_frame_url,
        },
        "last_frame_source": {
            "shot_id": req.to_shot_id,
            "video_url": to_video_url,
            "frame_role": "to_first",
            "extracted_image_url": to_frame_url,
        },
    }

    existing_transitions = dict(stored_generated_files.get("transitions") or {})
    existing_transitions.update(generated_files.get("transitions") or {})
    existing_transitions[transition_id] = result
    timeline = _serialize_timeline([dict(shot) for shot in storyboard_shots], existing_transitions)

    await _persist_manual_pipeline_state(
        db,
        project_id=project_id,
        pipeline_id=normalized_pipeline_id,
        story_id=tracking_story_id,
        updates={
            "generated_files": {
                "transitions": existing_transitions,
                "timeline": timeline,
            },
        },
        merge_generated_files=True,
    )

    persisted_story = await repo.get_story(db, tracking_story_id) if tracking_story_id else None
    if persisted_story:
        try:
            await persist_storyboard_generation_state(
                db,
                story_id=tracking_story_id,
                story=persisted_story,
                generated_files={
                    "transitions": {transition_id: result},
                    "timeline": timeline,
                },
                pipeline_id=normalized_pipeline_id,
                project_id=project_id,
            )
        except Exception:
            logger.exception(
                "Transition storyboard persistence failed project_id=%s pipeline_id=%s story_id=%s transition_id=%s",
                project_id,
                normalized_pipeline_id,
                tracking_story_id,
                transition_id,
            )

    return TransitionResult(**result)

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
    from app.services.ffmpeg import VIDEO_DIR, url_to_local_path, concat_videos as do_concat

    if not req.video_urls:
        raise HTTPException(status_code=400, detail="Video list is empty")

    normalized_pipeline_id = _normalize_optional_id(pipeline_id)
    tracking_story_id = resolve_tracking_story_id(project_id, _normalize_optional_id(story_id))
    base_url = str(request.base_url).rstrip("/")
    local_paths = [url_to_local_path(url, base_url) for url in req.video_urls]
    output_path = str(VIDEO_DIR / f"episode_{project_id}.mp4")
    resolved_story_id = tracking_story_id

    if normalized_pipeline_id:
        pipeline = await _persist_manual_pipeline_state(
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
        resolved_story_id = _normalize_optional_id(pipeline.get("story_id")) or tracking_story_id

    try:
        await do_concat(local_paths, output_path)
    except (FileNotFoundError, ValueError) as exc:
        if normalized_pipeline_id:
            await _persist_manual_pipeline_state(
                db,
                project_id=project_id,
                pipeline_id=normalized_pipeline_id,
                story_id=resolved_story_id,
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
                story_id=resolved_story_id,
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
            story_id=resolved_story_id,
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

    if resolved_story_id:
        story = await repo.get_story(db, resolved_story_id)
        if story:
            await persist_storyboard_generation_state(
                db,
                story_id=resolved_story_id,
                story=story,
                pipeline_id=normalized_pipeline_id or "",
                project_id=project_id,
                final_video_url=video_url,
            )

    return ConcatResponse(
        video_url=video_url,
        pipeline_id=normalized_pipeline_id,
        story_id=resolved_story_id,
    )
