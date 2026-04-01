# AutoMedia 提示词框架文档

> 更新日期：2026-04-01
>
> 当前口径：按仓库现有代码同步，区分“已落地默认行为”和“兼容字段/回退行为”。

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

Step 4.5 场景参考图
  build_episode_environment_prompts()

Step 5   运行期一致性拼装
  build_story_context()
  build_generation_payload()

Step 6   过渡视频
  _build_transition_prompt()
  generate_transition_video()
```

---

## 二、文件索引

| 文件 | 作用 |
|------|------|
| `app/prompts/story.py` | Step 1-3 主 prompt 模板 |
| `app/prompts/storyboard.py` | Step 4 分镜导演 prompt |
| `app/prompts/character.py` | 角色三视图设定图 prompt |
| `app/services/story_llm.py` | 灵感分析、世界构建、大纲、剧本、chat、refine、apply-chat |
| `app/services/storyboard.py` | 剧本转 Shot，兼容旧格式并补全缺省字段 |
| `app/services/scene_reference.py` | 环境图 prompt、环境分组与复用 |
| `app/services/story_context_service.py` | 角色外貌缓存、场景风格缓存提取 |
| `app/core/story_context.py` | 运行期角色/场景锚点清洗与 payload 拼装 |
| `app/core/story_assets.py` | 角色图、环境图、`source_scene_key` 辅助 |
| `app/routers/pipeline.py` | 过渡 prompt 组装与 transition 运行期入口 |

---

## 三、Step 1：灵感审计

**Prompt**：`ANALYZE_PROMPT`

**目标**：

- 审计世界观是否清晰
- 审计主角动机是否明确
- 审计核心冲突是否具备视觉表现力

**输出结构**：

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

- 无 API Key 时走 mock
- 成功后立即创建 `story_id`
- Step 1 只负责灵感审计，不负责大纲与人物资产

---

## 四、Step 2：世界构建

**Prompt**：`WB_SYSTEM_PROMPT` + `WB_USER_TEMPLATE`

**当前规则**：

- 每轮只问一个问题
- `question.type` 固定为 `options`
- 每轮必须给 3 个选项
- 必须问满 6 轮
- 第 6 轮完成时返回 `complete`
- 完成时把 `world_summary` 写入 `selected_setting`

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

- `_ensure_world_building_question_options()` 会为选项补齐兜底值
- 完成世界构建后会失效 `scene_style_cache`

---

## 五、Step 3：故事生成与修改

### 5.1 大纲生成

**Prompt**：`OUTLINE_PROMPT`

**输出结构**：

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
- 持久化时会由 Story 规范化逻辑补齐：
  - `characters[*].id`
  - `relationships[*].source_id / target_id`
- 写回大纲后会清空旧 `scenes`

### 5.2 剧本生成

**Prompt**：`SCRIPT_PROMPT`

**当前场景字段**：

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
      "visual": "人物位置/动作/镜头感",
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

- Step 3 已要求 `lighting / mood / key_actions / shot_suggestions / transition_from_previous`
- Step 3 当前不输出 `scene_intensity`
- `scene_intensity` 由 Step 4 分镜导演 prompt 负责

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
- refine 不允许返回缺失 `id` 的角色
- 写回后会按变更类型失效：
  - `characters` -> `character_appearance_cache`
  - `outline` -> `scene_style_cache`

### 5.4 对话式修改

**入口**：`build_chat_messages()` + `/api/v1/story/chat` + `build_apply_chat_prompt()` + `apply_chat()`

**当前支持模式**：

| 模式 | 展示格式 |
|------|------|
| `character` | `当前角色修改：...` / `对剧情的影响：...` |
| `episode` | `当前剧情修改：...` / `对后续剧情的影响：...` |
| `outline` | `当前大纲修改：...` / `联动影响：...` / `REFINE_JSON:{...}` |
| `generic` | 简短通用建议 |

**当前实现说明**：

- 聊天层和应用层都默认不允许改角色名和 `role`
- `apply_chat()` 从数据库读取权威对象后再写回
- 角色应用只改 `description`
- 集数应用只改 `title / summary`

---

## 六、Step 4：分镜导演 Prompt

**Prompt**：`app/prompts/storyboard.py`

### 6.1 当前强约束

- 严格忠于脚本，不发明剧情、人物和道具
- `image_prompt` 与 `final_video_prompt` 必须分离
- `image_prompt` 负责静态首帧
- `final_video_prompt` 负责短视频运动
- 若视频要求半身、双手、关键道具或明确空间关系，`image_prompt` 必须先把这些内容落进首帧，不能把缺失信息留给视频阶段“补全”
- `source_scene_key` 必须跟随 `SCENE SOURCE MAP`
- 若脚本或角色参考明确给出正面/侧面/背面朝向，必须保留
- 正常主镜头不围绕双帧设计
- `last_frame_prompt` 当前主线应保持 `null`

### 6.2 当前 `Shot` 结构

```json
{
  "shot_id": "scene1_shot1",
  "source_scene_key": "ep01_scene01",
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
  "last_frame_prompt": null,
  "audio_reference": {
    "type": "dialogue | narration | sfx | null",
    "content": "内容"
  },
  "mood": "情绪短语",
  "scene_position": "establishing | development | climax | resolution",
  "transition_from_previous": "过渡说明",
  "last_frame_url": null
}
```

### 6.3 后处理与兼容

`parse_script_to_storyboard()` 当前会：

- 兼容旧字段：
  - `visual_prompt -> final_video_prompt`
  - `visual_description_zh -> storyboard_description`
  - `shot_size / camera_motion -> camera_setup`
  - `dialogue -> audio_reference`
- 自动补齐缺失的 `visual_elements`
- 自动补齐缺失的 `scene_intensity = "low"`
- 根据脚本内容构建 `SCENE SOURCE MAP`
- 用映射回写 `source_scene_key`
- 规范化 camera movement
- 清空普通 shot 的：
  - `last_frame_prompt`
  - `last_frame_url`

这意味着：

- 当前主镜头链路已经明确收口到单首帧 I2V
- `last_frame_*` 只剩兼容字段，不再是运行期主数据
- 真正的 transition 双帧输入来自相邻主镜头视频抽帧，而不是 storyboard 里的 `last_frame_prompt / last_frame_url`

---

## 七、Step 4.5：场景参考图 Prompt

**入口**：`app/services/scene_reference.py::build_episode_environment_prompts()`

### 7.1 当前目标

- 按集聚合相似场景
- 每组只生成 1 张主环境图
- 环境图必须是纯环境，不包含人物表演

### 7.2 Prompt 口径

当前环境图 prompt 会强调：

- `Environment reference key art`
- `Pure environment plate only`
- `No characters, no faces, no bodies, no costumes, no action`

同时 negative prompt 会排除：

- `person / human / man / woman / child`
- `face / portrait / silhouette`
- `costume / weapon`
- `split composition / clutter`

### 7.3 当前运行方式

- 环境图结果写入 `episode_reference_assets`
- 同时按 `scene_key` 回填到 `scene_reference_assets`
- 复用优先使用 `reuse_signature`
- 老资产不足以精确命中时，会回退到环境锚点相似度判断

---

## 八、Step 5：运行期一致性与 Prompt 拼装

### 8.1 StoryContext 提取层

`story_context_service.py` 负责把 Story 中的长期资产整理成运行期可消费结构：

- `character_appearance_cache`
- `scene_style_cache`
- `art_style`
- 角色图中的 `visual_dna`

`build_story_context()` 最终构建：

- `character_locks`
- `scene_styles`
- `global_negative_prompt`
- `clean_character_section`

### 8.2 运行期主入口

`build_generation_payload()` 是图片/视频主链路统一入口，当前会产出：

```json
{
  "shot_id": "scene1_shot1",
  "image_prompt": "...",
  "final_video_prompt": "...",
  "source_scene_key": "ep01_scene01",
  "negative_prompt": "...",
  "reference_images": [
    {"kind": "character", "image_url": "...", "weight": 0.58},
    {"kind": "scene", "image_url": "...", "weight": 0.42}
  ]
}
```

主镜头 mainline 刻意不再输出 `last_frame_prompt`。当前真实运行时输入是：

- `image_prompt`
- `final_video_prompt`
- `negative_prompt`
- `reference_images`

### 8.3 当前拼装逻辑

`build_generation_payload()` 当前会同时处理：

1. 角色外观一致性
2. 场景风格补充
3. 全局 `art_style`
4. `negative_prompt`
5. `source_scene_key`
6. 命中的场景参考图
7. 参考图列表 `reference_images`
8. 首帧与视频约束对齐，避免视频要求的主体范围、手部或关键道具缺失在首帧之外

### 8.4 场景参考图如何进入主链路

运行期会先根据：

- `shot.source_scene_key`
- 或 `shot_id -> scene index`

找到命中的环境图资产，然后做两件事：

1. 生成一段 `scene_reference_extra`，并入 `image_prompt`
2. 将环境图作为 `reference_images` 中的 `scene` 参考

### 8.5 角色图如何进入主链路

运行期会从 `character_images` 中找到命中的角色设定图，并作为：

- `reference_images[0]`
- `kind = character`

同时仍会保留清洗后的角色外观锚点注入。

### 8.6 provider 兼容行为

图片服务当前支持把 `reference_images` 发给 provider。

如果 provider 对 `reference_images` 或 `reference_strengths` 返回 `400 / 422`：

- 服务会自动重试一次
- 重试时移除 `reference_images`
- 这样不会因为参考图能力缺失直接阻断主链路

---

## 九、主镜头视频 Prompt 规则

### 9.1 当前真实口径

- 主镜头视频统一单首帧 I2V
- `generate_videos_batch()` 固定传入 `last_frame_url=""`
- 即使老数据里仍有 `last_frame_url`，主链路也不会继续消费

### 9.2 `separated` / `chained` / `integrated`

| 策略 | Prompt 侧真实行为 |
|------|------|
| `separated` | 先图，再单首帧 I2V，再合成音频 |
| `chained` | 仍然是单首帧 I2V，只保留按场景分组执行节奏 |
| `integrated` | 当前先图后视频，不包含真正语音一体化 prompt 或 API |

---

## 十、过渡视频 Prompt

### 10.1 Prompt 来源

`app/routers/pipeline.py::_build_transition_prompt()` 当前会组合：

- `from_shot` 的收束状态
- `to_shot` 的开场状态
- `to_shot.transition_from_previous`
- 用户额外输入的 `transition_prompt`
- 统一的主题约束：保持人物、服装、环境、光线、摄像机逻辑连续

### 10.2 当前原则

- transition 是独立运行时资产，不回写为普通 Shot
- 双帧只存在于 `generate_transition_video()`
- 锚点帧必须由后端从相邻主镜头视频提取
- transition prompt 不直接拼接整段主镜头长 prompt，而是做短桥接

### 10.3 与主镜头的边界

- 主镜头：`image_prompt + final_video_prompt + negative_prompt + reference_images`
- 过渡视频：提取 `from_last` 和 `to_first` 两张帧图后，再调用双帧视频接口

---

## 十一、当前边界

- `last_frame_prompt / last_frame_url` 仍保留在 schema 中，但只是兼容字段
- 真正 integrated 视频语音一体化 prompt 未落地
- 角色一致性仍是“缓存 + Visual DNA + 启发式清洗”方案，不是 DSPy / VLM 闭环
- 过渡视频当前只有生成，没有独立删除接口

---

## 十二、阅读顺序建议

1. `app/prompts/story.py`
2. `app/prompts/storyboard.py`
3. `app/services/scene_reference.py`
4. `app/services/storyboard.py`
5. `app/services/story_context_service.py`
6. `app/core/story_context.py`
7. `app/routers/pipeline.py`
