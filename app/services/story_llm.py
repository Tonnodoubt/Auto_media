import asyncio
import json as _json
import logging
from typing import Any, Callable, Optional

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from app.core.config import settings
from app.schemas.story import SceneScript
from app.services import story_repository as repo
from app.services.story_mock import (
    MOCK_WB_QUESTIONS,
    mock_analyze_idea, mock_generate_outline, mock_generate_script, mock_chat,
    mock_world_building_start, mock_world_building_turn,
)
from app.prompts.story import (
    ANALYZE_PROMPT, WB_SYSTEM_PROMPT, WB_USER_TEMPLATE,
    OUTLINE_BATCH_PROMPT, OUTLINE_BLUEPRINT_PROMPT, SCRIPT_PROMPT, REFINE_PROMPT,
    build_apply_chat_prompt, build_chat_messages,
)
from app.services.llm.telemetry import LLMCallTracker, estimate_request_chars, normalize_usage
from app.services.quality import run_quality_guarded_generation

MODEL_MAP = {
    "qwen": "qwen-plus",
    "openai": "gpt-4o-mini",
    "zhipu": "glm-4-flash",
    "gemini": "gemini-2.0-flash",
    "claude":      "claude-sonnet-4-6",
    "siliconflow": "deepseek-ai/DeepSeek-V3",
}


logger = logging.getLogger(__name__)
_outline_generation_locks: dict[str, asyncio.Lock] = {}


def _should_use_dev_mock(api_key: str, feature_name: str) -> bool:
    normalized_key = str(api_key or "").strip()
    if normalized_key:
        return False
    if settings.debug:
        return True
    raise HTTPException(
        status_code=400,
        detail=f"{feature_name} 需要可用的 LLM API Key，请在前端设置或后端 .env 中完成配置",
    )


def _append_world_building_option(target: list[str], value: Any) -> None:
    if value is None:
        return
    normalized = str(value).strip()
    if not normalized or normalized in target:
        return
    target.append(normalized)


def _coerce_world_building_options(raw_options: Any) -> list[str]:
    normalized: list[str] = []

    if isinstance(raw_options, str):
        _append_world_building_option(normalized, raw_options)
        return normalized

    if isinstance(raw_options, dict):
        for key in ("label", "text", "value", "name"):
            if key in raw_options:
                _append_world_building_option(normalized, raw_options.get(key))
                if normalized:
                    return normalized
        return normalized

    if isinstance(raw_options, (list, tuple)):
        for item in raw_options:
            if isinstance(item, dict):
                for key in ("label", "text", "value", "name"):
                    if key in item:
                        _append_world_building_option(normalized, item.get(key))
                        break
            else:
                _append_world_building_option(normalized, item)
    return normalized


def _format_outline_guidance_list(raw_items: Any, *, fallback: str) -> str:
    if not isinstance(raw_items, list):
        return fallback

    normalized_items = [str(item).strip() for item in raw_items if str(item or "").strip()]
    if not normalized_items:
        return fallback
    return "\n".join(f"- {item}" for item in normalized_items)


def _normalize_outline_text_list(raw_items: Any, *, fallback: Any = None) -> list[str] | None:
    fallback_items = None
    if isinstance(fallback, list):
        fallback_items = [str(item).strip() for item in fallback if str(item or "").strip()]

    if not isinstance(raw_items, list):
        return fallback_items

    normalized_items = [str(item).strip() for item in raw_items if str(item or "").strip()]
    if normalized_items:
        return normalized_items
    return fallback_items


def _normalize_episode_number(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _find_outline_episode(outline: list[dict], episode_number: Any) -> dict | None:
    normalized_episode = _normalize_episode_number(episode_number)
    if normalized_episode is None:
        return None

    for episode in outline:
        if _normalize_episode_number(episode.get("episode")) == normalized_episode:
            return episode
    return None


def _normalize_episode_outline_payload(payload: dict[str, Any], *, fallback_episode: dict | None = None) -> dict[str, Any]:
    normalized = dict(fallback_episode or {})

    episode_number = _normalize_episode_number(payload.get("episode"))
    if episode_number is None and fallback_episode is not None:
        episode_number = _normalize_episode_number(fallback_episode.get("episode"))
    if episode_number is not None:
        normalized["episode"] = episode_number

    title = str(payload.get("title") or "").strip()
    if title:
        normalized["title"] = title

    summary = str(payload.get("summary") or "").strip()
    if summary:
        normalized["summary"] = summary

    beats = _normalize_outline_text_list(
        payload.get("beats"),
        fallback=fallback_episode.get("beats") if isinstance(fallback_episode, dict) else None,
    )
    if beats is not None:
        normalized["beats"] = beats

    scene_list = _normalize_outline_text_list(
        payload.get("scene_list"),
        fallback=fallback_episode.get("scene_list") if isinstance(fallback_episode, dict) else None,
    )
    if scene_list is not None:
        normalized["scene_list"] = scene_list

    return normalized


def _resolve_apply_chat_current_item(story: dict[str, Any], change_type: str, current_item: dict[str, Any]) -> dict[str, Any]:
    if change_type == "character":
        characters = list(story.get("characters") or [])
        current_id = str(current_item.get("id", "")).strip()
        current_name = str(current_item.get("name", "")).strip()
        for character in characters:
            if current_id and str(character.get("id", "")).strip() == current_id:
                return dict(character)
            if not current_id and current_name and str(character.get("name", "")).strip() == current_name:
                return dict(character)
        return dict(current_item or {})

    outline = list(story.get("outline") or [])
    authoritative_episode = _find_outline_episode(outline, current_item.get("episode"))
    if authoritative_episode:
        return dict(authoritative_episode)
    return dict(current_item or {})


def _fallback_world_building_options(question: dict) -> list[str]:
    question_text = str(question.get("text") or "").strip()
    question_dimension = str(question.get("dimension") or "").strip()
    for candidate in MOCK_WB_QUESTIONS:
        if question_dimension and str(candidate.get("dimension") or "").strip() == question_dimension:
            return list(candidate.get("options") or [])
        if question_text and str(candidate.get("text") or "").strip() == question_text:
            return list(candidate.get("options") or [])
    return []


def _ensure_world_building_question_options(question: Any):
    if not isinstance(question, dict):
        return question
    if question.get("type") != "options":
        return question

    options = _coerce_world_building_options(question.get("options"))
    for fallback in _fallback_world_building_options(question):
        if len(options) >= 3:
            break
        _append_world_building_option(options, fallback)

    if options == question.get("options"):
        return question
    return {**question, "options": options[:3]}


def _normalize_world_building_question(question: Any) -> dict[str, Any] | None:
    normalized_question = _ensure_world_building_question_options(question)
    if not isinstance(normalized_question, dict):
        return None

    question_type = str(normalized_question.get("type") or "options").strip() or "options"
    question_text = str(normalized_question.get("text") or "").strip()
    dimension = str(normalized_question.get("dimension") or "").strip()
    options = _coerce_world_building_options(normalized_question.get("options"))

    if not question_text:
        return None

    payload: dict[str, Any] = {
        "type": question_type,
        "text": question_text,
    }
    if options:
        payload["options"] = options[:3]
    if dimension:
        payload["dimension"] = dimension
    return payload


def _world_building_history_question_entry(question: dict[str, Any]) -> dict[str, Any]:
    entry = {
        "role": "ai",
        "text": question.get("text", ""),
        "type": question.get("type", "options"),
    }
    if question.get("options"):
        entry["options"] = list(question.get("options") or [])
    if question.get("dimension"):
        entry["dimension"] = question.get("dimension")
    return entry


def _normalize_frontend_world_building_history(raw_history: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_history, list):
        return []

    normalized_history: list[dict[str, Any]] = []
    for entry in raw_history:
        if not isinstance(entry, dict):
            continue
        role = str(entry.get("role") or "").strip()
        if role == "user":
            text = str(entry.get("text") or entry.get("content") or "").strip()
            # Legacy wb_history stored the initial seed prompt as a raw user message; the UI does not need it.
            if text and not text.startswith("种子想法："):
                normalized_history.append({"role": "user", "text": text})
            continue

        if role in {"ai", "assistant"}:
            question = _normalize_world_building_question(
                {
                    "type": entry.get("type"),
                    "text": entry.get("text"),
                    "options": entry.get("options"),
                    "dimension": entry.get("dimension"),
                }
            )
            if question is None:
                content = str(entry.get("content") or "").strip()
                if not content:
                    continue
                try:
                    parsed = _parse_json(content)
                except Exception:
                    continue
                question = _normalize_world_building_question(parsed.get("question"))
            if question is not None:
                normalized_history.append(_world_building_history_question_entry(question))

    return normalized_history


def _normalize_world_building_answered_items(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    answered_items: list[dict[str, str]] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        question = str(entry.get("question") or "").strip()
        answer = str(entry.get("answer") or "").strip()
        dimension = str(entry.get("dimension") or "").strip()
        if not question or not answer:
            continue
        answered_item = {
            "question": question,
            "answer": answer,
        }
        if dimension:
            answered_item["dimension"] = dimension
        answered_items.append(answered_item)
    return answered_items


def _build_world_building_state_from_history(
    *,
    idea: str,
    frontend_history: list[dict[str, Any]],
) -> dict[str, Any]:
    answered: list[dict[str, str]] = []
    pending_question: dict[str, Any] | None = None

    for entry in frontend_history:
        role = str(entry.get("role") or "").strip()
        if role == "ai":
            pending_question = _normalize_world_building_question(entry)
            continue

        if role == "user" and pending_question is not None:
            answer = str(entry.get("text") or "").strip()
            if answer:
                answered_item = {
                    "question": pending_question.get("text", ""),
                    "answer": answer,
                }
                dimension = str(pending_question.get("dimension") or "").strip()
                if dimension:
                    answered_item["dimension"] = dimension
                answered.append(answered_item)
            pending_question = None

    return {
        "idea": str(idea or "").strip(),
        "answered": answered,
        "current_question": pending_question,
    }


def _load_world_building_state(story: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    idea = str(story.get("idea") or "").strip()
    frontend_history = _normalize_frontend_world_building_history(story.get("wb_history"))
    derived_state = _build_world_building_state_from_history(idea=idea, frontend_history=frontend_history)

    meta = story.get("meta") or {}
    raw_state = meta.get("wb_state") if isinstance(meta, dict) else None
    if not isinstance(raw_state, dict):
        return frontend_history, derived_state

    current_question = _normalize_world_building_question(raw_state.get("current_question"))
    answered = _normalize_world_building_answered_items(raw_state.get("answered"))
    state = {
        "idea": str(raw_state.get("idea") or idea).strip(),
        "answered": answered or derived_state.get("answered", []),
        "current_question": current_question if current_question is not None else derived_state.get("current_question"),
    }
    return frontend_history, state


def _build_world_building_turn_messages(
    *,
    state: dict[str, Any],
    answer: str,
    turn: int,
) -> list[dict[str, str]]:
    current_question = _normalize_world_building_question(state.get("current_question"))
    if current_question is None:
        raise ValueError("当前缺少待回答的世界观问题")

    answered_items = _normalize_world_building_answered_items(state.get("answered"))
    answered_lines = []
    for item in answered_items:
        dimension = str(item.get("dimension") or "").strip()
        question = item.get("question", "")
        answer_text = item.get("answer", "")
        if dimension:
            answered_lines.append(f"- {dimension}：{answer_text}")
        else:
            answered_lines.append(f"- {question}：{answer_text}")
    answered_block = "\n".join(answered_lines) if answered_lines else "无，当前为第 1 轮。"

    option_lines = "\n".join(f"- {option}" for option in list(current_question.get("options") or [])) or "- 无选项信息"
    dimension = str(current_question.get("dimension") or "").strip() or "未指定维度"
    prompt = (
        f"种子想法：{state.get('idea', '')}\n"
        f"已确认设定：\n{answered_block}\n\n"
        f"当前问题（第 {turn} / 6 轮）：\n"
        f"- 维度：{dimension}\n"
        f"- 问题：{current_question.get('text', '')}\n"
        f"- 可选项：\n{option_lines}\n\n"
        f"用户本轮回答：{str(answer or '').strip()}\n\n"
        "请结合以上已确认设定继续推进世界观构建：\n"
        "1. 如果尚未问满 6 轮，返回 status=questioning，并给出下一题\n"
        "2. 如果已经问满 6 轮，返回 status=complete，并给出完整 world_summary\n"
        "3. 只返回 JSON，不要其他内容。"
    )
    return [
        {"role": "system", "content": WB_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]


def _merge_characters(existing_characters: list[dict], incoming_characters: list[dict]) -> list[dict]:
    for character in incoming_characters:
        char_id = str(character.get("id", "")).strip()
        if char_id:
            continue
        logger.warning("Refine returned character without id: %s", character)
        raise ValueError("Refine returned character without a valid id")

    incoming_by_id = {
        str(character.get("id", "")).strip(): character
        for character in incoming_characters
        if str(character.get("id", "")).strip()
    }

    merged: list[dict] = []
    used_ids: set[str] = set()
    for character in existing_characters:
        char_id = str(character.get("id", "")).strip()
        incoming = incoming_by_id.get(char_id)
        if incoming:
            merged.append({**character, **incoming})
            used_ids.add(char_id)
        else:
            merged.append(character)

    for character in incoming_characters:
        char_id = str(character.get("id", "")).strip()
        if not char_id or char_id in used_ids:
            continue
        merged.append(character)
    return merged


def _merge_outline(existing_outline: list[dict], incoming_outline: list[dict]) -> list[dict]:
    incoming_by_episode = {
        episode.get("episode"): episode
        for episode in incoming_outline
        if episode.get("episode") is not None
    }
    merged: list[dict] = []
    used_episodes: set[int] = set()
    for episode in existing_outline:
        ep_num = episode.get("episode")
        incoming = incoming_by_episode.get(ep_num)
        if incoming:
            merged.append({**episode, **incoming})
            used_episodes.add(ep_num)
        else:
            merged.append(episode)

    for episode in incoming_outline:
        ep_num = episode.get("episode")
        if ep_num in used_episodes:
            continue
        merged.append(episode)
    return merged


def _preserve_character_identity_fields(existing_characters: list[dict], incoming_characters: list[dict]) -> list[dict]:
    existing_by_id = {
        str(character.get("id", "")).strip(): character
        for character in existing_characters
        if str(character.get("id", "")).strip()
    }

    sanitized: list[dict] = []
    for character in incoming_characters:
        char_id = str(character.get("id", "")).strip()
        existing = existing_by_id.get(char_id)
        if existing:
            sanitized.append(
                {
                    **character,
                    "name": existing.get("name", character.get("name", "")),
                    "role": existing.get("role", character.get("role", "")),
                }
            )
            continue
        sanitized.append(character)
    return sanitized


def _extract_apply_chat_ai_signal(change_type: str, text: str) -> str:
    normalized_lines = [str(line).strip() for line in str(text or "").replace("\r", "").split("\n") if str(line).strip()]
    if not normalized_lines:
        return ""

    prefixes = {
        "character": ("当前角色修改：",),
        "episode": ("当前剧情修改：",),
    }.get(change_type, ())

    for line in normalized_lines:
        if any(line.startswith(prefix) for prefix in prefixes):
            return line
    return normalized_lines[0]


def _build_apply_chat_history_text(change_type: str, chat_history: list) -> str:
    history_lines: list[str] = []
    for message in chat_history:
        if isinstance(message, dict):
            role = message.get("role", "")
            text = message.get("text", "")
        else:
            role = getattr(message, "role", "")
            text = getattr(message, "text", "")
        normalized_text = str(text or "").strip()
        if not normalized_text:
            continue
        if role == "user":
            history_lines.append(f"用户: {normalized_text}")
            continue
        ai_signal = _extract_apply_chat_ai_signal(change_type, normalized_text)
        if ai_signal:
            history_lines.append(f"AI: {ai_signal}")
    return "\n".join(history_lines)


def _make_client(api_key: str, base_url: str) -> AsyncOpenAI:
    return AsyncOpenAI(api_key=api_key, base_url=base_url or None)


def _get_model(provider: str, model: str = "") -> str:
    return model or MODEL_MAP.get(provider, "qwen-plus")


def _telemetry_provider(provider: str) -> str:
    normalized = str(provider or "").strip()
    return normalized or "openai-compatible"


def _build_llm_tracker(
    *,
    operation: str,
    provider: str,
    model: str,
    messages: list[dict[str, Any]],
    story_id: str = "",
    extra: Optional[dict[str, Any]] = None,
) -> LLMCallTracker:
    context: dict[str, Any] = {"operation": operation}
    if story_id:
        context["story_id"] = story_id
    if extra:
        for key, value in extra.items():
            if value is None:
                continue
            normalized = str(value).strip() if isinstance(value, str) else value
            if normalized == "":
                continue
            context[key] = normalized
    return LLMCallTracker(
        provider=_telemetry_provider(provider),
        model=model,
        request_chars=estimate_request_chars(messages=messages),
        context=context,
    )


def _usage_dict(usage: Any) -> dict[str, int] | None:
    if usage is None:
        return None
    normalized = normalize_usage(usage)
    return {
        "prompt_tokens": normalized.get("prompt_tokens", 0),
        "completion_tokens": normalized.get("completion_tokens", 0),
    }


EXPECTED_OUTLINE_EPISODES = (1, 2, 3, 4, 5, 6)


def _get_outline_generation_lock(story_id: str) -> asyncio.Lock:
    lock = _outline_generation_locks.get(story_id)
    if lock is None:
        lock = asyncio.Lock()
        _outline_generation_locks[story_id] = lock
    return lock


def _normalize_text_list(value: Any, *, field_name: str, required: bool = False) -> list[str]:
    if value is None:
        if required:
            raise ValueError(f"{field_name} 必须存在且为数组")
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} 必须为数组")

    normalized_items = [str(item or "").strip() for item in value if str(item or "").strip()]
    if required and not normalized_items:
        raise ValueError(f"{field_name} 不能为空")
    return normalized_items


def _normalize_dict_list(value: Any, *, field_name: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} 必须为数组")

    normalized_items: list[dict[str, Any]] = []
    for entry in value:
        if not isinstance(entry, dict):
            raise ValueError(f"{field_name} 中的每一项都必须是对象")
        normalized_items.append(dict(entry))
    return normalized_items


def _normalize_required_outline_text(value: Any, *, field_name: str, episode_number: int) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"第 {episode_number} 集缺少有效的 {field_name}")
    return normalized


def _normalize_required_outline_text_list(value: Any, *, field_name: str, episode_number: int) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"第 {episode_number} 集缺少有效的 {field_name}")

    normalized_items: list[str] = []
    for item in value:
        normalized = str(item or "").strip()
        if not normalized:
            raise ValueError(f"第 {episode_number} 集的 {field_name} 包含空条目")
        normalized_items.append(normalized)
    return normalized_items


def _validate_generated_outline_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("返回结果必须是 JSON 对象")

    meta = payload.get("meta")
    if not isinstance(meta, dict):
        raise ValueError("meta 必须存在且为对象")

    if _normalize_episode_number(meta.get("episodes")) != len(EXPECTED_OUTLINE_EPISODES):
        raise ValueError("meta.episodes 必须等于 6")

    outline = payload.get("outline")
    if not isinstance(outline, list):
        raise ValueError("outline 必须存在且为数组")
    if len(outline) != len(EXPECTED_OUTLINE_EPISODES):
        raise ValueError("outline 必须完整包含 6 集")

    normalized_outline: list[dict[str, Any]] = []
    returned_episodes: list[int] = []
    for entry in outline:
        if not isinstance(entry, dict):
            raise ValueError("outline 中的每一项都必须是对象")

        episode_number = _normalize_episode_number(entry.get("episode"))
        if episode_number is None:
            raise ValueError("outline 中存在缺少 episode 的条目")

        normalized_entry = {
            **entry,
            "episode": episode_number,
            "title": _normalize_required_outline_text(
                entry.get("title"),
                field_name="title",
                episode_number=episode_number,
            ),
            "summary": _normalize_required_outline_text(
                entry.get("summary"),
                field_name="summary",
                episode_number=episode_number,
            ),
            "beats": _normalize_required_outline_text_list(
                entry.get("beats"),
                field_name="beats",
                episode_number=episode_number,
            ),
            "scene_list": _normalize_required_outline_text_list(
                entry.get("scene_list"),
                field_name="scene_list",
                episode_number=episode_number,
            ),
        }
        normalized_outline.append(normalized_entry)
        returned_episodes.append(episode_number)

    expected_episodes = list(EXPECTED_OUTLINE_EPISODES)
    if returned_episodes != expected_episodes:
        raise ValueError("outline.episode 必须按 1, 2, 3, 4, 5, 6 连续返回")

    return {
        **payload,
        "meta": {**meta, "episodes": len(EXPECTED_OUTLINE_EPISODES)},
        "outline": normalized_outline,
    }


def _validate_outline_blueprint_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("blueprint 返回结果必须是 JSON 对象")

    meta = payload.get("meta")
    if not isinstance(meta, dict):
        raise ValueError("blueprint.meta 必须存在且为对象")

    if _normalize_episode_number(meta.get("episodes")) != len(EXPECTED_OUTLINE_EPISODES):
        raise ValueError("blueprint.meta.episodes 必须等于 6")

    season_plan = payload.get("season_plan")
    if not isinstance(season_plan, dict):
        raise ValueError("blueprint.season_plan 必须存在且为对象")

    episode_arcs = season_plan.get("episode_arcs")
    if not isinstance(episode_arcs, list):
        raise ValueError("blueprint.season_plan.episode_arcs 必须存在且为数组")
    if len(episode_arcs) != len(EXPECTED_OUTLINE_EPISODES):
        raise ValueError("blueprint.season_plan.episode_arcs 必须完整包含 6 集")

    normalized_episode_arcs: list[dict[str, Any]] = []
    returned_episodes: list[int] = []
    for entry in episode_arcs:
        if not isinstance(entry, dict):
            raise ValueError("blueprint.season_plan.episode_arcs 中的每一项都必须是对象")
        episode_number = _normalize_episode_number(entry.get("episode"))
        if episode_number is None:
            raise ValueError("blueprint.season_plan.episode_arcs 中存在缺少 episode 的条目")
        arc = str(entry.get("arc") or "").strip()
        if not arc:
            raise ValueError(f"blueprint 第 {episode_number} 集缺少有效的 arc")
        normalized_episode_arcs.append({
            **entry,
            "episode": episode_number,
            "arc": arc,
        })
        returned_episodes.append(episode_number)

    if returned_episodes != list(EXPECTED_OUTLINE_EPISODES):
        raise ValueError("blueprint.season_plan.episode_arcs 必须按 1, 2, 3, 4, 5, 6 连续返回")

    return {
        **payload,
        "meta": {**meta, "episodes": len(EXPECTED_OUTLINE_EPISODES)},
        "characters": _normalize_dict_list(payload.get("characters"), field_name="blueprint.characters"),
        "relationships": _normalize_dict_list(payload.get("relationships"), field_name="blueprint.relationships"),
        "season_plan": {
            **season_plan,
            "episode_arcs": normalized_episode_arcs,
            "location_glossary": _normalize_text_list(
                season_plan.get("location_glossary"),
                field_name="blueprint.season_plan.location_glossary",
            ),
            "tone_rules": _normalize_text_list(
                season_plan.get("tone_rules"),
                field_name="blueprint.season_plan.tone_rules",
            ),
        },
    }


def _validate_outline_batch_payload(payload: Any, *, expected_episodes: list[int]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("outline batch 返回结果必须是 JSON 对象")

    outline = payload.get("outline")
    if not isinstance(outline, list):
        raise ValueError("outline batch.outline 必须存在且为数组")
    if len(outline) != len(expected_episodes):
        raise ValueError("outline batch.outline 的集数与预期不一致")

    normalized_outline: list[dict[str, Any]] = []
    returned_episodes: list[int] = []
    for entry in outline:
        if not isinstance(entry, dict):
            raise ValueError("outline batch.outline 中的每一项都必须是对象")

        episode_number = _normalize_episode_number(entry.get("episode"))
        if episode_number is None:
            raise ValueError("outline batch.outline 中存在缺少 episode 的条目")
        if episode_number not in expected_episodes:
            raise ValueError(f"outline batch 返回了未请求的 episode={episode_number}")

        normalized_outline.append(
            {
                **entry,
                "episode": episode_number,
                "title": _normalize_required_outline_text(
                    entry.get("title"),
                    field_name="title",
                    episode_number=episode_number,
                ),
                "summary": _normalize_required_outline_text(
                    entry.get("summary"),
                    field_name="summary",
                    episode_number=episode_number,
                ),
                "beats": _normalize_required_outline_text_list(
                    entry.get("beats"),
                    field_name="beats",
                    episode_number=episode_number,
                ),
                "scene_list": _normalize_required_outline_text_list(
                    entry.get("scene_list"),
                    field_name="scene_list",
                    episode_number=episode_number,
                ),
            }
        )
        returned_episodes.append(episode_number)

    if returned_episodes != expected_episodes:
        raise ValueError("outline batch.episode 必须与请求的集数完全一致且顺序一致")

    return {
        "outline": normalized_outline,
    }


def _build_outline_batch_ranges(concurrency: int) -> list[list[int]]:
    episodes = list(EXPECTED_OUTLINE_EPISODES)
    if concurrency <= 1:
        return [episodes]
    if concurrency == 2:
        return [episodes[:3], episodes[3:]]
    return [episodes[:2], episodes[2:4], episodes[4:]]


def _merge_usage_totals(usages: list[dict[str, int] | None]) -> dict[str, int] | None:
    total = {"prompt_tokens": 0, "completion_tokens": 0}
    has_usage = False
    for usage in usages:
        if usage is None:
            continue
        has_usage = True
        total["prompt_tokens"] += usage.get("prompt_tokens", 0)
        total["completion_tokens"] += usage.get("completion_tokens", 0)
    return total if has_usage else None


async def _request_outline_json_completion(
    *,
    client: AsyncOpenAI,
    resolved_model: str,
    provider: str,
    story_id: str,
    prompt: str,
    operation: str,
    validator: Callable[[Any], dict[str, Any]],
    extra: Optional[dict[str, Any]] = None,
) -> tuple[dict[str, Any], dict[str, int] | None]:
    messages = [{"role": "user", "content": prompt}]
    tracker = _build_llm_tracker(
        operation=operation,
        provider=provider,
        model=resolved_model,
        messages=messages,
        story_id=story_id,
        extra=extra,
    )

    try:
        resp = await client.chat.completions.create(
            model=resolved_model,
            messages=messages,
        )
    except Exception as exc:
        tracker.record_failure(exc)
        raise

    response_text = resp.choices[0].message.content or ""
    usage = getattr(resp, "usage", None)
    try:
        data = _parse_json(response_text)
        validated = validator(data)
    except Exception as exc:
        tracker.record_failure(exc, usage=usage, response_text=response_text)
        raise

    tracker.record_success(usage=usage, response_text=response_text)
    return validated, _usage_dict(usage)


async def _generate_outline_blueprint(
    *,
    client: AsyncOpenAI,
    selected_setting: str,
    resolved_model: str,
    provider: str,
    story_id: str,
    prompt_suffix: str = "",
) -> tuple[dict[str, Any], dict[str, int] | None]:
    prompt = OUTLINE_BLUEPRINT_PROMPT.format(selected_setting=selected_setting)
    if str(prompt_suffix or "").strip():
        prompt = f"{prompt}\n\n{prompt_suffix.strip()}"
    return await _request_outline_json_completion(
        client=client,
        resolved_model=resolved_model,
        provider=provider,
        story_id=story_id,
        prompt=prompt,
        operation="story.generate_outline.blueprint",
        validator=_validate_outline_blueprint_payload,
    )


async def _generate_outline_batch(
    *,
    client: AsyncOpenAI,
    blueprint: dict[str, Any],
    target_episodes: list[int],
    resolved_model: str,
    provider: str,
    story_id: str,
    prompt_suffix: str = "",
) -> tuple[dict[str, Any], dict[str, int] | None]:
    prompt = OUTLINE_BATCH_PROMPT.format(
        blueprint_json=_json.dumps(blueprint, ensure_ascii=False),
        target_episodes=", ".join(str(episode) for episode in target_episodes),
    )
    if str(prompt_suffix or "").strip():
        prompt = f"{prompt}\n\n{prompt_suffix.strip()}"
    return await _request_outline_json_completion(
        client=client,
        resolved_model=resolved_model,
        provider=provider,
        story_id=story_id,
        prompt=prompt,
        operation="story.generate_outline.batch",
        validator=lambda payload: _validate_outline_batch_payload(payload, expected_episodes=target_episodes),
        extra={"episode_range": f"{target_episodes[0]}-{target_episodes[-1]}"},
    )


def _parse_json(content: str):
    import json as _json
    content = content.strip()
    if content.startswith("```"):
        parts = content.split("```")
        content = parts[1] if len(parts) > 1 else parts[0]
        if content.startswith("json"):
            content = content[4:]
    return _json.loads(content.strip())


async def refine(story_id: str, change_type: str, change_summary: str, db: AsyncSession, api_key: str = "", base_url: str = "", provider: str = "", model: str = "") -> dict:
    import json as _json
    story = await repo.get_story(db, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="故事不存在")
    if _should_use_dev_mock(api_key, "故事细化"):
        return {"characters": None, "relationships": None, "outline": None, "meta_theme": None}

    client = _make_client(api_key, base_url)
    story_data = {k: v for k, v in story.items() if k not in ('created_at', 'updated_at')}
    prompt = REFINE_PROMPT.format(
        story_json=_json.dumps(story_data, ensure_ascii=False),
        change_type=change_type,
        change_summary=change_summary,
    )
    resolved_model = _get_model(provider, model)
    messages = [{"role": "user", "content": prompt}]
    tracker = _build_llm_tracker(
        operation="story.refine",
        provider=provider,
        model=resolved_model,
        messages=messages,
        story_id=story_id,
        extra={"change_type": change_type},
    )
    try:
        resp = await client.chat.completions.create(
            model=resolved_model,
            messages=messages,
        )
    except Exception as exc:
        tracker.record_failure(exc)
        raise
    response_text = resp.choices[0].message.content
    usage = getattr(resp, "usage", None)
    try:
        data = _parse_json(response_text)
    except Exception as exc:
        tracker.record_failure(exc, usage=usage, response_text=response_text)
        return {"characters": None, "relationships": None, "outline": None, "meta_theme": None}

    # 写回数据库，保持 DB 与前端状态同步
    updates = {}
    try:
        if data.get("characters") is not None:
            sanitized_characters = _preserve_character_identity_fields(
                list(story.get("characters") or []),
                list(data["characters"] or []),
            )
            updates["characters"] = _merge_characters(list(story.get("characters") or []), sanitized_characters)
    except ValueError as exc:
        tracker.record_failure(exc, usage=usage, response_text=response_text)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    try:
        if data.get("relationships") is not None:
            updates["relationships"] = data["relationships"]
        if data.get("outline") is not None:
            existing_outline = list(story.get("outline") or [])
            normalized_outline = [
                _normalize_episode_outline_payload(
                    episode,
                    fallback_episode=_find_outline_episode(existing_outline, episode.get("episode")) if isinstance(episode, dict) else None,
                )
                for episode in list(data["outline"] or [])
                if isinstance(episode, dict)
            ]
            updates["outline"] = _merge_outline(existing_outline, normalized_outline)
        if data.get("meta_theme") is not None:
            existing_meta = story.get("meta") or {}
            updates["meta"] = {**existing_meta, "theme": data["meta_theme"]}
        latest_story = story
        if updates:
            if "characters" in updates or "outline" in updates:
                updates["scenes"] = []
            await repo.save_story(db, story_id, updates)
            invalidate_appearance = "characters" in updates
            invalidate_scene_style = "outline" in updates
            if invalidate_appearance or invalidate_scene_style:
                await repo.invalidate_story_consistency_cache(
                    db,
                    story_id,
                    appearance=invalidate_appearance,
                    scene_style=invalidate_scene_style,
                )
            latest_story = await repo.get_story(db, story_id)
    except Exception as exc:
        tracker.record_failure(exc, usage=usage, response_text=response_text)
        raise

    tracker.record_success(usage=usage, response_text=response_text)

    return {
        "characters": latest_story.get("characters") if data.get("characters") is not None else None,
        "relationships": latest_story.get("relationships") if data.get("relationships") is not None else None,
        "outline": latest_story.get("outline") if data.get("outline") is not None else None,
        "meta_theme": data.get("meta_theme"),
        "usage": _usage_dict(usage),
    }


async def analyze_idea(idea: str, genre: str, tone: str, db: AsyncSession, api_key: str = "", base_url: str = "", provider: str = "", model: str = "") -> dict:
    if _should_use_dev_mock(api_key, "灵感分析"):
        return await mock_analyze_idea(idea, genre, tone, db=db)

    import uuid
    client = _make_client(api_key, base_url)
    prompt = ANALYZE_PROMPT.format(idea=idea, genre=genre, tone=tone)
    resolved_model = _get_model(provider, model)
    messages = [{"role": "user", "content": prompt}]
    tracker = _build_llm_tracker(
        operation="story.analyze_idea",
        provider=provider,
        model=resolved_model,
        messages=messages,
    )
    try:
        resp = await client.chat.completions.create(
            model=resolved_model,
            messages=messages,
        )
    except Exception as exc:
        tracker.record_failure(exc)
        raise
    response_text = resp.choices[0].message.content
    story_id = str(uuid.uuid4())
    usage = getattr(resp, "usage", None)
    try:
        data = _parse_json(response_text)
        await repo.save_story(db, story_id, {"idea": idea, "genre": genre, "tone": tone})
    except Exception as exc:
        tracker.record_failure(exc, usage=usage, response_text=response_text)
        raise
    tracker.record_success(usage=usage, response_text=response_text)
    return {
        "story_id": story_id,
        "analysis": data.get("analysis", ""),
        "suggestions": data.get("suggestions", []),
        "placeholder": data.get("placeholder", ""),
        "usage": _usage_dict(usage),
    }


async def generate_outline(story_id: str, selected_setting: str, db: AsyncSession, api_key: str = "", base_url: str = "", provider: str = "", model: str = "") -> dict:
    if _should_use_dev_mock(api_key, "大纲生成"):
        return await mock_generate_outline(story_id, selected_setting, db=db)

    client = _make_client(api_key, base_url)
    resolved_model = _get_model(provider, model)
    lock = _get_outline_generation_lock(story_id)

    async with lock:
        try:
            existing_story = await repo.get_story(db, story_id) if hasattr(db, "execute") else {}

            async def _generate_outline_candidate(prompt_suffix: str, _attempt: int) -> tuple[dict[str, Any], dict[str, Any]]:
                usage_parts: list[dict[str, int] | None] = []
                blueprint, blueprint_usage = await _generate_outline_blueprint(
                    client=client,
                    selected_setting=selected_setting,
                    resolved_model=resolved_model,
                    provider=provider,
                    story_id=story_id,
                    prompt_suffix=prompt_suffix,
                )
                usage_parts.append(blueprint_usage)

                batch_ranges = _build_outline_batch_ranges(settings.outline_generation_concurrency)
                # 分批并发生成，既降低单次输出长度，也避免把 6 集完全拆散导致风格漂移。
                tasks = [
                    asyncio.create_task(
                        _generate_outline_batch(
                            client=client,
                            blueprint=blueprint,
                            target_episodes=target_episodes,
                            resolved_model=resolved_model,
                            provider=provider,
                            story_id=story_id,
                            prompt_suffix=prompt_suffix,
                        )
                    )
                    for target_episodes in batch_ranges
                ]
                try:
                    batch_results = await asyncio.gather(*tasks)
                except Exception:
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    raise

                outline_entries: list[dict[str, Any]] = []
                for batch_payload, batch_usage in batch_results:
                    usage_parts.append(batch_usage)
                    outline_entries.extend(batch_payload.get("outline", []))

                # 最终统一排序后再做整体验证，保证返回给前端的 outline 永远按 episode 升序。
                outline_entries.sort(key=lambda entry: entry.get("episode", 0))
                validated_data = _validate_generated_outline_payload(
                    {
                        "meta": blueprint.get("meta"),
                        "characters": blueprint.get("characters", []),
                        "relationships": blueprint.get("relationships", []),
                        "outline": outline_entries,
                    }
                )
                return validated_data, _merge_usage_totals(usage_parts)

            validated_data, outline_usage, quality_run = await run_quality_guarded_generation(
                family="story_outline",
                provider=provider,
                model=resolved_model,
                api_key=api_key,
                base_url=base_url,
                generate_candidate=_generate_outline_candidate,
                candidate_payload_builder=lambda candidate: {
                    "meta": candidate.get("meta"),
                    "characters": candidate.get("characters", []),
                    "relationships": candidate.get("relationships", []),
                    "outline": candidate.get("outline", []),
                },
                telemetry_context={"story_id": story_id},
            )

            generated_meta = dict(validated_data.get("meta") or {})
            existing_meta = dict(existing_story.get("meta") or {})
            quality_runs = dict(existing_meta.get("quality_runs") or {})
            quality_runs["story_outline"] = quality_run
            merged_meta = {
                **existing_meta,
                **generated_meta,
                "quality_runs": quality_runs,
            }

            await repo.save_story(db, story_id, {
                "selected_setting": selected_setting,
                "meta": merged_meta,
                "characters": validated_data.get("characters", []),
                "relationships": validated_data.get("relationships", []),
                "outline": validated_data.get("outline", []),
                "scenes": [],
            })
            await repo.invalidate_story_consistency_cache(db, story_id, appearance=True, scene_style=True)
            latest_story = await repo.get_story(db, story_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"大纲生成失败：模型返回的 outline 无效，{exc}",
            ) from exc

    return {
        "story_id": story_id,
        "meta": latest_story.get("meta"),
        "characters": latest_story.get("characters", []),
        "relationships": latest_story.get("relationships", []),
        "outline": latest_story.get("outline", []),
        "usage": outline_usage,
        "quality": quality_run,
    }


async def chat(
    story_id: str,
    message: str,
    db: AsyncSession,
    api_key: str = "",
    base_url: str = "",
    provider: str = "",
    model: str = "",
    mode: str = "generic",
    context: Optional[dict] = None,
):
    if _should_use_dev_mock(api_key, "对话生成"):
        async for chunk in mock_chat(story_id, message, db=db, mode=mode, context=context):
            yield chunk
        return

    client = _make_client(api_key, base_url)
    resolved_model = _get_model(provider, model)
    messages = build_chat_messages(mode, message, context)
    tracker = _build_llm_tracker(
        operation="story.chat",
        provider=provider,
        model=resolved_model,
        messages=messages,
        story_id=story_id,
        extra={"mode": mode},
    )
    try:
        stream = await client.chat.completions.create(
            model=resolved_model,
            messages=messages,
            stream=True,
        )
    except Exception as exc:
        tracker.record_failure(exc)
        raise

    chunks: list[str] = []
    try:
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                tracker.mark_first_token()
                chunks.append(delta)
                yield delta
    except Exception as exc:
        tracker.record_failure(exc, response_text="".join(chunks))
        raise
    tracker.record_success(response_text="".join(chunks))


async def generate_script(
    story_id: str,
    db: AsyncSession,
    api_key: str = "",
    base_url: str = "",
    provider: str = "",
    model: str = "",
    resume_from_episode: int | None = None,
):
    story = await repo.get_story(db, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="故事不存在")
    outline = story.get("outline", [])
    if not outline:
        raise HTTPException(status_code=400, detail="剧本生成失败：当前故事缺少大纲，请先完成世界观与大纲生成")
    if resume_from_episode is not None:
        outline = [
            episode
            for episode in outline
            if (_normalize_episode_number(episode.get("episode")) or 0) >= resume_from_episode
        ]
        if not outline:
            raise HTTPException(status_code=400, detail="续生成失败：指定的起始集数不在当前大纲范围内")
    if _should_use_dev_mock(api_key, "剧本生成"):
        async for scene in mock_generate_script(story_id):
            if resume_from_episode is not None:
                episode_number = _normalize_episode_number(scene.get("episode"))
                if episode_number is None or episode_number < resume_from_episode:
                    continue
            yield scene
        return
    characters = story.get("characters", [])
    characters_text = "\n".join(
        f"- {c['name']}（{c.get('role', '')}）：{c.get('description', '')}"
        for c in characters
    ) or "无角色信息"
    client = _make_client(api_key, base_url)

    total_prompt = 0
    total_completion = 0
    async def generate_episode_task(ep: dict[str, Any]) -> dict[str, Any]:
        prompt = SCRIPT_PROMPT.format(
            episode=ep["episode"],
            title=ep["title"],
            summary=ep["summary"],
            characters_text=characters_text,
            beats_text=_format_outline_guidance_list(
                ep.get("beats"),
                fallback="- 未提供额外节拍，请根据剧情概要自行拆出本集冲突递进。",
            ),
            scene_list_text=_format_outline_guidance_list(
                ep.get("scene_list"),
                fallback="- 未提供额外场景切分，请根据剧情概要自行划分 3-5 个稳定场景。",
            ),
        )
        resolved_model = _get_model(provider, model)
        messages = [{"role": "user", "content": prompt}]
        tracker = _build_llm_tracker(
            operation="story.generate_script_episode",
            provider=provider,
            model=resolved_model,
            messages=messages,
            story_id=story_id,
            extra={"episode": ep.get("episode")},
        )
        try:
            stream = await client.chat.completions.create(
                model=resolved_model,
                messages=messages,
                stream=True,
                stream_options={"include_usage": True},
            )
        except Exception as exc:
            tracker.record_failure(exc)
            resolved_base_url = base_url or "(default)"
            logger.exception(
                "Script generation request failed story_id=%s episode=%s provider=%s model=%s base_url=%s",
                story_id,
                ep.get("episode"),
                provider or "(default)",
                resolved_model,
                resolved_base_url,
            )
            raise RuntimeError(
                f"Script generation request failed (provider={provider or '(default)'}, "
                f"model={resolved_model}, base_url={resolved_base_url}, episode={ep.get('episode')}): {exc}"
            ) from exc

        chunks = []
        episode_prompt_tokens = 0
        episode_completion_tokens = 0
        try:
            async for chunk in stream:
                choices = getattr(chunk, "choices", None) or []
                if choices:
                    delta = getattr(choices[0].delta, "content", None)
                    if delta:
                        # First content delta is the best approximation of user-visible model latency.
                        tracker.mark_first_token()
                        chunks.append(delta)
                usage = getattr(chunk, "usage", None)
                if usage:
                    prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                    completion_tokens = getattr(usage, "completion_tokens", 0) or 0
                    episode_prompt_tokens += prompt_tokens
                    episode_completion_tokens += completion_tokens
        except Exception as exc:
            tracker.record_failure(
                exc,
                usage={
                    "prompt_tokens": episode_prompt_tokens,
                    "completion_tokens": episode_completion_tokens,
                },
                response_text="".join(chunks),
            )
            raise

        content = "".join(chunks)
        usage = {
            "prompt_tokens": episode_prompt_tokens,
            "completion_tokens": episode_completion_tokens,
        }
        try:
            parsed_episode = _parse_json(content)
            validated_episode = SceneScript.model_validate(parsed_episode)
            normalized_episode = validated_episode.model_dump()
            normalized_episode["episode"] = ep["episode"]
            normalized_episode["title"] = normalized_episode.get("title") or ep["title"]
            if not normalized_episode.get("scenes"):
                raise ValueError(f"第 {ep['episode']} 集未返回有效场景")
        except Exception as exc:
            tracker.record_failure(exc, usage=usage, response_text=content)
            raise RuntimeError(f"第 {ep['episode']} 集返回结构无效，请重试") from exc

        tracker.record_success(usage=usage, response_text=content)
        return {"scene": normalized_episode, "usage": usage}

    running_tasks: dict[int, asyncio.Task] = {}
    task_to_index: dict[asyncio.Task, int] = {}
    completed_results: dict[int, dict[str, Any]] = {}
    next_to_start = 0
    next_to_emit = 0
    concurrency = max(1, min(settings.script_generation_concurrency, len(outline)))

    def start_next_task() -> bool:
        nonlocal next_to_start
        if next_to_start >= len(outline):
            return False
        task = asyncio.create_task(generate_episode_task(outline[next_to_start]))
        running_tasks[next_to_start] = task
        task_to_index[task] = next_to_start
        next_to_start += 1
        return True

    try:
        while len(running_tasks) < concurrency and start_next_task():
            pass

        while next_to_emit < len(outline):
            while next_to_emit in completed_results:
                result = completed_results.pop(next_to_emit)
                usage = result["usage"]
                total_prompt += usage["prompt_tokens"]
                total_completion += usage["completion_tokens"]
                yield result["scene"]
                next_to_emit += 1
                while len(running_tasks) < concurrency and start_next_task():
                    pass

            if next_to_emit >= len(outline):
                break

            done_tasks, _ = await asyncio.wait(
                running_tasks.values(),
                return_when=asyncio.FIRST_COMPLETED,
            )
            for done_task in done_tasks:
                completed_index = task_to_index.pop(done_task)
                running_tasks.pop(completed_index, None)
                completed_results[completed_index] = done_task.result()
            while len(running_tasks) < concurrency and start_next_task():
                pass
    finally:
        pending_tasks = [task for task in running_tasks.values() if not task.done()]
        for task in pending_tasks:
            task.cancel()
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)

    yield {"__usage__": {"prompt_tokens": total_prompt, "completion_tokens": total_completion}}


async def world_building_start(idea: str, db: AsyncSession, api_key: str = "", base_url: str = "", provider: str = "", model: str = "") -> dict:
    import uuid
    if _should_use_dev_mock(api_key, "世界观生成"):
        return await mock_world_building_start(idea, db=db)

    story_id = str(uuid.uuid4())
    client = _make_client(api_key, base_url)
    messages = [
        {"role": "system", "content": WB_SYSTEM_PROMPT},
        {"role": "user", "content": WB_USER_TEMPLATE.format(idea=idea)},
    ]
    resolved_model = _get_model(provider, model)
    tracker = _build_llm_tracker(
        operation="story.world_building_start",
        provider=provider,
        model=resolved_model,
        messages=messages,
        story_id=story_id,
    )
    try:
        resp = await client.chat.completions.create(
            model=resolved_model,
            messages=messages,
        )
    except Exception as exc:
        tracker.record_failure(exc)
        raise
    response_text = resp.choices[0].message.content
    usage = getattr(resp, "usage", None)
    try:
        data = _parse_json(response_text)
        messages.append({"role": "assistant", "content": response_text})
        await repo.save_story(db, story_id, {"idea": idea, "wb_history": messages, "wb_turn": 1})
    except Exception as exc:
        tracker.record_failure(exc, usage=usage, response_text=response_text)
        raise
    tracker.record_success(usage=usage, response_text=response_text)
    return {
        "story_id": story_id,
        "status": data.get("status", "questioning"),
        "turn": 1,
        "question": _ensure_world_building_question_options(data.get("question")),
        "world_summary": data.get("world_summary"),
        "usage": _usage_dict(usage),
    }


async def world_building_turn(story_id: str, answer: str, db: AsyncSession, api_key: str = "", base_url: str = "", provider: str = "", model: str = "") -> dict:
    if _should_use_dev_mock(api_key, "世界观追问"):
        return await mock_world_building_turn(story_id, answer, db=db)

    story = await repo.get_story(db, story_id)
    history = story.get("wb_history", [])
    turn = story.get("wb_turn", 1)

    history = history + [{"role": "user", "content": answer}]
    client = _make_client(api_key, base_url)
    resolved_model = _get_model(provider, model)
    tracker = _build_llm_tracker(
        operation="story.world_building_turn",
        provider=provider,
        model=resolved_model,
        messages=history,
        story_id=story_id,
        extra={"turn": turn},
    )
    try:
        resp = await client.chat.completions.create(
            model=resolved_model,
            messages=history,
        )
    except Exception as exc:
        tracker.record_failure(exc)
        raise
    response_text = resp.choices[0].message.content
    usage = getattr(resp, "usage", None)
    try:
        data = _parse_json(response_text)
        history = history + [{"role": "assistant", "content": response_text}]
        new_turn = turn + 1
        updates = {"wb_history": history, "wb_turn": new_turn}
        if data.get("status") == "complete":
            updates["selected_setting"] = data.get("world_summary", "")
        await repo.save_story(db, story_id, updates)
        if data.get("status") == "complete":
            await repo.invalidate_story_consistency_cache(db, story_id, scene_style=True)
    except Exception as exc:
        tracker.record_failure(exc, usage=usage, response_text=response_text)
        raise
    tracker.record_success(usage=usage, response_text=response_text)
    return {
        "story_id": story_id,
        "status": data.get("status", "questioning"),
        "turn": new_turn,
        "question": _ensure_world_building_question_options(data.get("question")),
        "world_summary": data.get("world_summary"),
        "usage": _usage_dict(usage),
    }

async def apply_chat(story_id: str, change_type: str, chat_history: list, current_item: dict,
                     db: AsyncSession, api_key: str = "", base_url: str = "", provider: str = "", model: str = "") -> dict:
    if not api_key:
        raise HTTPException(status_code=400, detail="apply_chat 需要提供 api_key")

    story = await repo.get_story(db, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="故事不存在")

    authoritative_item = _resolve_apply_chat_current_item(story, change_type, current_item)
    client = _make_client(api_key, base_url)
    history_text = _build_apply_chat_history_text(change_type, chat_history)
    prompt = build_apply_chat_prompt(change_type, authoritative_item, history_text)

    resolved_model = _get_model(provider, model)
    messages = [{"role": "user", "content": prompt}]
    tracker = _build_llm_tracker(
        operation="story.apply_chat",
        provider=provider,
        model=resolved_model,
        messages=messages,
        story_id=story_id,
        extra={"change_type": change_type},
    )
    try:
        resp = await client.chat.completions.create(
            model=resolved_model,
            messages=messages,
        )
    except Exception as exc:
        tracker.record_failure(exc)
        raise
    response_text = resp.choices[0].message.content
    usage = getattr(resp, "usage", None)
    try:
        data = _parse_json(response_text)
    except Exception as e:
        tracker.record_failure(e, usage=usage, response_text=response_text)
        logger.warning(
            "Apply chat response JSON parsing failed story_id=%s change_type=%s error_type=%s response_chars=%s",
            story_id,
            change_type,
            type(e).__name__,
            len(str(response_text or "")),
        )
        return {}

    try:
        if change_type == "character":
            characters = list(story.get("characters") or [])
            current_id = str(authoritative_item.get("id", "")).strip()
            updated_character = None
            for c in characters:
                if current_id and str(c.get("id", "")).strip() == current_id:
                    c["description"] = data.get("description", c.get("description", ""))
                    updated_character = dict(c)
                    break
                if not current_id and c.get("name") == authoritative_item.get("name"):
                    c["description"] = data.get("description", c.get("description", ""))
                    updated_character = dict(c)
                    break
            if characters:
                await repo.save_story(db, story_id, {"characters": characters, "scenes": []})
                await repo.invalidate_story_consistency_cache(db, story_id, appearance=True)
            if updated_character is not None:
                tracker.record_success(usage=usage, response_text=response_text)
                return {
                    "name": updated_character.get("name", authoritative_item.get("name", "")),
                    "role": updated_character.get("role", authoritative_item.get("role", "")),
                    "description": updated_character.get("description", authoritative_item.get("description", "")),
                }
        else:
            outline = list(story.get("outline") or [])
            current_episode_number = _normalize_episode_number(authoritative_item.get("episode"))
            updated_episode = None
            for ep in outline:
                if _normalize_episode_number(ep.get("episode")) == current_episode_number:
                    ep.update(_normalize_episode_outline_payload(data, fallback_episode=ep))
                    updated_episode = dict(ep)
                    break
            if outline:
                await repo.save_story(
                    db,
                    story_id,
                    {"outline": outline, "meta": dict(story.get("meta") or {}), "scenes": []},
                )
                await repo.invalidate_story_consistency_cache(db, story_id, scene_style=True)
            if updated_episode is not None:
                tracker.record_success(usage=usage, response_text=response_text)
                return updated_episode
    except Exception as exc:
        tracker.record_failure(exc, usage=usage, response_text=response_text)
        raise

    tracker.record_success(usage=usage, response_text=response_text)
    return data
