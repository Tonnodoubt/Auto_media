from __future__ import annotations

from typing import Any, Mapping


APPEARANCE_CACHE_SCHEMA_VERSION = 1
SCENE_STYLE_CACHE_SCHEMA_VERSION = 1


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def coerce_cache_schema_version(value: Any) -> int | None:
    normalized = _normalize_text(value)
    if not normalized:
        return None
    try:
        return int(normalized)
    except (TypeError, ValueError):
        return None


def _schema_version_is_compatible(value: Any, *, current_schema_version: int) -> bool:
    normalized = _normalize_text(value)
    if not normalized:
        return True
    schema_version = coerce_cache_schema_version(normalized)
    if schema_version is None:
        return False
    return 1 <= schema_version <= current_schema_version


def is_appearance_cache_entry_compatible(entry: Mapping[str, Any] | None) -> bool:
    if not isinstance(entry, Mapping):
        return False
    if not _schema_version_is_compatible(
        entry.get("schema_version"),
        current_schema_version=APPEARANCE_CACHE_SCHEMA_VERSION,
    ):
        return False
    return any(_normalize_text(entry.get(field)) for field in ("body", "clothing", "negative_prompt"))


def is_scene_style_cache_entry_compatible(entry: Mapping[str, Any] | None) -> bool:
    if not isinstance(entry, Mapping):
        return False
    if not _schema_version_is_compatible(
        entry.get("schema_version"),
        current_schema_version=SCENE_STYLE_CACHE_SCHEMA_VERSION,
    ):
        return False
    return any(_normalize_text(entry.get(field)) for field in ("image_extra", "video_extra", "negative_prompt"))
