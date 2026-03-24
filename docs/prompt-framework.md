# Auto_media 提示词框架文档

> 更新日期：2026-03-24

---

## 一、总体架构

```
Step 1    灵感输入 ─── ANALYZE_PROMPT              # 要素审计，返回追问维度
Step 2    世界构建 ─── WB_SYSTEM_PROMPT             # 6 轮引导式问答
Step 2.5  角色锚定 ─── generate_character_image     # 生成参考图 → 提取 Visual DNA（详见 video-pipeline.md）
Step 3    剧本生成 ─── OUTLINE_PROMPT               # 大纲（角色 + 关系 + 分集）
                   └── SCRIPT_PROMPT               # 逐集导演分镜剧本（标注 scene_intensity）
                   └── REFINE_PROMPT / apply_chat   # 用户修改 → 局部更新
Step 4    分镜生成 ─── storyboard.SYSTEM_PROMPT     # 剧本 → 物理级 Shot List（注入 Visual DNA + 镜头流上下文）
Step 4.5  分镜审查 ─── Judge Agent                  # 逻辑/物理一致性检查（详见 video-pipeline.md）
Step 5    素材生成 ─── final_video_prompt → 视频 API # 后处理：强度分级 + Negative Prompt（详见 video-pipeline.md）
                   └── audio_reference → TTS / 音效管线
```

---

## 二、文件索引

| 文件 | 职责 |
|------|------|
| `app/prompts/story.py` | 剧本全流程 prompt 模板（Step 1-3）：ANALYZE / WB / OUTLINE / SCRIPT / REFINE / apply_chat |
| `app/prompts/storyboard.py` | 分镜导演 prompt（Step 4）：SYSTEM_PROMPT + USER_TEMPLATE |
| `app/prompts/character.py` | 角色视觉 prompt（Step 2.5/5）：build_character_prompt + build_character_section |
| `app/prompts/__init__.py` | 统一导出入口 |
| `app/services/story_llm.py` | 剧本业务逻辑（LLM 调用 + DB 读写，prompt 从 `app/prompts` 导入） |
| `app/services/storyboard.py` | 分镜业务逻辑（LLM 调用 + Shot 解析，prompt 从 `app/prompts` 导入） |
| `app/services/image.py` | 图片生成逻辑（API 调用，prompt 从 `app/prompts` 导入） |
| `app/schemas/storyboard.py` | Shot / CameraSetup / VisualElements / AudioReference 数据模型 |
| `app/services/llm/` | LLM 多厂商适配层（OpenAI / Claude / Qwen / Zhipu / Gemini） |

> 后端处理逻辑（Visual DNA 注入、Negative Prompt、Judge Agent、起始帧策略、强度切换）详见 [video-pipeline.md](video-pipeline.md)。

---

## 三、Step 1 — 灵感要素审计（ANALYZE_PROMPT）

**位置**：`story_llm.py:20` | **触发**：用户提交初始灵感

**输入**：`{idea}` 用户灵感、`{genre}` 风格、`{tone}` 基调

**输出**：

```json
{
  "analysis": "简短分析（1-2句，指出最大缺失要素）",
  "suggestions": [
    {
      "label": "追问维度名称",
      "options": ["选项A", "选项B", "选项C"]
    }
  ],
  "placeholder": "引导用户自由输入的提示语"
}
```

---

## 四、Step 2 — 世界构建 6 轮问答（WB_SYSTEM_PROMPT）

**位置**：`story_llm.py:136` | **触发**：灵感审计完成后

**规则**：每轮聚焦一个维度、必须给 3 个选项、强制 6 轮、禁止开放式问题。

**维度优先级**：时代背景 → 权力结构 → 主角处境 → 核心冲突 → 主要人物 → 情感基调

**输出**：

```json
{
  "status": "questioning",
  "question": {
    "type": "options",
    "text": "问题文本",
    "options": ["选项A", "选项B", "选项C"],
    "dimension": "当前维度"
  },
  "world_summary": null
}
```

第 6 轮返回 `"status": "complete"` 并在 `world_summary` 中写入完整世界观 + 人物设定。

---

## 五、Step 3 — 剧本生成

### 5.1 OUTLINE_PROMPT — 大纲

**位置**：`story_llm.py:45` | **输入**：`{selected_setting}` 完整世界观

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
    {"episode": 1, "title": "集标题", "summary": "剧情概要，包含具体场景和冲突"}
  ]
}
```

### 5.2 SCRIPT_PROMPT — 导演分镜剧本

**位置**：`story_llm.py:65` | **输入**：`{episode}` `{title}` `{characters_text}` `{summary}`

每集 3-5 个场景，情绪弧线：开场建立 → 发展递进 → 高潮爆发 → 收尾余韵。

每个场景必须标注 `scene_intensity`，后续 Step 4 根据此标签动态切换分镜 Prompt 策略：

```json
{
  "episode": 1,
  "title": "集标题",
  "scenes": [
    {
      "scene_number": 1,
      "scene_intensity": "low | high",
      "environment": "时间/地点/天气（具象细节）",
      "lighting": "主光方向 + 色温 + 阴影特征",
      "mood": "情绪基调短语",
      "visual": "人物位置/动作/表情/镜头角度（不含对话，不含心理描写）",
      "key_actions": ["原子动作1", "原子动作2"],
      "shot_suggestions": ["景别+运动建议1", "景别+运动建议2"],
      "transition_from_previous": "硬切 / 叠化 / 声音先入（第一场景为 null）",
      "audio": [
        {"character": "角色名或旁白", "line": "台词内容"}
      ]
    }
  ]
}
```

**`scene_intensity` 判定规则**（在 SCRIPT_PROMPT 中注入）：
- `"high"`：系统觉醒、激烈冲突、情绪爆发、大招释放、决定性转折瞬间
- `"low"`：交代时间地点、角色行走、简单对话、日常过场

### 5.3 REFINE_PROMPT — 修改联动

**位置**：`story_llm.py:108` | **输入**：`{story_json}` `{change_type}` `{change_summary}`

判断角色列表 / 人物关系 / 剧情大纲 / 故事主题是否需更新，不受影响的返回 `null`。

```json
{
  "characters": null,
  "relationships": null,
  "outline": null,
  "meta_theme": null
}
```

### 5.4 apply_chat — 对话式局部修改

**位置**：`story_llm.py:398`

根据修改对象动态构建 prompt，从对话历史中提炼修改结果：

- 角色修改 → `{"description": "修改后的角色描述"}`
- 集数修改 → `{"title": "...", "summary": "..."}`

---

## 六、Step 4 — 工业级分镜导演（storyboard.SYSTEM_PROMPT）

> 将文学剧本翻译为物理级 AI 视频生成指令。这是整条管线中**最关键**的转换步骤。

### 6.1 三条核心转换法则

**法则 1：绝对物理客观化** — 严禁心理描写，全部转为摄像机可见的物理行为。

| 禁止（抽象） | 替换为（物理可见） |
|-------------|----------------|
| "他很愤怒" | "咬紧牙关，额头青筋暴起，胸口剧烈起伏" |
| "她感到恐惧" | "瞳孔骤缩，嘴唇微颤，双手攥紧衣角" |
| "气氛紧张" | "空气弥漫淡淡烟雾，窗外雷声隐隐" |

**法则 2：原子动作分解** — 每个 Shot 仅 1-2 个核心物理动作，时长 3-5 秒。

**法则 3：角色一致性嵌入** — 每个含角色的 Shot，`subject_and_clothing` 必须使用该角色的 **Visual DNA**（固定描述串），禁止 LLM 自由发挥外貌描述。Visual DNA 由 Step 2.5 生成并存储在 `character_images[name]["visual_dna"]` 中。

**法则 4：镜头流连续性** — 相邻镜头的背景和光影必须保持衔接。在 `final_video_prompt` 中，当场景未切换时，加入连续性短语（如 `maintaining the same office background as previous shot`、`continuing the warm golden-hour lighting from the previous frame`），避免跳戏。

### 6.2 镜头强度分级策略（scene_intensity）

后端根据 Step 3 中每个场景的 `scene_intensity` 标签，动态切换分镜 Prompt 策略。把好钢用在刀刃上——普通镜头追求稳定不崩，高潮镜头榨干算力。

#### Low — 普通日常（过场/交代镜头）

**核心诉求**：稳定、不出错、交代清楚物理关系。越简单越不容易触发画面崩坏。

| 维度 | 策略 |
|------|------|
| 景别 | MWS / MS / WS 为主，避免极端景别 |
| 运镜 | Static 或简单 Pan，禁止复杂运镜组合 |
| 光影 | 自然光、均匀照明、标准白平衡，不使用戏剧性打光词汇 |
| 人物描述 | 简洁：服装颜色 + 基本动作，无需材质/纹理细节 |
| 渲染标签 | `cinematic, 4k resolution`（降级，节省算力和成本） |
| Prompt 长度 | 中等（60-100 词），指令明确，不堆砌参数 |

**示例**：

```json
{
  "shot_id": "scene2_shot1",
  "estimated_duration": 3,
  "scene_intensity": "low",
  "storyboard_description": "日间，李明拿着咖啡走进明亮的现代办公室，过场镜头。",
  "camera_setup": {
    "shot_size": "MWS",
    "camera_angle": "Eye-level",
    "movement": "Static"
  },
  "visual_elements": {
    "subject_and_clothing": "Li Ming, 25-year-old Asian man, light blue striped shirt, black trousers",
    "action_and_expression": "Walking steadily forward holding a white paper coffee cup, calm and slightly tired expression",
    "environment_and_props": "Modern open-plan office, blurry glowing monitors and potted plants in background",
    "lighting_and_color": "Even bright natural morning light from windows, no harsh shadows, clean realistic colors"
  },
  "final_video_prompt": "Medium Wide Shot, Eye-level, Static. A 25-year-old Asian man in a light blue striped shirt and black trousers walks steadily forward holding a white paper coffee cup, calm slightly tired expression. Modern open-plan office with blurry glowing monitors and potted plants. Even bright natural morning light from windows, clean realistic colors. Cinematic, 4k resolution, photorealistic, --ar 16:9",
  "audio_reference": {
    "type": null,
    "content": null
  },
  "mood": "mundane and routine",
  "scene_position": "establishing"
}
```

#### High — 高潮核心（Money Shot / 情绪爆发）

**核心诉求**：视觉冲击力、极高画质、微观细节。堆砌摄影参数、材质和物理描述，榨干渲染精度。

| 维度 | 策略 |
|------|------|
| 景别 | ECU / CU 为主，微距镜头，极端景别 |
| 运镜 | Slow Dolly in + Slow motion 120fps 等复合运镜 |
| 光影 | Chiaroscuro、Rim lighting、Split lighting 等戏剧性打光，明确色温和阴影 |
| 人物描述 | 微观级：皮肤毛孔、冷汗滑落轨迹、瞳孔反光内容、服装褶皱纹理 |
| 渲染标签 | `masterpiece, 8k resolution, shot on ARRI Alexa 65 macro lens`（全力渲染） |
| Prompt 长度 | 长（120-180 词），密集堆砌物理参数 |

**示例**：

```json
{
  "shot_id": "scene5_shot3",
  "estimated_duration": 4,
  "scene_intensity": "high",
  "storyboard_description": "李明被羞辱后猛然抬头，瞳孔剧烈收缩，眼中闪现蓝色系统数据流。命运转折的决定性瞬间。",
  "camera_setup": {
    "shot_size": "ECU",
    "camera_angle": "Eye-level",
    "movement": "Slow Dolly in"
  },
  "visual_elements": {
    "subject_and_clothing": "Extreme close-up of Li Ming's face, ultra-detailed skin texture with visible pores, messy black bangs falling over forehead, a single drop of cold sweat forming at the temple",
    "action_and_expression": "Eyes snapping wide open abruptly, eyelids trembling, pupils constricting violently in shock, no body movement — pure facial micro-expression explosion",
    "environment_and_props": "Completely dark background, severely out-of-focus with extremely shallow depth of field, all attention on the face",
    "lighting_and_color": "Sudden intense cold-blue holographic light from front off-screen illuminating face, dark pupil clearly reflecting scrolling glowing blue digital code, high contrast chiaroscuro, subsurface scattering on skin, cyberpunk dramatic tension"
  },
  "final_video_prompt": "Extreme Close-Up macro shot, Eye-level, Slow Dolly in, Slow motion 120fps. Young Asian man's face in ultra-detail, visible skin pores, messy black bangs, a single drop of cold sweat rolling down temple. Eyes snapping wide open, eyelids trembling, pupils constricting violently in pure shock. Completely dark severely out-of-focus background, extremely shallow depth of field. Sudden intense cold-blue holographic light from front off-screen, dark pupil perfectly reflecting scrolling glowing blue digital code. High contrast chiaroscuro, subsurface scattering on skin. Masterpiece, 8k resolution, highly detailed, photorealistic, shot on ARRI Alexa 65 macro lens, --ar 16:9",
  "audio_reference": {
    "type": "sfx",
    "content": "尖锐的电子蜂鸣声渐强"
  },
  "mood": "shocking revelation",
  "scene_position": "climax"
}
```

#### 分级对比

| 维度 | Low（日常过场） | High（高潮核心） |
|------|---------------|----------------|
| 渲染分辨率 | 4k | 8k |
| Prompt 长度 | 60-100 词 | 120-180 词 |
| 光影复杂度 | 自然光 / 均匀照明 | Chiaroscuro / Rim / Volumetric |
| 动作精度 | "走路" "拿东西" | "瞳孔收缩" "冷汗滑落轨迹" |
| 材质描述 | 颜色级（"蓝色衬衫"） | 纹理级（"粗糙褶皱的深灰廉价西装"） |
| 运镜 | Static / 简单 Pan | Slow Dolly in + Slow motion 120fps |
| 渲染标签 | `cinematic, 4k` | `masterpiece, 8k, ARRI Alexa 65 macro lens` |
| API 成本 | 低 | 高（约 3-5x） |

#### 后端分发逻辑

在 `parse_script_to_storyboard()` 调用前，根据场景的 `scene_intensity` 注入不同的渲染标签后缀：

```python
RENDER_TAGS = {
    "low": "Cinematic, 4k resolution, photorealistic, --ar 16:9",
    "high": "Masterpiece, 8k resolution, highly detailed, photorealistic, shot on ARRI Alexa 65 macro lens, --ar 16:9",
}
```

### 6.3 final_video_prompt 万能公式

```
[景别] + [拍摄角度] + [镜头运动]
+ [主体外貌与服装]
+ [主体动作/微表情]
+ [环境/道具]
+ [光影/色彩]
+ [渲染标签]
```

### 6.4 专业术语字典

| 类别 | 术语 |
|------|------|
| **景别** | ECU, CU, MCU, MS, MWS, WS, EWS, OTS |
| **角度** | Eye-level, Low angle, High angle, Dutch angle, Bird's eye, Worm's eye |
| **运镜** | Static, Slow Dolly in, Dolly out, Pan left/right, Tilt up/down, Tracking shot, Handheld subtle shake, Crane up/down |
| **光影** | Rembrandt lighting, Rim lighting, Volumetric lighting, Harsh cold white light, Warm golden hour, Split lighting, Silhouette lighting, Cyberpunk neon lighting, Chiaroscuro |
| **渲染标签** | Cinematic, 8k resolution, highly detailed, photorealistic, shot on ARRI Alexa 65, 35mm lens, --ar 16:9 |

### 6.5 Shot 输出结构

采用 Chain-of-Thought 结构化拆分：LLM 先逐项填写 `camera_setup` 和 `visual_elements`，再基于这些字段组装 `final_video_prompt`，防止遗漏任何维度。

```json
{
  "shot_id": "scene1_shot2",
  "estimated_duration": 3,
  "scene_intensity": "high",
  "storyboard_description": "牧之身着黑色机能风衣，从暗巷阴影中缓步走出，蓝色霓虹侧逆光勾勒轮廓。",
  "camera_setup": {
    "shot_size": "MS",
    "camera_angle": "Low angle",
    "movement": "Static"
  },
  "visual_elements": {
    "subject_and_clothing": "Mu Zhi, 28-year-old East Asian man, short black hair with undercut, wearing a black tactical trench coat with high collar and matte metallic buckles, dark combat boots, lean athletic build, scar on left eyebrow",
    "action_and_expression": "Stepping forward from deep shadow into dim light, eyes narrowed with determination, lips pressed into a thin line, left hand brushing the coat open slightly",
    "environment_and_props": "Cyberpunk alley background falling into soft bokeh, wet pavement reflecting his silhouette, faint steam around his ankles",
    "lighting_and_color": "Strong blue rim lighting from behind outlining his silhouette, faint warm fill from a neon sign on his face, deep shadows across torso, teal-and-amber split color grading"
  },
  "final_video_prompt": "Medium Shot, Low angle, Static. Mu Zhi, a 28-year-old East Asian man with short black hair and undercut, wearing a black tactical trench coat with high collar and matte metallic buckles, dark combat boots, lean athletic build, scar on left eyebrow. Stepping forward from deep shadow, eyes narrowed with determination, lips pressed thin, left hand brushing the coat open. Cyberpunk alley in soft bokeh, wet pavement reflecting his silhouette, faint steam around ankles. Strong blue rim lighting from behind, faint warm neon fill on face, deep torso shadows, teal-and-amber split color grading. Cinematic, 8k resolution, highly detailed, photorealistic, shot on ARRI Alexa 65, 35mm lens, --ar 16:9",
  "audio_reference": {
    "type": null,
    "content": null
  },
  "mood": "tense and determined",
  "scene_position": "development"
}
```

**字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `shot_id` | string | `scene{N}_shot{M}` |
| `estimated_duration` | int | 时长（秒），3-5 |
| `scene_intensity` | string | `low`（日常过场）/ `high`（高潮核心），继承自 SCRIPT_PROMPT 的场景标签 |
| `storyboard_description` | string | 中文画面简述，供前端展示 |
| `camera_setup.shot_size` | string | 景别枚举 |
| `camera_setup.camera_angle` | string | 拍摄角度枚举 |
| `camera_setup.movement` | string | 运镜方式枚举 |
| `visual_elements.subject_and_clothing` | string | 主体完整物理描述（英文） |
| `visual_elements.action_and_expression` | string | 原子物理动作 + 微表情（英文） |
| `visual_elements.environment_and_props` | string | 环境/道具/景深（英文） |
| `visual_elements.lighting_and_color` | string | 光源/色温/阴影/色彩倾向（英文） |
| `final_video_prompt` | string | 按公式组装的完整英文 prompt，直接送入视频生成 API |
| `audio_reference.type` | string? | `dialogue` / `narration` / `sfx` / `null` |
| `audio_reference.content` | string? | 原文台词/旁白/音效描述 |
| `mood` | string | 情绪基调英文短语 |
| `scene_position` | string | `establishing` / `development` / `climax` / `resolution` |

### 6.6 节奏与时长规则

| 类型 | 时长 | 景别倾向 |
|------|------|---------|
| 环境建立（无动作） | 4s | WS / EWS |
| 动作镜头 | 3s | MS / MWS |
| 对话镜头 | 4-5s | MCU / OTS |
| 情绪特写 | 3-4s | CU / ECU |

- 每个新场景首个 Shot 必须用 WS 或 EWS 建立环境
- 连续 2 个 Shot 不得使用相同景别或相同运镜
- 运镜匹配情绪：Static → 紧张、Slow Dolly in → 亲密、Handheld → 紧迫、Tracking → 追逐

### 6.7 USER_TEMPLATE

```
Convert this Audio-Visual Script into physically-precise storyboard shots.

{character_section}

---
{script}
---

IMPORTANT:
- For each character, use the EXACT Visual DNA description provided above in subject_and_clothing. Do NOT invent or modify character appearance.
- For each shot, FIRST fill in camera_setup and visual_elements fields completely.
- THEN compose final_video_prompt by assembling all visual_elements following the mandatory formula.
- The final_video_prompt must be self-contained: a reader seeing ONLY this field must fully understand what to render.
- When consecutive shots share the same scene, add continuity phrases (e.g. "maintaining the same background", "continuing the lighting from previous frame").

Return a JSON array of shots only.
```

---

## 七、Step 2.5 / Step 5 — 角色设计图与 Visual DNA（image.py）

**位置**：`image.py:88`，`_build_character_prompt(name, role, description)`

### 7.1 角色参考图生成 Prompt

根据 role 注入视觉基调：

| 角色类型 | 注入提示 |
|----------|---------|
| 反派 / villain | `villain, sinister expression, dark presence` |
| 主角 / protagonist | `protagonist, determined expression, heroic bearing` |
| 配角 / supporting | `supporting character, approachable expression` |

**输出 prompt**：

```
Character portrait of {name}, {role_cue},
character description: {description},
unique individual character design, distinctive appearance,
cinematic portrait, highly detailed, professional character concept art,
clean background, studio lighting, 8k resolution, photorealistic
```

### 7.2 Visual DNA（视觉锚点）

**问题**：LLM 每次生成分镜时自由发挥角色外貌描述，导致同一角色跨镜头不一致（发型变化、服装扣子数变化等）。

**解决方案**：在 Step 2.5 生成角色参考图后，提取一段固定的英文外貌描述串（Visual DNA），存入 `character_images[name]["visual_dna"]`，后续所有分镜中该角色的 `subject_and_clothing` 字段强制使用此固定描述，不让 LLM 自由发挥。

**Visual DNA 格式要求**（固定英文短语串，约 30-50 词）：

```
{age}-year-old {ethnicity} {gender}, {hair_style} {hair_color} hair,
{distinguishing_feature}, wearing {clothing_material} {clothing_color} {clothing_type}
with {clothing_detail}, {body_type} build, {other_marks}
```

**示例**：

```
28-year-old East Asian man, short black hair with undercut,
distinct scar on left eyebrow, wearing matte black tactical techwear jacket
with orange nylon straps, dark combat boots, lean athletic build
```

**存储位置**：`story.character_images` JSON 字段

```json
{
  "牧之": {
    "image_url": "/media/characters/xxx.png",
    "image_path": "media/characters/xxx.png",
    "portrait_prompt": "Character portrait of 牧之...",
    "visual_dna": "28-year-old East Asian man, short black hair with undercut, distinct scar on left eyebrow, wearing matte black tactical techwear jacket with orange nylon straps, dark combat boots, lean athletic build"
  }
}
```

**注入方式**：在 `_build_character_section()` 中，将 `visual_dna` 作为强制约束传给分镜 LLM（替代让 LLM 自行描述角色外貌）。具体注入逻辑详见 [video-pipeline.md](video-pipeline.md)。

> **替代方案**：如视频 API 支持换脸功能（如 Kling FaceSwap），可在视频生成后统一替换角色面部，无需在 Prompt 层面保持一致性。两种方案可并用。

---

## 八、LLM 适配层（`app/services/llm/`）

所有 prompt 通过统一接口发送：

```
provider.complete(system_prompt, user_message) -> str
provider.complete_with_usage(system_prompt, user_message) -> (str, usage)
```

支持：OpenAI / Claude / Qwen（DashScope） / Zhipu（GLM） / Gemini

---

## 九、Shot Schema 定义（`app/schemas/storyboard.py`）

```python
from pydantic import BaseModel, Field
from typing import List, Optional


class CameraSetup(BaseModel):
    shot_size: str = Field(description="EWS/WS/MWS/MS/MCU/CU/ECU/OTS")
    camera_angle: str = Field(description="Eye-level/Low angle/High angle/Dutch angle/Bird's eye/Worm's eye")
    movement: str = Field(description="Static/Slow Dolly in/Dolly out/Pan left/Pan right/Tilt up/Tilt down/Tracking shot/Handheld subtle shake/Crane up/Crane down")


class VisualElements(BaseModel):
    subject_and_clothing: str = Field(description="主体完整物理描述")
    action_and_expression: str = Field(description="1-2 个原子物理动作 + 微表情")
    environment_and_props: str = Field(description="环境/道具/前后景/景深")
    lighting_and_color: str = Field(description="光源/色温/阴影/色彩倾向")


class AudioReference(BaseModel):
    type: Optional[str] = Field(default=None, description="dialogue/narration/sfx")
    content: Optional[str] = Field(default=None, description="原文台词或音效描述")


class Shot(BaseModel):
    shot_id: str = Field(description="scene{N}_shot{M}")
    estimated_duration: int = Field(default=4, description="时长（秒），3-5")
    scene_intensity: str = Field(default="low", description="low=日常过场 / high=高潮核心")
    storyboard_description: str = Field(description="中文画面简述，供前端展示")
    camera_setup: CameraSetup
    visual_elements: VisualElements
    final_video_prompt: str = Field(description="完整英文 Prompt，直送视频生成 API")
    audio_reference: Optional[AudioReference] = Field(default=None)
    mood: Optional[str] = Field(default=None)
    scene_position: Optional[str] = Field(default=None)


class Usage(BaseModel):
    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)


class Storyboard(BaseModel):
    shots: List[Shot]
    usage: Optional[Usage] = Field(default=None)
```

---

## 十、旧格式兼容（`_parse_shots` 过渡期适配）

当前代码中 `_parse_shots()` 用 `Shot(**item)` 直接解析 LLM 输出。为了过渡期同时支持旧格式，增加映射逻辑：

| 旧字段 | 新字段 | 映射 |
|--------|--------|------|
| `visual_description_zh` | `storyboard_description` | 重命名 |
| `visual_prompt` | `final_video_prompt` | 重命名，内容公式化增强 |
| `camera_motion` | `camera_setup.movement` | 提升为嵌套对象 |
| `shot_size` (顶层) | `camera_setup.shot_size` | 移入嵌套对象 |
| `dialogue` | `audio_reference.content` | 提升为嵌套对象 |

```python
def _parse_shots(raw: str) -> List[Shot]:
    cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
    data = json.loads(cleaned)
    shots = []
    for item in data:
        if "visual_prompt" in item and "final_video_prompt" not in item:
            item["final_video_prompt"] = item.pop("visual_prompt")
        if "visual_description_zh" in item and "storyboard_description" not in item:
            item["storyboard_description"] = item.pop("visual_description_zh")
        if "camera_motion" in item and "camera_setup" not in item:
            item["camera_setup"] = {
                "shot_size": item.pop("shot_size", "MS"),
                "camera_angle": "Eye-level",
                "movement": item.pop("camera_motion"),
            }
        if "dialogue" in item and "audio_reference" not in item:
            dlg = item.pop("dialogue")
            item["audio_reference"] = {
                "type": "dialogue" if dlg else None,
                "content": dlg,
            }
        if "visual_elements" not in item:
            item["visual_elements"] = {
                "subject_and_clothing": "",
                "action_and_expression": "",
                "environment_and_props": "",
                "lighting_and_color": "",
            }
        shots.append(Shot(**item))
    return shots
```

---

## 十一、设计原则

1. **中英文分工**：叙事 prompt 用中文，视觉/分镜 prompt 用英文（主流视觉模型对英文 Tag 解析最精准）。
2. **全程 JSON**：所有 prompt 要求纯 JSON 返回，前端直接解析，禁止额外文字。
3. **Chain-of-Thought 防遗漏**：`visual_elements` 4 子字段强制 LLM 逐项填写人物/动作/环境/光影，再组装 `final_video_prompt`，比单一字段遗漏率从 ~30% 降至 ~5%。
4. **前端可编辑性**：`camera_setup` 3 子字段对应 Vue 下拉框，用户微调后重新拼接 prompt，无需重调 LLM。
5. **物理客观化**：视频模型无法渲染"他很伤心"，但可以渲染"瞳孔放大、嘴角下撇、手指攥紧衣角"。
6. **音频解耦**：`audio_reference.type` 区分 dialogue / narration / sfx，后端按类型分发 TTS 或音效管线。
7. **Visual DNA 锚定**：角色外貌使用 Step 2.5 提取的固定描述串，禁止 LLM 自由发挥，从 Prompt 层面解决跨镜头角色漂移。
8. **镜头流连续性**：同场景相邻 Shot 在 `final_video_prompt` 中加入衔接短语，避免背景/光影跳戏。
9. **模块化更新**：REFINE_PROMPT 只更新受影响模块，其余返回 `null`，避免过度重写。
10. **镜头强度分级**：`scene_intensity` 在 SCRIPT_PROMPT 阶段标注，分镜阶段动态注入不同渲染标签（low=4k / high=8k+macro），API 成本和画质的最优平衡。

> 后端处理层面的质量控制（Negative Prompt 注入、Judge Agent 审查、起始帧策略、build_final_prompt 组装逻辑）详见 [video-pipeline.md](video-pipeline.md)。

---

## 十二、提示词集中管理（已完成）

### 重构概述

所有提示词已从业务逻辑文件中提取到独立的 `app/prompts/` 目录，按管线阶段组织：

```
app/prompts/
├── __init__.py       (45行)   统一导出入口
├── story.py          (209行)  Step 1-3：ANALYZE / WB / OUTLINE / SCRIPT / REFINE + build_apply_chat_prompt
├── storyboard.py     (117行)  Step 4：SYSTEM_PROMPT + USER_TEMPLATE
└── character.py      (54行)   Step 2.5/5：build_character_prompt + build_character_section
```

### 业务文件变化

| 文件 | 重构前 | 重构后 | 变化 |
|------|--------|--------|------|
| `services/story_llm.py` | 462 行（含 5 个 prompt 常量 + apply_chat 模板） | 315 行（纯业务逻辑） | -147 行 |
| `services/storyboard.py` | 179 行（含 SYSTEM_PROMPT + _build_character_section） | 47 行（纯业务逻辑） | -132 行 |
| `services/image.py` | 186 行（含 _build_character_prompt） | 166 行（纯业务逻辑） | -20 行 |

### 导入方式

```python
# story_llm.py
from app.prompts.story import (
    ANALYZE_PROMPT, WB_SYSTEM_PROMPT, WB_USER_TEMPLATE,
    OUTLINE_PROMPT, SCRIPT_PROMPT, REFINE_PROMPT,
    build_apply_chat_prompt,
)

# storyboard.py
from app.prompts.storyboard import SYSTEM_PROMPT, USER_TEMPLATE
from app.prompts.character import build_character_section

# image.py
from app.prompts.character import build_character_prompt
```

### 迁移中处理的陷阱

1. **`WB_USER_TEMPLATE`**：原 `world_building_start()` 中的内联 f-string `f"种子想法：{idea}..."` 已提取为独立模板常量，改用 `.format(idea=idea)` 调用。
2. **`build_apply_chat_prompt()`**：原 `apply_chat()` 中的动态 prompt 构建（含 `json.dumps` + `{{}}` 转义花括号）已封装为独立函数，模板中 JSON 花括号用 `{{` `}}` 转义以兼容 `.format()`。
3. **`world_building_turn()`**：不引用任何 prompt 常量（从 DB 读 `wb_history`），无需迁移。
4. **`chat()`**：纯透传函数，无自定义 prompt，无需迁移。
