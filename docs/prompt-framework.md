# AutoMedia 提示词框架文档

> 更新日期：2026-03-26
>
> 本文档按当前仓库代码同步，区分“已落地默认行为”和“兼容/回退行为”。

---

## 一、当前提示词主链路

```text
Step 1   灵感审计
  ANALYZE_PROMPT

Step 2   世界构建
  WB_SYSTEM_PROMPT + WB_USER_TEMPLATE

Step 3   故事生成与修改
  OUTLINE_PROMPT
  SCRIPT_PROMPT
  REFINE_PROMPT
  CHAT_SYSTEM_PROMPT + build_chat_messages()
  build_apply_chat_prompt()

Step 4   分镜导演
  storyboard.SYSTEM_PROMPT + USER_TEMPLATE

Step 5   角色资产与运行期一致性
  build_character_prompt()
  APPEARANCE_SYSTEM_PROMPT
  SCENE_STYLE_SYSTEM_PROMPT
  build_generation_payload()
```

---

## 二、文件索引

| 文件 | 作用 |
|------|------|
| `app/prompts/story.py` | Step 1-3 的主 prompt 模板 |
| `app/prompts/storyboard.py` | Step 4 分镜导演 prompt |
| `app/prompts/character.py` | 角色三视图设定图 prompt 与角色参考段落拼装 |
| `app/services/story_llm.py` | 灵感分析、世界构建、大纲、剧本、chat、refine、apply-chat |
| `app/services/storyboard.py` | 剧本转 Shot，兼容旧格式并补全缺省字段 |
| `app/services/story_context_service.py` | 角色外貌缓存、场景风格缓存提取 |
| `app/core/story_context.py` | 运行期角色/场景锚点清洗与 prompt 拼装 |
| `app/core/story_assets.py` | `design_prompt` / `visual_dna` / 角色资产记录辅助 |

---

## 三、Step 1：灵感审计

**Prompt**：`ANALYZE_PROMPT`

**目标**：

- 审计世界观是否清晰
- 审计主角动机是否明确
- 审计核心冲突是否具备视觉表现力

**输出 JSON**：

```json
{
  "analysis": "1-2句缺口分析",
  "suggestions": [
    {
      "label": "追问维度",
      "options": ["选项A", "选项B", "选项C"]
    }
  ],
  "placeholder": "引导用户继续输入"
}
```

**当前实现说明**：

- 无 API Key 时走 mock，并先落库 `idea / genre / tone`
- 返回 `story_id`，作为后续 Story 主键

---

## 四、Step 2：世界构建

**Prompt**：`WB_SYSTEM_PROMPT` + `WB_USER_TEMPLATE`

**当前规则**：

- 每轮只问一个问题
- `question.type` 固定为 `options`
- 每轮必须给 3 个选项
- 必须问满 6 轮
- 第 6 轮完成时返回 `complete`
- `world_summary` 必须汇总已收集的维度与人物设定

**返回结构**：

```json
{
  "status": "questioning | complete",
  "question": {
    "type": "options",
    "text": "问题文本",
    "options": ["选项A", "选项B", "选项C"],
    "dimension": "当前维度"
  },
  "world_summary": null
}
```

**当前实现说明**：

- `world_building_start()` 创建新的 `story_id`，并保存 `wb_history / wb_turn`
- `world_building_turn()` 在完成时把结果写入 `selected_setting`
- 完成世界构建后会失效 `scene_style_cache`

---

## 五、Step 3：故事生成与修改

### 5.1 大纲生成

**Prompt**：`OUTLINE_PROMPT`

**输出 JSON**：

```json
{
  "meta": {"title": "故事标题", "genre": "类型", "episodes": 6, "theme": "主题"},
  "characters": [
    {"name": "角色名", "role": "主角/配角", "description": "角色描述"}
  ],
  "relationships": [
    {"source": "角色A", "target": "角色B", "label": "关系描述"}
  ],
  "outline": [
    {"episode": 1, "title": "集标题", "summary": "剧情概要"}
  ]
}
```

**当前实现说明**：

- Prompt 本身不要求角色 ID
- 持久化时会由 `normalize_story_record()` 自动补齐并规范化：
  - `characters[*].id`
  - `relationships[*].source_id / target_id`
  - `character_images` 与 `character_appearance_cache` 统一按 `character_id` 收口

### 5.2 导演分镜剧本

**Prompt**：`SCRIPT_PROMPT`

**当前字段**：

```json
{
  "episode": 1,
  "title": "集标题",
  "scenes": [
    {
      "scene_number": 1,
      "environment": "时间/地点/天气",
      "lighting": "主光方向/色温/阴影",
      "mood": "情绪短语",
      "visual": "人物位置/动作/表情/镜头角度",
      "key_actions": ["动作1", "动作2"],
      "shot_suggestions": ["镜头建议1", "镜头建议2"],
      "transition_from_previous": "与上一场景的衔接方式",
      "audio": [
        {"character": "角色名或旁白", "line": "台词或旁白"}
      ]
    }
  ]
}
```

**关键说明**：

- 当前 `SCRIPT_PROMPT` 已要求 `lighting / mood / key_actions / shot_suggestions / transition_from_previous`
- 当前 **没有** 在 Step 3 输出中要求 `scene_intensity`
- Step 4 的分镜 prompt 会自行要求输出 `scene_intensity`
- 如果分镜 LLM 返回旧格式或缺少该字段，`parse_script_to_storyboard()` 会默认补成 `"low"`

### 5.3 结构化联动修改

**Prompt**：`REFINE_PROMPT`

**返回结构**：

```json
{
  "characters": null,
  "relationships": null,
  "outline": null,
  "meta_theme": null
}
```

**当前约束**：

- 如果返回 `characters`，已存在角色必须保留原有 `id`
- 如果返回 `relationships`，优先返回 `source_id / target_id`
- 返回结果写回数据库后，会按变更类型失效一致性缓存

### 5.4 对话式局部修改

**入口**：`build_chat_messages()` + `/api/v1/story/chat` + `build_apply_chat_prompt()` + `apply_chat()`

**聊天模式**：

- `character`：返回 2 行纯文本
  - `当前角色修改：...`
  - `对剧情的影响：...`
- `episode`：返回 2 行纯文本
  - `当前剧情修改：...`
  - `对后续剧情的影响：...`
- `outline`：返回 3 行纯文本
  - `当前大纲修改：...`
  - `联动影响：...`
  - `REFINE_JSON:{...}` 供前端隐藏读取

**当前支持类型**：

- `character`
- `episode`

**输出**：

- 角色聊天展示层：只给结构化短建议，不给长篇分析，不输出代码块
- 角色应用层：只修改 `description`
- 集数修改：`title / summary`

**当前实现说明**：

- `CHAT_SYSTEM_PROMPT` 强制“顺着用户意图、少解释、少反驳、短文本分类输出”
- 角色名字与 `role` 标签在 AI 聊天与 `apply_chat()` 中都被视为不可修改字段
- `outline` 模式通过隐藏的 `REFINE_JSON` 单行结构，把建议展示和后续联动摘要分离
- `apply_chat()` 从数据库读取当前权威对象后再写回
- 角色修改会失效 `character_appearance_cache`
- 集数修改会失效 `scene_style_cache`

---

## 六、Step 4：分镜导演 Prompt

**Prompt**：`app/prompts/storyboard.py`

### 6.1 当前强约束

- 严格忠于脚本，不得发明剧情、人物、道具
- `image_prompt` 与 `final_video_prompt` 必须分离
- `image_prompt` 只描述静态首帧，不写运镜
- `final_video_prompt` 必须写运镜和单个核心动作
- 每条对白只能分配给一个 Shot，不能重复
- 强制检查镜头连续性、状态延续和转场平滑
- 如果脚本或角色参考明确给出正面/侧面/背面朝向，必须保留该 cue
- 不得凭空发明人物朝向

### 6.2 Shot 结构

当前 `Shot` schema：

```json
{
  "shot_id": "scene1_shot1",
  "estimated_duration": 4,
  "scene_intensity": "low",
  "storyboard_description": "中文画面简述",
  "camera_setup": {
    "shot_size": "MS",
    "camera_angle": "Eye-level",
    "movement": "Static"
  },
  "visual_elements": {
    "subject_and_clothing": "主体与服装",
    "action_and_expression": "动作与表情",
    "environment_and_props": "环境与道具",
    "lighting_and_color": "光影与色彩"
  },
  "image_prompt": "静态首帧 prompt",
  "final_video_prompt": "视频运动 prompt",
  "last_frame_prompt": "可选尾帧 prompt",
  "audio_reference": {
    "type": "dialogue | narration | sfx | null",
    "content": "内容"
  },
  "mood": "情绪短语",
  "scene_position": "establishing | development | climax | resolution",
  "transition_from_previous": "过渡说明",
  "last_frame_url": "可选尾帧 URL"
}
```

### 6.3 兼容与回退

`parse_script_to_storyboard()` 当前会兼容旧返回格式并自动补齐：

- `visual_prompt -> final_video_prompt`
- `visual_description_zh -> storyboard_description`
- 平铺 `shot_size / camera_motion -> camera_setup`
- `dialogue -> audio_reference`
- 缺失的 `scene_intensity -> "low"`

**当前没有后端二次注入固定 render tags 的专门分发逻辑**；分镜质量控制主要依赖 Step 4 prompt 本身的约束。

---

## 七、Step 5：角色资产与运行期一致性

### 7.1 角色设定图 Prompt

**入口**：`build_character_prompt()`

**当前口径**：

- 角色图不是头像肖像 prompt，而是标准三视图资产 prompt
- 主字段为 `design_prompt`
- 兼容字段为 `prompt`

**模板核心**：

```text
Standard three-view character turnaround sheet for {name}, ...
show front view, side profile, and back view of the same character on one sheet,
full body in all three views, neutral standing pose, clear silhouette, ...
```

### 7.2 角色资产数据

`build_character_asset_record()` 当前会保存：

- `image_url`
- `image_path`
- `prompt`
- `design_prompt`
- `asset_kind=character_sheet`
- `framing=three_view`
- `character_id`
- `character_name`
- `visual_dna`（有值时）

**当前 API 约束**：

- `/api/v1/character/generate`
- `/api/v1/character/generate-all`

这两个入口都要求角色具备 `character_id`，禁止按角色名复用或覆盖人设图。

### 7.3 StoryContext 提取 Prompt

运行期不是直接把三视图 prompt 全量塞回分镜，而是先做两类抽取：

1. `APPEARANCE_SYSTEM_PROMPT`
   - 提取角色稳定外貌锚点
   - 结果写入 `meta["character_appearance_cache"]`
   - 若已有角色资产，会把 `visual_dna` 回填到 `character_images[character_id]`

2. `SCENE_STYLE_SYSTEM_PROMPT`
   - 提取可复用场景风格锚点
   - 结果写入 `meta["scene_style_cache"]`

### 7.4 运行期 Prompt 拼装

`build_generation_payload()` 当前是运行期主组装入口，会统一产出：

- `image_prompt`
- `final_video_prompt`
- `last_frame_prompt`
- `negative_prompt`

当前行为：

- `build_generation_payload()` 主链路会消费 `StoryContext.character_locks`，把干净的角色外观约束、场景风格和 `negative_prompt` 分字段组装，而不是把旧的人设图 prompt 整段透传
- `StoryContext` 侧会优先消费干净的 `character_appearance_cache`，再回退到 `visual_dna`，最后才回退到角色描述中的可见外貌信息
- 运行时兼容增强层会结合 `build_character_reference_anchor()` 提供清洗后的角色参考锚点，并用 `infer_shot_view_hint()` 识别镜头中的 front / side / back 视角提示，生成诸如 `match the shot's front view` / `side profile` / `back view` 的朝向约束
- `build_character_reference_anchor()` 会清洗掉性格、命运、剧情摘要、studio/background 等非物理词，只保留体貌与默认服装；这些角色锚点与 `art_style`、`negative_prompt` 保持分离
- `infer_shot_view_hint()` 只负责从镜头文本和结构化视觉字段中推断朝向提示，不参与 `art_style` 或污染排除词拼装
- 因此完整运行链应理解为：`build_generation_payload()` 负责主字段组装，`build_character_reference_anchor()` / `infer_shot_view_hint()` 负责运行时角色锚点与朝向提示，两者共同构成最终的一致性注入层
- `art_style` 与 `negative_prompt` 分离，不再混写
- 场景缓存关键词未命中时，仍会回退到 `genre` 级风格规则

---

## 八、当前边界

- Step 3 剧本输出当前没有 `scene_intensity` 字段；Step 4 会要求输出，缺省时后端补 `"low"`
- 角色一致性当前是“结构化缓存 + `visual_dna` + 启发式回退”的组合，不是 DSPy/VLM 闭环
- Prompt 层已经支持 `last_frame_prompt` / `last_frame_url`，但不同视频 provider 的消费程度不一致

---

## 九、阅读顺序建议

1. `app/prompts/story.py`
2. `app/prompts/storyboard.py`
3. `app/prompts/character.py`
4. `app/services/story_llm.py`
5. `app/services/story_context_service.py`
6. `app/core/story_context.py`
