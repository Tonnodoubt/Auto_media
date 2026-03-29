from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import logging
import re
from time import monotonic
from typing import Any, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.story_assets import (
    build_character_asset_record,
    get_character_asset_entry,
    get_character_design_prompt,
)
from app.core.story_context import (
    StoryContext,
    build_story_context,
    sanitize_body_features,
    sanitize_default_clothing,
)
from app.services import story_repository as repo
from app.services.llm.factory import get_llm_provider


_logger = logging.getLogger(__name__)


@dataclass
class _StoryContextLockEntry:
    lock: asyncio.Lock
    last_used: float


_STORY_CONTEXT_LOCK_TTL_SECONDS = 900.0
_STORY_CONTEXT_LOCK_MAXSIZE = 512
_story_context_locks: dict[str, _StoryContextLockEntry] = {}


APPEARANCE_SYSTEM_PROMPT = """
You extract stable visual anchors for image and video generation.

Return strict JSON only in this shape:
{
  "characters": [
    {
      "id": "stable character id from input",
      "body": "immutable physical traits only, in concise English, max 18 words",
      "clothing": "default outfit and always-on accessories/headwear only, in concise English, max 12 words",
      "negative_prompt": "optional contamination exclusions only, max 12 words"
    }
  ]
}

Rules:
- Keep only immutable appearance traits in body: age bracket, gender presentation, hair color/style, eye color, skin tone, build, distinctive facial traits.
- Keep clothing to the normal default outfit and stable accessories/headwear, not scene-specific actions or poses.
- If the character normally wears a hat, hood, glasses, scarf, jewelry, mask, or signature accessory, keep it in clothing.
- Exclude lighting, background, camera words, emotions, personality, role arc, story summary, studio terms, art tags.
- Output concise English phrases suitable for image/video prompting.
""".strip()

SCENE_STYLE_SYSTEM_PROMPT = """
You compress story setting into compact visual consistency anchors for image and video generation.

Return strict JSON only in this shape:
{
  "styles": [
    {
      "keywords": ["optional short keyword", "optional location keyword"],
      "image_extra": "short visual environment anchors for still-image generation, concise English, max 18 words",
      "video_extra": "short motion-safe environment anchors for video generation, concise English, max 16 words",
      "negative_prompt": "optional concise exclusions, max 12 words"
    }
  ]
}

Rules:
- Prefer production-design anchors: architecture, materials, props, atmosphere, era cues.
- Do not repeat camera instructions, movement, dialogue, plot events, or art-style tags.
- Keep the output compact and globally reusable across many shots.
- If the setting is historical or ancient, include concise exclusions against modern intrusions when useful.
""".strip()


def _collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _trim_words(text: str, limit: int) -> str:
    words = _collapse_spaces(text).split()
    if len(words) <= limit:
        return _collapse_spaces(text).strip(" ,.;:!?，。；：！？、")
    return " ".join(words[:limit]).strip(" ,.;:!?，。；：！？、")


_PROVIDER_KEY_ATTRS = {
    "claude": "anthropic_api_key",
    "openai": "openai_api_key",
    "qwen": "qwen_api_key",
    "zhipu": "zhipu_api_key",
    "gemini": "gemini_api_key",
    "siliconflow": "siliconflow_api_key",
}


def _parse_json(content: str) -> dict[str, Any]:
    normalized = content.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", normalized, flags=re.IGNORECASE)
    if fenced:
        normalized = fenced.group(1)
    elif normalized.startswith("```"):
        normalized = re.sub(r"^```(?:json)?\s*", "", normalized, flags=re.IGNORECASE)
    return json.loads(normalized.strip())


def _prune_story_context_locks(now: float | None = None) -> None:
    current_time = monotonic() if now is None else now
    stale_story_ids = [
        story_id
        for story_id, entry in _story_context_locks.items()
        if not entry.lock.locked() and current_time - entry.last_used > _STORY_CONTEXT_LOCK_TTL_SECONDS
    ]
    for story_id in stale_story_ids:
        _story_context_locks.pop(story_id, None)

    if len(_story_context_locks) <= _STORY_CONTEXT_LOCK_MAXSIZE:
        return

    removable_entries = sorted(
        (
            (entry.last_used, story_id)
            for story_id, entry in _story_context_locks.items()
            if not entry.lock.locked()
        ),
        key=lambda item: item[0],
    )
    while len(_story_context_locks) > _STORY_CONTEXT_LOCK_MAXSIZE and removable_entries:
        _, story_id = removable_entries.pop(0)
        _story_context_locks.pop(story_id, None)


def _get_story_context_lock(story_id: str) -> asyncio.Lock:
    now = monotonic()
    _prune_story_context_locks(now)
    entry = _story_context_locks.get(story_id)
    if entry is None:
        entry = _StoryContextLockEntry(lock=asyncio.Lock(), last_used=now)
        _story_context_locks[story_id] = entry
    else:
        entry.last_used = now
    return entry.lock


def _missing_appearance_cache_names(story: Mapping[str, Any]) -> set[str]:
    characters = list(story.get("characters") or [])
    meta = dict(story.get("meta") or {})
    cached = dict(meta.get("character_appearance_cache") or {})
    return {
        identifier
        for character in characters
        for identifier in [_collapse_spaces(str(character.get("id", ""))) or _collapse_spaces(str(character.get("name", "")))]
        if identifier and identifier not in cached
    }


def _needs_appearance_cache(story: Mapping[str, Any]) -> bool:
    return bool(_missing_appearance_cache_names(story))


def _needs_scene_style_cache(story: Mapping[str, Any]) -> bool:
    meta = dict(story.get("meta") or {})
    cached = meta.get("scene_style_cache") or []
    return bool(story.get("selected_setting")) and not cached


def _has_effective_llm_credentials(provider: str, api_key: str) -> bool:
    normalized_provider = (provider or "").strip().lower()
    if api_key:
        return True
    key_attr = _PROVIDER_KEY_ATTRS.get(normalized_provider)
    return bool(key_attr and getattr(settings, key_attr, ""))


def _normalize_appearance_entry(
    description: str,
    entry: Mapping[str, Any] | None,
) -> dict[str, str]:
    entry = entry or {}
    body = sanitize_body_features(str(entry.get("body", "")), fallback_description=description)
    clothing = sanitize_default_clothing(str(entry.get("clothing", "")), fallback_description=description)
    negative_prompt = _trim_words(str(entry.get("negative_prompt", "")), 12)
    normalized = {
        "body": _trim_words(body, 18),
        "clothing": _trim_words(clothing, 12),
        "negative_prompt": negative_prompt,
    }
    return {key: value for key, value in normalized.items() if value}


async def extract_character_appearance(
    story: Mapping[str, Any],
    *,
    provider: str,
    model: str = "",
    api_key: str = "",
    base_url: str = "",
) -> dict[str, dict[str, str]]:
    characters = list(story.get("characters") or [])
    if not characters:
        return {}

    llm = get_llm_provider(provider, model=model, api_key=api_key, base_url=base_url)
    character_payload = [
        {
            "id": character.get("id", ""),
            "name": character.get("name", ""),
            "role": character.get("role", ""),
            "description": character.get("description", ""),
        }
        for character in characters
        if character.get("name")
    ]
    raw, _ = await llm.complete_messages_with_usage(
        system=APPEARANCE_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    "Extract stable appearance anchors for these characters.\n"
                    f"{json.dumps(character_payload, ensure_ascii=False)}"
                ),
                "cacheable": True,
            }
        ],
        temperature=0.1,
        enable_caching=True,
    )
    data = _parse_json(raw)
    parsed = data.get("characters") or []
    output: dict[str, dict[str, str]] = {}
    if not isinstance(parsed, list):
        return output

    parsed_by_id: dict[str, Mapping[str, Any]] = {}
    for item in parsed:
        if not isinstance(item, Mapping):
            continue
        item_id = _collapse_spaces(str(item.get("id", "")))
        if item_id:
            parsed_by_id[item_id] = item

    for character in characters:
        char_id = _collapse_spaces(str(character.get("id", "")))
        if not char_id:
            continue
        entry = parsed_by_id.get(char_id) or {}
        if not isinstance(entry, Mapping):
            continue
        normalized_entry = _normalize_appearance_entry(str(character.get("description", "")), entry)
        if normalized_entry:
            output[char_id] = normalized_entry
    return {identifier: value for identifier, value in output.items() if any(value.values())}


async def extract_scene_style_cache(
    story: Mapping[str, Any],
    *,
    provider: str,
    model: str = "",
    api_key: str = "",
    base_url: str = "",
) -> list[dict[str, Any]]:
    world_summary = _collapse_spaces(str(story.get("selected_setting", "")))
    if not world_summary:
        return []

    llm = get_llm_provider(provider, model=model, api_key=api_key, base_url=base_url)
    raw, _ = await llm.complete_messages_with_usage(
        system=SCENE_STYLE_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    "Compress this story setting into reusable scene-style anchors.\n"
                    f"Genre: {story.get('genre', '')}\n"
                    f"World Summary: {world_summary}"
                ),
                "cacheable": True,
            }
        ],
        temperature=0.1,
        enable_caching=True,
    )
    data = _parse_json(raw)
    styles = data.get("styles") or []
    if not isinstance(styles, list):
        return []

    output: list[dict[str, Any]] = []
    for style in styles:
        if not isinstance(style, Mapping):
            continue
        keywords = style.get("keywords") or []
        if not isinstance(keywords, list):
            keywords = []
        image_extra = _trim_words(str(style.get("image_extra", "")), 18)
        video_extra = _trim_words(str(style.get("video_extra", "")), 16)
        negative_prompt = _trim_words(str(style.get("negative_prompt", "")), 12)
        if image_extra or video_extra or negative_prompt:
            output.append(
                {
                    "keywords": [_collapse_spaces(str(keyword)) for keyword in keywords if str(keyword).strip()],
                    "image_extra": image_extra,
                    "video_extra": video_extra,
                    "negative_prompt": negative_prompt,
                }
            )
    return output[:3]


async def _project_visual_dna(
    db: AsyncSession,
    story_id: str,
    story: Mapping[str, Any],
    appearance_cache: Mapping[str, Mapping[str, str]],
) -> None:
    existing_images = dict(story.get("character_images") or {})
    updates: dict[str, dict[str, Any]] = {}

    characters_by_id = {
        str(character.get("id", "")).strip(): character
        for character in (story.get("characters") or [])
        if str(character.get("id", "")).strip()
    }
    characters_by_name = {
        _collapse_spaces(str(character.get("name", ""))): character
        for character in (story.get("characters") or [])
        if _collapse_spaces(str(character.get("name", "")))
    }

    for identifier, appearance in appearance_cache.items():
        body = _collapse_spaces(str(appearance.get("body", "")))
        if not body:
            continue
        normalized_identifier = _collapse_spaces(str(identifier))
        character = characters_by_id.get(normalized_identifier) or characters_by_name.get(normalized_identifier) or {}
        char_id = _collapse_spaces(str(character.get("id", "")))
        character_name = _collapse_spaces(str(character.get("name", "")))
        lookup_id = char_id or normalized_identifier
        current = get_character_asset_entry(existing_images, lookup_id, name=character_name or normalized_identifier)
        has_existing_asset = any(
            _collapse_spaces(str(current.get(field, "")))
            for field in ("image_url", "image_path", "design_prompt", "prompt", "visual_dna")
        )
        if not has_existing_asset:
            continue
        if _collapse_spaces(str(current.get("visual_dna", ""))) == body:
            continue
        target_key = char_id or normalized_identifier
        updates[target_key] = build_character_asset_record(
            image_url=_collapse_spaces(str(current.get("image_url", ""))),
            image_path=_collapse_spaces(str(current.get("image_path", ""))),
            prompt=get_character_design_prompt(existing_images, lookup_id, name=character_name or normalized_identifier),
            existing=current,
            visual_dna=body,
            character_id=char_id,
            character_name=character_name,
        )

    if updates:
        await repo.upsert_character_images(db, story_id, updates)


async def prepare_story_context(
    db: AsyncSession,
    story_id: str | None,
    *,
    provider: str = "",
    model: str = "",
    api_key: str = "",
    base_url: str = "",
) -> tuple[dict[str, Any], StoryContext | None]:
    if not story_id:
        return {}, None

    story = await repo.get_story(db, story_id)
    if not story:
        return {}, None

    can_call_llm = bool(provider) and _has_effective_llm_credentials(provider, api_key)
    story_lock = _get_story_context_lock(story_id)

    if can_call_llm:
        async with story_lock:
            story = await repo.get_story(db, story_id)
            if _needs_appearance_cache(story):
                try:
                    appearance_cache = dict((story.get("meta") or {}).get("character_appearance_cache") or {})
                    missing_identifiers = _missing_appearance_cache_names(story)
                    extracted = await extract_character_appearance(
                        story,
                        provider=provider,
                        model=model,
                        api_key=api_key,
                        base_url=base_url,
                    )
                    extracted = {
                        identifier: value
                        for identifier, value in extracted.items()
                        if identifier in missing_identifiers and identifier not in appearance_cache
                    }
                    if extracted:
                        appearance_cache.update(extracted)
                        await repo.upsert_story_meta_cache(db, story_id, "character_appearance_cache", appearance_cache)
                        await _project_visual_dna(db, story_id, story, extracted)
                        story = await repo.get_story(db, story_id)
                except Exception:
                    _logger.exception("Failed to extract character appearance cache for story_id=%s", story_id)

            if _needs_scene_style_cache(story):
                try:
                    styles = await extract_scene_style_cache(
                        story,
                        provider=provider,
                        model=model,
                        api_key=api_key,
                        base_url=base_url,
                    )
                    if styles:
                        await repo.upsert_story_meta_cache(db, story_id, "scene_style_cache", styles)
                        story = await repo.get_story(db, story_id)
                except Exception:
                    _logger.exception("Failed to extract scene style cache for story_id=%s", story_id)

    return story, build_story_context(story)
