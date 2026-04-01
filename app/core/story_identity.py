from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping
from uuid import uuid4

from app.core.character_profile import sanitize_character_profile_description
from app.core.consistency_cache import coerce_cache_schema_version


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_name_key(value: Any) -> str:
    return _normalize_text(value).casefold()


def _new_character_id() -> str:
    return f"char_{uuid4().hex[:12]}"


def _normalize_cache_metadata(entry: Mapping[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(dict(entry or {}))

    schema_version = coerce_cache_schema_version(normalized.get("schema_version"))
    if schema_version is None:
        normalized.pop("schema_version", None)
    else:
        normalized["schema_version"] = schema_version

    for key in ("source_provider", "source_model", "updated_at"):
        value = _normalize_text(normalized.get(key))
        if value:
            normalized[key] = value
        else:
            normalized.pop(key, None)

    return normalized


def _coerce_character(record: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(record or {})
    return {
        "id": _normalize_text(data.get("id")),
        "name": _normalize_text(data.get("name")),
        "role": _normalize_text(data.get("role")),
        "description": sanitize_character_profile_description(_normalize_text(data.get("description"))),
    }


def normalize_characters(
    characters: list[Mapping[str, Any]] | None,
    *,
    existing_characters: list[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    existing_list = [_coerce_character(character) for character in (existing_characters or [])]
    existing_by_id = {
        character["id"]: character
        for character in existing_list
        if character.get("id")
    }
    existing_by_name: dict[str, list[dict[str, Any]]] = {}
    for character in existing_list:
        name_key = _normalize_name_key(character.get("name"))
        if name_key:
            existing_by_name.setdefault(name_key, []).append(character)

    used_ids: set[str] = set()
    output: list[dict[str, Any]] = []
    for raw_character in characters or []:
        character = _coerce_character(raw_character)
        if not any(character.values()):
            continue

        char_id = character["id"]
        if char_id and char_id in used_ids:
            char_id = ""

        if not char_id:
            name_key = _normalize_name_key(character["name"])
            candidates = [
                item for item in existing_by_name.get(name_key, [])
                if item.get("id") and item["id"] not in used_ids
            ]
            if len(candidates) == 1:
                char_id = candidates[0]["id"]

        if not char_id:
            char_id = _new_character_id()

        if char_id in existing_by_id:
            merged = dict(existing_by_id[char_id])
            merged.update({k: v for k, v in character.items() if v or k == "id"})
            character = _coerce_character(merged)
            character["id"] = char_id
        else:
            character["id"] = char_id

        used_ids.add(char_id)
        output.append(character)

    return output


def normalize_relationships(
    relationships: list[Mapping[str, Any]] | None,
    *,
    characters: list[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    characters = [_coerce_character(character) for character in (characters or [])]
    chars_by_id = {
        character["id"]: character
        for character in characters
        if character.get("id")
    }
    ids_by_name: dict[str, list[str]] = {}
    for character in characters:
        name_key = _normalize_name_key(character.get("name"))
        if name_key and character.get("id"):
            ids_by_name.setdefault(name_key, []).append(character["id"])

    output: list[dict[str, Any]] = []
    for raw_relationship in relationships or []:
        relationship = dict(raw_relationship or {})
        source = _normalize_text(relationship.get("source"))
        target = _normalize_text(relationship.get("target"))
        label = _normalize_text(relationship.get("label"))
        source_id = _normalize_text(relationship.get("source_id"))
        target_id = _normalize_text(relationship.get("target_id"))

        if not source_id and source:
            candidates = ids_by_name.get(_normalize_name_key(source), [])
            if len(candidates) == 1:
                source_id = candidates[0]
        if not target_id and target:
            candidates = ids_by_name.get(_normalize_name_key(target), [])
            if len(candidates) == 1:
                target_id = candidates[0]

        if source_id and source_id in chars_by_id:
            source = chars_by_id[source_id]["name"]
        if target_id and target_id in chars_by_id:
            target = chars_by_id[target_id]["name"]

        if not source and not source_id:
            continue
        if not target and not target_id:
            continue

        output.append({
            "source": source,
            "target": target,
            "source_id": source_id or None,
            "target_id": target_id or None,
            "label": label,
        })

    return output


def normalize_character_images(
    character_images: Mapping[str, Any] | None,
    *,
    characters: list[Mapping[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    if not isinstance(character_images, Mapping):
        return {}

    characters = [_coerce_character(character) for character in (characters or [])]
    chars_by_id = {
        character["id"]: character
        for character in characters
        if character.get("id")
    }
    ids_by_name: dict[str, list[str]] = {}
    for character in characters:
        name_key = _normalize_name_key(character.get("name"))
        if name_key and character.get("id"):
            ids_by_name.setdefault(name_key, []).append(character["id"])

    normalized: dict[str, dict[str, Any]] = {}
    for raw_key, raw_value in character_images.items():
        if not isinstance(raw_value, Mapping):
            continue
        key = _normalize_text(raw_key)
        entry = deepcopy(dict(raw_value))
        target_id = ""

        if key in chars_by_id:
            target_id = key
        else:
            candidate_ids = ids_by_name.get(_normalize_name_key(key), [])
            if len(candidate_ids) == 1:
                target_id = candidate_ids[0]

        if not target_id:
            embedded_id = _normalize_text(entry.get("character_id"))
            if embedded_id in chars_by_id:
                target_id = embedded_id

        if not target_id:
            embedded_name_ids = ids_by_name.get(_normalize_name_key(entry.get("character_name")), [])
            if len(embedded_name_ids) == 1:
                target_id = embedded_name_ids[0]

        if not target_id:
            target_id = key

        if target_id in chars_by_id:
            entry["character_id"] = target_id
            entry["character_name"] = chars_by_id[target_id]["name"]
        elif key:
            entry.setdefault("character_name", key)

        merged = dict(normalized.get(target_id) or {})
        merged.update(entry)
        normalized[target_id] = merged

    return normalized


def normalize_character_appearance_cache(
    appearance_cache: Mapping[str, Any] | None,
    *,
    characters: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if not isinstance(appearance_cache, Mapping):
        return {}

    characters = [_coerce_character(character) for character in (characters or [])]
    chars_by_id = {
        character["id"]: character
        for character in characters
        if character.get("id")
    }
    ids_by_name: dict[str, list[str]] = {}
    for character in characters:
        name_key = _normalize_name_key(character.get("name"))
        if name_key and character.get("id"):
            ids_by_name.setdefault(name_key, []).append(character["id"])

    normalized: dict[str, Any] = {}
    for raw_key, raw_value in appearance_cache.items():
        if not isinstance(raw_value, Mapping):
            continue
        key = _normalize_text(raw_key)
        target_id = key if key in chars_by_id else ""
        if not target_id:
            candidate_ids = ids_by_name.get(_normalize_name_key(key), [])
            if len(candidate_ids) == 1:
                target_id = candidate_ids[0]
        normalized_entry = _normalize_cache_metadata(raw_value)
        for field in ("body", "clothing", "negative_prompt"):
            value = _normalize_text(normalized_entry.get(field))
            if value:
                normalized_entry[field] = value
            else:
                normalized_entry.pop(field, None)
        normalized[target_id or key] = normalized_entry
    return normalized


def normalize_scene_style_cache(scene_style_cache: list[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    if not isinstance(scene_style_cache, list):
        return []

    normalized: list[dict[str, Any]] = []
    for raw_entry in scene_style_cache:
        if not isinstance(raw_entry, Mapping):
            continue
        entry = _normalize_cache_metadata(raw_entry)
        keywords = raw_entry.get("keywords") or []
        if isinstance(keywords, list):
            entry["keywords"] = [_normalize_text(keyword) for keyword in keywords if _normalize_text(keyword)]
        else:
            entry["keywords"] = []
        for field in ("image_extra", "video_extra", "negative_prompt"):
            value = _normalize_text(raw_entry.get(field))
            if value:
                entry[field] = value
            else:
                entry.pop(field, None)
        if "always_apply" in raw_entry:
            entry["always_apply"] = bool(raw_entry.get("always_apply"))
        if entry.get("image_extra") or entry.get("video_extra") or entry.get("negative_prompt"):
            normalized.append(entry)
    return normalized


def normalize_story_record(
    record: Mapping[str, Any] | None,
    *,
    existing_story: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    story = deepcopy(dict(record or {}))
    existing_story = dict(existing_story or {})

    characters_source = story.get("characters") if "characters" in story else existing_story.get("characters")
    if characters_source is not None or "characters" in story:
        story["characters"] = normalize_characters(
            characters_source,
            existing_characters=existing_story.get("characters"),
        )

    relationships_source = story.get("relationships") if "relationships" in story else existing_story.get("relationships")
    if relationships_source is not None or "relationships" in story:
        story["relationships"] = normalize_relationships(
            relationships_source,
            characters=story.get("characters"),
        )

    character_images_source = story.get("character_images") if "character_images" in story else existing_story.get("character_images")
    if character_images_source is not None or "character_images" in story:
        story["character_images"] = normalize_character_images(
            character_images_source,
            characters=story.get("characters"),
        )

    meta = deepcopy(dict(existing_story.get("meta") or {}))
    if "meta" in story and isinstance(story.get("meta"), Mapping):
        meta.update(deepcopy(dict(story.get("meta") or {})))
    if "character_appearance_cache" in meta:
        meta["character_appearance_cache"] = normalize_character_appearance_cache(
            meta.get("character_appearance_cache"),
            characters=story.get("characters"),
        )
    if "scene_style_cache" in meta:
        meta["scene_style_cache"] = normalize_scene_style_cache(meta.get("scene_style_cache"))
    if meta or "meta" in story:
        story["meta"] = meta

    return story
