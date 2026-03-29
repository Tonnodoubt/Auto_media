from __future__ import annotations

import logging
from copy import deepcopy
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Mapping
from app.schemas.pipeline import PipelineStatus

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
else:
    AsyncSession = Any

logger = logging.getLogger(__name__)

STORYBOARD_GENERATION_META_KEY = "storyboard_generation"
_TRANSIENT_SHOT_KEYS = {"ttsLoading", "imageLoading", "videoLoading"}
_DEPRECATED_SHOT_KEYS = {"last_frame_prompt", "last_frame_url"}


def serialize_shot_for_storage(shot: Any) -> dict[str, Any]:
    if hasattr(shot, "model_dump"):
        data = shot.model_dump(mode="json")
    elif hasattr(shot, "dict"):
        data = shot.dict()
    else:
        data = dict(shot)
    return {
        key: deepcopy(value)
        for key, value in data.items()
        if key not in _TRANSIENT_SHOT_KEYS and key not in _DEPRECATED_SHOT_KEYS
    }


def load_storyboard_generation_state(story: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(story, Mapping):
        return {}
    meta = story.get("meta")
    if not isinstance(meta, Mapping):
        return {}
    state = meta.get(STORYBOARD_GENERATION_META_KEY)
    return deepcopy(dict(state)) if isinstance(state, Mapping) else {}


def _merge_generated_files(
    existing: Mapping[str, Any] | None,
    incoming: Mapping[str, Any] | None,
) -> dict[str, Any]:
    merged = deepcopy(dict(existing)) if isinstance(existing, Mapping) else {}
    if not isinstance(incoming, Mapping):
        return merged

    for key, value in dict(incoming).items():
        if isinstance(merged.get(key), Mapping) and isinstance(value, Mapping):
            nested = deepcopy(dict(merged.get(key) or {}))
            nested.update(deepcopy(dict(value)))
            merged[key] = nested
            continue
        merged[key] = deepcopy(value)
    return merged


def _merge_shots(
    existing_shots: list[dict[str, Any]],
    incoming_shots: list[Any],
    *,
    partial: bool,
) -> list[dict[str, Any]]:
    serialized_incoming = [serialize_shot_for_storage(shot) for shot in incoming_shots]
    if not partial:
        return serialized_incoming

    existing_map = {
        str(shot.get("shot_id", "")): deepcopy(shot)
        for shot in existing_shots
        if isinstance(shot, Mapping) and shot.get("shot_id")
    }
    incoming_order: list[str] = []
    for shot in serialized_incoming:
        shot_id = str(shot.get("shot_id", ""))
        if not shot_id:
            continue
        existing_map[shot_id] = {**existing_map.get(shot_id, {}), **shot}
        incoming_order.append(shot_id)

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for shot in existing_shots:
        if not isinstance(shot, Mapping):
            continue
        shot_id = str(shot.get("shot_id", ""))
        if not shot_id or shot_id not in existing_map:
            continue
        merged.append(deepcopy(existing_map[shot_id]))
        seen.add(shot_id)

    for shot_id in incoming_order:
        if shot_id in seen or shot_id not in existing_map:
            continue
        merged.append(deepcopy(existing_map[shot_id]))
        seen.add(shot_id)

    return merged


def _apply_generated_files_to_shots(
    shots: list[dict[str, Any]],
    generated_files: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(generated_files, Mapping):
        return shots

    shot_map = {
        str(shot.get("shot_id", "")): deepcopy(shot)
        for shot in shots
        if isinstance(shot, Mapping) and shot.get("shot_id")
    }

    def _ensure_shot(shot_id: str) -> dict[str, Any]:
        if shot_id not in shot_map:
            shot_map[shot_id] = {"shot_id": shot_id}
        return shot_map[shot_id]

    for result in (generated_files.get("tts") or {}).values():
        if not isinstance(result, Mapping):
            continue
        shot_id = str(result.get("shot_id", ""))
        if not shot_id:
            continue
        shot = _ensure_shot(shot_id)
        shot["audio_url"] = result.get("audio_url")
        if result.get("duration_seconds") is not None:
            shot["audio_duration"] = result.get("duration_seconds")
        elif result.get("audio_duration") is not None:
            shot["audio_duration"] = result.get("audio_duration")

    for result in (generated_files.get("images") or {}).values():
        if not isinstance(result, Mapping):
            continue
        shot_id = str(result.get("shot_id", ""))
        if not shot_id:
            continue
        shot = _ensure_shot(shot_id)
        shot["image_url"] = result.get("image_url")
        shot["image_path"] = result.get("image_path")
        shot.pop("last_frame_url", None)

    for result in (generated_files.get("videos") or {}).values():
        if not isinstance(result, Mapping):
            continue
        shot_id = str(result.get("shot_id", ""))
        if not shot_id:
            continue
        shot = _ensure_shot(shot_id)
        shot["video_url"] = result.get("video_url")
        if result.get("video_path") is not None:
            shot["video_path"] = result.get("video_path")

    ordered_ids = [str(shot.get("shot_id", "")) for shot in shots if isinstance(shot, Mapping) and shot.get("shot_id")]
    for shot_id in shot_map:
        if shot_id not in ordered_ids:
            ordered_ids.append(shot_id)
    return [deepcopy(shot_map[shot_id]) for shot_id in ordered_ids if shot_id]


def build_storyboard_generation_state(
    story: Mapping[str, Any] | None,
    *,
    shots: list[Any] | None = None,
    partial_shots: bool = False,
    usage: Mapping[str, Any] | None = None,
    generated_files: Mapping[str, Any] | None = None,
    pipeline_id: str = "",
    project_id: str = "",
    story_id: str = "",
    final_video_url: str | None = None,
) -> dict[str, Any]:
    state = load_storyboard_generation_state(story)
    state.setdefault("shots", [])

    if shots is not None:
        state["shots"] = _merge_shots(
            list(state.get("shots") or []),
            shots,
            partial=partial_shots,
        )
    if usage is not None:
        state["usage"] = deepcopy(dict(usage))
    if generated_files is not None:
        state["generated_files"] = _merge_generated_files(
            state.get("generated_files"),
            generated_files,
        )
        state["shots"] = _apply_generated_files_to_shots(
            list(state.get("shots") or []),
            generated_files,
        )
    if project_id:
        state["project_id"] = project_id
    if pipeline_id:
        state["pipeline_id"] = pipeline_id
    if story_id:
        state["story_id"] = story_id
    if final_video_url is not None:
        state["final_video_url"] = final_video_url
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    return state


async def persist_storyboard_generation_state(
    db: AsyncSession,
    *,
    story_id: str,
    story: Mapping[str, Any] | None,
    shots: list[Any] | None = None,
    partial_shots: bool = False,
    usage: Mapping[str, Any] | None = None,
    generated_files: Mapping[str, Any] | None = None,
    pipeline_id: str = "",
    project_id: str = "",
    final_video_url: str | None = None,
) -> dict[str, Any]:
    from app.services import story_repository as repo

    normalized_story_id = str(story_id or "").strip()
    if not normalized_story_id:
        logger.warning(
            "Skipping storyboard_generation persistence because story_id is empty. story_id=%r pipeline_id=%r project_id=%r",
            story_id,
            pipeline_id,
            project_id,
        )
        return {}
    state = build_storyboard_generation_state(
        story,
        shots=shots,
        partial_shots=partial_shots,
        usage=usage,
        generated_files=generated_files,
        pipeline_id=pipeline_id,
        project_id=project_id,
        story_id=normalized_story_id,
        final_video_url=final_video_url,
    )
    await repo.upsert_story_meta_cache(
        db,
        normalized_story_id,
        STORYBOARD_GENERATION_META_KEY,
        state,
    )
    return state


async def persist_generated_files_to_pipeline(
    db: AsyncSession,
    *,
    project_id: str,
    pipeline_id: str,
    story_id: str,
    generated_files: Mapping[str, Any] | None = None,
    final_video_url: str | None = None,
) -> dict[str, Any]:
    from app.services import story_repository as repo

    normalized_pipeline_id = str(pipeline_id or "").strip()
    normalized_story_id = str(story_id or "").strip()
    if not normalized_pipeline_id or not normalized_story_id:
        logger.warning(
            "Skipping pipeline generated_files persistence because pipeline_id/story_id is empty. pipeline_id=%r story_id=%r normalized_pipeline_id=%r normalized_story_id=%r",
            pipeline_id,
            story_id,
            normalized_pipeline_id,
            normalized_story_id,
        )
        return {}

    existing_pipeline = await repo.get_pipeline(db, normalized_pipeline_id)
    merged_generated_files = _merge_generated_files(
        existing_pipeline.get("generated_files"),
        generated_files,
    )
    if final_video_url is not None:
        merged_generated_files["final_video_url"] = final_video_url

    next_pipeline = {
        "status": existing_pipeline.get("status"),
        "progress": existing_pipeline.get("progress", 0),
        "current_step": existing_pipeline.get("current_step"),
        "error": existing_pipeline.get("error"),
        "progress_detail": existing_pipeline.get("progress_detail"),
        "generated_files": merged_generated_files,
    }

    if not next_pipeline["status"]:
        next_pipeline["status"] = PipelineStatus.PENDING
    if not next_pipeline["current_step"]:
        next_pipeline["current_step"] = "Manual asset persisted"

    await repo.save_pipeline(
        db,
        normalized_pipeline_id,
        normalized_story_id,
        next_pipeline,
    )
    return merged_generated_files
