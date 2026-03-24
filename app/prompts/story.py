# -*- coding: utf-8 -*-
"""
剧本生成全流程提示词模板（Step 1-3）

所有提示词使用 Python .format() 占位符，花括号 {{ }} 为转义。
"""
import json as _json


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


# ============================================================================
# Step 3: 对话式局部修改（apply_chat）
# ============================================================================

_APPLY_CHAT_CHARACTER_TEMPLATE = (
    "以下是关于角色「{name}」的修改讨论：\n\n"
    "{history_text}\n\n"
    "当前角色信息：{current_item_json}\n\n"
    "根据讨论内容，提炼出修改后的角色描述。\n"
    "要求：只包含角色描述正文，不要包含分析、解释或建议语句。\n"
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
    else:
        return _APPLY_CHAT_EPISODE_TEMPLATE.format(
            episode=current_item.get("episode", ""),
            title=current_item.get("title", ""),
            history_text=history_text,
            current_item_json=current_item_json,
        )
