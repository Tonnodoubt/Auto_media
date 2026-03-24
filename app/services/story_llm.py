from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from app.services import story_repository as repo
from app.services.story_mock import (
    mock_analyze_idea, mock_generate_outline, mock_generate_script, mock_chat,
    mock_world_building_start, mock_world_building_turn,
)
from app.prompts.story import (
    ANALYZE_PROMPT, WB_SYSTEM_PROMPT, WB_USER_TEMPLATE,
    OUTLINE_PROMPT, SCRIPT_PROMPT, REFINE_PROMPT,
    build_apply_chat_prompt,
)

MODEL_MAP = {
    "qwen": "qwen-plus",
    "openai": "gpt-4o-mini",
    "zhipu": "glm-4-flash",
    "gemini": "gemini-2.0-flash",
    "claude":      "claude-sonnet-4-6",
    "siliconflow": "deepseek-ai/DeepSeek-V3",
}


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
    if not api_key:
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
    if data.get("characters") is not None:
        updates["characters"] = data["characters"]
    if data.get("relationships") is not None:
        updates["relationships"] = data["relationships"]
    if data.get("outline") is not None:
        updates["outline"] = data["outline"]
    if data.get("meta_theme") is not None:
        existing_meta = story.get("meta") or {}
        updates["meta"] = {**existing_meta, "theme": data["meta_theme"]}
    if updates:
        await repo.save_story(db, story_id, updates)

    return {
        "characters": data.get("characters"),
        "relationships": data.get("relationships"),
        "outline": data.get("outline"),
        "meta_theme": data.get("meta_theme"),
        "usage": {"prompt_tokens": usage.prompt_tokens, "completion_tokens": usage.completion_tokens} if usage else None,
    }


async def analyze_idea(idea: str, genre: str, tone: str, db: AsyncSession, api_key: str = "", base_url: str = "", provider: str = "", model: str = "") -> dict:
    if not api_key:
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
    if not api_key:
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
    })
    return {
        "story_id": story_id,
        **data,
        "usage": None,
    }


async def chat(story_id: str, message: str, db: AsyncSession, api_key: str = "", base_url: str = "", provider: str = "", model: str = ""):
    if not api_key:
        async for chunk in mock_chat(story_id, message, db=db):
            yield chunk
        return

    client = _make_client(api_key, base_url)
    stream = await client.chat.completions.create(
        model=_get_model(provider, model),
        messages=[{"role": "user", "content": message}],
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


async def generate_script(story_id: str, db: AsyncSession, api_key: str = "", base_url: str = "", provider: str = "", model: str = ""):
    if not api_key:
        async for scene in mock_generate_script(story_id):
            yield scene
        return

    story = await repo.get_story(db, story_id)
    outline = story.get("outline", [])
    if not outline:
        async for scene in mock_generate_script(story_id):
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
    for ep in outline:
        prompt = SCRIPT_PROMPT.format(
            episode=ep["episode"],
            title=ep["title"],
            summary=ep["summary"],
            characters_text=characters_text,
        )
        resp = await client.chat.completions.create(
            model=_get_model(provider, model),
            messages=[{"role": "user", "content": prompt}],
        )
        if resp.usage:
            total_prompt += resp.usage.prompt_tokens
            total_completion += resp.usage.completion_tokens
        try:
            yield _parse_json(resp.choices[0].message.content)
        except Exception:
            yield {"episode": ep["episode"], "title": ep["title"], "scenes": []}

    yield {"__usage__": {"prompt_tokens": total_prompt, "completion_tokens": total_completion}}


async def world_building_start(idea: str, db: AsyncSession, api_key: str = "", base_url: str = "", provider: str = "", model: str = "") -> dict:
    import uuid
    if not api_key:
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
        "question": data.get("question"),
        "world_summary": data.get("world_summary"),
        "usage": {"prompt_tokens": usage.prompt_tokens, "completion_tokens": usage.completion_tokens} if usage else None,
    }


async def world_building_turn(story_id: str, answer: str, db: AsyncSession, api_key: str = "", base_url: str = "", provider: str = "", model: str = "") -> dict:
    if not api_key:
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
    usage = resp.usage
    return {
        "story_id": story_id,
        "status": data.get("status", "questioning"),
        "turn": new_turn,
        "question": data.get("question"),
        "world_summary": data.get("world_summary"),
        "usage": {"prompt_tokens": usage.prompt_tokens, "completion_tokens": usage.completion_tokens} if usage else None,
    }

async def apply_chat(story_id: str, change_type: str, chat_history: list, current_item: dict,
                     db: AsyncSession, api_key: str = "", base_url: str = "", provider: str = "", model: str = "") -> dict:
    import json as _json
    if not api_key:
        raise HTTPException(status_code=400, detail="apply_chat 需要提供 api_key")

    client = _make_client(api_key, base_url)
    history_text = "\n".join(
        f"{'用户' if m.role == 'user' else 'AI'}: {m.text}" for m in chat_history
    )

    prompt = build_apply_chat_prompt(change_type, current_item, history_text)

    resp = await client.chat.completions.create(
        model=_get_model(provider, model),
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        data = _parse_json(resp.choices[0].message.content)
    except Exception as e:
        print(f"[APPLY_CHAT] JSON 解析失败: {e!r} | 原始响应: {resp.choices[0].message.content!r:.500}")
        return {}

    # 从 DB 取权威数据，避免写入客户端篡改的其他项目数据
    story = await repo.get_story(db, story_id)
    if change_type == "character":
        characters = list(story.get("characters") or [])
        for c in characters:
            if c.get("name") == current_item.get("name"):
                c["description"] = data.get("description", c["description"])
                break
        if characters:
            await repo.save_story(db, story_id, {"characters": characters})
    else:
        outline = list(story.get("outline") or [])
        for ep in outline:
            if ep.get("episode") == current_item.get("episode"):
                ep["title"] = data.get("title", ep["title"])
                ep["summary"] = data.get("summary", ep["summary"])
                break
        if outline:
            await repo.save_story(db, story_id, {"outline": outline})

    return data

