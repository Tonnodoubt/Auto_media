# Auto_media 视频生成与视觉一致性统一文档

> 更新日期：2026-04-01
>
> 文档定位：本文件是视频生成主链路、视觉一致性资产层、场景参考图、首帧生成、历史链式方案的统一入口。
>
> 状态说明：
>
> - 当前主链路已落地 `StoryContext`、分字段 prompt 组装、场景参考图资产、`scene reference -> shot first frame -> single-frame I2V`。
> - 当前已补齐 Phase 3 固定样本、seed 脚本与人工验收 runbook；真实 provider 串行验收仍待执行。
> - DSPy 提取器、VLM 质检闭环、Prompt Caching 深化、独立数字资产库仍属于后续增强。
> - “链式视频生成”保留为历史/备选方案，不是当前默认实现路径。
>
> 提示词模板详见 [prompt-framework.md](prompt-framework.md)。

---

## 一、统一结论

当前项目里，视频一致性问题已经不是“单纯把 prompt 写长一点”就能解决，而是要靠一套统一的运行时资产层：

1. `StoryContext`
   - 统一收口角色外貌锁、基础画风、场景风格补充、负向约束
2. 场景参考图资产
   - 按集生成共享环境组，为首帧图片提供稳定环境基准
3. 分字段 prompt 组装
   - 主链路字段是 `image_prompt`、`final_video_prompt`、`negative_prompt`
   - `last_frame_prompt` 只保留兼容/特殊终态场景，不进入普通主镜头运行期
4. 单帧主链路
   - 当前主镜头生成已经收口为 `scene reference -> shot first frame -> image-to-video`

旧文档中三个常见误区，需要在这里一次性澄清：

1. 当前主链路不是“把角色设定图 prompt 直接拼回镜头 prompt”
2. 当前主链路不是“所有镜头默认走链式传最后一帧”
3. 当前项目还没有独立的 `digital_assets` 资产库表，现阶段正式资产仍以 `Story.character_images` 和 `Story.meta[...]` 为主

---

## 二、主链路总览

```text
剧本 / 分镜数据
  │
  ├─ 0. StoryContext 构建
  │     ├─ character_appearance_cache
  │     ├─ scene_style_cache
  │     ├─ art_style
  │     └─ negative_prompt
  │
  ├─ 1. 场景参考图命中
  │     └─ scene_reference_assets / episode_reference_assets
  │
  ├─ 2. 生成 payload
  │     ├─ image_prompt
  │     ├─ final_video_prompt
  │     ├─ negative_prompt
  │     └─ reference_images
  │
  ├─ 3. 首帧图片生成
  │     └─ scene reference + shot image prompt
  │
  ├─ 4. 单帧 I2V 视频生成
  │     └─ motion-focused final_video_prompt
  │
  └─ 5. 可选后处理 / 规划能力
        ├─ VLM 抽检与有限次重试
        ├─ Prompt Caching
        └─ DSPy 结构化提取
```

当前最重要的设计边界是：

- 图片阶段消费 `image_prompt`
- 视频阶段消费 `image_url + final_video_prompt`
- `last_frame_prompt` 不属于普通主镜头 mainline；transition 使用的是后端提取的双帧 URL
- `negative_prompt` 作为独立字段或 provider 参数处理，不回退成正向 prompt 的机械拼接

---

## 三、当前已落地的一致性资产层

### 3.1 现有资产存储位置

| 资产 | 存储位置 | 当前用途 |
|------|------|------|
| 角色设定图 | `Story.character_images` | 存 `design_prompt / visual_dna / image_url / image_path` |
| 角色外貌缓存 | `Story.meta["character_appearance_cache"]` | 运行时主缓存，提供 `body / clothing / negative_prompt` |
| 场景风格缓存 | `Story.meta["scene_style_cache"]` | 为图片/视频 prompt 补充场景级风格 |
| 环境图组资产 | `Story.meta["episode_reference_assets"]` | 每集环境组主资产 |
| 场景命中环境图 | `Story.meta["scene_reference_assets"]` | `scene_key -> 环境组资产` 映射 |

### 3.2 当前项目还没有什么

以下能力还没有作为正式运行时能力落地：

- 独立 `digital_assets` 表
- 跨故事资产版本管理
- 资产标签检索和 UI 管理后台
- 通用数字资产库 CRUD

因此“数字资产库”在当前项目里的正确理解，是“Story 级一致性资产层”，而不是独立 DAM 系统。

### 3.3 StoryContext 作为统一入口

当前主链路已经以 `StoryContext` 为运行时收口点，避免自动模式、手动模式、单镜头接口各自拼装 prompt。

推荐理解为：

```python
@dataclass
class CharacterLock:
    body_features: str
    default_clothing: str
    negative_prompt: str = ""

@dataclass
class SceneStyle:
    image_extra: str
    video_extra: str
    negative_prompt: str = ""

@dataclass
class StoryContext:
    base_art_style: str
    global_negative_prompt: str
    character_locks: dict[str, CharacterLock]
    scene_styles: list[SceneStyle]
    clean_character_section: str
```

字段来源口径：

| 字段 | 当前来源 |
|------|------|
| `base_art_style` | `Story.art_style` |
| `character_locks` | `meta.character_appearance_cache` 优先，其次 `character_images.visual_dna`，最后角色描述 |
| `scene_styles` | `Story.genre` + `Story.selected_setting` + `meta.scene_style_cache` |
| `world_summary` | 真实落点优先取 `Story.selected_setting`，不是只看 `meta["world_summary"]` |

---

## 四、角色一致性：从 Visual DNA 到 CharacterLock

### 4.1 当前问题

如果只依赖分镜 LLM 自由描述角色外貌，会出现：

- 同一角色跨镜头发型、服装、体型漂移
- 角色设定图虽然已生成，但没有被稳定投影到运行时
- 多角色同框时外貌属性串扰

### 4.2 当前正确口径

角色一致性已经从“直接重用 character sheet prompt”收敛为“结构化外貌锁 + 干净角色块”：

1. 主缓存是 `meta["character_appearance_cache"]`
2. `character_images[*]["visual_dna"]` 仅保留为兼容投影字段
3. 上游传给 storyboard 的是干净版 `Character Reference`
4. 运行时再按图片/视频阶段分别注入对应字段

### 4.3 推荐存储格式

```json
{
  "character_appearance_cache": {
    "char_liming": {
      "body": "young male, silver-white hair, ice blue eyes, slender build",
      "clothing": "white hanfu with blue cloud embroidery",
      "negative_prompt": "modern casualwear"
    }
  }
}
```

读取优先级：

1. `meta.character_appearance_cache[character_id]`
2. `character_images[character_id].visual_dna`
3. `characters[].description`

### 4.4 干净角色块，而不是回灌原始设定图 prompt

当前上游和运行时都应避免把三视图设定图里的噪声词重新注入生成链路，例如：

- `clean background`
- `character sheet`
- `front / side / back view`
- 排版要求
- 纯设定图摄影棚语言

正确目标是保留 immutable traits，并允许镜头级服装、姿态、动作继续由分镜和剧情驱动。

---

## 五、场景参考图：当前正式方案

### 5.1 当前定位

场景参考图已经是当前主链路的一部分，不再只是设计稿。

它负责：

1. 稳定环境空间、光线方向、主色调、背景道具
2. 作为首帧图片生成的环境基准
3. 为同集内共享物理空间的多个场景提供复用资产

它不负责：

1. 主角 pose
2. 剧情动作
3. 镜头过渡
4. 直接替代主镜头视频生成

### 5.2 当前粒度

当前不是“一场一个参考图按钮”，而是：

```text
Episode
  -> Environment Group 1
  -> Environment Group 2
  -> ...
```

也就是每集统一生成环境图组，再把 `scene_key` 映射回命中的环境组。

### 5.3 当前每组只生成一张主环境图

当前正式运行时结构只有：

- `variants.scene`

不再把旧的 `wide / close` 双图结构作为目标态保留。

### 5.4 当前环境图必须是纯环境图

环境图 prompt 已经收紧为：

- 只保留环境锚点
- 弱化或移除情绪、剧情、人物动作
- 明确排除人物、脸、服装、武器、姿态、叙事 beat

可概括为：

```text
主环境参考图 = 环境空间 + 光线 + 背景道具
不承担主角表演，不承担剧情推进
```

### 5.5 当前分组逻辑

环境分组逻辑的目标不是“文本越像越合并”，而是“同一物理空间尽量合并，不同空间尽量拆开”。

当前主要依据：

1. `place_anchors`
2. `object_anchors`
3. `environment_signature`
4. 噪声剔除

不会主导分组的噪声包括：

- 情绪词
- 动作词
- 镜头词
- 抽象修辞
- 不足以代表空间结构的时间词

### 5.6 当前资产结构

```json
{
  "meta": {
    "episode_reference_assets": {
      "ep01_env01": {
        "status": "ready",
        "environment_pack_key": "ep01_env01",
        "affected_scene_keys": ["ep01_scene01", "ep01_scene02"],
        "variants": {
          "scene": {
            "prompt": "...",
            "image_url": "/media/episodes/ep01_env01_scene_xxxx.png",
            "image_path": "media/episodes/ep01_env01_scene_xxxx.png"
          }
        },
        "reuse_signature": "..."
      }
    },
    "scene_reference_assets": {
      "ep01_scene01": { "...命中的环境组资产副本..." }
    }
  }
}
```

### 5.7 接口与展示

当前已实现接口：

```text
POST /api/v1/story/{story_id}/scene-reference/generate
```

当前前端口径：

1. 每集一处环境图组面板
2. 单个 scene 不重复展示按钮和缩略图
3. 每组只显示 1 张主场景参考图
4. scene 只展示自己命中的环境组

### 5.8 复用与重建规则

当前不会因为轻微文案改动就整集重生。

流程是：

1. 重新读取本集 scene
2. 重新计算环境组
3. 计算每组 `reuse_signature`
4. 命中则复用旧资产
5. 只有新增组或签名明显变化的组才重生

通常触发重生的条件：

- 物理空间变化
- 核心背景结构变化
- 关键环境道具变化
- `art_style` 明显变化

---

## 六、首帧与主镜头生成：当前默认路径

### 6.1 当前主镜头链路

当前默认实现已收口为：

```text
scene reference
  -> shot first frame image
  -> motion-focused final_video_prompt
  -> single-frame image-to-video
```

而不是：

```text
first frame + last frame
  -> 强行双帧约束所有主镜头
```

### 6.2 为什么必须保留分字段 Prompt

当前已经明确拆分：

- `image_prompt`：首帧静态内容、构图、环境、定格姿态，以及视频必须一开始就看见的人体范围、手部、关键道具、空间关系
- `final_video_prompt`：动作、运镜、短时运动执行，默认建立在首帧已经满足主体信息的前提上
- `last_frame_prompt`：兼容字段，普通主镜头不再消费

因此一致性层不能再回退成一个“大一统 prompt”。

推荐运行时产物仍然是 bundle：

```python
payload = {
    "image_prompt": "...",
    "final_video_prompt": "...",
    "negative_prompt": "...",     # optional
    "reference_images": [...],    # optional
}
```

### 6.3 当前 Prompt 组装公式

```text
图片正向 prompt:
  [干净角色块] + [image_prompt] + [scene_style image extra] + [art_style]

视频正向 prompt:
  [干净角色块] + [final_video_prompt] + [scene_style video extra] + [art_style]
```

当前额外约束是：

1. 首帧图片是主镜头视频的起始状态，不能和 `final_video_prompt` 打架。
2. 如果视频要求至少半身、双手、道具或明确空间关系，这些内容必须优先落在首帧里，不能指望视频“凭空补出来”。
3. 同一场景相邻镜头虽然单独生成，但剧情上必须视作连续动作；后一镜首帧不能无故重置成独立海报或纯脸部特写。

负向 prompt 规则：

- 图片 provider 支持独立参数时，单独传入
- 视频 provider 若不支持，则默认丢弃 negative，不做机械正向改写
- 少量人工校验过的 guardrails 可以进入 `scene_style` 或 provider 适配层

### 6.4 当前已完成的主链路修正

相较旧稿，当前仓库已经完成这些关键修正：

1. 自动流水线、手动 `/pipeline/*`、单镜头 `/image/*` 与 `/video/*` 统一复用主入口
2. `Shot` schema 仍兼容 `last_frame_prompt`，但运行时主 bundle 已收口为 `image_prompt / final_video_prompt / negative_prompt / reference_images`
3. `_postprocess_shot()` 优先保留分镜 LLM 产物，只做轻量归一化
4. 运行时优先读取 `StoryContext`，而不是回灌原始角色设定图 prompt
5. 图片链路中的 `negative_prompt` 已与 `art_style` 解耦

---

## 七、链式视频生成：历史文档收口后的备选方案

### 7.1 方案定义

链式视频生成指的是：同一场景内，后一个镜头直接使用前一个视频的最后一帧作为起始图。

```text
场景首镜头 -> 首帧生图 -> 视频1 -> 提取最后一帧
                               ↓
后续镜头   <- 复用最后一帧 -> 视频2 -> 提取最后一帧
```

### 7.2 这个方案解决什么

它主要解决：

- 同场景相邻镜头的视觉连续性
- 角色和背景在短链路内的自然延续
- 不依赖参考图 API 的基本连续性增强

### 7.3 为什么它不是当前默认主链路

链式方案虽然有价值，但当前不作为默认实现，原因包括：

1. 当前主链路已经有场景参考图 + 首帧图 + 单帧 I2V，能覆盖大部分一致性需求
2. 链式模式会引入串行依赖，显著增加时延
3. 视频压缩后再抽帧重喂，会带来质量累积衰减
4. 单镜头失败会阻塞同场景后续镜头
5. 它与当前“主镜头去双帧污染”的收口方向并不完全一致

### 7.4 适合重新评估的场景

如果后续要重新启用链式模式，更适合限定在以下条件：

- 超强连续性的长场景
- 同一空间内连续动作表演
- provider 对 I2V 起始帧稳定性较好
- 场景内镜头数可控

建议仍保留“场景内链式、场景间并行”的设计原则，而不是全局串行。

### 7.5 保留的风险结论

链式模式的风险仍成立：

- 最后一帧需要可访问 URL 或可上传资产
- 画质可能逐步衰减
- 错误恢复需要断点续生
- 单场景镜头数越多，耗时越高

因此当前统一口径是：保留为备选方案，不与现网默认路径混写。

---

## 八、规划中的增强能力

### 8.1 DSPy 结构化提取

目标：

- 将角色外貌提取从硬编码 prompt 演进为结构化抽取
- 输出继续写入 `meta["character_appearance_cache"]`
- 生产环境只加载离线编译结果，不在请求链路实时 compile

### 8.2 VLM 反馈闭环

建议挂载点：

- 图片生成后检查角色外貌、服装、主体数量
- 视频生成后检查起始帧一致性、动作完成度、终态是否符合要求
- 失败时只对当前 shot 增加纠错指令并有限次重试

成本控制原则：

1. 不默认全量检查
2. 新角色首次出场必检
3. 大跨度换装必检
4. 同场景连续镜头建议抽检

### 8.3 Prompt Caching

前置条件不是“立刻上缓存”，而是先保证静态前缀稳定：

- 去掉时间戳、UUID、调试寄语等动态噪声
- 把结构化 `messages` 作为长期演进方向
- `cache_fingerprint` 只用于调试和观测，不进入业务分支

### 8.4 独立数字资产库

如果未来要做真正的数字资产库，建议把它看成当前 Story 级资产层的下一阶段，而不是与现有缓存体系并行再造一套真相源。

推荐顺序：

1. 先稳定 Story 级一致性资产
2. 再引入跨 Story 复用和检索
3. 最后再考虑独立表、标签系统和管理 UI

---

## 九、自动模式与手动模式的统一要求

后续所有一致性增强都应同时覆盖：

1. 自动流水线
2. 手动 `/pipeline/*`
3. 单镜头 `/image/*`
4. 单镜头 `/video/*`

不能只在 `PipelineExecutor` 做增强，否则手动补图、手动补视频会重新分叉。

统一原则：

- 统一走 `StoryContext`
- 统一走分字段 payload
- 统一消费场景参考图资产
- provider 差异只留在适配层

---

## 十、当前验收结论

截至 2026-04-01，当前主链路已经满足：

1. 角色一致性不再依赖原始设定图 prompt 直接回灌
2. 主镜头运行时 bundle 已收口为 `image_prompt / final_video_prompt / negative_prompt / reference_images`
3. 场景参考图已具备按集分组、复用、展示、持久化能力
4. 主镜头链路已收口为“场景参考图 -> 首帧图 -> 单帧 I2V”
5. 旧 `wide / close` 环境双图结构不再是正式目标态

当前仍未落地：

1. DSPy 提取器
2. VLM 自动质检与重试闭环
3. 真正独立的数字资产库
4. 基于真实 provider 的 Phase 3 人工串行验收闭环
5. 将链式模式作为正式默认策略

---

## 十一、建议阅读顺序

1. `README.md`
2. 本文档
3. [prompt-framework.md](prompt-framework.md)
4. [feature-documentation.md](feature-documentation.md)
5. [END_TO_END_CONSISTENCY_IMPLEMENTATION_PLAN.md](END_TO_END_CONSISTENCY_IMPLEMENTATION_PLAN.md)
