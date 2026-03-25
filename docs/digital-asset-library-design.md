# 剧本视觉一致性引擎设计方案

> 修订日期：2026-03-25
>
> 目标：在同一个剧本的流水线执行过程中，自动保证所有镜头在画风、场景氛围、人物外貌上的视觉一致性。无需新增用户界面，纯后端实现。

---

## 一、结论

该方案在当前项目中可以实施，但原始草案里有几处与仓库现状不一致的假设，必须先修正再落地：

1. `world_summary` 当前真实落点是 `Story.selected_setting`，不是 `Story.meta["world_summary"]`。
2. 自动流水线、手动分镜、手动素材生成三条链路都要一起改，不能只改 `PipelineExecutor`。
3. `negative_prompt` 不能只补到 `generate_images_batch()`，`generate_image()` 与 `generate_videos_chained()` 也必须同步。
4. `Story.meta` 的写入不能依赖通用浅合并；需要专门的缓存写入/失效策略，避免覆盖原有 `meta.title/theme/...`。
5. 现有文档中已存在 `character_images[name]["visual_dna"]` 概念；本方案需要给出兼容策略，避免两套锚点来源并存后互相冲突。

本文档是按当前仓库实际结构修订后的可实施版本。

### 1.1 当前仓库已完成的前置修复

以下内容已经在当前仓库落地，不再属于本设计的待实现范围：

1. `frontend/src/api/story.js` 已导出共享 `getHeaders()`，`VideoGeneration.vue` 改为复用该函数，手动 Step5 会透传 `X-Art-Style`。
2. `/api/v1/image/*`、`/api/v1/video/*`、`/pipeline/{id}/generate-assets`、`/pipeline/{id}/render-video` 都已经可以消费 `X-Art-Style`。
3. `Shot` schema 已正式拆分为 `image_prompt`、`final_video_prompt`、`last_frame_prompt`，分镜 LLM 不再只产出单一 `visual_prompt`。
4. `app/services/storyboard.py` 的 `_postprocess_shot()` 会优先保留分镜 LLM 已生成的图片/视频 prompt，只做轻量归一化与兜底补全，不再无脑重组 prompt。
5. `PipelineExecutor` 当前通过 `_build_image_prompts()` 和 `_build_video_prompt()` 分别构造图片/视频阶段输入；两者共享角色增强策略，但不再复用同一个 prompt 字段。

因此本文档后续讨论的重点，不是“画风 header 怎么传”，而是更深一层的视觉一致性治理：去污染、角色锚点结构化、场景风格缓存和统一的分字段 prompt 组装。

### 1.2 对本轮评审建议的采纳结论

本轮外部评审整体方向正确，但在当前项目里不应“全部立刻硬上”。更合适的采纳口径如下：

1. **Prompt Caching 的前缀稳定性治理：采纳，且有必要。**
   这是缓存命中率的前置条件。只要后续要做 Prompt Caching，就必须先治理静态块里的时间戳、UUID、调试寄语等动态噪音。
2. **`negative_prompt` 自动改写成正向规则：不作为通用方案采纳。**
   对当前项目的多 provider 视频链路而言，自动改写风险大、可解释性差，也容易与 `final_video_prompt` 的连续性骨架冲突。更适合的做法是：只允许少量人工定义、经验证有效的正向 guardrails，不能从任意 negative 文本自动推导。
3. **`CharacterLock` 权重语法（如 SD/Flux 权重标签）：不作为基线方案采纳。**
   当前项目同时覆盖图片和视频、多厂商 provider，模型专属权重语法不具备通用性。Phase 1 应优先通过“只保留 immutable traits + 缩短角色块 + 调整拼接顺序”来降污染；若后续某个 provider 明确验证有效，再在适配层做定向增强。
4. **SQLite 并发写的 Retry/锁保护：采纳，但作为 repository 保护栏，不作为 Phase 1 阻塞项。**
   当前仓库已经有 `json_set(...)` 的局部更新先例，这是正确方向。若后续 appearance cache / scene cache 开始频繁写入，再在 helper 层补轻量 retry/backoff 即可。
5. **结构化 `messages` 演进：采纳，但分阶段实施。**
   当前代码里已经存在直接传 `messages` 的链路，也还保留 `BaseLLMProvider.complete(system, user)` 旧接口。适合先在高收益长上下文请求上落地，再逐步统一 provider 抽象，而不是一口气全仓替换。

### 1.3 模块化现状与重构口径

当前项目的模块化基础是存在的，但核心生成链路还没有真正收口。

现状判断：

- `provider factory`、`schema`、`repository` 这几层已经初步模块化
- 真正的核心耦合点仍集中在 prompt 组装与角色一致性链路
- 同一件事目前分散在 `prompts/*`、`storyboard.py`、`pipeline_executor.py`、`image.py`、`video.py` 多处共同决定

因此本文档的实施原则不是“先做功能，重构以后再说”，而是：

1. **本方案落地时，应同步完成最小必要的结构重构。**
   也就是把“统一上下文 + 分字段 payload 组装”抽成清晰模块，而不是继续在现有文件上叠加条件分支。
2. **重构边界要收敛。**
   本次只重构“生成链路核心模块”，不顺手扩大到全仓通用抽象、数据库大迁移、全 provider 接口统一重写。
3. **目标是提升结构质量，而不是制造一轮大面积改名。**
   优先消除重复 prompt 组装、角色增强重复注入、手动/自动链路分叉三类结构问题。

---

## 二、当前问题与真实链路

### 2.1 已确认存在的问题

| 类型 | 当前根因 | 现象 |
|------|------|------|
| 画风漂移 | 所有镜头统一追加 `art_style`，缺少场景级补充风格 | 宗门、山巅、战场的环境气质不够分化 |
| 场景漂移 | `final_video_prompt` 由分镜 LLM 逐镜头自由生成 | 同一地点在连续镜头中背景词不稳定 |
| 上游人物污染 | `build_character_section()` 直接把肖像 prompt 传给分镜 LLM | `studio lighting`、`clean background` 被写进场景镜头 |
| 下游人物污染 | `_enhance_prompt_with_character()` 再次把 portrait prompt 拼到镜头 prompt 末尾 | 污染词二次注入，且格式不利于图片/视频 API |
| Prompt 职责回退风险 | 当前 `image_prompt` / `final_video_prompt` / `last_frame_prompt` 已经分工明确，若一致性层回退成单一 prompt 重建，会破坏字段职责 | 图片首帧变成动态描述，视频动作提示又被静态环境段落冲淡 |
| 服装漂移 | 肖像 prompt 中的默认服装被所有镜头无条件继承 | 剧情明确换装时仍保留初始服装 |
| 多角色混融 | 多角色同框时外貌词简单拼接 | 角色特征串扰 |
| 手动链路分叉 | 手动页面实际同时存在 `/pipeline/*` 与 `/image/*`、`/video/*` 两套素材链路 | 若后续只改其中一套，自动/手动仍会继续分叉 |

### 2.2 当前项目中的真实注入链路

```text
build_character_prompt()                  # app/prompts/character.py
  -> 生成肖像 prompt（含 clean background / studio lighting）
  -> 写入 story.character_images[name]["prompt"]

build_character_section()                # app/prompts/character.py
  -> 将 portrait prompt 拼进 Character Reference
  -> parse_script_to_storyboard() 传给分镜 LLM

storyboard.SYSTEM_PROMPT / Law 2.5 + 3   # app/prompts/storyboard.py
  -> LLM 同时生成 image_prompt / final_video_prompt / last_frame_prompt
  -> 仍要求外观提示词 verbatim embed
  -> 三类 prompt 都可能被 portrait prompt 污染

_postprocess_shot()                      # app/services/storyboard.py
  -> 优先保留分镜 LLM 已生成的三类 prompt
  -> 只做轻量归一化、兼容旧字段、fallback 补全
  -> 这意味着运行期一致性方案必须做“分字段增强”，不能退回单一 prompt 重组

_enhance_prompt_with_character()         # app/services/pipeline_executor.py
  -> 再把 portrait prompt 拼到 image_prompt / final_video_prompt / last_frame_prompt 尾部
  -> 当前图片与视频已分字段输入，污染问题仍在，但分字段链路已成立
```

一致性引擎必须同时修复上游 `build_character_section()` 和下游 `_enhance_prompt_with_character()` 两个入口。

---

## 三、设计原则

### 3.1 保留双 Prompt 架构，而不是重新合并成一个 Prompt

不能把当前已经拆分好的 `image_prompt` 和 `final_video_prompt` 再重新揉成一个“万能 prompt”。

当前这几个字段的职责已经明确分化：

- `image_prompt`：静态首帧、构图、定格姿态、环境与光线
- `final_video_prompt`：镜头运动方式、主体可见动作、短时运动执行
- `last_frame_prompt`：显著状态变化镜头的结束参考帧

因此一致性引擎的目标不应是：

```text
build_shot_prompt() -> 同一个字符串同时喂给图片和视频
```

而应是：

```text
build_generation_payload(shot, ctx) -> {
  image_prompt,
  final_video_prompt,
  last_frame_prompt?,
  negative_prompt?
}
```

### 3.2 保留各字段自己的“连续性骨架”

不能丢弃分镜 LLM 已产出的 prompt 字段。它们已经分别承载了不同层面的信息：

- `image_prompt` 承载首帧静态状态
- `final_video_prompt` 承载动作与运镜
- `last_frame_prompt` 承载动作终态

因此正确策略不是“推翻重建”，而是分别增强：

```text
图片 prompt:
  [干净角色块] + [image_prompt 首帧骨架] + [scene_style image extra] + [base art_style]

视频 prompt:
  [干净角色块] + [final_video_prompt 运动骨架] + [scene_style video extra] + [base art_style]

尾帧 prompt:
  [干净角色块] + [last_frame_prompt 终态骨架] + [scene_style image extra] + [base art_style]
```

### 3.3 一致性上下文只在运行期集中构建

在流水线开始时构建 `StoryContext`，之后自动模式与手动模式都从中读取；但读取结果必须是“分字段增强”，不能覆盖分镜阶段已有的字段分工。

## 四、StoryContext 设计

```python
@dataclass
class CharacterLock:
    body_features: str
    default_clothing: str
    negative_prompt: str = ""

@dataclass
class SceneStyle:
    keywords: list[str]
    extra_prompt: str

@dataclass
class StoryContext:
    base_art_style: str
    scene_styles: list[SceneStyle]
    global_negative_prompt: str
    character_locks: dict[str, CharacterLock]
    clean_character_section: str
    cache_fingerprint: str = ""
```

### 4.1 字段来源

| 字段 | 当前正确来源 | 说明 |
|------|------|------|
| `base_art_style` | `Story.art_style` | 现有逻辑保留 |
| `scene_styles` | `Story.genre` + `Story.selected_setting` | `selected_setting` 才是当前 world summary 实际落点 |
| `character_locks` | `meta.character_appearance_cache` 优先，其次 `character_images.visual_dna`，最后 `characters.description` | 兼容新旧链路 |
| `clean_character_section` | 运行期动态生成 | 不再透传 portrait prompt |

### 4.2 `world_summary` 的修正规则

原始草案写 `Story.meta["world_summary"]`，这与当前仓库不一致。

当前项目里：

- 世界观问答完成后，完整总结写入 `Story.selected_setting`
- `wb_history` 仅保存对话历史
- `meta` 当前没有统一写入 `world_summary`

因此本方案落地时应按以下顺序取值：

```python
world_summary = (
    story.get("selected_setting")
    or (story.get("meta") or {}).get("world_summary", "")
)
```

如果未来希望规范化，可在后续版本把 world summary 同步写入 `meta["world_summary"]`，但这不是 Phase 1 前置条件。

### 4.3 静态块清洗与 `cache_fingerprint`

只要后续要接入 Prompt Caching，就不应直接把原始 `SYSTEM_PROMPT` / `selected_setting` / few-shot 文本原封不动送去做缓存判断。

推荐在 `app/core/story_context.py` 或其上层 request builder 中补一层静态块标准化：

```python
def get_cache_fingerprint(story_ctx: StoryContext, system_prompt: str, stable_blocks: list[str]) -> str:
    normalized_blocks = [normalize_cache_block(system_prompt), *map(normalize_cache_block, stable_blocks)]
    payload = "\n\n".join(block for block in normalized_blocks if block.strip())
    return sha256(payload.encode("utf-8")).hexdigest()
```

标准化时应主动剔除或归一化以下内容：

- 时间戳、`Generated at: ...`
- UUID / request id
- 调试用寄语、随机标语
- 与本轮请求强相关但不稳定的临时说明

说明：

- `cache_fingerprint` 主要用于调试、观测和缓存启用判断，不应用于业务分支决策
- 若静态前缀尚未稳定，宁可暂时关闭 caching，也不要让 provider 层去“猜测”哪些内容可缓存

---

## 五、角色锚点提取与存储策略

### 5.1 结构化提取

```python
APPEARANCE_EXTRACT_PROMPT = """
Extract physical appearance for image generation. Output JSON:
{
  "body": "immutable traits only: age, gender, hair color/style, eye color, skin tone, build. Max 25 words.",
  "clothing": "default outfit only. Max 15 words."
}
Exclude: emotions, personality, backstory, scene context, lighting, background, style tags.

Character: {name}（{role}）
Description: {description}
"""
```

### 5.2 推荐存储方式

推荐把 LLM 提取结果写入：

```json
Story.meta["character_appearance_cache"] = {
  "黎明": {
    "body": "young male, silver-white hair, ice blue eyes, slender build",
    "clothing": "white hanfu with blue cloud embroidery"
  }
}
```

同时兼容回填：

```json
Story.character_images["黎明"]["visual_dna"] = "young male, silver-white hair, ice blue eyes, slender build"
```

这样可以兼顾：

- 运行期需要结构化字段，便于拆分 `body` / `clothing`
- 旧文档和旧链路已经引用的 `visual_dna`
- 用户可能已经生成人设图的现状

这里要明确关系：

- `character_appearance_cache` 是运行期主缓存
- `visual_dna` 是兼容投影字段，不再是唯一真相源
- 当结构化缓存生成成功后，建议同步回填 `character_images[name]["visual_dna"]`

### 5.3 旧 `visual_dna` 的清理与投影策略

为避免前端、人设图链路和运行期缓存出现“双真相”，建议明确如下口径：

1. 一旦 `character_appearance_cache[name]` 存在，它就是唯一主数据源
2. `visual_dna` 只保留为兼容投影字段，应由结构化缓存单向覆盖
3. 若发现 `visual_dna` 与结构化缓存冲突，应以结构化缓存为准

推荐的过渡方式：

- 方案 A：提供一次性修复脚本，把已有 `visual_dna` 回填/规范化到 `character_appearance_cache`
- 方案 B：在读取 story 或生成人设图前做惰性修复
- 方案 C：在调试接口中显式暴露“当前主数据源来自哪里”

### 5.4 读取优先级

`build_story_context()` 中对每个角色的读取顺序应为：

1. `meta.character_appearance_cache[name]`
2. `character_images[name].visual_dna`
3. `characters[].description`

如果命中第 2 层，仅能直接作为 `body_features` 使用；`default_clothing` 仍应为空或再次提取。

---

## 六、场景风格来源

### 6.1 第一层：genre 内置规则

保留原设计，按 `Story.genre` 映射静态 `SceneStyle` 与全局 `negative_prompt`。

### 6.2 第二层：world summary 动态补充

`extract_scene_styles_from_world_summary()` 可以作为增强项保留，但输入应改为：

```python
extract_scene_styles_from_world_summary(
    world_summary=story.get("selected_setting", ""),
    genre=story.get("genre", ""),
)
```

缓存建议写入：

```json
Story.meta["scene_style_cache"] = [...]
```

---

## 七、Prompt 构建策略

### 7.1 核心公式

```text
图片正向 prompt:
  [干净角色块] + [image_prompt] + [scene_style image extra] + [art_style]

视频正向 prompt:
  [干净角色块] + [final_video_prompt] + [scene_style video extra] + [art_style]

尾帧正向 prompt:
  [干净角色块] + [last_frame_prompt] + [scene_style image extra] + [art_style]

负向 prompt:
  [portrait contamination terms] + [genre negative] + [single-character negative]
```

推荐运行期产物是一个 bundle，而不是单字符串：

```python
payload = build_generation_payload(shot, ctx)

payload = {
    "image_prompt": "...",
    "final_video_prompt": "...",
    "last_frame_prompt": "...",   # optional
    "negative_prompt": "...",     # optional
}
```

### 7.2 角色块构建

- 单角色：直接拼 `body_features` + `default_clothing`
- 多角色：优先使用自然语言位置关系，而不是生硬的 `Character 1 / Character 2` 标签
- 换装检测：按角色局部上下文判断，不对整个镜头全文做全局禁用

推荐的多角色组装方式：

```text
[Character A body & clothing] stands on the left, while
[Character B body & clothing] sits on the right
```

或：

```text
[Character A body & clothing] in the foreground,
[Character B body & clothing] slightly behind him
```

说明：

- 对现代扩散模型，空间关系描述通常比编号标签更自然
- 若底层模型对自然语言分离效果不佳，再退回 `Character 1 / Character 2` 作为兜底策略
- 角色名字应尽量贴近自己的外貌描述，减少属性绑定距离

属性绑定示例：

```text
BAD:
Character A and Character B are talking. A is wearing red, B is wearing blue.

GOOD:
Character A (wearing red) and Character B (wearing blue) are talking.
```

额外约束：

- `body_features` 必须只保留 immutable traits，不得携带 `pale skin under studio light` 这类会与场景光影冲突的描述
- 不把 `(trait:1.2)`、`[trait]` 等模型专属权重语法作为主链路标准
- 若后续某个图片 provider 明确验证“低权重 body_features”有效，应仅在适配层局部开启

### 7.3 `negative_prompt` 的使用边界

`negative_prompt` 是图片生成阶段能力，不应只写在设计稿中而不落实到调用链。

必须同步修改：

- `generate_images_batch()`
- `generate_image()`
- `generate_videos_chained()` 内部首帧生图调用

如果某图片服务不支持独立的 `negative_prompt` 参数，则在适配层中处理，不要直接把 negative 文本拼进正向 prompt。

视频阶段需要明确降级原则：

- 主流视频生成 API 往往不支持独立 `negative_prompt`，或支持非常弱
- 如果视频 provider 不支持独立 negative 参数，应直接丢弃 negative，不做文本硬拼接
- 不要把运行期自由文本 negative 机械改写成 `"do not include ..."` 或 `"avoid ..."` 之类的正向提示
- 若某类题材确实需要补充强约束，应维护少量人工校验过的正向 guardrails，并放入 `SceneStyle.extra_prompt` 或 provider 适配层。例如：

```text
strictly ancient Chinese architecture, no modern materials or urban elements
```

但这类 guardrail 必须满足：

- 来源是人工维护的 allowlist，不是从任意 negative 文本自动推导
- 语义与当前题材稳定一致，不与 `final_video_prompt` 主叙事冲突
- 仅对验证有效的 provider / 模式开启

- 视频阶段的一致性应主要依赖：
  - `build_generation_payload()` 生成的分字段正向 prompt
  - 首帧图片的准确性
  - chained 模式下的帧传递

### 7.4 图片与视频阶段都必须沿着“分字段”切换

当前项目里，运行期已经是“图片走 `image_prompt`，视频走 `final_video_prompt`，尾帧走 `last_frame_prompt`”的结构。如果一致性引擎只更新其中一个字段，污染与漂移会在其他字段中继续保留。

因此运行期应统一读取同一个 payload，但分别消费自己的字段：

```python
payload = build_generation_payload(s, ctx)

image_prompt = payload["image_prompt"]
video_prompt = payload["final_video_prompt"]
last_frame_prompt = payload.get("last_frame_prompt")
```

若视频提供方未来支持独立 negative 参数，再追加 `payload["negative_prompt"]`；在此之前，视频层默认只消费正向 prompt。

---

## 八、上游修复：干净版 Character Section

`build_character_section()` 不能再把 portrait prompt 直接传给分镜 LLM。

替代方式：

```python
def build_clean_character_section(character_locks: dict[str, CharacterLock],
                                  characters: list[dict]) -> str:
    lines = ["## Character Reference (maintain EXACT physical appearance across all shots)"]
    for char in characters:
        name = char.get("name", "")
        role = char.get("role", "")
        desc = char.get("description", "")
        lock = character_locks.get(name)

        lines.append(f"- **{name}**（{role}）：{desc}")
        if lock:
            lines.append(f"  Visual DNA (embed verbatim): {lock.body_features}")
        else:
            lines.append("  Visual DNA: use description conservatively, do not invent new traits")
    return "\\n".join(lines)
```

`parse_script_to_storyboard()` 应新增：

```python
character_section_override: Optional[str] = None
```

并按优先级：

```python
character_section = character_section_override or build_character_section(character_info)
```

---

## 九、影响范围与需同步修改的模块

本方案不是单文件改造，至少影响以下模块。

### 9.1 新增模块

1. `app/core/story_context.py`
   - `CharacterLock`
   - `SceneStyle`
   - `StoryContext`
   - `build_story_context()`
   - `build_generation_payload()`
   - `build_image_generation_prompt()`
   - `build_video_generation_prompt()`
   - `build_last_frame_generation_prompt()`
   - `build_negative_prompt()`
   - `build_clean_character_section()`
   - `character_appears_in_shot()`
   - `should_inject_clothing_for()`

### 9.2 现有模块改造

2. `app/services/pipeline_executor.py`
   - `run_full_pipeline()` 增加 `story_id`
   - 构建 `StoryContext`
   - `_build_image_prompts()` / `_build_video_prompt()` 改为委托 `build_generation_payload()`
   - `_enhance_prompt_with_character()` 标记 `@deprecated`，短期保留兼容签名

3. `app/services/storyboard.py`
   - `parse_script_to_storyboard()` 新增 `character_section_override`
   - 可选支持 `characters_in_shot`
   - `_postprocess_shot()` 与未来一致性层配合时，继续遵守“优先保留分镜 LLM 已生成字段，只做归一化与增强”

4. `app/routers/pipeline.py`
   - `/auto-generate` 透传 `story_id` 给 executor
   - `/storyboard` 在有 `story_id` 时也走 `StoryContext`
   - `/generate-assets` / `/render-video` 手动 pipeline 模式要消费同一个 `payload` 组装逻辑，但分别取自己的字段（图片取 `image_prompt`，视频取 `final_video_prompt`）

5. `app/routers/image.py` / `app/routers/video.py`
   - 当前已支持 `art_style` header
   - 后续要继续接入统一的 `build_generation_payload()`，而不是只做尾部样式追加

6. `app/services/image.py`
   - `generate_image()` 增加 `negative_prompt`
   - `generate_images_batch()` 增加 `negative_prompt`
   - `generate_character_image()` 是否增加 `negative_prompt` 可选，Phase 1 非必须

7. `app/services/video.py`
   - `generate_videos_chained()` 首帧生图调用需要透传 `negative_prompt`
   - 分离式/一体式视频 prompt 组装逻辑要与图片阶段共用同一份 `payload` 来源，但继续消费 `final_video_prompt`

8. `app/services/story_repository.py`
   - 增加专用缓存更新方法，不建议通过通用浅合并直接写 `meta`
   - 当前项目使用 SQLite，优先参考 `character_images` 的 `json_set(...)` 写法，在数据库层完成局部更新
   - 例如：
     - `upsert_story_meta_cache(story_id, key, value)`
     - `remove_story_meta_keys(story_id, keys)`

9. `app/routers/story.py` / `app/schemas/story.py`
   - 如果需要开放缓存调试或手动修复入口，补充 `meta` patch 能力
   - 若不开放 API，至少在文档中说明缓存只通过内部服务写入

10. `app/services/story_llm.py`
   - 当 `characters` 被 `patch/refine/apply_chat` 修改后，失效人物外貌缓存
   - 当 `selected_setting/genre` 变化后，失效场景风格缓存

11. `app/schemas/storyboard.py`（可选增强）
   - 新增 `characters_in_shot: list[str] = []`

12. `app/services/llm/base.py` 与各 provider 实现
   - 从 `system: str + user: str` 逐步演进到结构化 `messages: list[dict]`
   - Prompt Caching 由 provider 适配层按厂商能力处理，不能假设所有厂商都支持 `cache_control`

13. `app/services/storyboard.py` / `app/services/story_llm.py`
   - 在上层按“静态前缀在前，动态任务在后”构建 messages
   - 对世界观摘要、系统指令、few-shot 样本等稳定内容接入 Prompt Caching

### 9.3 本次实施应同步完成的结构重构

为了避免该方案最终变成“功能补丁散落在多个文件里”，实施时应把下面这些结构性动作与功能一起完成：

1. **抽出单一的生成组装入口。**
   新能力不再分别塞进 `pipeline_executor.py`、`image.py`、`video.py`；统一收口到 `app/core/story_context.py` 的 payload builder。
2. **明确模块职责边界。**
   - `prompts/*`：只负责 LLM 提示词模板
   - `storyboard.py`：只负责分镜解析、字段归一化、兼容旧格式
   - `story_context.py`：只负责运行期一致性上下文与 payload 组装
   - `image.py` / `video.py`：只负责调用下游生成服务
3. **弱化 router 层业务拼装。**
   `pipeline.py`、`image.py`、`video.py` 路由层只负责参数接入和流程编排，不再承担 prompt 决策逻辑。
4. **保留兼容层，但冻结旧入口继续扩散。**
   `_enhance_prompt_with_character()`、旧式 fallback prompt 仍可短期保留，但不再作为新增逻辑挂载点。
5. **自动链路与手动链路一起改。**
   本次不接受“先只改 auto-generate，手动后补”的做法，否则结构分叉会继续扩大。

---

## 十、缓存与 CRUD 策略

### 10.1 为什么不能直接依赖通用 `save_story(meta=...)`

当前仓库的 `save_story()` 是浅合并：

```python
merged = {**existing, **data, "id": story_id}
```

这意味着如果直接写：

```python
save_story(..., {"meta": {"character_appearance_cache": ...}})
```

会整块覆盖原来的 `meta`，从而丢失已有的 `title`、`theme`、`episodes` 等信息。

因此缓存相关数据应使用专门 helper，优先在 repository/数据库层完成局部更新，而不是在服务层四处手动读写拼装。

当前项目的推荐实现顺序：

1. 在 `story_repository.py` 增加专用 helper
2. 对 SQLite 使用 `json_set(...)` 完成局部更新
3. 如果未来迁移到 PostgreSQL，再切换为 `jsonb_set(...)`

服务层手动深合并只能作为过渡方案，不应成为长期标准做法。

并发保护建议：

- repository helper 内对 `database is locked` / `SQLITE_BUSY` 做 2 到 3 次短重试
- 退避时间保持在 50ms 到 200ms 量级，避免放大锁竞争
- 尽量保持单条 `json_set(...)` 更新，避免回退到 read-modify-write
- 当前 executor 主要是异步并发而非多线程并行，因此 retry 属于保护栏，不是 Phase 1 必须先解决的架构阻塞

### 10.2 推荐缓存键

```json
meta = {
  "character_appearance_cache": {...},
  "scene_style_cache": [...],
  "consistency_cache_version": 1
}
```

### 10.3 失效规则

| 触发事件 | 必须失效的缓存 |
|------|------|
| `characters` 修改 | `character_appearance_cache`，必要时同步清理 `character_images[*].visual_dna` |
| `genre` 修改 | `scene_style_cache` |
| `selected_setting` 修改 | `scene_style_cache` |
| 角色人设图重生成 | 不强制清空 appearance cache，但若重新生成时人工修正了外貌，应允许显式刷新 |

### 10.4 可选调试能力

为了便于排查“一致性失效”问题，建议至少保留一种方式查看当前缓存：

- 方案 A：内部日志输出 `StoryContext`
- 方案 B：增加只读调试接口
- 方案 C：在现有 `GET /story/{story_id}` 返回中直接观察 `meta`

---

## 十一、Prompt Caching 机制

### 11.1 为什么要接入

当前分镜与剧本相关的 LLM 请求中，存在大量“长且固定”的前缀内容，例如：

- 很长的 system prompt
- 长达数千字的世界观设定 / `selected_setting`
- 标准 few-shot 样本
- 固定格式的角色约束说明

这些内容在一次长剧本流水线中会被反复发送和重复编码。引入 Prompt Caching 的目标是：

1. 降低重复输入成本
2. 降低首字延迟（TTFT）
3. 减少超大 payload 带来的超时或网关拒收概率

### 11.2 机制边界

Prompt Caching 不是“无限扩容”机制，且必须遵守两条硬约束：

- 它可以减少重复大前缀的传输/计算成本
- 它可以提升长固定 prompt 的稳定性
- 但它不能突破模型本身的上下文窗口上限

也就是说：

- 如果总 prompt 已经超过模型 context limit，仍然需要裁剪、摘要或分段
- Prompt Caching 只能优化“长但仍在可接受范围内”的固定内容

除此之外，还必须遵守“前缀定律”：

- 缓存必须命中连续的头部 Token 序列
- 任何动态变量都必须放在 prompt 最后面
- 如果在长世界观设定前插入动态内容，后面的缓存会整体失效

因此消息排布必须始终遵循：

```text
[静态 System] -> [静态 Story Context] -> [静态 Few-shot] -> [动态 Current Task]
```

### 11.3 推荐缓存对象

优先缓存以下内容：

1. `SYSTEM_PROMPT`
2. world summary / `selected_setting`
3. 固定 few-shot 示例
4. 标准化角色规则块
5. 长篇但稳定的导演规则说明

不建议缓存：

- 当前轮用户输入
- 高频变化的镜头列表
- 临时拼接的 shot-level prompt

### 11.4 厂商差异：显式缓存 vs 隐式缓存

Prompt Caching 不是统一协议，不同 provider 差异很大：

| Provider 类型 | 机制 | 适配原则 |
|------|------|------|
| Anthropic / Claude | 显式缓存（Explicit） | 需要在指定内容块上打 `cache_control` |
| OpenAI / DeepSeek / 多数 OpenAI-compatible 服务 | 隐式缓存（Implicit） | 不需要也不应伪造 `cache_control`；只要前缀完全一致且足够长，系统会自动命中 |
| 不支持缓存的旧模型 | 无 | 忽略 caching 参数，正常请求 |

这意味着：

- 不能假设所有厂商都接受 `cache_control: {"type": "ephemeral"}`
- 对 OpenAI-compatible provider 强行塞 `cache_control` 很可能直接报错
- Prompt Caching 必须由 provider 适配层决定如何落地，而不是在业务层硬编码同一套 JSON 结构

### 11.5 起步阈值与启用条件

缓存前缀不能太短。

工程上建议采用以下规则：

- 只有当稳定前缀预计超过 `1024 tokens` 时才考虑启用缓存
- 不再使用“800 字”或“1200 字”这类过低且不稳定的字符阈值
- 对 Claude 这类显式缓存模型，过短文本打断点可能反而增加额外写缓存成本

实现上可先使用轻量级估算器，避免一开始就引入 provider 专属 tokenizer 依赖：

```python
def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 2)
```

说明：

- 这是启发式估算，只用于判断是否值得开启 caching
- 若后续某 provider 已有可靠 tokenizer，再在适配层替换为更精确实现

因此建议在实现中使用：

```python
estimated_prefix_tokens >= 1024
```

作为默认启用阈值。

### 11.6 接入位置

需在 FastAPI 后端构建请求体时，对“长且稳定”的消息块做缓存处理。

当前项目里的主要接入点：

- `app/services/storyboard.py`
- `app/services/story_llm.py`
- `app/services/llm/base.py`
- `app/services/llm/claude.py`
- `app/services/llm/openai.py`
- 其他 OpenAI-compatible provider 封装

### 11.7 接口设计建议：放弃单字符串，改为结构化 Messages

当前 `BaseLLMProvider` 只接受：

```python
complete(system: str, user: str, ...)
complete_with_usage(system: str, user: str, ...)
```

这对 Prompt Caching 不够，因为：

- 缓存通常附着在“消息块”级别，而不是单纯字符串级别
- provider 适配层无法可靠判断一整段 `user: str` 里哪部分是稳定前缀，哪部分是动态尾部
- 依赖正则或长度切割去猜 `stable_prefix` / `dynamic_suffix` 非常脆弱

因此长期上必须演进为结构化 `messages` 接口。

但结合当前仓库现状，更合理的实施顺序是：

1. 先在高收益长上下文链路（如 `storyboard`、world building、后续 appearance extraction）引入统一的 request builder
2. 让 request builder 显式区分静态块与动态块
3. 再逐步把 `BaseLLMProvider` 从 `system + user` 迁移到 `messages`

原因是当前仓库同时存在两类调用：

- 一类已经直接使用 OpenAI-compatible `messages=[...]`
- 一类仍依赖 `BaseLLMProvider.complete(system, user)`

因此“结构化 messages”应当是明确方向，但不适合写成所有 provider 在 Phase 1 一次性完成的硬要求

建议目标接口：

```python
complete_messages_with_usage(
    messages: list[dict],
    temperature: float = 0.3,
    enable_caching: bool = True,
)
```

上层调用方负责把静态前缀和动态输入拆开，例如：

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": selected_setting},
    {"role": "user", "content": FEW_SHOT_EXAMPLES},
    {"role": "user", "content": current_task},
]
```

### 11.8 Provider 兼容策略

不同 LLM provider 对 Prompt Caching 的支持程度不同，因此必须做适配层降级：

- 支持显式缓存的 provider：按原生格式注入缓存标记
- 采用隐式缓存的 provider：什么都不做，只保证 messages 顺序稳定
- 不支持的 provider：忽略 `enable_caching`，正常发送请求

也就是说，Prompt Caching 应是“可选增强”，不能成为请求成功的前置条件。

### 11.9 Anthropic 适配层参考

```python
def _format_messages_for_claude(messages: list[dict], enable_caching: bool) -> list[dict]:
    formatted = copy.deepcopy(messages)

    if enable_caching:
        # Claude 最多支持有限数量的缓存断点，优先给最后一个长静态块打标
        for msg in reversed(formatted):
            if msg["role"] in ("system", "user") and len(msg["content"]) > 2000:
                if isinstance(msg["content"], str):
                    msg["content"] = [{
                        "type": "text",
                        "text": msg["content"],
                        "cache_control": {"type": "ephemeral"},
                    }]
                break

    return formatted
```

说明：

- 上述逻辑只适用于显式缓存 provider
- OpenAI-compatible provider 不应复用这段逻辑
- 具体断点数量和规则以目标模型官方限制为准

### 11.10 与一致性引擎（StoryContext）的协同

Prompt Caching 建议优先用于以下一致性相关请求：

- `parse_script_to_storyboard()` 调用时的超长 `SYSTEM_PROMPT`
- `build_story_context()` 内部的角色外貌提取 prompt
- 世界观问答完成后，后续重复引用的 `selected_setting`

这样在 50 个镜头以上的故事里：

- 第 1 次请求写入缓存
- 后续请求复用静态 `StoryContext` 和导演规则
- 仅对少量动态镜头描述按全价计费

从而最大化降本与提速收益。

---

## 十二、手动模式与自动模式的统一要求

当前项目至少存在五条相关路径：

1. 自动一键生成：`/pipeline/{project_id}/auto-generate`
2. 手动分镜：`/pipeline/{project_id}/storyboard`
3. 手动批量素材生成：`/pipeline/{project_id}/generate-assets`
4. 手动单镜头生图：`/image/{project_id}/generate`
5. 手动单镜头生视频：`/video/{project_id}/generate`

如果后续只改自动一键生成，或者只改 `pipeline/*` 不改 `/image/*`、`/video/*`，用户在手动流程中仍会得到另一套 prompt 行为，导致系统继续“双轨制”：

- 自动模式看起来一致性更好
- 手动模式仍然保留污染 prompt
- 同一 story 在两条流程里的输出风格不一致

因此 Phase 1 的最低要求是：

- `auto-generate` 接入 `StoryContext`
- `storyboard` 支持 `character_section_override`
- `generate-assets` 与 `render-video` 复用同一套 `build_generation_payload()` 逻辑，但分别消费 `image_prompt` / `final_video_prompt`
- `/image/*` 与 `/video/*` 也要复用同一套分字段 prompt 组装能力，而不是停留在仅消费 `art_style`

---

## 十三、分阶段实施建议

### Phase 1：核心改造，不新增 UI

1. 新增 `app/core/story_context.py`
2. `pipeline_executor.py` 接入 `StoryContext`
3. `storyboard.py` 支持 `character_section_override`
4. `pipeline.py` 同步自动/手动两条链路
5. `image.py` 与 `video.py` 接入 `build_generation_payload()` 的分字段结果
6. `image.py` 与 `video.py` 打通 `negative_prompt`
7. `story_repository.py` 增加专用缓存读写 helper
8. 增加缓存失效逻辑

Phase 1 的补充要求：

- 以上步骤在实施时，默认包含 9.3 节定义的最小必要重构
- 不允许只把逻辑“挪一份”到新文件，同时保留旧链路继续增长
- 所有新增一致性逻辑都应优先挂在 `story_context.py`，而不是继续塞回 `pipeline_executor.py`

### Phase 1.5：为 Prompt Caching 做工程准备

9. 补 `normalize_cache_block()` / `get_cache_fingerprint()`
10. 给长静态前缀增加粗略 token 估算和启用阈值判断
11. 先在高收益链路引入结构化 request builder
12. 对支持的 provider 接入 Prompt Caching；不支持则自动降级

### Phase 2：增强能力

13. 增加 `extract_character_appearance()` LLM 提取
14. 回填 `character_images[name]["visual_dna"]`
15. 可选新增 `Shot.characters_in_shot`
16. 可选新增 `extract_scene_styles_from_world_summary()`

---

## 十四、兼容性说明

| 现有能力 | 修订后的处理方式 |
|------|------|
| `Story.art_style` | 继续作为 `StoryContext.base_art_style` |
| `image_prompt` / `final_video_prompt` / `last_frame_prompt` | 继续作为分镜输出的 canonical fields；一致性引擎只能增强，不应回退成单字段 |
| `inject_art_style()` | 保留为兜底工具；主链路由 `build_generation_payload()` 分字段组装 |
| `_enhance_prompt_with_character()` | 废弃但短期保留签名，避免外部调用报错 |
| `build_character_section()` | 保留旧函数作为无 `StoryContext` 时兜底 |
| `character_images[name]["visual_dna"]` | 作为兼容字段继续支持，但不再是唯一数据源 |
| Prompt Caching | 仅对支持的 provider 启用；不支持时自动忽略，不影响主流程 |
| 无 `story_id` 的旧流程 | `StoryContext` 为 `None` 时退回原逻辑，不阻断旧接口 |

---

## 十五、最终建议

按当前项目实际情况，推荐采用以下落地口径：

1. 运行期结构化缓存放在 `Story.meta["character_appearance_cache"]`
2. world summary 读取 `Story.selected_setting`
3. `character_images[name]["visual_dna"]` 作为兼容投影字段保留
4. 保持 `image_prompt` / `final_video_prompt` / `last_frame_prompt` 三字段分工，不回退成单一 prompt
5. 自动与手动链路同时接入 `StoryContext`
6. 缓存写入与失效通过专用 helper 管理，不直接裸写 `meta`
7. Prompt Caching 在“静态前缀已稳定”后再接入，并始终保留“不支持即降级”的 provider 兼容路径
8. 不把 negative 自动正向改写、模型专属权重语法写入主方案，只保留为 provider 定向优化的可选项
9. 该方案实施时同步完成最小必要的模块化重构，不采用“功能先打补丁、结构以后再收拾”的路径

这样改动最小，且能与当前仓库和既有文档保持连续性。
