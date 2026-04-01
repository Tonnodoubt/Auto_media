import logging
from typing import Any, Optional

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from app.core.config import settings
from app.services import story_repository as repo
from app.services.story_mock import (
    MOCK_WB_QUESTIONS,
    mock_analyze_idea, mock_generate_outline, mock_generate_script, mock_chat,
    mock_world_building_start, mock_world_building_turn,
)
from app.prompts.story import (
    ANALYZE_PROMPT, WB_SYSTEM_PROMPT, WB_USER_TEMPLATE,
    OUTLINE_PROMPT, SCRIPT_PROMPT, REFINE_PROMPT,
    build_apply_chat_prompt, build_chat_messages,
)

MODEL_MAP = {
    "qwen": "qwen-plus",
    "openai": "gpt-4o-mini",
    "zhipu": "glm-4-flash",
    "gemini": "gemini-2.0-flash",
    "claude":      "claude-sonnet-4-6",
    "siliconflow": "deepseek-ai/DeepSeek-V3",
}


logger = logging.getLogger(__name__)


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
    resp = await client.chat.completions.create(
        model=_get_model(provider, model),
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        data = _parse_json(resp.choices[0].message.content)
    except Exception:
        return {"characters": None, "relationships": None, "outline": None, "meta_theme": None}
    usage = resp.usage

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
        raise HTTPException(status_code=502, detail=str(exc)) from exc
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

    return {
        "characters": latest_story.get("characters") if data.get("characters") is not None else None,
        "relationships": latest_story.get("relationships") if data.get("relationships") is not None else None,
        "outline": latest_story.get("outline") if data.get("outline") is not None else None,
        "meta_theme": data.get("meta_theme"),
        "usage": {"prompt_tokens": usage.prompt_tokens, "completion_tokens": usage.completion_tokens} if usage else None,
    }


async def analyze_idea(idea: str, genre: str, tone: str, db: AsyncSession, api_key: str = "", base_url: str = "", provider: str = "", model: str = "") -> dict:
    if _should_use_dev_mock(api_key, "灵感分析"):
        return await mock_analyze_idea(idea, genre, tone, db=db)

    import json as _json
    import uuid
    client = _make_client(api_key, base_url)
    prompt = ANALYZE_PROMPT.format(idea=idea, genre=genre, tone=tone)
    resp = await client.chat.completions.create(
        model=_get_model(provider, model),
        messages=[{"role": "user", "content": prompt}],
    )
    data = _parse_json(resp.choices[0].message.content)
    story_id = str(uuid.uuid4())
    await repo.save_story(db, story_id, {"idea": idea, "genre": genre, "tone": tone})
    usage = resp.usage
    return {
        "story_id": story_id,
        "analysis": data.get("analysis", ""),
        "suggestions": data.get("suggestions", []),
        "placeholder": data.get("placeholder", ""),
        "usage": {"prompt_tokens": usage.prompt_tokens, "completion_tokens": usage.completion_tokens} if usage else None,
    }


async def generate_outline(story_id: str, selected_setting: str, db: AsyncSession, api_key: str = "", base_url: str = "", provider: str = "", model: str = "") -> dict:
    if _should_use_dev_mock(api_key, "大纲生成"):
        return await mock_generate_outline(story_id, selected_setting, db=db)

    client = _make_client(api_key, base_url)
    prompt = OUTLINE_PROMPT.format(selected_setting=selected_setting)
    # Stream to prevent ReadError on slow LLM responses
    stream = await client.chat.completions.create(
        model=_get_model(provider, model),
        messages=[{"role": "user", "content": prompt}],
        stream=True,
    )
    chunks = []
    async for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            chunks.append(delta)
    content = "".join(chunks)
    data = _parse_json(content)
    await repo.save_story(db, story_id, {
        "selected_setting": selected_setting,
        "meta": data.get("meta"),
        "characters": data.get("characters", []),
        "relationships": data.get("relationships", []),
        "outline": data.get("outline", []),
        "scenes": [],
    })
    await repo.invalidate_story_consistency_cache(db, story_id, appearance=True, scene_style=True)
    latest_story = await repo.get_story(db, story_id)
    return {
        "story_id": story_id,
        "meta": latest_story.get("meta"),
        "characters": latest_story.get("characters", []),
        "relationships": latest_story.get("relationships", []),
        "outline": latest_story.get("outline", []),
        "usage": None,
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
    stream = await client.chat.completions.create(
        model=_get_model(provider, model),
        messages=build_chat_messages(mode, message, context),
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


async def generate_script(story_id: str, db: AsyncSession, api_key: str = "", base_url: str = "", provider: str = "", model: str = ""):
    if _should_use_dev_mock(api_key, "剧本生成"):
        async for scene in mock_generate_script(story_id):
            yield scene
        return

    story = await repo.get_story(db, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="故事不存在")
    outline = story.get("outline", [])
    if not outline:
        if settings.debug:
            async for scene in mock_generate_script(story_id):
                yield scene
            return
        raise HTTPException(status_code=400, detail="剧本生成失败：当前故事缺少大纲，请先完成世界观与大纲生成")
    characters = story.get("characters", [])
    characters_text = "\n".join(
        f"- {c['name']}（{c.get('role', '')}）：{c.get('description', '')}"
        for c in characters
    ) or "无角色信息"
    client = _make_client(api_key, base_url)

    total_prompt = 0
    total_completion = 0
    for ep in outline:
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
        try:
            stream = await client.chat.completions.create(
                model=resolved_model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                stream_options={"include_usage": True},
            )
        except Exception as exc:
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
        async for chunk in stream:
            choices = getattr(chunk, "choices", None) or []
            if choices:
                delta = getattr(choices[0].delta, "content", None)
                if delta:
                    chunks.append(delta)
            usage = getattr(chunk, "usage", None)
            if usage:
                total_prompt += getattr(usage, "prompt_tokens", 0) or 0
                total_completion += getattr(usage, "completion_tokens", 0) or 0

        content = "".join(chunks)
        try:
            yield _parse_json(content)
        except Exception:
            yield {"episode": ep["episode"], "title": ep["title"], "scenes": []}

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
    resp = await client.chat.completions.create(
        model=_get_model(provider, model),
        messages=messages,
    )
    data = _parse_json(resp.choices[0].message.content)
    messages.append({"role": "assistant", "content": resp.choices[0].message.content})
    await repo.save_story(db, story_id, {"idea": idea, "wb_history": messages, "wb_turn": 1})
    usage = resp.usage
    return {
        "story_id": story_id,
        "status": data.get("status", "questioning"),
        "turn": 1,
        "question": _ensure_world_building_question_options(data.get("question")),
        "world_summary": data.get("world_summary"),
        "usage": {"prompt_tokens": usage.prompt_tokens, "completion_tokens": usage.completion_tokens} if usage else None,
    }


async def world_building_turn(story_id: str, answer: str, db: AsyncSession, api_key: str = "", base_url: str = "", provider: str = "", model: str = "") -> dict:
    if _should_use_dev_mock(api_key, "世界观追问"):
        return await mock_world_building_turn(story_id, answer, db=db)

    story = await repo.get_story(db, story_id)
    history = story.get("wb_history", [])
    turn = story.get("wb_turn", 1)

    history = history + [{"role": "user", "content": answer}]
    client = _make_client(api_key, base_url)
    resp = await client.chat.completions.create(
        model=_get_model(provider, model),
        messages=history,
    )
    data = _parse_json(resp.choices[0].message.content)
    history = history + [{"role": "assistant", "content": resp.choices[0].message.content}]
    new_turn = turn + 1
    updates = {"wb_history": history, "wb_turn": new_turn}
    if data.get("status") == "complete":
        updates["selected_setting"] = data.get("world_summary", "")
    await repo.save_story(db, story_id, updates)
    if data.get("status") == "complete":
        await repo.invalidate_story_consistency_cache(db, story_id, scene_style=True)
    usage = resp.usage
    return {
        "story_id": story_id,
        "status": data.get("status", "questioning"),
        "turn": new_turn,
        "question": _ensure_world_building_question_options(data.get("question")),
        "world_summary": data.get("world_summary"),
        "usage": {"prompt_tokens": usage.prompt_tokens, "completion_tokens": usage.completion_tokens} if usage else None,
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

    resp = await client.chat.completions.create(
        model=_get_model(provider, model),
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        data = _parse_json(resp.choices[0].message.content)
    except Exception as e:
        print(f"[APPLY_CHAT] JSON 解析失败: {e!r} | 原始响应: {resp.choices[0].message.content!r:.500}")
        return {}

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
            return updated_episode

    return data
