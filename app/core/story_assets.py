from __future__ import annotations

import re
from typing import Any, Mapping


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def extract_scene_index_from_shot_id(shot_id: str) -> int | None:
    match = re.match(r"scene(\d+)_shot\d+$", _normalize_text(shot_id), flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def extract_scene_number_from_source_scene_key(source_scene_key: str) -> int | None:
    normalized = _normalize_text(source_scene_key)
    if not normalized:
        return None
    exact_match = re.match(r"ep\d+_scene(\d+)$", normalized, flags=re.IGNORECASE)
    if exact_match:
        return int(exact_match.group(1))
    alias_match = re.match(r"scene(\d+)$", normalized, flags=re.IGNORECASE)
    if alias_match:
        return int(alias_match.group(1))
    return None


def extract_episode_number_from_source_scene_key(source_scene_key: str) -> int | None:
    normalized = _normalize_text(source_scene_key)
    if not normalized:
        return None
    match = re.search(r"ep(\d+)", normalized, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _is_usable_scene_reference_asset(asset: Mapping[str, Any]) -> bool:
    status = _normalize_text(asset.get("status", ""))
    if status and status != "ready":
        return False
    variants = asset.get("variants")
    if not isinstance(variants, Mapping):
        return False
    scene_variant = variants.get("scene")
    if not isinstance(scene_variant, Mapping):
        return False
    return bool(_normalize_text(scene_variant.get("image_url", "")) or _normalize_text(scene_variant.get("image_path", "")))


def get_character_asset_entry(
    character_images: Mapping[str, Any] | None,
    identifier: str = "",
    *,
    name: str = "",
) -> dict[str, Any]:
    if not isinstance(character_images, Mapping):
        return {}
    normalized_identifier = _normalize_text(identifier)
    if not normalized_identifier:
        return {}
    entry = character_images.get(normalized_identifier)
    normalized_name = _normalize_text(name)
    if not isinstance(entry, Mapping) and normalized_name:
        legacy_entry = character_images.get(normalized_name)
        if isinstance(legacy_entry, Mapping):
            entry = legacy_entry
    if not isinstance(entry, Mapping):
        for candidate in character_images.values():
            if not isinstance(candidate, Mapping):
                continue
            if _normalize_text(candidate.get("character_id")) == normalized_identifier:
                entry = candidate
                break
            if normalized_name and _normalize_text(candidate.get("character_name")) == normalized_name:
                entry = candidate
                break
    return dict(entry) if isinstance(entry, Mapping) else {}


def get_character_visual_dna(
    character_images: Mapping[str, Any] | None,
    identifier: str = "",
    *,
    name: str = "",
) -> str:
    entry = get_character_asset_entry(character_images, identifier, name=name)
    return _normalize_text(entry.get("visual_dna", ""))


def get_character_design_prompt(
    character_images: Mapping[str, Any] | None,
    identifier: str = "",
    *,
    name: str = "",
) -> str:
    entry = get_character_asset_entry(character_images, identifier, name=name)
    return _normalize_text(entry.get("design_prompt") or entry.get("prompt", ""))


def build_character_asset_record(
    *,
    image_url: str,
    image_path: str,
    prompt: str,
    existing: Mapping[str, Any] | None = None,
    visual_dna: str = "",
    character_id: str = "",
    character_name: str = "",
) -> dict[str, Any]:
    record = dict(existing or {})
    record.update(
        {
            "image_url": image_url,
            "image_path": image_path,
            "prompt": prompt,
            "design_prompt": prompt,
            "asset_kind": "character_sheet",
            "framing": "three_view",
        }
    )
    normalized_character_id = _normalize_text(character_id)
    if normalized_character_id:
        record["character_id"] = normalized_character_id
    normalized_character_name = _normalize_text(character_name)
    if normalized_character_name:
        record["character_name"] = normalized_character_name
    normalized_visual_dna = _normalize_text(visual_dna)
    if normalized_visual_dna:
        record["visual_dna"] = normalized_visual_dna
    return record


def get_scene_reference_asset(
    story_or_meta: Mapping[str, Any] | None,
    source_scene_key: str = "",
    *,
    shot_id: str = "",
) -> dict[str, Any]:
    if not isinstance(story_or_meta, Mapping):
        return {}

    meta = story_or_meta.get("meta") if isinstance(story_or_meta.get("meta"), Mapping) else story_or_meta
    if not isinstance(meta, Mapping):
        return {}

    assets = meta.get("scene_reference_assets")
    if not isinstance(assets, Mapping):
        return {}

    normalized_key = _normalize_text(source_scene_key)
    if normalized_key:
        exact = assets.get(normalized_key)
        if isinstance(exact, Mapping) and _is_usable_scene_reference_asset(exact):
            return dict(exact)

    scene_number = extract_scene_number_from_source_scene_key(normalized_key)
    if scene_number is None:
        scene_number = extract_scene_index_from_shot_id(shot_id)
    if scene_number is None:
        return {}

    def _collect_matches(suffix: str) -> list[dict[str, Any]]:
        return [
            dict(asset)
            for key, asset in assets.items()
            if isinstance(asset, Mapping)
            and _normalize_text(key).lower().endswith(suffix.lower())
            and _is_usable_scene_reference_asset(asset)
        ]

    episode_number = extract_episode_number_from_source_scene_key(normalized_key)
    if episode_number is not None:
        episode_suffix = f"ep{episode_number:02d}_scene{scene_number:02d}"
        matches = _collect_matches(episode_suffix)
        if len(matches) == 1:
            return matches[0]
        if matches:
            return {}

    matches = _collect_matches(f"_scene{scene_number:02d}")
    if len(matches) == 1:
        return matches[0]
    return {}
