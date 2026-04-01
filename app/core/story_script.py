from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.core.story_assets import get_character_appearance_cache_entry, get_character_visual_dna


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _normalize_scene_selection(selected_scene_numbers: Mapping[Any, Any] | None) -> dict[int, set[int]]:
    normalized: dict[int, set[int]] = {}
    if not isinstance(selected_scene_numbers, Mapping):
        return normalized

    for episode_key, scene_numbers in selected_scene_numbers.items():
        try:
            episode = int(str(episode_key).strip())
        except (TypeError, ValueError):
            continue

        normalized_scene_numbers: set[int] = set()
        if isinstance(scene_numbers, Mapping):
            for scene_number, is_selected in scene_numbers.items():
                if not is_selected:
                    continue
                try:
                    normalized_scene_numbers.add(int(scene_number))
                except (TypeError, ValueError):
                    continue
        elif isinstance(scene_numbers, (list, tuple, set)):
            for scene_number in scene_numbers:
                try:
                    normalized_scene_numbers.add(int(scene_number))
                except (TypeError, ValueError):
                    continue
        else:
            continue

        if normalized_scene_numbers:
            normalized[episode] = normalized_scene_numbers

    return normalized


def _format_emotion_tags(emotion_tags: Any) -> str:
    if not isinstance(emotion_tags, list):
        return ""

    parts: list[str] = []
    for tag in emotion_tags:
        if not isinstance(tag, Mapping):
            continue
        target = _normalize_text(tag.get("target"))
        emotion = _normalize_text(tag.get("emotion"))
        intensity = tag.get("intensity")
        if target and emotion and intensity is not None:
            parts.append(f"{target}:{emotion} {intensity}")
        elif emotion and intensity is not None:
            parts.append(f"{emotion} {intensity}")
        elif emotion:
            parts.append(emotion)
    return "；".join(parts)


def _dedupe_lines(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        normalized = _normalize_text(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _build_scene_coverage_items(scene: Mapping[str, Any]) -> list[str]:
    coverage_items: list[str] = []

    visual = _normalize_text(scene.get("visual"))
    if visual:
        coverage_items.append(f"画面主线：{visual}")

    for action in scene.get("key_actions") or []:
        normalized = _normalize_text(action)
        if normalized:
            coverage_items.append(f"关键动作：{normalized}")

    for prop in scene.get("key_props") or []:
        normalized = _normalize_text(prop)
        if normalized:
            coverage_items.append(f"关键道具：{normalized}")

    for audio in scene.get("audio", []) or []:
        if not isinstance(audio, Mapping):
            continue
        character = _normalize_text(audio.get("character"))
        line = _normalize_text(audio.get("line"))
        if character and line:
            coverage_items.append(f"台词/旁白：{character}：{line}")

    transition = _normalize_text(scene.get("transition_from_previous"))
    if transition:
        coverage_items.append(f"衔接要求：{transition}")

    return _dedupe_lines(coverage_items)


def _serialize_scene_lines(scene: Mapping[str, Any]) -> list[str]:
    lines = [f"## 场景{scene['scene_number']}"]

    scene_heading = _normalize_text(scene.get("scene_heading"))
    if scene_heading:
        lines.append(f"【场景标题】{scene_heading}")

    environment_anchor = _normalize_text(scene.get("environment_anchor"))
    if environment_anchor:
        lines.append(f"【环境锚点】{environment_anchor}")

    lines.append(f"【环境】{_normalize_text(scene.get('environment'))}")

    lighting = _normalize_text(scene.get("lighting"))
    if lighting:
        lines.append(f"【光线】{lighting}")

    mood = _normalize_text(scene.get("mood"))
    if mood:
        lines.append(f"【氛围】{mood}")

    emotion_text = _format_emotion_tags(scene.get("emotion_tags"))
    if emotion_text:
        lines.append(f"【情感标尺】{emotion_text}")

    key_props = [
        _normalize_text(prop)
        for prop in (scene.get("key_props") or [])
        if _normalize_text(prop)
    ]
    if key_props:
        lines.append(f"【关键道具】{'；'.join(key_props)}")

    lines.append(f"【画面】{_normalize_text(scene.get('visual'))}")

    coverage_items = _build_scene_coverage_items(scene)
    if coverage_items:
        lines.append("【内容覆盖清单】")
        lines.extend(f"- {item}" for item in coverage_items)

    key_actions = [
        _normalize_text(action)
        for action in (scene.get("key_actions") or [])
        if _normalize_text(action)
    ]
    if key_actions:
        lines.append("【动作拆解】")
        lines.extend(f"- {action}" for action in key_actions)

    shot_suggestions = [
        _normalize_text(suggestion)
        for suggestion in (scene.get("shot_suggestions") or [])
        if _normalize_text(suggestion)
    ]
    if shot_suggestions:
        lines.append("【镜头建议】")
        lines.extend(f"- {suggestion}" for suggestion in shot_suggestions)

    transition = _normalize_text(scene.get("transition_from_previous"))
    if transition:
        lines.append(f"【过渡】{transition}")

    for audio in scene.get("audio", []) or []:
        if not isinstance(audio, Mapping):
            continue
        character = _normalize_text(audio.get("character"))
        line = _normalize_text(audio.get("line"))
        if character and line:
            lines.append(f"【{character}】{line}")

    return lines


def _safe_build_character_reference_anchor(
    character_images: Mapping[str, Any],
    name: str,
    *,
    character_id: str,
    description: str,
    appearance_entry: Mapping[str, Any] | None = None,
) -> str:
    try:
        from app.core.story_context import build_character_reference_anchor
    except ModuleNotFoundError:
        return ""

    return build_character_reference_anchor(
        character_images,
        name,
        character_id=character_id,
        description=description,
        appearance_entry=appearance_entry,
    )


def serialize_story_to_script(
    story: Mapping[str, Any],
    *,
    selected_scene_numbers: Mapping[Any, Any] | None = None,
) -> str:
    scenes = story.get("scenes", []) or []
    selection = _normalize_scene_selection(selected_scene_numbers)
    selection_enabled = selected_scene_numbers is not None

    serialized_episode_blocks: list[list[str]] = []
    for episode in scenes:
        if not isinstance(episode, Mapping):
            continue

        raw_episode_number = episode.get("episode")
        episode_number = _normalize_int(raw_episode_number)
        episode_scene_lines: list[str] = []
        for scene in episode.get("scenes", []) or []:
            if not isinstance(scene, Mapping):
                continue

            if selection_enabled:
                if episode_number is None:
                    continue
                if episode_number not in selection:
                    continue
                scene_number = _normalize_int(scene.get("scene_number"))
                if scene_number is None or scene_number not in selection[episode_number]:
                    continue

            if not episode_scene_lines:
                episode_heading_number = episode_number if episode_number is not None else raw_episode_number
                episode_scene_lines.append(f"# 第{episode_heading_number}集 {_normalize_text(episode.get('title'))}")
            episode_scene_lines.append("")
            episode_scene_lines.extend(_serialize_scene_lines(scene))

        if episode_scene_lines:
            serialized_episode_blocks.append(episode_scene_lines)

    if not serialized_episode_blocks:
        return ""

    lines: list[str] = []
    characters = story.get("characters", []) or []
    character_images = story.get("character_images", {}) or {}
    meta = story.get("meta") if isinstance(story.get("meta"), Mapping) else {}
    appearance_cache = meta.get("character_appearance_cache") if isinstance(meta.get("character_appearance_cache"), Mapping) else {}
    if characters:
        lines.append("# 角色信息")
        for character in characters:
            if not isinstance(character, Mapping):
                continue
            char_id = _normalize_text(character.get("id"))
            name = _normalize_text(character.get("name"))
            role = _normalize_text(character.get("role"))
            description = _normalize_text(character.get("description"))
            lines.append(f"- {name}（{role}）：{description}")

            appearance_entry = get_character_appearance_cache_entry(
                appearance_cache,
                char_id,
                name=name,
            )
            visual_dna = get_character_visual_dna(character_images, char_id, name=name)
            reference_anchor = _safe_build_character_reference_anchor(
                character_images,
                name,
                character_id=char_id,
                description=description,
                appearance_entry=appearance_entry,
            )
            if reference_anchor:
                lines.append(f"  Visual DNA: {reference_anchor}")
            elif visual_dna:
                lines.append(f"  Visual DNA: {visual_dna}")
        lines.append("")

    for index, block in enumerate(serialized_episode_blocks):
        if index > 0 and lines and lines[-1] != "":
            lines.append("")
        lines.extend(block)

    return "\n".join(lines).strip()
