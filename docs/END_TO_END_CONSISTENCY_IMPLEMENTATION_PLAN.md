# 全流程一致性实施计划

> 更新日期：2026-04-01
>
> 文档定位：基于当前仓库实际代码、测试、README 与已落地接口，重新整理“全流程一致性”现状、缺口、优先级与实施顺序。
>
> 使用原则：本文件只写当前已实现事实与明确计划，不把未来项写成现状；若与旧设计文档冲突，以代码和当前接口行为为准。

---

## 1. 这份文档要解决什么

当前项目的一致性能力已经不再是“设计稿阶段”:

1. `StoryContext` 已经成为图片/视频主链路的运行期一致性入口。
2. `prepare_story_context()` 已经承担“按需补齐结构化缓存”的职责。
3. Scene Reference、手动分镜、自动流水线、transition、拼接、恢复都已经接入同一套大方向。

但仓库里仍然同时存在：

1. 文档描述偏旧。
2. 个别入口仍保留 fallback / legacy path。
3. `storyboard_generation` 与 `pipeline.generated_files` 的边界容易被误解。
4. `character_appearance_cache`、`scene_style_cache`、`visual_dna` 仍处于“统一中但未完全收口”的过渡态。

这份文档的目标，是把下面四件事说清楚：

1. 当前项目真实已经落地了什么。
2. 哪些描述在旧文档里已经落后或不统一。
3. 接下来应该按什么顺序继续收口。
4. 哪些边界必须保持，不能在后续改造时被破坏。

---

## 2. 当前项目的真实一致性主链路

### 2.1 运行主线

当前实际主线如下：

```text
Story / selected_setting / characters / art_style
  -> generate_outline() => meta.logline / meta.visual_tone / outline[*].beats / outline[*].scene_list
  -> generate_script() => scenes[*].scene_heading / environment_anchor / lighting / mood / emotion_tags / key_props / key_actions
  -> serialize_story_to_script() / storyboard-script
  -> prepare_story_context()
  -> parse_script_to_storyboard()
  -> Scene Reference assets
  -> build_generation_payload()
  -> image / video / transition
  -> concat
  -> storyboard_generation 恢复态 + pipeline.generated_files 运行态
```

### 2.2 已经落地的核心能力

#### 补充：文字生成与分镜输入层已经补齐结构化中间层

- 代码落点：
  - `app/prompts/story.py`
  - `app/schemas/story.py`
  - `app/core/story_script.py`
  - `app/routers/story.py`
  - `frontend/src/api/story.js`
- 大纲层当前已经稳定输出并消费：
  - `meta.logline`
  - `meta.visual_tone`
  - `outline[*].beats`
  - `outline[*].scene_list`
- 剧本层当前已经稳定输出并消费：
  - `scene_heading`
  - `environment_anchor`
  - `lighting`
  - `mood`
  - `emotion_tags`
  - `key_props`
  - `key_actions`
  - `transition_from_previous`
- 当前已存在 `/{story_id}/storyboard-script` 接口，会把选中的场景序列化成统一 storyboard 输入文本，而不是继续依赖前端临时拼接。
- 前端当前也会把 `selected_scenes` 显式传给该接口，保证“选哪些场景进入分镜”有稳定的后端真相源。
- 这说明项目当前已经不只是“故事 JSON -> 分镜 JSON”，而是形成了：
  - Logic Layer：大纲
  - Narrative Layer：剧本场景
  - Vision Layer 输入：序列化 storyboard script
  的三段式前置链路。

#### A. `StoryContext` 已是运行期主入口

- 代码落点：`app/core/story_context.py`
- 当前 `build_generation_payload()` 会统一生成：
  - `image_prompt`
  - `final_video_prompt`
  - `negative_prompt`
  - `reference_images`
  - `source_scene_key`
- 手动批量图、手动批量视频、单镜头图、单镜头视频、transition 生成前的 prompt 组装，已经都围绕这套能力展开。
- 但这套入口当前只负责运行期图片 / 视频生成 payload，不直接替代上游“文字生成”提示词体系；故事生成、导演分镜、角色设定图、环境图、appearance/style 抽取仍分别沿现有模块维护。

#### B. `prepare_story_context()` 已经负责“按需准备缓存”

- 代码落点：`app/services/story_context_service.py`
- 当前在有可用 LLM 凭证时，会按需补齐：
  - `meta.character_appearance_cache`
  - `meta.scene_style_cache`
- `character_appearance_cache` 当前抽取字段是：
  - `body`
  - `clothing`
  - `negative_prompt`
  - `schema_version`
  - `source_provider`
  - `source_model`
  - `updated_at`
- `scene_style_cache` 当前抽取字段是：
  - `keywords`
  - `image_extra`
  - `video_extra`
  - `negative_prompt`
  - `schema_version`
  - `source_provider`
  - `source_model`
  - `updated_at`
- 这些缓存缺失时才会补；不是每次都重算。
- appearance / style 抽取请求当前已经带 `cacheable`，并会打开 caching 开关。
- 但实际是否命中 provider caching 取决于 provider 实现与 token threshold，当前不能把它写成“所有 provider 都已统一生效”。
- `normalize_story_record()` 当前也会归一化这些 metadata 字段，避免 story 读写后口径漂移。
- `StoryContext.cache_fingerprint` 已存在，但当前仅用于调试和观测，不参与业务分支。

#### C. Scene Reference 已进入图片 / 视频主链路

- 代码落点：`app/services/scene_reference.py`、`app/routers/story.py`
- 当前按“每集环境组”生成共享环境图，而不是按单场景重复生成。
- 结果会写入：
  - `meta.episode_reference_assets`
  - `meta.scene_reference_assets`
- 分镜 Shot 会带 `source_scene_key`。
- `build_generation_payload()` 会把命中的 Scene Reference 继续投影到：
  - `image_prompt`
  - `final_video_prompt`
  - `negative_prompt`
- 运行期图片参考会优先组合：
  - 角色设定图
  - 命中的场景环境图

#### D. 角色资产与缓存已经基本按 ID-first 收口

- 代码落点：`app/core/story_identity.py`、`app/services/story_repository.py`、`app/routers/character.py`
- 当前 `save_story()` / `get_story()` 会归一化：
  - `characters`
  - `relationships`
  - `character_images`
  - `meta.character_appearance_cache`
- 角色图接口当前要求显式传入 `character_id`，阻止按角色名复用或覆盖人设图。
- `story.patch` 在角色或大纲更新后，会按变更类型失效一致性缓存，避免旧缓存继续污染运行期。

#### E. 图片与视频都已经区分正向 prompt 和 negative prompt

- 图片服务：`app/services/image.py`
  - 运行期 `negative_prompt` 不是只看 shot 自身字段，而是会合并：
    - shot `negative_prompt`
    - `ctx.global_negative_prompt`
    - 命中角色锁定信息里的 `negative_prompt`
    - 命中已知角色时额外补充一组运行期人物一致性负面约束（换脸、换发型、主衣物漂移、服装颜色/材质漂移、配饰缺失、肢体异常、多人重复等）
    - 命中 Scene Reference 后追加的环境一致性负面约束
  - `reference_images` 会合并去重：
    - shot 自带 `reference_images`
    - 命中的角色设定图
    - 命中的场景环境图
    - 同场景上一张已生成主镜头图（图片批量生成链路，以及 auto chained 策略里的图片阶段，都会作为下一张图的 continuity 参考）
  - 若 provider 因 `negative_prompt` 返回 400/422，会先去掉它再重试。
  - 若仍因 `reference_images` 返回 400/422，会继续去掉参考图再重试。
- 视频服务：`app/services/video.py`
  - 主镜头视频支持单首帧 I2V
  - `negative_prompt` 已作为运行期参数保留并传入 provider
  - 视频入口 / 手动页 / pipeline executor 当前也会保留 `reference_images` 元数据，不再在 runtime prepare 阶段直接丢失；但普通主镜头视频请求本身仍主要只实际消费 `image_url` 首帧图，当前并没有把通用 `reference_images` 列表原生下发给 video provider
  - 但 provider 支持度并不完全一致：
    - `dashscope` / `minimax` / `kling` 当前会原生透传 `negative_prompt`
    - `doubao` 当前仍不支持原生 `negative_prompt` 字段，但运行期已经把高优先级身份 / 服装 / 解剖 / 背景 / 镜头抖动 guardrails 折叠进优化后的文本提示词，降低人物漂移和突变风险
  - 双帧只对支持双帧的 provider 开放

#### F. 主镜头与 transition 的边界已经明确

- 普通主镜头统一走单首帧 I2V。
- `last_frame_prompt / last_frame_url` 已从主镜头主链路退出，只保留兼容痕迹。
- 运行期主镜头视频 prompt 当前已经额外注入：
  - 身份锁
  - 主衣物锁
  - 动作幅度必须清晰可见
  - 运镜幅度必须可读
  - 肢体 / 手部 / 解剖保持稳定
- transition 只允许相邻镜头。
- transition 必须建立在已有主镜头视频之上。
- transition 的首尾锚点优先从相邻主镜头视频抽帧；抽帧失败时会回退到已有静态分镜图。
- transition 的前镜尾帧当前会从更贴近视频末尾的位置抽取，避免过早抽到仍处在明显运动中的尾段画面。

#### G. 手动页、单资产接口、自动流水线都已经具备状态持久化

- 手动分镜接口会同时写入：
  - `story.meta.storyboard_generation`
  - `pipeline.generated_files`
- 单资产接口会稳定写入：
  - `story.meta.storyboard_generation`
- 单资产接口在请求显式提供 `pipeline_id`，或能从恢复态解析出 `pipeline_id` 时，也会同步写入：
  - `pipeline.generated_files`
- 自动 `auto-generate` 当前会按阶段持续写入 `pipeline.generated_files`，至少包含：
  - `storyboard`
  - `tts`
  - `images`
  - `videos`
  - `meta`
- 自动 `auto-generate` 在提供 `story_id` 时，也会把上述运行态快照镜像到：
  - `story.meta.storyboard_generation`
- 因此自动流水线当前仍以 `pipeline` 为主要运行态真相源，但 restore / history 不再只能依赖手动链路写回。
- `storyboard_generation` 当前不仅保存恢复态，也会镜像部分 `generated_files`、`shots`、`pipeline_id`、`project_id`、`story_id`、`final_video_url`。
- 手动 runtime 在解析“当前 storyboard shot 列表”时，当前优先级是：
  - `storyboard_generation.shots`
  - `pipeline.generated_files.storyboard.shots`
  - `storyboard_generation.generated_files.storyboard.shots`
- 当单镜头图片或视频被重生成时，系统会按依赖关系失效相关视频、transition、`final_video_url`，并同步重建 `timeline`。

#### H. 当前已有测试保护

一致性相关测试已存在，不是纯文档设计态：

- `tests/test_story_prompts.py`
- `tests/test_story_script_serializer.py`
- `tests/test_character_prompts.py`
- `tests/test_character_design_prompt.py`
- `tests/test_storyboard_prompt.py`
- `tests/test_storyboard_normalization.py`
- `tests/test_story_context.py`
- `tests/test_story_router.py`
- `tests/test_pipeline_runtime.py`
- `tests/test_scene_reference.py`
- `tests/test_scene_reference_lightweight.py`
- `tests/test_storyboard_state.py`
- `tests/test_image_reference_security.py`
- `tests/test_image_service_retry.py`
- `tests/test_story_identity.py`
- `tests/test_story_mainline.py`
- `tests/test_story_context_anchor_boundaries.py`
- `tests/test_single_frame_mainline.py`

---

## 3. 当前文档里需要统一修正的点

这部分专门列出“旧说法容易误导开发”的地方。

### 3.1 `storyboard_generation` 不能再只写成“纯手动恢复态”

当前真实情况是：

1. 它确实服务于手动分镜页恢复。
2. 但它也会同步镜像 `generated_files`。
3. 它还会把 `tts / images / videos` 结果反写回 `shots`，方便前端恢复。
4. `pipeline_id / project_id / story_id / final_video_url` 也会写入这里。

因此更准确的口径应是：

- `pipeline.generated_files` 是运行态主真相源。
- `storyboard_generation` 是手动页恢复态，并镜像一部分运行资产，便于刷新和历史恢复。

### 3.2 `pipeline.generated_files` 仍然是运行期主真相源

当前 `generated_files` 可能包含：

1. `storyboard`
2. `tts`
3. `images`
4. `videos`
5. `transitions`
6. `timeline`
7. `final_video_url`
8. `meta`

transition 与 concat 更偏向读取 pipeline 当前真实资产，而不是只看前端临时状态。

但在“当前 storyboard shot 列表”的解析上，代码还有一个更精确的优先级：

1. 优先读取 `storyboard_generation.shots`
2. 其次读取 `pipeline.generated_files.storyboard.shots`
3. 再其次读取 `storyboard_generation.generated_files.storyboard.shots`

因此更准确的表述应是：

- 运行期资产真相源仍以 `pipeline.generated_files` 为主；
- 但手动恢复和 runtime shot 顺序解析会优先信任 `storyboard_generation.shots`。

### 3.3 `StoryContext` 已统一主方向，但并未完全去掉 fallback

当前仍存在过渡态路径：

1. `app/routers/image.py` 里仍保留 `_build_basic_payload()` 兜底。
2. `app/services/pipeline_executor.py` 里仍保留 `_build_generation_payload()` fallback 注释与兼容逻辑。
3. `build_story_context()` 仍会在缓存缺失时回退到：
   - `character_images.visual_dna`
   - `design_prompt`
   - `description`

因此当前更准确的表述应是：

- 主链路已经统一到 `StoryContext`。
- 但工程上仍保留有限 fallback，用于避免入口在异常时彻底失效。

### 3.4 `character_appearance_cache` 还不是绝对唯一来源

当前真实逻辑是：

1. 优先使用 `meta.character_appearance_cache`
2. 缺失时回退到 `character_images.visual_dna`
3. 再缺失时回退到 `design_prompt / description` 清洗结果

这条优先级当前已经落到多个消费入口：

- `build_story_context()`
- 分镜角色参考块 `build_character_section()`
- `serialize_story_to_script()`

同时，`prepare_story_context()` 还会把抽取出的 `body` 投影回 `character_images.visual_dna`。

这说明项目现状不是“完全去掉 visual_dna”，而是：

- 正在把结构化缓存作为主消费源；
- 但 `visual_dna` 仍是兼容投影层。

### 3.5 `scene_style_cache` 也不是唯一风格来源

当前 `StoryContext` 的场景风格由两部分组成：

1. 基于 `genre` 的内置 `_GENRE_STYLE_RULES`
2. `meta.scene_style_cache` 的结构化抽取结果

所以当前不是“只有 scene_style_cache 在工作”，而是“genre 规则 + scene_style_cache 叠加”。

### 3.6 transition 的描述需要更精确

当前 transition 规则不是单纯“从相邻主镜头视频里抽帧”，而是：

1. 先要求相邻主镜头视频已经存在。
2. 再尝试从视频抽取：
   - 前镜最后一帧
   - 后镜第一帧
3. 若抽帧失败且有对应分镜图，则回退到分镜图。
4. 只允许支持双帧的 provider，目前代码口径默认要求 `doubao`。
5. 运行期会优先读取 pipeline / `storyboard_generation` 合并后的真实资产，而不是信任请求体临时传入的镜头视频地址。

### 3.7 角色资产键控不能再写成“按名字为主”

当前真实逻辑是：

1. `save_story()` / `get_story()` 会归一化 `characters / relationships / character_images / character_appearance_cache`
2. 角色图生成接口要求显式 `character_id`
3. 运行期仍保留少量按名字匹配的 fallback，但那是兼容查找，不是权威主键

因此更准确的口径应是：

- 角色一致性的稳定主键是 `characters[*].id`
- `character_images` 与 `meta.character_appearance_cache` 应尽量对齐到角色 ID
- 角色名是展示字段和兼容匹配字段，不应再被当作唯一权威键

### 3.8 `negative_prompt` 的描述需要更精确

当前真实逻辑不是“有个负面提示词字段”这么简单，而是分层合并与按 provider 落地：

1. 单镜头运行期 `negative_prompt` 当前会合并：
   - shot 自身 `negative_prompt`
   - 场景风格侧汇总后的 `ctx.global_negative_prompt`
   - 命中角色外观锁定后的角色级 `negative_prompt`
   - 命中 Scene Reference 后附加的环境一致性负面约束
2. transition 不是单独发明一套负面提示词，而是合并前后相邻 shot 的 `negative_prompt`。
3. 图片链路已经有通用降级重试：
   - 先丢 `negative_prompt`
   - 再丢 `reference_images`
4. 视频链路当前只是统一透传 `negative_prompt` 参数，但实际是否生效取决于 provider 能力，不能写成“所有视频 provider 都稳定支持 negative prompt”。

因此更准确的口径应是：

- `negative_prompt` 已进入统一运行期 payload。
- 但其效果当前仍有 provider 差异，尤其视频侧还不是完全等价能力。

### 3.9 文字 / 图片 / 视频三类提示词与参考资产不能混写

当前真实项目里，这三类能力彼此相关，但不共用一套字段语义：

1. 文字生成提示词
   - 主要落在：
     - `app/prompts/story.py`
     - `app/prompts/storyboard.py`
     - `app/services/story_context_service.py` 的 appearance / scene style 抽取提示词
   - 这部分负责生成或修正文案、结构化故事、分镜 JSON、结构化缓存，不直接等同于运行期 `build_generation_payload()`
2. 图片生成提示词与参考图
   - 运行期主字段是：
     - `image_prompt`
     - `negative_prompt`
     - `reference_images`
   - 其中 `reference_images` 当前是通用多参考图入口，会合并：
     - shot 自带参考图
     - 角色设定图
     - 场景环境图
     - 同场景上一张已生成主镜头图（图片批量生成与 chained video 的图片阶段）
3. 视频生成提示词与参考资产
   - 运行期主字段是：
     - `final_video_prompt`
     - `negative_prompt`
   - 普通主镜头视频当前真正依赖的视觉参考资产是：
     - `image_url` 首帧图
   - transition 当前真正依赖的视觉参考资产是：
     - 前镜最后一帧 `first_frame_url`
     - 后镜第一帧 `last_frame_url`
     - 抽帧失败时回退到相邻 shot 的静态分镜图
   - 当前项目并没有统一的“视频多参考图 `reference_images` 原生透传层”，不能把图片链路的参考图能力直接写成视频链路现状

因此更准确的口径应是：

- 文字生成、图片生成、视频生成都属于要持续优化的 prompt family。
- 但“图片参考图”与“视频参考图”当前不是同一实现机制。
- 视频侧更准确的说法应是“首帧 / 尾帧锚点与上游首帧图真相”，而不是泛化成图片式 `reference_images`。

### 3.10 上游文字层与 storyboard 输入层已经比旧文档更结构化

当前旧文档里另一个容易缺失的事实是：上游并不只是“outline + scenes”这么简单，字段边界已经明显增强。

当前真实情况包括：

1. 大纲层已经稳定要求：
   - `meta.logline`
   - `meta.visual_tone`
   - `outline[*].beats`
   - `outline[*].scene_list`
2. 剧本层已经稳定要求：
   - `scene_heading`
   - `environment_anchor`
   - `lighting`
   - `mood`
   - `emotion_tags`
   - `key_props`
   - `key_actions`
   - `transition_from_previous`
3. `serialize_story_to_script()` 与 `storyboard-script` 接口已经把这些字段串成稳定 storyboard 输入，不再只是简单拼接 `【环境】` 和 `【画面】`
4. `app/services/storyboard.py` 当前还会补：
   - `audio_reference.speaker`
   - narration 统一映射到 `旁白`
   - 单角色 dialogue 的 speaker 自动补全
   - `characters` 字段归一化

因此更准确的口径应是：

- 当前前置链路已经形成更清晰的 Logic Layer / Narrative Layer / Vision Input 边界。
- 后续 DSPy / Judge 优化应直接复用这些现有字段，而不是重新发明一套中间结构。

---

## 4. 当前必须遵守的边界

后续所有一致性改造，都应继续遵守这些边界。

### 4.1 `StoryContext` 继续作为运行期统一入口

- 不再新建“第五套 prompt 中心”。
- 新的运行期一致性能力优先挂在：
  - `prepare_story_context()`
  - `build_generation_payload()`
- 故事生成、分镜生成、角色设定图、环境图、transition 等前置 prompt family 仍沿各自现有入口演进，但不能再长出并行真相源。

### 4.2 普通主镜头继续保持单首帧 I2V

- 不把双帧逻辑重新引回主镜头。
- `last_frame_prompt / last_frame_url` 不再回流主链路。
- 双帧只留给 transition。

### 4.3 文本风格缓存与图像参考资产分开治理

- `scene_style_cache` 是文本风格锚点。
- `episode_reference_assets / scene_reference_assets` 是图像参考资产。
- 两类都能影响运行期，但职责不同，不能混写成一个缓存。

### 4.4 provider 不支持时优先“丢弃参数”而不是污染正向 prompt（后续目标态）

- 以下原则描述的是后续目标态，不代表所有 provider 现在都已经满足这一边界。
- 图片 provider 拒绝 `negative_prompt` 时，去掉它再试。
- 图片 provider 拒绝 `reference_images` 时，去掉它再试。
- 视频 provider 当前还没有统一的自动降级重试层；现状是保留 `negative_prompt` 接口参数，再由各 provider 自己决定透传或忽略。
- 当前例外：`doubao` 仍会将高优先级 guardrails 折叠进正向 prompt，需兼容此行为直到替换或迁移完成。
- 后续若补视频侧 capability negotiation / fallback，也应优先做“按 provider 丢弃不支持参数”，而不是把负面约束污染进正向 prose。
- 不应把“不要出现什么”反向塞回正向 prose。

### 4.5 状态边界继续保持“双层”

- `pipeline.generated_files` 继续作为运行期主真相源。
- `story.meta.storyboard_generation` 继续作为手动恢复态和镜像层。
- 后续可以继续收口，但不要重新退回“只有前端内存态”。
- 当某个 shot 的图片或视频被重生成时，相关依赖资产必须继续按规则失效传播，不能留下过期 transition 或过期 `final_video_url`。

### 4.6 角色资产继续以 `character_id` 为主键

- 不再新引入“按角色名直接覆写角色图/外观缓存”的入口。
- `character_images` 与 `character_appearance_cache` 继续优先对齐到稳定角色 ID。
- 按名字匹配只保留为兼容查找，不提升为新的权威数据口径。

### 4.7 文档不得把未来项写成现状

以下能力当前仍未进入正式主链路：

- DSPy 运行时代码
- Judge / Review / Shadow mode
- Feedback Loop 自动重试闭环
- 独立数字资产库
- transition 删除接口

---

## 5. 当前推荐目标态

在现有仓库基础上，推荐继续沿当前骨架增量收口，而不是重做架构。

### 5.1 目标结构

```text
Story data
  -> outline / scenes / storyboard-script
  -> prepare_story_context()
  -> storyboard / scene reference
  -> build_generation_payload()
  -> image / video / transition / concat
  -> pipeline.generated_files
  -> storyboard_generation restore mirror
```

### 5.2 一致性能力分层

#### 第零层：文字结构层

- `meta.logline`
- `meta.visual_tone`
- `outline[*].beats`
- `outline[*].scene_list`
- `scenes[*].scene_heading`
- `scenes[*].environment_anchor`
- `scenes[*].emotion_tags`
- `scenes[*].key_props`
- `scenes[*].key_actions`
- `serialize_story_to_script()`
- `storyboard-script`

#### 第一层：结构化与资产层

- `character_appearance_cache`
- `scene_style_cache`
- `character_images`
- `story identity normalization`
- prompt caching prep / cache fingerprint
- `episode_reference_assets`
- `scene_reference_assets`

#### 第二层：运行期组装层

- `prepare_story_context()`
- `build_story_context()`
- `build_generation_payload()`

#### 第三层：执行层

- storyboard
- tts
- image
- video
- transition
- concat

#### 第四层：恢复与状态层

- `pipeline.generated_files`
- `story.meta.storyboard_generation`

#### 第五层：后置质量增强层（必须落地）

- 更严格 schema 与版本化
- DSPy 离线优化（覆盖所有主要 prompt family）
- Judge / Feedback Loop
- 面向生成质量的系统性优化闭环

当前优先级应该是先把前四层收稳，再推进第五层质量能力落地。

### 5.3 后续质量优化应覆盖的三类 family

后续做 DSPy、Judge、Feedback Loop 或其他质量优化时，范围应显式覆盖下面三类，而不是只盯运行期 `negative_prompt`：

#### A. 文字生成提示词 family

- 灵感审计 / 世界构建 / 大纲生成 / 导演剧本 / refine / apply-chat
- 分镜导演提示词
- appearance / scene style 结构化提取提示词

#### B. 图片生成提示词与参考图 family

- 角色设定图提示词
- 环境图提示词
- 运行期 `image_prompt / negative_prompt`
- `reference_images` 的选择、合并、去重、权重与降级策略

#### C. 视频生成提示词与参考资产 family

- 运行期 `final_video_prompt / negative_prompt`
- transition bridge 提示词
- 普通主镜头的首帧图一致性
- transition 的首尾帧锚点选择、抽帧回退与 provider 能力差异

---

## 6. 分阶段实施顺序

### Phase 1：先把运行期契约和文档口径收口（状态：已完成，主文档口径已对齐）

#### 当前状态

当前主文档口径已经完成一轮显式对齐，`README`、`video-pipeline`、`feature-documentation`、`database-persistence-implementation` 与本文件的主边界已基本一致。

当前完成情况：

- `[已完成]` 本文档已统一 `StoryContext`、`storyboard_generation`、`pipeline.generated_files`、transition、ID-first 口径
- `[已完成]` 当前仍保留的 fallback / legacy path 已在文档里显式标出
- `[已完成]` 主要现状文档已同步到同一套运行期边界：
  - `README.md`
  - `docs/video-pipeline.md`
  - `docs/feature-documentation.md`
  - `docs/database-persistence-implementation.md`

已经有的基础：

1. `build_generation_payload()` 已是主入口。
2. 图片/视频/transition 都已消费其结果或围绕其结果组装。
3. 主镜头单首帧 I2V 与 transition 双帧边界已明确。
4. `negative_prompt` 与 `reference_images` 已进入运行期。
5. 角色资产与 appearance cache 已基本按 ID-first 归一化。

仍然存在的问题：

1. 个别入口仍保留 fallback builder。
2. auto / manual / single asset / transition 的统一口径虽然已有文档与测试基线，但人工收官还没真正执行。
3. `visual_dna` 仍是兼容投影层，尚未进入最终退役节奏。

#### 本阶段目标

把“现有已经能跑的事实”统一成稳定契约，而不是继续容忍多种说法并存。

#### 本阶段要做什么

1. 统一文档中对 `StoryContext`、`storyboard_generation`、`pipeline.generated_files` 的描述。
2. 统一 transition 的真实规则描述。
3. 标记哪些 fallback 仍保留，哪些不应再扩散。
4. 明确 auto 与 manual 的状态真相源边界。
5. 明确角色资产与外观缓存的 ID-first 口径。

#### 完成标准

1. 新文档不再把过渡态写成终态。
2. 所有主要文档对状态边界描述一致。
3. 后续开发者不会再误以为 `storyboard_generation` 是唯一真相源。

### Phase 2：把结构化缓存契约做硬（状态：进行中，主消费链路已进一步收口）

#### 当前状态

已经从“可用但偏宽松”推进到“核心字段与元数据已落地”，但还没完全收口。

当前完成情况：

- `[已完成]` `schema_version / source_provider / source_model / updated_at` 已落地
- `[已完成]` 不兼容未来 schema 的缓存已不会继续被运行期直接消费，且会触发按需刷新
- `[已完成]` 提取失败不污染已有缓存的写回边界已成立
- `[已完成]` story 归一化已覆盖缓存 metadata 字段
- `[已完成]` `character_appearance_cache` 在存在时，已经优先进入：
  - `build_story_context()`
  - 分镜角色参考块 `build_character_section()`
  - `serialize_story_to_script()`
- `[进行中]` `visual_dna` 的最终退役策略尚未定稿

现状：

1. `character_appearance_cache` 已稳定消费 `body / clothing / negative_prompt`
2. `scene_style_cache` 已稳定消费 `keywords / image_extra / video_extra / negative_prompt`
3. `schema_version / source_provider / source_model / updated_at` 已经落地
4. runtime 当前会忽略超前 schema 的缓存，并在有可用 LLM 凭证时按需刷新
5. `normalize_story_record()` 已能归一化上述 metadata 字段
6. 分镜角色参考块与 storyboard-script 输入层在有结构化缓存时，已经优先消费 `character_appearance_cache`
7. `visual_dna` 仍处于兼容投影层，尚未决定最终退役节奏

#### 本阶段目标

让缓存从“可用”升级为“可演进、可校验、可回滚”。

#### 本阶段要做什么

1. 把现有 `schema_version` 从“已存在字段”推进到“有明确演进策略”的正式契约。
2. 继续补齐 cache metadata 的读写、归一化与失败保护测试。
3. 明确 `visual_dna` 的最终角色：保留兼容投影还是逐步退役。
4. 为后续缓存升级预留兼容迁移规则，避免下一轮结构调整再次口径漂移。

#### 完成标准

1. 文档、代码、测试对缓存字段口径一致。
2. 缓存写入失败不会破坏现有稳定结果。
3. 结构化缓存成为更明确的主数据源。

### Phase 3：做全入口一致性验收（状态：进行中，已完成显式最小基线验收）

#### 当前状态

主方向正确，而且已经补上一轮显式最小基线验收；当前剩余缺口主要是基于真实故事样本的人工收官。

当前完成情况：

- `[已完成]` 已有多条单元测试和集成测试覆盖手动/单资产/恢复/transition 边界
- `[已完成]` `auto-generate` 已补齐运行态持久化与 restore 基线测试，覆盖成功写回与中途失败保留快照
- `[已完成]` 已补充固定样本 story、seed 脚本与人工验收 runbook：
  - `docs/phase3_manual_acceptance_story.json`
  - `scripts/manual/seed_phase3_manual_story.py`
  - `docs/phase3-manual-acceptance-runbook.md`
- `[已完成]` 固定样本故事已按当前最关键风险重新收紧，用于专门压测：
  - 首帧图不能只剩脸
  - 双手 / 上半身 / 道具必须在首帧就建立
  - 同场景相邻镜头必须保持连续剧情感，而不是重置成独立海报图
- `[已完成]` 已按文档推荐基线跑通：
  - `uv run python -m unittest discover -s tests -q`
  - `node --test frontend/src/utils/storyChat.test.js frontend/src/utils/storyChat.multiline-sections.test.js frontend/src/utils/storyChat.numbering.test.js`
  - `npm --prefix frontend run build`
- `[进行中]` 仍缺一轮基于该固定样本的真实人工串行验收结论（auto / manual / single asset / transition / concat / restore）

需要一起看的入口：

1. `auto-generate`
2. 手动 `storyboard -> generate-assets -> render-video`
3. 单镜头 `tts / image / video`
4. `transitions/generate`
5. `concat`
6. History 恢复

#### 本阶段目标

确认这些入口在同一故事、同一分镜、同一恢复场景下，表现符合统一预期。

#### 本阶段要做什么

1. 核对相同 Shot 在不同入口下是否得到相同 prompt 组装。
2. 核对状态写回是否都能正确恢复。
3. 核对 transition 是否始终基于 pipeline 当前真实视频资产。
4. 核对 `negative_prompt` 在 image / video / transition 三条链路中的组成是否符合统一预期。
5. 核对刷新、历史恢复、重新生成是否会出现状态分叉。

#### 完成标准

1. auto / manual / single asset / transition 的行为可解释。
2. 恢复逻辑不再依赖前端临时状态。
3. 文档与测试都能覆盖这些边界。

### Phase 4：在前三层稳定并经人工检查后，落实 DSPy、Judge 与 Feedback Loop（状态：未开始）

#### 当前状态

都未正式开始。

当前完成情况：

- `[未开始]` DSPy compile / optimizer
- `[未开始]` Judge / shadow mode
- `[未开始]` Feedback Loop 自动闭环

#### 这不是“可选增强”，而是后置实施

当前把这部分放在 Phase 4，不代表它们可做可不做，而是因为：

1. 当前项目先要把运行期主链路、状态真相源与恢复边界收稳。
2. 质量优化闭环一旦过早接入，容易把问题混入主链路，导致难以定位回归来源。
3. 当前更稳妥的节奏是：先完成前面三层优化，人工检查通过后，再把 DSPy、Judge、Feedback Loop 作为完整质量层落地。

#### 本阶段目标

把质量增强层建立在已经稳定的字段、状态边界和验收样本上，而不是边跑边改主链路。

因此文档口径应明确为：

- `DSPy`
- `Judge`
- `Feedback Loop`
- 其他面向生成质量的优化能力

都属于后续要落实的正式能力，不是长期搁置的“以后再说”项。

#### 当前不能误写成已支持的内容

1. DSPy compile / optimizer 流程
2. Judge / review_required
3. shadow mode
4. 局部自动重试闭环

#### 推荐方向

1. DSPy 目标应扩展为“离线优化所有主要提示词体系”，但不改运行期主入口与状态真相源。
2. 优化范围应覆盖：
   - `app/prompts/story.py` 的灵感审计 / 世界构建 / 故事生成 / refine / apply-chat 提示词
   - `app/prompts/storyboard.py` 的分镜导演提示词
   - `app/prompts/character.py` 的角色设定图提示词
   - `app/services/scene_reference.py` 的环境图提示词
   - `app/services/story_context_service.py` 的 appearance / scene style 结构化提取提示词
   - `app/core/story_context.py` 的运行期 `image_prompt / final_video_prompt / negative_prompt / reference_images` 组装策略
   - `app/routers/pipeline.py` 的 transition bridge 提示词与 transition 负面提示词合并策略
3. DSPy 优化后的产物仍应写回现有字段和现有入口，例如：
   - `outline / scenes / storyboard`
   - `meta.character_appearance_cache`
   - `meta.scene_style_cache`
   - `image_prompt / final_video_prompt / negative_prompt`
   - `reference_images` 选择结果
4. 需要补一层 provider capability matrix，至少显式覆盖：
   - image provider 对 `negative_prompt` / `reference_images` 的原生支持
   - video provider 对 `negative_prompt` / 单首帧 I2V / 双帧 transition 的原生支持
5. Judge / Feedback Loop 的评测维度里应单独纳入：
   - 文字生成结构稳定性
   - 角色一致性
   - 环境一致性
   - 图片参考图命中率
   - 视频首帧 / 尾帧锚点命中率
   - 负面约束命中率
   - provider 降级前后质量差异
6. 生产环境只加载离线 compile / optimizer 结果，不在请求链路实时训练或实时搜索。
7. Judge / Feedback Loop 应作为可关闭的质量增强层接入，但它们本身属于后续必须落地的质量能力。
8. 这部分工作的目标不是“锦上添花”，而是系统性提升故事生成、分镜生成、角色一致性、环境一致性和视频成片质量。

#### 三层 DSPy 方案（方案态，尚未实施）

以下内容当前仍是设计提案，不代表仓库已经具备对应模块、编译流程或自动重试闭环。

##### 第一层：剧情大纲（Logic Layer）

目标：

1. 只确定核心冲突、节奏推进、视觉基调和场景切分。
2. 把“这一集发生什么”与“每个场景承担什么任务”写清楚。
3. 不提前长出对白、镜头语言或摄影化环境细节。

DSPy 模块建议：

- `OutlinePlanner`

建议输入：

- `selected_setting`
- 角色基础信息
- 故事主题 / 类型 / 风格约束

建议输出：

- `meta.logline`
- `meta.visual_tone`
- `outline[*].summary`
- `outline[*].beats`
- `outline[*].scene_list`

Judge 重点：

- logline 是否清楚包含主角 / 目标 / 阻碍 / 冲突
- beats 是否真正体现转折，而不是剧情复述
- `scene_list` 是否按 `[时间] [内/外] [地点]` 稳定切分
- 相同地点是否尽量复用同一命名，避免上游就把环境切碎

##### 第二层：剧本（Narrative Layer）

目标：

1. 补齐动作线、对白、场景情绪弧线和关键物件。
2. 把环境写成可复用的“稳定场景说明”，服务后续 scene reference，而不是追求文学化铺陈。
3. 保持和大纲层、分镜层边界清晰，不重写整集摘要，不提前写 shot list。

DSPy 模块建议：

- `NarrativeSceneWriter`

建议输入：

- `OutlinePlanner` 的结构化输出
- 角色稳定视觉锚点
- 场景复用约束

建议输出：

- `scene_heading`
- `environment_anchor`
- `environment`
- `lighting`
- `visual`
- `emotion_tags`
- `key_props`
- `key_actions`
- `audio`

Judge 重点：

- `environment_anchor` 是否在同地点场景间保持一致
- `environment` 是否只保留稳定空间信息，而不是混入动作、情绪、镜头和一次性微细节
- `key_props` 是否覆盖剧情关键物件
- `emotion_tags` 是否能支撑后续表情强度与 `scene_intensity` 映射

##### 第三层：分镜（Vision Layer）

目标：

1. 只做视觉翻译，把剧本文字转成可执行镜头参数与图生视频 prompt。
2. 明确景别、机位、运镜、首帧状态、动作变化和跨镜头衔接。
3. 不重复解释剧情，不重写人物小传，不重新发明环境设定。

DSPy 模块建议：

- `StoryboardTranslator`

建议输入：

- `NarrativeSceneWriter` 的结构化剧本
- 角色外观锁定信息
- scene reference / appearance extraction 的稳定缓存结果

建议输出：

- `storyboard_description`
- `camera_setup`
- `visual_elements`
- `image_prompt`
- `final_video_prompt`
- `scene_intensity`
- `transition_from_previous`

Judge 重点：

- `storyboard_description` 是否只写当前镜头可见状态，而非整段剧情复述
- `environment_and_props` 是否只保留当前镜头可见的稳定环境子集和关键道具
- `scene_intensity` 是否与 `emotion_tags` 的峰值和可见动作强度一致
- `image_prompt` / `final_video_prompt` 是否分别承担静态首帧与短时动作指令，而不是互相复制

#### Judge / Feedback Loop 设计（方案态，尚未实施）

建议按“分层 judge + 跨层 judge + 局部回写”设计，而不是一次性让一个大 judge 重写全链路。

分层 judge：

1. `OutlineJudge`
   - 看冲突是否成立、beats 是否清楚、场景切分是否稳定
2. `NarrativeJudge`
   - 看环境描述是否可复用、对白是否服务剧情、关键道具是否完整
3. `StoryboardJudge`
   - 看镜头拆分是否合理、镜头语言是否可执行、连续性锚点是否充分

跨层 judge：

1. 逻辑层到剧本层
   - beats 是否都被映射到对应场景
   - `scene_list` 与 `scene_heading / environment_anchor` 是否仍一一对应
2. 剧本层到分镜层
   - `key_props` 命中率
   - `emotion_tags -> scene_intensity / facial expression` 映射质量
   - 同一 `environment_anchor` 的环境复用率
3. 分镜层到运行期生成层
   - `image_prompt` 首帧命中率
   - `final_video_prompt` 动作命中率
   - Scene Reference 复用后的一致性收益

建议优先跟踪的指标：

1. 结构稳定性得分
2. 相同地点环境复用率
3. 关键道具命中率
4. 情感标尺到表情 / 肢体强度映射质量
5. 首帧 / 尾帧锚点命中率
6. provider 降级前后质量差异

建议的 feedback 动作：

1. 只重写失败层和失败片段，不整集重写
2. 优先局部修复 `outline[*]` / `scenes[*]` / `storyboard[*]`
3. 回写仍必须落在现有字段，不新增并行真相源
4. 所有 feedback 模块都应支持关闭、灰度、回退

#### 额外实施要求

1. 不能让 DSPy 直接绕开 `prepare_story_context()` 或 `build_generation_payload()`。
2. 不能新增一套与 `pipeline.generated_files` / `storyboard_generation` 并行的运行期真相源。
3. 必须先建立 prompt 级评测集、评分标准和回归基线，再逐类替换。
4. 所有优化都应支持按 prompt family 独立启停和快速回退。

#### 完成标准

1. 关闭增强层时，当前主链路行为完全不变。
2. 打开 DSPy 优化后，所有主要 prompt family 都有可观测收益或至少不退化。
3. 打开 Judge / Feedback Loop 后，质量收益可解释、重试成本可控、失败回退路径清晰。
4. `negative_prompt` 的效果评测能够区分 image / video / transition 三类入口，以及不同 provider 的真实支持差异。
5. 自动模式、手动模式、单资产入口在开启优化后仍共享同一套运行期边界。
6. 任一 prompt family 或任一质量增强模块回退到原始实现时，不影响其他 family 与恢复逻辑。

### Phase 5：最后压缩 fallback / legacy path（状态：未开始，明确后置）

#### 当前状态

仍处于过渡态，而且当前明确后置到 DSPy 阶段完成并经人工检查后再处理。

当前完成情况：

- `[未开始]` fallback builder 尚未删除
- `[未开始]` `visual_dna` 兼容层尚未收口

当前仍保留：

1. `_build_basic_payload()` 兜底逻辑
2. PipelineExecutor 内部 fallback payload
3. `visual_dna` 投影与兼容消费

#### 本阶段目标

在不破坏可用性的前提下，逐步让更多入口只走 `StoryContext` 主链路。

#### 本阶段要做什么

1. 盘点哪些 fallback 只是临时保底，哪些已经变成事实依赖。
2. 把能删掉的 legacy builder 收掉。
3. 把保留的兜底逻辑限定在极小范围，并补测试。

#### 完成标准

1. 主入口不再偷偷拼装私有 prompt。
2. 兜底逻辑只在异常场景生效。
3. 文档能清楚标出剩余兼容层。

---

## 7. 统一数据口径

### 7.1 Story 侧核心字段

当前应继续视为一致性核心数据的字段：

1. `stories.characters`
2. `stories.relationships`
3. `stories.outline[*].summary / beats / scene_list`
4. `stories.scenes[*].scene_heading / environment_anchor / lighting / mood / emotion_tags / key_props / key_actions / transition_from_previous / audio`
5. `stories.character_images`
6. `stories.selected_setting`
7. `stories.art_style`
8. `stories.meta.character_appearance_cache`
9. `stories.meta.scene_style_cache`
10. `stories.meta.episode_reference_assets`
11. `stories.meta.scene_reference_assets`
12. `stories.meta.storyboard_generation`

其中：

- `characters[*].id` 是角色一致性的稳定主键。
- `character_images` 与 `meta.character_appearance_cache` 应优先和该 ID 对齐。

### 7.2 Pipeline 侧核心字段

当前应继续把 `pipelines.generated_files` 视为运行期主真相源，重点包括：

1. `storyboard`
2. `tts`
3. `images`
4. `videos`
5. `transitions`
6. `timeline`
7. `final_video_url`
8. `meta`

### 7.3 Shot 运行期关键字段

当前主链路稳定依赖的字段包括：

1. `shot_id`
2. `image_prompt`
3. `final_video_prompt`
4. `negative_prompt`
5. `reference_images`
6. `source_scene_key`
7. `characters`
8. `audio_reference.type / speaker / content`
9. `scene_intensity`
10. `scene_position`
11. `transition_from_previous`
12. `image_url`
13. `video_url`
14. `audio_url`
15. `audio_duration`

下列字段当前不应被写成已进入正式主链路：

1. `review_required`
2. `feedback_*`
3. 新的多级 judge 字段

### 7.4 参考资产口径

当前文档里如果要写“参考图 / 参考资产”，应按下面口径区分：

1. 文字生成阶段
   - 主要依赖故事、角色、设定、历史修改记录等文本上下文
   - 当前没有统一的运行期 `reference_images` 字段
2. 图片生成阶段
   - 统一参考资产入口是 `reference_images`
   - 来源可包括角色设定图、场景环境图、shot 自带参考图、同场景上一张已生成主镜头图
3. 视频生成阶段
   - 普通主镜头的主要视觉参考资产是 `image_url` 首帧图
   - transition 的主要视觉参考资产是 `first_frame_url / last_frame_url`
   - 当前不能把视频侧描述成“已支持通用多参考图列表”

---

## 8. 推荐验收方式

后续每推进一个阶段，建议都按下面顺序验收。

### 8.1 先看入口是否继续统一

- 是否继续围绕 `prepare_story_context()` 与 `build_generation_payload()`
- 是否又长出新的私有 prompt builder
- DSPy 优化是否仍复用现有 prompt family，而不是再长出一套平行运行链路

### 8.2 再看状态边界是否仍然清晰

- `pipeline.generated_files` 是否仍是运行期主真相源
- `storyboard_generation` 是否仍是恢复态镜像层

### 8.3 再看全入口行为

- auto
- manual
- single asset
- transition
- concat
- restore
- 文字生成、图片生成、视频生成三类 prompt family 是否仍各自清晰，且没有被混写成一套字段语义
- image / video provider 间 `negative_prompt` 的真实支持差异是否已被正确表达和兜底

### 8.4 最后看测试

当前建议的最小验证基线：

```bash
uv run python -m unittest discover -s tests -q
node --test frontend/src/utils/storyChat.test.js frontend/src/utils/storyChat.multiline-sections.test.js frontend/src/utils/storyChat.numbering.test.js
npm --prefix frontend run build
```

本轮实际执行结论（2026-04-01）：

1. 上述三条最小基线均已实际跑通。
2. 为保证基线稳定通过，已额外收口两处环境敏感问题：
   - `start.py` 在 Windows 解析 `ffmpeg` 时，优先使用 `winget` 包内二进制，避免被宿主机 Unix 常见目录误命中。
   - `tests/test_story_mainline.py` 显式固定 `story_llm.settings.debug = True`，避免测试结果被本机 `.env` 漂移污染。
3. Phase 3 剩余的人工收官，当前已具备固定样本、seed 脚本与 runbook，但尚未执行真实 provider 的整轮人工串行验收。

若要执行 Phase 3 剩余的人工收官，当前推荐直接按这份 runbook 走：

- `docs/phase3-manual-acceptance-runbook.md`

若开始接入 DSPy，建议额外补一层专项验收：

- 按 prompt family 分开做 before / after 对照评测
- 对 story / storyboard / character / scene reference / transition / appearance extraction / scene-style extraction 分别保留基线样本
- 验证开启和关闭 DSPy 优化时，`StoryContext`、状态写回与恢复行为保持一致
- 对图片 `reference_images` 与视频首帧 / 尾帧锚点分别保留专项样本，避免把两类参考机制混为一谈
- 对 `negative_prompt` 额外保留 provider 维度样本，验证 image / video / transition 的命中率、降级行为与质量收益

---

## 9. 最终结论

对当前项目来说，最稳妥的路线不是推倒重来，而是继续沿着现有主线增量收口：

1. 先统一文档口径和运行期契约。
2. 再把结构化缓存契约做硬。
3. 再做全入口一致性验收。
4. 在前三层稳定并经人工检查后，继续把 DSPy、Judge、Feedback Loop 以及其他质量优化能力完整落地。
5. 最后再压缩 fallback / legacy path。

这条路线的价值在于：

1. 不会破坏当前已经跑通的主链路。
2. 能准确反映仓库今天真实状态。
3. 能让后续开发建立在现有代码与测试之上，而不是建立在过时描述上。
4. 能把“先稳定链路，再系统提质”的目标表达清楚，避免把后续质量能力误读成可选项。

---

## 10. 当前实际修改归纳（2026-03-31）

这一节按“当前仓库已经改了什么”来整理，不再只记录单轮优化。

### 已经完成的实际修改

#### A. 上游文字层已经更结构化

1. 大纲提示词与 schema 已经补齐：
   - `meta.logline`
   - `meta.visual_tone`
   - `outline[*].beats`
   - `outline[*].scene_list`
2. 剧本提示词与 schema 已经补齐：
   - `scene_heading`
   - `environment_anchor`
   - `lighting`
   - `mood`
   - `emotion_tags`
   - `key_props`
   - `key_actions`
   - `transition_from_previous`
3. mock 数据、主链路测试和 story schema 已经同步到这套字段，不再只是旧版 `environment / visual / audio` 三字段。

#### B. storyboard 输入层已经稳定成后端能力

1. `serialize_story_to_script()` 已经把角色、Visual DNA、场景标题、环境锚点、情感标尺、关键道具、动作拆解、台词统一序列化，并在存在 `character_appearance_cache` 时优先消费其 `body / clothing`。
2. `/{story_id}/storyboard-script` 接口已存在。
3. `selected_scenes` 既支持列表，也支持布尔 map 结构，并会在后端统一归一化。
4. 前端已经改为显式调用该接口，而不是继续在前端临时拼 storyboard 输入文本。

#### C. 角色提示词与视觉锚点已进一步收紧

1. `app/core/character_profile.py` 已新增，对角色描述中的微观噪声、机关步骤、毫米级细节做清洗。
2. 角色设定图 prompt 现在更明确地只消费视觉锚点，不再把性格、能力、剧情机关直接塞进角色图 prompt。
3. 三视图角色设定图 prompt 已明确要求“同一时刻、同一人物、只改变视角”。
4. 分镜角色参考块现在优先消费 `character_appearance_cache` 的结构化 `body / clothing`，缺失时再回退 `visual_dna` 与 `design_prompt / prompt`，进一步压缩“立绘 prompt 直接污染分镜输入”的风险。

#### D. Scene Reference 已进一步贴近“可复用环境图”

1. 环境分组当前会显式优先利用 `environment_anchor`，而不是只靠整段环境文案模糊聚类。
2. 环境图 prompt 更强调：
   - Environment only
   - One clean master environment reference image
   - No characters
3. scene reference 结果当前会写入并保留：
   - `summary_environment`
   - `summary_visuals`
   - `updated_at`
4. 已补 lightweight tests，覆盖“相同环境锚点应复用同一环境组”的行为。

#### E. 运行期一致性层继续增强

1. `build_generation_payload()` 继续统一输出：
   - `image_prompt`
   - `final_video_prompt`
   - `negative_prompt`
   - `reference_images`
   - `source_scene_key`
2. 正向 / 负向 prompt 当前已经进入图片、视频、transition 主链路。
3. 视频侧 provider 能力差异已经在实现里显式保留：
   - `dashscope / minimax / kling` 透传 `negative_prompt`
   - `doubao` 保留参数但原生忽略
4. 图片一致性链路现在不只覆盖手动 / 单资产图片批量生成，也覆盖 auto chained 策略里的图片阶段：同场景内会把上一张已生成主镜头图继续喂给下一张图。
5. 图片首帧 prompt 现在会额外约束“必须能支撑后续视频动作”，显式避免：
   - 图片被收成只剩脸部的独立人像
   - 视频开场才突然补出原本首帧没建立的手、道具或更大范围身体裁切
   - `camera_setup.shot_size` 与首帧构图口径冲突
6. 非首个同场景 shot 当前会额外注入“这是同一场景连续时刻，不是新的独立海报图 / 建立镜头”的运行期提示，减轻跨分镜单独生成时的状态重置感。
7. transition 当前仍严格建立在相邻主镜头视频资产之上，并优先读 pipeline / storyboard_generation 合并后的真实状态。

#### F. 结构化缓存契约已经推进了一步

1. `character_appearance_cache` 与 `scene_style_cache` 现在都带：
   - `schema_version`
   - `source_provider`
   - `source_model`
   - `updated_at`
2. `prepare_story_context()` 在成功抽取后才写入这些缓存 metadata，不会在失败时污染已有缓存。
3. runtime 现在会跳过不兼容未来 schema 的缓存，并在有凭证时按需刷新这些缓存。
4. `normalize_story_record()` 已能归一化这些 metadata 字段，并保留未来 schema version 供刷新判定使用。
5. 这说明 Phase 2 不再是“完全未动”，而是已经完成了最关键的一半。

#### G. 分镜 JSON 归一化已经更严格

1. narration 当前会统一映射到 `audio_reference.type = narration` 且 `speaker = 旁白`
2. 单角色 dialogue 会自动补全 speaker
3. 泛化代词 speaker 会尽量清洗掉，避免把“他/她”直接保存为 speaker 真相
4. `characters` 字段当前也会做显式归一化，避免把路人、群众、未确认身份的人混入正式角色名单

#### H. 测试保护面已经明显扩大

当前已新增或增强的测试，不再只覆盖运行期 payload，还包括：

1. `tests/test_story_prompts.py`
2. `tests/test_story_script_serializer.py`
3. `tests/test_character_prompts.py`
4. `tests/test_character_design_prompt.py`
5. `tests/test_storyboard_prompt.py`
6. `tests/test_storyboard_normalization.py`
7. `tests/test_scene_reference_lightweight.py`
8. `tests/test_story_context.py`
9. `tests/test_story_identity.py`
10. `tests/test_story_router.py`
11. `tests/test_story_mainline.py`
12. `tests/test_pipeline_runtime.py`
13. `tests/test_image_service_retry.py`
14. `tests/test_single_frame_mainline.py`
15. `tests/test_doubao_video_provider.py`

#### I. Phase 3 的最小基线验收已经显式执行

1. 已跑通 `uv run python -m unittest discover -s tests -q`
2. 已跑通前端 `storyChat` 三组 Node 测试
3. 已跑通 `npm --prefix frontend run build`
4. 这意味着 Phase 3 已经从“只有局部保护”推进到“已有一轮明确的最小基线验收结论”
5. 已新增一条显式的后端全流程模拟测试，覆盖：
   - `serialize_story_to_script()` 从 story scenes 生成 storyboard 输入文本
   - `generate_storyboard`
   - `generate_assets` 的首帧图生成
   - `render_video`
   - `generate_transition`
   - `concat_videos`
6. 这条模拟测试会额外检查：
   - 图片首帧构图是否与后续视频动作冲突
   - 同场景下一镜头图片是否带上上一镜头首帧 continuity 参考
   - transition prompt / timeline / final export sequence 是否按真实运行态串联
7. 已新增 auto pipeline persistence tests，额外覆盖：
   - `run_full_pipeline()` 会把 `storyboard / tts / images / videos / meta` 按阶段写入 `pipeline.generated_files`
   - 在存在 `story_id` 时，同步镜像到 `story.meta.storyboard_generation`
   - auto 链路中途失败时，最新 storyboard 快照不会被后续失败状态清空，便于 restore / history 排查

### 当前仍未执行或未完全完成的内容

#### 1. fallback 收口还没做

当前仍保留：

1. `app/routers/image.py::_build_basic_payload()`
2. `app/services/pipeline_executor.py::_build_generation_payload()` 的 fallback / legacy 路径
3. `visual_dna` 的兼容投影与兼容消费

因此 Phase 5 仍应保留为后续动作，不能误标成已完成。

#### 2. 全入口一致性验收还没做成“人工收官”

虽然现在已经完成了一轮显式最小基线验收，而且相关代码路径已有测试覆盖，但仍缺一轮基于真实故事样本的人工串行验收来一起钉死：

1. auto
2. manual
3. single asset
4. transition
5. concat
6. restore

当前已经补上固定样本、seed 脚本和 runbook，但还没把这轮 runbook 真正执行完并记录结论。

所以 Phase 3 当前更准确的状态是“进行中，最小基线已完成，人工收官已有固定样本与执行方案，但验收结论待补”。

#### 3. DSPy / Judge / Feedback Loop 仍未正式开始

当前仍未落地：

1. DSPy compile / optimizer
2. 分层 judge
3. 自动 feedback retry loop
4. shadow mode / review_required 真正运行态字段

因此 Phase 4 仍然是方案态，不应在文档里被误写成“已有基础模块”。

### 当前推荐顺序（按实际修改后重排）

1. 先按 `docs/phase3-manual-acceptance-runbook.md` 执行一轮基于固定样本的人工全入口验收，把当前已落地能力真正钉死。
2. 再根据人工验收结论，决定 `visual_dna` 兼容层的保留边界与后续退役节奏。
3. 人工检查通过后，再推进 DSPy / Judge / Feedback Loop。
4. DSPy 阶段完成后，再做一轮人工检查与专项验收。
5. 最后再收最危险的 fallback / legacy path，避免过早混入回归来源。
