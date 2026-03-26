from __future__ import annotations

from typing import Any, Mapping


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


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
