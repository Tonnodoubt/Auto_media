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

当前任务属于第一层：剧情大纲（Logic Layer）。
这一层只负责搭建冲突、转折、节奏和场景切分，不要写成剧本，不要提前写成分镜。

请以JSON格式返回完整大纲，结构如下：
{{
  "meta": {{
    "title": "故事标题",
    "genre": "类型",
    "episodes": 6,
    "theme": "主题",
    "logline": "一句话核心冲突",
    "visual_tone": "一句话视觉风格基调"
  }},
  "characters": [
    {{"name": "角色名", "role": "主角/配角", "description": "角色描述"}}
  ],
  "relationships": [
    {{"source": "角色A", "target": "角色B", "label": "关系描述"}}
  ],
  "outline": [
    {{
      "episode": 1,
      "title": "集标题",
      "summary": "本集逻辑推进摘要：只写因果、冲突、转折、结果",
      "beats": ["Beat 1", "Beat 2", "Beat 3"],
      "scene_list": ["Scene 1: [夜] [室外] [天台] - 主角发现信封，内心动摇。"]
    }}
  ]
}}

角色描述（`characters[].description`）额外要求：
1. 角色描述本质上是“角色小传”，要先写视觉锚点，再写身份处境、核心性格、行为方式
2. 至少包含可稳定识别的外貌信息，例如年龄段、发型发色、体型、标志性服装或配饰
3. 习惯描写必须服务于人物辨识或性格表达，保持概括、可感知
4. 禁止写与塑造人物无关的微观操作细节，例如精确位置、固定砖块/石阶、路线坐标、误差范围、毫米级划痕、机关触发步骤
5. 禁止把剧情机关、作案流程、镜头调度、场景走位写进角色描述
6. 每个角色描述保持简洁，不要写成剧情摘要

大纲层额外要求：
1. `logline` 必须是一句话，清楚说明主角、目标、阻碍和核心冲突
2. `summary` 只写剧情逻辑，不写对白，不写镜头语言，不写摄影机运动
3. `beats` 只写本集的关键转折点，每条一句
4. `scene_list` 只做场景切分与场景任务说明，强调 [时间] [内/外] [地点] 和当场发生的核心事件
5. `scene_list` 中相同地点应尽量使用同一命名，避免同一环境被反复换叫法
6. 大纲层不要写过细环境材质、光线方向、构图和表演微动作，那是后两层的工作

只返回JSON，不要其他内容。"""


# ============================================================================
# Step 3: 导演分镜剧本
# ============================================================================

SCRIPT_PROMPT = """你是一位资深短剧编剧。根据以下信息，为第{episode}集「{title}」写第二层：剧本（Narrative Layer）。

主要角色：
{characters_text}

剧情概要：{summary}

本集节拍：
{beats_text}

场景切分参考：
{scene_list_text}

这一层的目标：
1. 提供标准场景剧本、动作线、对白和情感刻度
2. 为后续分镜和环境图生成提供“足够稳定、但不过度摄影化”的中层文本
3. 不要把这一层写成大纲摘要，也不要写成分镜头列表

输出要求（用于后续 AI 视频生成与环境图生成）：
- 每集 3-5 个场景
- 所有描述必须具象、可视化，但保持“剧本动作线”风格，不要写镜头角度、运镜、焦段、构图术语
- `scene_heading` 使用标准场景标题格式，体现 [时间] [内/外] [地点]
- `environment_anchor` 只写该场景的稳定地点名，用于后续环境复用；相同地点必须尽量复用完全一致的叫法
- `environment` 的职责是帮助后续生成可复用的场景参考图，因此只写稳定环境信息：
  - 时间段 / 天气
  - 空间类型与结构关系
  - 固定建筑、主要家具、入口、窗户、楼梯、柜台、栏杆等稳定物件
  - 稳定主光源类型
- `environment` 禁止包含：
  - 人物动作、人物情绪、剧情判断、镜头语言、一次性微小细节、无助于环境复用的装饰噪声
- `lighting` 只写稳定光源与整体光感，例如“雨夜天光混合廊下灯笼暖光”，不要写摄影机位级别的精细布光说明
- `visual` 是动作线（Action Line），负责写人物在该场景中发生了什么、谁和谁如何互动，不含对白文本
- `emotion_tags` 为该场景提供情感刻度，格式清晰，强度使用 0-1 小数
- `key_props` 显式列出剧情关键物件，避免后续图片/视频模型遗漏
- `key_actions` 只拆 1-3 个关键动作节点，供分镜层进一步展开
- `transition_from_previous` 如果填写，只写叙事上的承接，不写镜头剪辑术语
- `audio` 中只保留台词/旁白，画面与声音严格分离
- 整集应有情绪弧线：开场建立 → 发展递进 → 高潮爆发 → 收尾余韵

请以JSON格式返回，结构如下：
{{
  "episode": {episode},
  "title": "{title}",
  "scenes": [
    {{
      "scene_number": 1,
      "scene_heading": "[夜] [室外] [天台]",
      "environment_anchor": "天台",
      "environment": "只写稳定环境信息：地点、空间结构、固定陈设、主要入口、可复用布局",
      "lighting": "稳定光源与整体光感",
      "mood": "情绪基调短语",
      "emotion_tags": [
        {{"target": "角色名或scene", "emotion": "悲伤", "intensity": 0.8}}
      ],
      "key_props": ["关键物件1", "关键物件2"],
      "visual": "动作线：人物位置、动作、表情、互动关系，不含对白，不含镜头语言",
      "key_actions": ["动作1：具体可拍摄行为", "动作2：具体可拍摄行为"],
      "transition_from_previous": "与上一场景的叙事承接（第一个场景可为null）",
      "audio": [
        {{"character": "角色名或旁白", "line": "台词或旁白内容"}}
      ]
    }}
  ]
}}

剧本层额外约束：
1. 不要重复大纲里的整集摘要腔，不要反复解释主题和主线
2. `beats_text` 负责提醒本集的冲突推进，`scene_list_text` 负责提醒场景切分；你需要消化它们，但不要逐条复述成说明书
3. 不要输出 shot_suggestions、分镜编号、镜头景别、运镜等分镜层信息
4. 相同环境的 `environment_anchor` 与 `environment` 要尽量保持同一套稳定写法，方便后续复用同一张环境图
5. 如果场景发生在同一地点的不同区域，可在 `environment_anchor` 保持主地点稳定，在 `visual` 里体现人物移动

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
4. 任何角色 description 只允许保留外貌、身份/经历、核心性格、代表性习惯；禁止精确位置、误差范围、毫米级痕迹、固定触发动作、场景机关等无关细节
5. 如果返回 outline 中的某一集，必须同时返回该集完整的 title、summary、beats、scene_list 四个字段
6. 更新某一集剧情时，beats 与 scene_list 必须同步到修改后的剧情，禁止沿用已经失效的旧值

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
  "outline": null 或 [{{"episode": 1, "title": "标题", "summary": "概要", "beats": ["Beat 1"], "scene_list": ["Scene 1: [夜] [室内] [地点] - 场景任务"]}}],
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
    "4. 角色描述只保留外貌、身份/经历、核心性格、能体现人物的稳定习惯\n"
    "5. 如果写习惯，只能写概括性的识别特征；禁止精确位置、固定砖块/石阶、误差范围、毫米级划痕、机关触发步骤等微观细节\n"
    "6. 不要写成剧情线索、作案流程或镜头调度说明\n"
    "只返回 JSON，格式：\n"
    '{{"description": "修改后的角色描述正文"}}'
)

_APPLY_CHAT_EPISODE_TEMPLATE = (
    "以下是关于第 {episode} 集「{title}」的修改讨论：\n\n"
    "{history_text}\n\n"
    "当前集数信息：{current_item_json}\n\n"
    "根据讨论内容，提炼出修改后的整集信息。\n"
    "要求：\n"
    "1. 必须同时返回 title、summary、beats、scene_list 四个字段\n"
    "2. `beats` 只写本集关键转折点，每条一句\n"
    "3. `scene_list` 只写场景切分与场景任务，体现 [时间] [内/外] [地点]\n"
    "4. `summary`、`beats`、`scene_list` 必须互相一致，不能保留已经失效的旧值\n"
    "5. 只包含剧情内容本身，不要包含分析、解释或建议语句。\n"
    "只返回 JSON，格式：\n"
    '{{"title": "修改后的标题", "summary": "修改后的剧情摘要正文", "beats": ["Beat 1"], "scene_list": ["Scene 1: [夜] [室内] [地点] - 场景任务"]}}'
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
            "8. 如果没有明确剧情联动，就不要编造“基本不影响主线”这类兜底句\n"
            "9. 如果用户要求补充习惯或细节，只保留能体现人物性格或辨识度的稳定习惯\n"
            "10. 禁止写固定路线、精确位置、误差范围、毫米级痕迹、机关触发步骤等噪声细节\n\n"
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
