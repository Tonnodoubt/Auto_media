from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.services import story_repository as repo
from app.services.story_mock import (
    mock_analyze_idea, mock_generate_outline, mock_generate_script, mock_chat,
    mock_world_building_start, mock_world_building_turn,
)

MODEL_MAP = {
    "qwen": "qwen-plus",
    "openai": "gpt-4o-mini",
    "zhipu": "glm-4-flash",
    "gemini": "gemini-2.0-flash",
    "claude":      "claude-sonnet-4-6",
    "siliconflow": "deepseek-ai/DeepSeek-V3",
}

ANALYZE_PROMPT = """你是一位资深短剧编剧，擅长快节奏、高冲突、钩子密集的剧本创作。最终剧本将用于 AI 视频生成，请优先考虑视觉冲击力强、场景具象的设定。

用户原始灵感：{idea}
风格类型：{genre}
故事基调：{tone}

请对这个灵感进行【要素审计】：
1. 世界观是否清晰？
2. 主角动机是否强烈？
3. 核心冲突是否有视觉表现力？（优先具象超能力/场景，避免抽象设定）

以 JSON 格式返回，结构如下：
{{
  "analysis": "简短分析（1-2句，指出最大的缺失要素）",
  "suggestions": [
    {{
      "label": "追问维度名称",
      "options": ["选项A", "选项B", "选项C"]
    }}
  ],
  "placeholder": "引导用户自由输入的提示语"
}}

只返回 JSON，不要其他内容。"""

OUTLINE_PROMPT = """你是一位资深短剧编剧，擅长快节奏、高冲突、钩子密集的剧本创作。最终剧本将用于 AI 视频生成，请优先考虑视觉冲击力强、场景具象的设定。

故事设定：{selected_setting}

请以JSON格式返回完整大纲，结构如下：
{{
  "meta": {{"title": "故事标题", "genre": "类型", "episodes": 6, "theme": "主题"}},
  "characters": [
    {{"name": "角色名", "role": "主角/配角", "description": "角色描述"}}
  ],
  "relationships": [
    {{"source": "角色A", "target": "角色B", "label": "关系描述"}}
  ],
  "outline": [
    {{"episode": 1, "title": "集标题", "summary": "剧情概要，包含具体场景和冲突"}}
  ]
}}

只返回JSON，不要其他内容。"""

SCRIPT_PROMPT = """你是一位资深短剧导演兼编剧。根据以下信息，为第{episode}集「{title}」写导演分镜剧本。

主要角色：
{characters_text}

剧情概要：{summary}

输出要求（用于后续 AI 视频生成）：
- 【环境】和【画面】将直接送入图像生成 API，必须具象、可视化，避免抽象描述
- 【台词/旁白】将直接送入 TTS 语音 API，画面与声音严格分离
- 每集 3-5 个场景

请以JSON格式返回，结构如下：
{{
  "episode": {episode},
  "title": "{title}",
  "scenes": [
    {{
      "scene_number": 1,
      "environment": "时间、地点、天气、光线等环境描述，具象细节",
      "visual": "画面内容：人物位置、动作、表情、镜头角度等，不含对话",
      "audio": [
        {{"character": "角色名或旁白", "line": "台词或旁白内容"}}
      ]
    }}
  ]
}}

只返回JSON，不要其他内容。"""

REFINE_PROMPT = """你是一位资深短剧编剧。用户对故事内容进行了修改，请根据修改内容判断哪些模块需要更新，并返回更新后的内容。

当前故事完整信息：
{story_json}

用户的修改：
类型：{change_type}
内容：{change_summary}

请判断以下模块是否需要因此次修改而更新：
1. 角色列表（characters）：如果角色描述、性格、背景等发生了变化
2. 人物关系（relationships）：如果角色描述变化影响了人物之间的关系
3. 剧情大纲（outline）：如果修改影响了其他集的剧情走向
4. 故事主题（meta.theme）：如果整体主题发生了变化

只更新确实需要变化的模块，不需要变化的返回 null。

以 JSON 格式返回：
{{
  "characters": null 或 [{{"name": "角色名", "role": "角色定位", "description": "角色描述"}}],
  "relationships": null 或 [{{"source": "角色A", "target": "角色B", "label": "关系"}}],
  "outline": null 或 [{{"episode": 1, "title": "标题", "summary": "概要"}}],
  "meta_theme": null 或 "新的主题描述"
}}

只返回 JSON，不要其他内容。"""


WB_SYSTEM_PROMPT = """你是一位资深短剧编剧，正在通过提问帮助用户构建短剧世界观。

规则：
1. 每次只问一个问题，聚焦一个世界观维度
2. 每轮必须给出 3 个选项（type 固定为 "options"），禁止使用开放式问题
3. 选项要具体、有差异化，覆盖不同风格方向，让用户能快速做选择
4. 世界观核心维度（按优先级）：时代背景、权力结构、主角处境、核心冲突、主要人物（数量/性格/关系）、情感基调
5. 必须问满 6 轮，第 6 轮结束后返回 complete，不得提前结束
6. complete 时的 world_summary 必须包含所有已收集的维度信息和人物设定

严格以 JSON 返回：
{
  "status": "questioning" | "complete",
  "question": { "type": "options", "text": "...", "options": ["选项A", "选项B", "选项C"], "dimension": "..." } | null,
  "world_summary": null | "完整世界观描述，包含人物设定（仅 complete 时填写）"
}"""


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
    prompt = REFINE_PROMPT.format(
        story_json=_json.dumps(story, ensure_ascii=False),
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
    if data.get("characters"):
        updates["characters"] = data["characters"]
    if data.get("relationships"):
        updates["relationships"] = data["relationships"]
    if data.get("outline"):
        updates["outline"] = data["outline"]
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
    resp = await client.chat.completions.create(
        model=_get_model(provider, model),
        messages=[{"role": "user", "content": prompt}],
    )
    data = _parse_json(resp.choices[0].message.content)
    await repo.save_story(db, story_id, {
        "selected_setting": selected_setting,
        "meta": data.get("meta"),
        "characters": data.get("characters", []),
        "relationships": data.get("relationships", []),
        "outline": data.get("outline", []),
    })
    usage = resp.usage
    return {
        "story_id": story_id,
        **data,
        "usage": {"prompt_tokens": usage.prompt_tokens, "completion_tokens": usage.completion_tokens} if usage else None,
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
        {"role": "user", "content": f"种子想法：{idea}，请提出第一个世界观问题"},
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
                     db: AsyncSession, api_key: str = "", base_url: str = "", provider: str = "", model: str = "",
                     all_characters: Optional[list] = None, all_outline: Optional[list] = None) -> dict:
    import json as _json
    if not api_key:
        raise ValueError("apply_chat 需要提供 api_key")

    client = _make_client(api_key, base_url)
    history_text = "\n".join(
        f"{'用户' if m['role'] == 'user' else 'AI'}: {m['text']}" for m in chat_history
    )

    if change_type == "character":
        prompt = (
            f"以下是关于角色「{current_item.get('name')}」的修改讨论：\n\n"
            f"{history_text}\n\n"
            f"当前角色信息：{_json.dumps(current_item, ensure_ascii=False)}\n\n"
            "根据讨论内容，提炼出修改后的角色描述。\n"
            "要求：只包含角色描述正文，不要包含分析、解释或建议语句。\n"
            "只返回 JSON，格式：\n"
            '{"description": "修改后的角色描述正文"}'
        )
    else:
        prompt = (
            f"以下是关于第 {current_item.get('episode')} 集「{current_item.get('title')}」的修改讨论：\n\n"
            f"{history_text}\n\n"
            f"当前集数信息：{_json.dumps(current_item, ensure_ascii=False)}\n\n"
            "根据讨论内容，提炼出修改后的标题和剧情摘要。\n"
            "要求：只包含剧情内容本身，不要包含分析、解释或建议语句。\n"
            "只返回 JSON，格式：\n"
            '{"title": "修改后的标题", "summary": "修改后的剧情摘要正文"}'
        )

    resp = await client.chat.completions.create(
        model=_get_model(provider, model),
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        data = _parse_json(resp.choices[0].message.content)
    except Exception as e:
        print(f"[APPLY_CHAT] JSON 解析失败: {e!r} | 原始响应: {resp.choices[0].message.content!r:.500}")
        return {}

    # 使用前端传来的完整数组（最新状态），而非从 DB 读取（可能陈旧）
    if change_type == "character":
        characters = list(all_characters) if all_characters else []
        for c in characters:
            if c.get("name") == current_item.get("name"):
                c["description"] = data.get("description", c["description"])
                break
        if characters:
            await repo.save_story(db, story_id, {"characters": characters})
    else:
        outline = list(all_outline) if all_outline else []
        for ep in outline:
            if ep.get("episode") == current_item.get("episode"):
                ep["title"] = data.get("title", ep["title"])
                ep["summary"] = data.get("summary", ep["summary"])
                break
        if outline:
            await repo.save_story(db, story_id, {"outline": outline})

    return data

