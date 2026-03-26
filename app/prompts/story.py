# -*- coding: utf-8 -*-
"""
剧本生成全流程提示词模板（Step 1-3）

所有提示词使用 Python .format() 占位符，花括号 {{ }} 为转义。
"""
import json as _json
from typing import Optional


# ============================================================================
# Step 1: 灵感要素审计
# ============================================================================

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


# ============================================================================
# Step 2: 世界构建 6 轮问答
# ============================================================================

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

WB_USER_TEMPLATE = "种子想法：{idea}，请提出第一个世界观问题"


# ============================================================================
# Step 3: 大纲生成
# ============================================================================

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


# ============================================================================
# Step 3: 导演分镜剧本
# ============================================================================

SCRIPT_PROMPT = """你是一位资深短剧导演兼编剧。根据以下信息，为第{episode}集「{title}」写导演分镜剧本。

主要角色：
{characters_text}

剧情概要：{summary}

输出要求（用于后续 AI 视频生成）：
- 所有描述必须具象可视化，避免抽象修饰语。描写时包含服装颜色/材质、具体手势、人物空间关系
- 【环境】包含时间、地点、天气等物理环境
- 【光线】具体描述主光源方向、色温、阴影特征（如"暖黄色台灯从左侧照射，右半脸隐于阴影"）
- 【氛围】用一个短语概括情绪基调（如"紧张不安"、"温馨感动"、"压抑绝望"）
- 【画面】人物位置、动作、表情、镜头角度等可视化内容，不含对话
- 【动作拆解】将画面中的复杂动作拆解为 1-3 个独立可拍摄行为，每个动作一行
- 【镜头建议】给出 1-2 个镜头景别和运动建议（如"特写手部"、"俯拍全景"、"跟拍侧面"）
- 【过渡】与上一场景的衔接方式（如"硬切"、"叠化"、"声音先入"），第一个场景可省略
- 【台词/旁白】将直接送入 TTS 语音 API，画面与声音严格分离
- 每集 3-5 个场景
- 整集应有情绪弧线：开场建立→发展递进→高潮爆发→收尾余韵，场景之间有节奏变化

请以JSON格式返回，结构如下：
{{
  "episode": {episode},
  "title": "{title}",
  "scenes": [
    {{
      "scene_number": 1,
      "environment": "时间、地点、天气等环境描述，具象细节",
      "lighting": "光线描述：主光方向、色温、阴影特征",
      "mood": "情绪基调短语",
      "visual": "画面内容：人物位置、动作、表情、镜头角度等，不含对话",
      "key_actions": ["动作1：具体可拍摄行为", "动作2：具体可拍摄行为"],
      "shot_suggestions": ["景别+运动建议1", "景别+运动建议2"],
      "transition_from_previous": "与上一场景衔接方式（第一个场景可为null）",
      "audio": [
        {{"character": "角色名或旁白", "line": "台词或旁白内容"}}
      ]
    }}
  ]
}}

只返回JSON，不要其他内容。"""


# ============================================================================
# Step 3: 故事修改联动
# ============================================================================

REFINE_PROMPT = """你是一位资深短剧编剧。用户对故事内容进行了修改，请根据修改内容判断哪些模块需要更新，并返回更新后的内容。

当前故事完整信息：
{story_json}

用户的修改：
类型：{change_type}
内容：{change_summary}

固定约束：
1. 角色名字、主角/配角/反派等角色定位标签默认不可修改，除非用户明确要求手动修改这些字段
2. 如果只是调整角色描述、性格、经历、行为方式，必须保留该角色原有的 name 和 role
3. 如果只是调整某一集或整体剧情走向，禁止顺带改动角色名字和 role 标签

请判断以下模块是否需要因此次修改而更新：
1. 角色列表（characters）：如果角色描述、性格、背景等发生了变化
2. 人物关系（relationships）：如果角色描述变化影响了人物之间的关系
3. 剧情大纲（outline）：如果修改影响了其他集的剧情走向
4. 故事主题（meta.theme）：如果整体主题发生了变化

只更新确实需要变化的模块，不需要变化的返回 null。
如果只是剧本的局部问题修改，必须只返回受影响的角色 / 关系 / 集数，禁止无关内容整体重写。

角色与关系的 ID 规则：
1. 如果返回 characters，已存在角色必须保留原有 id，禁止改写或丢失 id
2. 如果返回 relationships，优先返回 source_id / target_id，并与 characters 中的 id 保持一致
3. 禁止仅靠角色名识别同一角色；同名角色也必须依赖 id 区分

以 JSON 格式返回：
{{
  "characters": null 或 [{{"id": "角色ID", "name": "角色名", "role": "角色定位", "description": "角色描述"}}],
  "relationships": null 或 [{{"source_id": "角色A_ID", "target_id": "角色B_ID", "source": "角色A", "target": "角色B", "label": "关系"}}],
  "outline": null 或 [{{"episode": 1, "title": "标题", "summary": "概要"}}],
  "meta_theme": null 或 "新的主题描述"
}}

只返回 JSON，不要其他内容。"""


# ============================================================================
# Step 3: 对话式局部修改（apply_chat）
# ============================================================================

_APPLY_CHAT_CHARACTER_TEMPLATE = (
    "以下是关于角色「{name}」的修改讨论：\n\n"
    "{history_text}\n\n"
    "当前角色信息：{current_item_json}\n\n"
    "根据讨论内容，只提炼修改后的角色描述。\n"
    "要求：\n"
    "1. 禁止修改角色名字\n"
    "2. 禁止修改主角/配角/反派等角色定位标签\n"
    "3. 只保留角色设定正文，不要包含分析、解释、建议或剧情影响说明\n"
    "只返回 JSON，格式：\n"
    '{{"description": "修改后的角色描述正文"}}'
)

_APPLY_CHAT_EPISODE_TEMPLATE = (
    "以下是关于第 {episode} 集「{title}」的修改讨论：\n\n"
    "{history_text}\n\n"
    "当前集数信息：{current_item_json}\n\n"
    "根据讨论内容，提炼出修改后的标题和剧情摘要。\n"
    "要求：只包含剧情内容本身，不要包含分析、解释或建议语句。\n"
    "只返回 JSON，格式：\n"
    '{{"title": "修改后的标题", "summary": "修改后的剧情摘要正文"}}'
)


def build_apply_chat_prompt(change_type: str, current_item: dict, history_text: str) -> str:
    """根据修改类型构建 apply_chat 的 user prompt。"""
    current_item_json = _json.dumps(current_item, ensure_ascii=False)
    if change_type == "character":
        return _APPLY_CHAT_CHARACTER_TEMPLATE.format(
            name=current_item.get("name", ""),
            history_text=history_text,
            current_item_json=current_item_json,
        )
    elif change_type == "episode":
        return _APPLY_CHAT_EPISODE_TEMPLATE.format(
            episode=current_item.get("episode", ""),
            title=current_item.get("title", ""),
            history_text=history_text,
            current_item_json=current_item_json,
        )
    else:
        raise ValueError(
            f"build_apply_chat_prompt: unknown change_type {change_type!r}; "
            "expected 'character' or 'episode'"
        )


CHAT_SYSTEM_PROMPT = """你是一位短剧协作修改助手，负责把用户的修改意图整理成简洁、可执行的建议。

通用规则：
1. 先顺着用户意图给方案，不要反驳用户，不要讲大道理，不要长篇分析
2. 如果存在剧情冲突，只能简短说明影响，并给出顺着用户意图的处理方式
3. 回复必须短、直接、可执行，禁止输出 markdown 列表、代码块、解释性前言和多余客套
4. 每个分类写 1-3 个要点即可，同一行内用中文分号“；”分隔，禁止换成长段落
5. 除非用户明确要求手动修改，否则禁止改动角色名字和主角/配角/反派等角色定位标签
"""


def _to_json_text(data: dict) -> str:
    return _json.dumps(data, ensure_ascii=False)


def _outline_summary_lines(outline: Optional[list[dict]]) -> str:
    if not outline:
        return "无"
    lines = []
    for episode in outline:
        ep_num = episode.get("episode", "")
        title = str(episode.get("title", "")).strip()
        summary = str(episode.get("summary", "")).strip()
        lines.append(f"第{ep_num}集《{title}》：{summary}")
    return "\n".join(lines)


def build_chat_messages(mode: str, message: str, context: Optional[dict] = None) -> list[dict]:
    """构建对话式修改助手的消息列表。"""
    context = context or {}
    user_message = str(message or "").strip()

    if mode == "character":
        character = context.get("character") or {}
        outline = context.get("outline") or []
        prompt = (
            "当前任务：协助用户修改单个角色设定。\n"
            "回复必须严格为 2 行纯文本，禁止空行，格式固定为：\n"
            "当前角色修改：要点1；要点2\n"
            "对剧情的影响：要点1；要点2\n\n"
            "额外约束：\n"
            "1. 只允许讨论角色描述、气质、经历、行为方式、视觉特征等设定\n"
            "2. 绝对不要建议修改角色名字\n"
            "3. 绝对不要建议修改主角/配角/反派等标签\n"
            "4. “当前角色修改”和“对剧情的影响”必须分开写，不能混写\n"
            "5. 第一行只允许写角色设定变化，禁止出现剧情、主线、冲突、后续、第几集等内容\n"
            "6. 第二行只允许写剧情联动，禁止重复角色设定描述\n"
            "7. 两行都必须保留固定标签原样输出，不要改写标签，不要合并成一行\n"
            "8. 如果没有明确剧情联动，就不要编造“基本不影响主线”这类兜底句\n\n"
            f"当前角色：{_to_json_text(character)}\n"
            f"当前大纲：\n{_outline_summary_lines(outline)}\n"
            f"用户要求：{user_message}"
        )
    elif mode == "episode":
        episode = context.get("episode") or {}
        outline = context.get("outline") or []
        prompt = (
            "当前任务：协助用户修改单集剧情。\n"
            "回复必须严格为 2 行纯文本，禁止空行，格式固定为：\n"
            "当前剧情修改：...\n"
            "对后续剧情的影响：...\n\n"
            "额外约束：\n"
            "1. 优先把用户要求落实到本集标题和剧情摘要\n"
            "2. 若会影响后续集数，只简短说明联动方向，不展开长篇分析\n"
            "3. 不要输出反问、说教和否定式劝阻\n\n"
            f"当前集信息：{_to_json_text(episode)}\n"
            f"完整大纲：\n{_outline_summary_lines(outline)}\n"
            f"用户要求：{user_message}"
        )
    elif mode == "outline":
        story_meta = context.get("meta") or {}
        characters = context.get("characters") or []
        outline = context.get("outline") or []
        prompt = (
            "当前任务：协助用户修改剧情大纲，并准备后续可应用的修改摘要。\n"
            "回复必须严格为 3 行纯文本，禁止空行，格式固定为：\n"
            "当前大纲修改：...\n"
            "联动影响：...\n"
            "REFINE_JSON:{\"change_type\":\"episode\"|\"character\",\"change_summary\":\"...\"}\n\n"
            "额外约束：\n"
            "1. 前两行给用户看，必须简短清楚\n"
            "2. 第三行只用于程序读取，必须是单行合法 JSON\n"
            "3. 大纲/剧情类修改优先使用 change_type=episode；只有用户明确在改角色设定时才用 character\n"
            "4. change_summary 必须是 1 句话摘要，不要换行，不要附带解释\n"
            "5. 不要输出代码块，不要输出其他多余内容\n\n"
            f"故事 meta：{_to_json_text(story_meta)}\n"
            f"角色列表：{_to_json_text(characters)}\n"
            f"当前大纲：\n{_outline_summary_lines(outline)}\n"
            f"用户要求：{user_message}"
        )
    else:
        prompt = (
            "请根据用户要求给出简短、直接、可执行的修改建议。\n"
            "回复控制在 2 句内，不要输出多余说明。\n\n"
            f"用户要求：{user_message}"
        )

    return [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
