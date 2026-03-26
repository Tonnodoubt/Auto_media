# 全流程一致性优化、DSPy 与 Generative Feedback Loops 实施主文档

> 合并来源：`docs/better.md` + `docs/DSPY_FEEDBACK_LOOP_INTEGRATION_PLAN.md`
>
> 修订日期：2026-03-26
>
> 文档定位：后续开发主文档。当前不改业务代码，只统一目标态、执行顺序、数据契约、验收口径与回滚方式。
>
> 核心结论：先完成 Prompt / Negative Prompt 全流程治理，再接入 DSPy，再接入 Generative Feedback Loops，最后推广到 auto / manual / transition 全入口。

---

## 0. 执行摘要

先记住下面 9 点：

1. 当前项目不是“完全没有一致性治理”，而是已经有基础能力，但还没有形成闭环。
2. 正向提示词和反向提示词都需要；当前反向提示词不是没有，而是还不够分层、分阶段、分 provider。
3. “反向提示词过少”确实不太合适，但也不能靠无限堆长解决；正确方向是分层构造、去重限长、按 provider 能力发送。
4. `StoryContext` 仍然是唯一的一致性入口，不能再造第四套 prompt 中心。
5. DSPy 的职责是把角色外貌提取变成结构化契约，不是接管运行时 prompt 拼装。
6. Generative Feedback Loop 的职责是生成后检查、反馈、局部重试，不是重写整条 prompt。
7. 执行顺序固定为：先优化 Prompt 与数据契约，再接 DSPy，再接 Feedback Loop，最后推广到全部入口。
8. 本方案不以向下兼容旧 schema 为目标；进入新链路的数据统一以新契约为准，旧故事如需复跑应先重建缓存。
9. 本轮仅产出实施文档，不执行真实代码改造。

---

## 1. 当前项目真实现状

基于当前仓库代码，项目已经具备以下基础：

### 1.1 已经落地的能力

1. `app/core/story_context.py`
   - 已负责统一构建 `StoryContext`
   - 已能输出 `image_prompt`、`final_video_prompt`、`last_frame_prompt`、`negative_prompt`
   - 已具备 `CharacterLock`、`SceneStyle`、`global_negative_prompt` 的基础结构

2. `app/services/story_context_service.py`
   - 已有结构化外貌提取与场景风格提取的 JSON 契约雏形
   - 但当前仍是“普通 LLM + prompt 提取器”，不是 DSPy 编译模块

3. `app/services/image.py`
   - 已支持独立 `negative_prompt` 字段
   - provider 拒绝 `negative_prompt` 时，会自动退化为“不带 negative 再试一次”

4. `app/services/video.py` 与 provider 层
   - 已支持把 `negative_prompt` 透传给视频 provider
   - `dashscope` / `kling` / `minimax` 可发送 native negative
   - `doubao` 当前保留参数但实际忽略，因为 provider 不提供原生 negative 字段

5. `app/services/pipeline_executor.py`
   - 已经是自动链路的主编排点
   - 但当前还没有真正的 VLM 检查、局部重试、人工复核标记与 per-shot QA 状态

### 1.2 当前缺口

1. 角色外貌提取还不是声明式结构化能力
   - 仍有 heuristic 回退
   - 稳定性依赖底层模型表现

2. 反向提示词还不够系统
   - 已经有字段，但目前主要来自 genre、scene style、character lock、shot 层零散输入
   - 还没有形成“按阶段、按镜头类型、按 provider 能力裁剪”的统一策略

3. 生成链路仍然偏“一次生成直出”
   - 图片生成后没有自动检查角色锁是否符合
   - 视频生成后没有自动检查动作完成度、终态是否到位
   - 出错时缺少结构化反馈与局部重试

4. 三类入口还没有完全共用同一套闭环规则
   - 自动流水线
   - 手动图片/视频生成
   - transition / 过渡资产生成

一句话总结：当前项目已经有“统一 payload 组装”的基础，但还没有走到“结构化约束 + 生成后验证 + 局部纠错”的完整系统。

---

## 2. 对 `docs/better.md` 的吸收、调整与取舍

`docs/better.md` 的价值主要在于给出了目标态全流程和 UI 背后的系统逻辑，但其中部分内容需要结合当前项目边界做调整。

### 2.1 建议直接吸收的部分

1. 渐进式承诺（Progressive Commitment）
   - 从文本到视觉锚点再到视频渲染，成本逐步升高
   - 这很适合作为后续全流程优化的总原则

2. “先锁定视觉锚点，再做昂贵生成”
   - 角色 DNA
   - 场景 key art
   - 统一 `StoryContext`

3. Prompt Caching 的静态到动态排布
   - `SYSTEM_PROMPT`
   - `Story Context`
   - `Few-shot`
   - `Current Task`

4. Art Style Header 的统一口径
   - 避免在每个 prompt 中重复堆基础画风词

5. 隐藏的重试环路与人工干预锚点
   - 闭环必须允许局部回退
   - 关键缓存字段必须允许人工 patch

### 2.2 需要调整后吸收的部分

1. “反向提示词过少”
   - 这个判断是对的
   - 但不能简单理解成“negative 越长越好”
   - 真正需要的是分层 negative 策略，而不是单条 prompt 越堆越长

2. “PipelineExecutor 必须重构成状态机”
   - 方向是合理的
   - 但首期不应直接大改为全新状态机框架
   - 更稳妥的做法是先在现有 `PipelineExecutor` 上增加 per-shot 状态、检查结果和重试记录

3. “纯后端实现，无需新增 UI”
   - 对首期是成立的
   - 但人工复核、手动 patch、过渡资产插入等能力，后续很可能仍需要前端入口承接

4. 指定某个固定 VLM 模型
   - 文档里可以保留“轻量 VLM / Judge 模型”这一层
   - 不应把实现写死在某一个具体模型名上

### 2.3 当前不直接采纳的部分

1. 不采纳“按角色名 keyed object”作为唯一结构
   - 统一使用 `character_id`

2. 不采纳“默认全量强检”
   - 成本和时延不可控
   - 应采用关键镜头必检 + 普通镜头抽检

3. 不采纳把 negative 硬拼进正向 prompt
   - 如果 provider 不支持 native negative，应直接丢弃 negative
   - 不能写成 `"do not include modern buildings"` 这类正向污染文本替代方案

4. 不采纳为旧 `visual_dna` 单字段长期维护兼容层
   - 新方案只保留一个主数据源
   - 旧数据如需进入新流程，先重建为新 schema

---

## 3. 关于正向提示词与反向提示词的明确结论

### 3.1 两者都必须保留

正向提示词负责定义“要生成什么”，反向提示词负责约束“不要出现什么”。

在当前项目里，两者都不可省：

1. 正向提示词
   - 锁定角色体貌、服装、动作、环境、画风

2. 反向提示词
   - 抑制现代穿帮
   - 抑制 studio / 肖像污染
   - 抑制多余人物、畸形肢体、裁切错误
   - 抑制与镜头目标不一致的元素

### 3.2 “反向提示词过少”是否不合适

结论：是，不太合适。

如果 negative 只有少量通用词，比如：

- `blur`
- `low quality`
- `modern objects`

那么它很难覆盖当前项目最常见的错误：

1. 角色图污染
   - studio lighting
   - clean background
   - half body portrait

2. 时代或类型穿帮
   - cars
   - neon signs
   - modern clothing
   - electric lights

3. 人物一致性错误
   - duplicate person
   - extra character
   - inconsistent outfit

4. 画面质量错误
   - cropped body
   - missing limbs
   - watermark
   - text

但同时也要明确：

- negative 不是越长越好
- 过长会导致 payload 膨胀、provider 拒绝、重点稀释
- 正确做法是“分层构造 + 去重 + 限长 + provider-aware”

### 3.3 推荐的 Negative Prompt 分层策略

后续统一使用下面的构造思路：

```text
negative_prompt =
  [artifact negatives]
+ [portrait contamination negatives]
+ [genre / era negatives]
+ [scene-specific negatives]
+ [character-specific negatives]
+ [shot-specific negatives]
```

各层职责如下：

1. `artifact negatives`
   - 文本、水印、logo、肢体错误、裁切错误、重复人物

2. `portrait contamination negatives`
   - studio background
   - clean backdrop
   - close-up portrait
   - camera test phrasing

3. `genre / era negatives`
   - 古风 / 仙侠镜头排除现代建筑、现代服装、车辆、电灯、塑料质感

4. `scene-specific negatives`
   - 针对场景基调图和场景规则缓存附加局部排除词

5. `character-specific negatives`
   - 针对单个角色的服装污染、错误身份、错误配饰

6. `shot-specific negatives`
   - 单角色镜头排除 crowd、second person
   - 尾帧控制镜头排除 wrong final pose

### 3.3.1 Negative Prompt 冲突覆写机制

为了防止上层通用 negative 与具体镜头需求冲突，`shot-specific negatives` 允许使用精确覆写语法删除继承词。

推荐规则：

```text
inherited negatives: text, watermark, logo, crowd
shot-specific negatives: -text, burnt edges
final negatives: watermark, logo, crowd, burnt edges
```

落地约束：

1. 只允许删除“标准化后的完整 term”，不做模糊匹配
2. 覆写语法只在 payload builder 内部生效，最终不会发送 `-text` 这类保留语法给 provider
3. 覆写能力只开放给 `shot-specific negatives`，不开放给上层通用规则
4. 剧情确实需要出现文字、招牌、信件、UI 字样时，必须通过这种覆写机制显式解除冲突

### 3.4 正向与反向的阶段性策略

不同阶段的 negative 应该不同，不能一套词打天下。

#### A. 角色人设图

目标：生成干净、可复用的角色视觉参考源。

```text
positive:
  [CharacterLock body] + [default clothing] + [neutral full-body sheet] + [art style]

negative:
  text, watermark, logo, studio props, extra objects, close-up portrait,
  half body, cropped body, duplicate person, inconsistent outfit
```

#### B. 场景基调图

目标：只锁环境，不引入剧情人物污染。

```text
positive:
  [scene style extra] + [selected setting anchor] + [art style]

negative:
  foreground character, portrait framing, modern intrusion, unrelated props
```

#### C. 镜头首帧图

目标：生成可供视频继续运动的第一帧。

```text
positive:
  [clean character lock] + [shot image_prompt] + [scene style extra] + [art style]

negative:
  [artifact negatives] + [genre negatives] + [character negatives] + [shot negatives]
```

#### D. 视频生成

目标：维持运动过程中的身份、服装、环境和终态一致性。

```text
positive:
  [clean character lock] + [final_video_prompt] + [scene style extra] + [art style]

negative:
  only send when provider supports native negative
```

关键规则：

1. provider 不支持 native negative 时，直接丢弃
2. 严禁把 negative 写成正向 prose 拼进去
3. `last_frame_prompt` 与视频终态检查应互相配套

---

## 4. 目标态全流程

结合当前项目实现和 `better.md` 的目标态，推荐统一为下面这条主链路：

```text
[剧本/世界观]
-> [StoryContext 基础缓存准备]
-> [Storyboard 生成]
-> [角色视觉 DNA / 角色图]
-> [场景风格缓存 / 场景 key art]
-> [统一镜头 payload 构建]
-> [图片生成]
-> [视频生成]
-> [Generative Feedback Loop 检查与局部重试]
-> [最终素材与拼接]
```

按阶段拆开如下：

1. 剧本与世界观建立
   - 产出 `Story`
   - 固化 `genre`、`selected_setting`、`art_style`

2. 一致性基础缓存准备
   - 产出 `CharacterLock` 来源缓存
   - 产出 `SceneStyle` 来源缓存

3. Storyboard 生成
   - 只输出镜头所需的动作、构图、环境、节奏
   - 不再把冗长角色描述原样灌进每个 shot

4. 角色视觉锚点生成
   - 生成角色图
   - 角色视觉主数据源只写入结构化外貌缓存

5. 场景风格锚点生成
   - 生成环境 key art
   - 写回 `scene_style_cache`

6. 统一 payload 构建
   - `image_prompt`
   - `final_video_prompt`
   - `last_frame_prompt`
   - `negative_prompt`

7. 图片与视频生成
   - 所有入口统一消费 `build_generation_payload()`

8. 闭环检查与局部纠错
   - 图片检查
   - 视频检查
   - 局部重试
   - 人工复核

---

## 5. 执行顺序与分阶段实施方案

后续实施顺序固定如下，不能跳步。

### Phase 1：先完成 Prompt 与数据契约治理

这一阶段必须先做完，再接 DSPy 和 Feedback Loop。

#### 5.1 目标

把当前“可运行但还不够系统”的 prompt 逻辑，稳定成一套统一、可测、可复用的基础层。

#### 5.2 本阶段要完成的事

1. 固化统一的正向 prompt 组装顺序

推荐公式：

```text
final_positive_prompt =
  [clean character lock]
+ [shot prompt]
+ [scene style extra]
+ [art style]
+ [retry extra_instructions]
```

2. 固化统一的 negative prompt 组装顺序

推荐公式：

```text
final_negative_prompt =
  [artifact negatives]
+ [genre / era negatives]
+ [scene negatives]
+ [character negatives]
+ [shot negatives]
```

3. 给运行时 payload 明确加入局部纠错入口
   - `shot.extra_instructions`
   - 由 `build_generation_payload()` 合并
   - 默认不持久化到剧本正文

4. 为 negative prompt 增加冲突覆写能力
   - 只允许 `shot-specific negatives` 删除继承词
   - 采用标准化 term 级别覆写，不做模糊删除

5. 补齐 provider 能力矩阵
   - 哪些支持 native negative
   - 哪些忽略 `last_frame_url`
   - 哪些需要自动去掉 negative 重试

6. 固化 Storyboard 上下文输入口径
   - `Storyboard` 只消费 `clean character section`
   - 不再把 portrait / studio / 角色立绘 prompt 原样透传进分镜生成

7. 固化 Prompt Caching 与画风注入规则
   - 消息顺序统一为：`SYSTEM_PROMPT -> Story Context -> Few-shot -> Current Task`
   - `art_style` 作为全局基调统一注入，不在每个 shot 内重复堆底层画风词

8. 埋点沉淀 DSPy 黄金数据集
   - 从人工调优后效果稳定、`qa_passed` 的角色样本中沉淀 `character description -> structured output`
   - 统一落盘到离线数据集，例如 `data/dspy_golden_dataset.jsonl`

9. 统一 auto / manual / transition 的 payload 构建口径
   - 不能三套入口各自拼 prompt

10. 固化测试
   - positive / negative 分离
   - negative override 只删除精确 term
   - 多角色镜头 negative 去重
   - provider 不支持 negative 时不污染 positive
   - `extra_instructions` 合并顺序正确

#### 5.3 主要落点

- `app/core/story_context.py`
- `app/services/storyboard.py`
- `app/services/image.py`
- `app/services/video.py`
- `app/services/pipeline_executor.py`
- `app/routers/pipeline.py`
- `tests/test_story_context.py`
- `tests/test_pipeline_runtime.py`

#### 5.4 完成标准

1. 所有入口统一通过 `build_generation_payload()` 产出 prompt
2. negative prompt 形成可解释的分层结构，不再只是零散拼接
3. negative override 机制已可用且有测试保护
4. `Storyboard` 链路不再吃脏的 portrait / studio prompt
5. provider 不支持 negative 时行为一致且可测试
6. 已开始稳定沉淀可供 DSPy 编译使用的黄金数据集
7. `extra_instructions` 已具备接入 Feedback Loop 的能力

### Phase 2：接入 DSPy，替代角色外貌提取主路径

#### 5.5 目标

把角色外貌提取从“长 prompt + 运气”升级为“结构化契约 + 可离线编译”。

#### 5.6 本阶段要完成的事

1. 定义 `CharacterAppearance` 输出结构
   - `body`
   - `clothing`
   - `negative_prompt`

2. 统一写入位置

```python
Story.meta["character_appearance_cache"][character_id]
```

3. 统一缓存 schema

```json
{
  "body": "...",
  "clothing": "...",
  "negative_prompt": "...",
  "source": "dspy_compiled_v1",
  "schema_version": "appearance_cache_v1",
  "updated_at": "2026-03-26T12:00:00Z"
}
```

4. 基于 Phase 1 沉淀的黄金数据集做离线 compile
   - 训练样本优先来自人工修正后稳定通过的真实业务数据
   - 不使用临时手写 dummy data 作为主训练来源

5. DSPy 只负责提取，不负责运行时 prompt 拼装

#### 5.7 主要落点

- `app/services/story_context_service.py`
- `app/core/story_context.py`
- 相关单元测试与离线样本集流程

#### 5.8 强约束

1. 不在 FastAPI 请求链路实时 compile
2. 不在 router 中直接调用 DSPy
3. DSPy 不可用时允许回退实现，但不回退数据契约

#### 5.9 完成标准

1. `character_appearance_cache` 主键统一为 `character_id`
2. DSPy 输出稳定写入 `appearance_cache_v1`
3. 黄金数据集已能支撑离线 compile 与回归评估
4. 运行时仍由 `StoryContext` 消费结构化缓存

### Phase 3：接入 Generative Feedback Loops

#### 5.10 目标

让生成链路从“一次生成直出”变成“生成 -> 检查 -> 反馈 -> 局部重试”。

#### 5.11 本阶段要完成的事

1. 在图片节点插入检查
   - 检查角色身份
   - 检查服装延续
   - 检查主体数量
   - 检查场景锚点

2. 在视频节点插入检查
   - 检查起始状态是否接上首帧
   - 检查动作是否完成
   - 检查终态是否符合 `last_frame_prompt`
   - 检查角色外貌是否漂移

3. 统一 Judge 输出契约

```json
{
  "passed": false,
  "score": 0.62,
  "issues": [
    {
      "code": "character_clothing_drift",
      "severity": "high",
      "message": "Main character is missing the dark blue robe."
    }
  ],
  "feedback": "CRITICAL FIX: restore the same dark blue robe and keep single-subject composition.",
  "should_retry": true
}
```

4. 统一反馈写回方式
   - 只更新 `shot.extra_instructions`
   - 不直接重写主 prompt 主体

5. 统一重试原则
   - 单镜头最多 1-2 次
   - 只重试当前镜头
   - 失败后标记人工复核

6. 引入影子模式（Shadow Mode）
   - 初期只记录 `judge_score`、`issue_codes`、建议反馈，不拦截生成结果
   - 连续观察一段时间后，再开启主动重试

7. 引入降级与熔断机制
   - 单镜头重试耗尽后，自动采纳得分最高的那次结果继续放行
   - 将该镜头标记为 `review_required = true`
   - 若 Judge 服务连续失败达到阈值，则对当前 pipeline run 打开熔断，后续镜头暂停 QA，只记录降级日志

#### 5.12 主要落点

- `app/services/pipeline_executor.py`
- 图片与视频生成节点的调用边界
- 相关日志与状态记录

#### 5.13 完成标准

1. 单镜头可独立执行检查与局部重试
2. 影子模式下可完整记录 Judge 行为且不阻塞主链路
3. 重试耗尽时能自动选择最高分结果继续放行
4. 关闭 Feedback Loop 时不影响原主链路
5. 可看到 issue code、retry 记录和人工复核标记

### Phase 4：推广到全部入口，并补足运行时状态管理

#### 5.14 目标

让 auto / manual / transition 共享同一套一致性规则，并补齐运行时可观测性。

#### 5.15 本阶段要完成的事

1. 推广到自动流水线
2. 推广到手动批量素材生成
3. 推广到手动单镜头图片/视频生成
4. 推广到 transition 资产生成
5. 为 shot 增加统一运行时状态

推荐状态枚举：

```text
pending | generating | qa_failed | qa_passed | completed | review_required
```

#### 5.16 完成标准

1. auto / manual / transition 共用同一套 `FeedbackPolicy`
2. 不存在入口级私有 prompt builder
3. 每个 shot 的检查与重试状态可观测

---

## 6. 统一数据契约

### 6.1 CharacterLock

运行时统一结构保持不变：

```python
@dataclass
class CharacterLock:
    name: str = ""
    body_features: str = ""
    default_clothing: str = ""
    negative_prompt: str = ""
```

### 6.2 外貌缓存

统一写入：

```python
Story.meta["character_appearance_cache"][character_id]
```

统一 schema：

```json
{
  "body": "young man, short black hair, slim build",
  "clothing": "dark blue robe",
  "negative_prompt": "modern clothing",
  "source": "dspy_compiled_v1",
  "schema_version": "appearance_cache_v1",
  "updated_at": "2026-03-26T12:00:00Z"
}
```

说明：

1. 这是角色外貌的唯一主数据源
2. 本方案不再为旧 `visual_dna` 单字段维护长期兼容路径
3. 旧故事如需进入新链路，应先重建为该结构

### 6.3 SceneStyle 缓存

建议统一延续当前缓存结构：

```json
{
  "keywords": ["teahouse", "river town"],
  "image_extra": "jiangnan river town, wooden teahouse, rain mist, warm lantern glow",
  "video_extra": "jiangnan river town, rain mist, warm lantern glow",
  "negative_prompt": "cars, neon signs"
}
```

### 6.4 JudgeResult

图片和视频检查统一返回：

```json
{
  "passed": true,
  "score": 0.87,
  "issues": [],
  "feedback": "",
  "should_retry": false
}
```

推荐 `issue_codes` 枚举至少覆盖：

- `character_identity_mismatch`
- `character_clothing_drift`
- `character_count_error`
- `scene_anchor_missing`
- `action_incomplete`
- `last_frame_state_mismatch`
- `orientation_conflict`
- `modern_artifact_detected`
- `style_mismatch`
- `judge_unreliable`

### 6.5 运行时 shot 字段

建议统一挂在运行时对象上，而不是写回剧本文本主体：

```python
shot.extra_instructions: str
shot.feedback_attempt: int
shot.feedback_issues: list[dict]
shot.review_required: bool
shot.status: str
```

### 6.6 Feature Flags 与运行配置

建议把 rollout 与降级开关集中到单一配置结构中，而不是散落在函数参数里：

```python
ConsistencyConfig(
    enable_negative_override=True,
    enable_dspy_extractor=False,
    enable_feedback_loop=False,
    feedback_shadow_mode=True,
    feedback_degradation_mode="best_score_continue",
    feedback_circuit_breaker_failures=5,
    appearance_cache_schema_version="appearance_cache_v1",
)
```

---

## 7. 成本控制、观测与回滚

### 7.1 成本控制

Feedback Loop 不允许默认全量强检。

推荐策略：

1. 必检
   - 新角色首次登场
   - 大跨度换装
   - 强依赖 `last_frame_prompt` 的镜头
   - 关键情绪或身份特写

2. 抽检
   - 同场景连续镜头每 3-5 镜抽检一次

3. 可跳过
   - 草稿模式
   - 重复性很高的低优先级镜头

### 7.2 Shadow Mode 上线策略

Feedback Loop 首次上线时，推荐先跑影子模式：

1. Judge 正常执行评分和问题分类
2. 所有结果默认放行，不触发自动重试
3. 先观察 `judge_score` 分布、误报率与 issue code 频率
4. 阈值稳定后，再切换到主动重试模式

### 7.3 最低日志字段

- `story_id`
- `pipeline_id`
- `shot_id`
- `feedback_enabled`
- `feedback_shadow_mode`
- `feedback_attempt`
- `judge_passed`
- `judge_score`
- `issue_codes`
- `retry_applied`
- `selected_best_attempt`
- `circuit_breaker_open`
- `final_review_required`

### 7.4 回滚顺序

若上线后出现质量或成本问题，按以下顺序回滚：

1. 先关闭 Feedback Loop，只保留 Prompt 治理与 DSPy 提取
2. 若 DSPy 质量不稳，再退回当前 heuristic 提取实现
3. 继续保留 Phase 1 的 prompt builder、negative override 和日志口径
4. 不为旧 schema 额外恢复兼容层

---

## 8. 最终推荐结论

对当前项目，最稳妥的路线不是直接大改架构，而是按以下顺序增量演进：

1. 先把 Prompt 与 Negative Prompt 做成全流程、分层、可测的统一基础层
2. 再用 DSPy 替代角色外貌提取主路径
3. 再把图片/视频生成升级为带检查与局部重试的闭环
4. 最后推广到 auto / manual / transition 全部入口

只有这样，项目才能从“字符串堆叠式 prompt 工程”逐步演进为“结构化约束 + 生成后验证 + 有限纠错”的一致性生成系统。
