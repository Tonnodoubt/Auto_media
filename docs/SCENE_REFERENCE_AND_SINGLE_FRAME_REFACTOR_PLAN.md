# 场景参考图与核心分镜单帧化重构方案

> 修订日期：2026-03-27
>
> 文档定位：对齐当前已实现代码，并明确后续 Phase 3 / Phase 4 的收口方向。
>
> 当前边界：场景参考图 Phase 1 / Phase 2 已落地；核心分镜首帧接入与主镜头双帧清理已按主链路完成。过渡视频后端本轮不做。

---

## 1. 当前问题与本轮目标

当前主链路的问题主要有两类：

1. 同一集里本该共享环境的多个场景，被拆成了过多环境组
   - 旧逻辑对 `environment / visual / lighting / mood` 的整段文本过于敏感
   - 抽象词、情绪词、动作词、镜头词会把本来相似的物理空间错误拆开

2. 环境图本身容易被人物和剧情污染
   - 角色动作、主角描述、情绪修辞被混进环境图 prompt
   - 生成结果不是“主环境参考图”，而更像“剧情图”

本轮已经先完成的目标是：

1. 以“每集一处入口”的方式生成共享环境图组
2. 同集内按环境相似度自动拆成 1 组或多组
3. 每组只生成 1 张主场景参考图，不再生成 `wide + close`
4. 环境图 prompt 明确排除主角、人体、服装、武器、动作、叙事内容
5. 小幅文本微调不强制整组重生，优先复用已有环境图资产

---

## 2. 当前已实现状态

### 2.1 已落地范围

目前代码中已经完成：

1. 前端按集展示共享环境图组入口与状态
2. 后端 `scene_reference` 服务生成本集环境图组
3. 同集内相似场景共组、差异大场景拆组
4. 每个环境组只生成单张 `scene` 参考图
5. 结果写入 `Story.meta.episode_reference_assets`
6. 同时把每个 `scene_key` 映射回对应环境组，写入 `Story.meta.scene_reference_assets`
7. 若环境组核心锚点未变化，则重新生成时直接复用旧资产

当前涉及文件包括：

- `app/services/scene_reference.py`
- `app/routers/story.py`
- `frontend/src/stores/story.js`
- `frontend/src/components/SceneStream.vue`
- `frontend/src/views/Step4Preview.vue`
- `frontend/src/views/VideoGeneration.vue`
- `tests/test_scene_reference.py`

### 2.2 当前未完成范围

以下内容仍未接入主链路：

1. `Shot` 级首帧图读取场景参考图
2. `Shot.source_scene_key` 的完整接线
3. 主镜头视频链路完全移除 `last_frame_url`
4. 过渡视频后端

所以本文件后半部分仍保留 Phase 3 / Phase 4 的后续计划，但前半部分全部以“已实现现状”为准。

---

## 3. 当前真实设计口径

### 3.1 共享环境图的粒度

当前不是“每个场景一套按钮、一套图片”，而是：

1. 每集只有一处环境图组生成入口
2. 后端读取该集全部 `ScriptScene`
3. 自动把相似环境归并成同一组
4. 差异大的环境再拆出额外组

也就是：

```text
Episode
  -> Environment Group 1
  -> Environment Group 2
  -> ...
```

而不是：

```text
Scene 1 -> 一套图
Scene 2 -> 一套图
Scene 3 -> 一套图
```

### 3.2 当前每组只生成一张图

当前代码已明确改为：

- 每个环境组只生成 1 张 `variants.scene`
- 不再生成 `wide`
- 不再生成 `close`
- 不保留旧双图兼容层作为正式方案

这张图的职责是：

1. 作为该环境组的主场景参考图
2. 提供稳定的环境布局、结构、光线方向、主色调、核心背景道具
3. 为后续首帧图生成提供统一环境基准

它不是：

1. 分镜首帧图
2. 过渡图
3. 剧情动作图
4. 主角 pose 图

### 3.3 当前环境图必须是“纯环境图”

环境图 prompt 已收紧为：

1. 只保留环境锚点
2. 弱化或移除情绪、剧情、人物动作
3. 明确禁止人物、脸、身体、服装、武器、动作、叙事 beat

当前 negative prompt 已明确排除：

- `person`
- `human`
- `man`
- `woman`
- `child`
- `face`
- `portrait`
- `silhouette`
- `full body`
- `costume`
- `weapon`

因此当前口径是：

```text
主环境参考图 = 环境空间 + 光线 + 背景道具
不包含主角表演，不承担剧情推进
```

---

## 4. 当前环境分组逻辑

### 4.1 分组目标

当前分组逻辑的目标不是“文本越像越合并”，而是：

1. 同一物理空间尽量合并
2. 不同物理空间尽量拆开
3. 抽象词、情绪词、动作词不能主导分组

### 4.2 当前实际做法

后端在 `app/services/scene_reference.py` 中，已经将场景分组改为“环境锚点优先”：

1. 从 `environment + visual` 中抽取 `place_anchors`
   - 例如：`王府回廊`、`地牢刑房`、`书房`、`庭院`

2. 从 `environment + visual` 中抽取 `object_anchors`
   - 例如：`朱红立柱`、`灯笼`、`青石地面`、`石墙`、`铁链`

3. 构造 `environment_signature`
   - 用于环境组相似度判断和后续复用签名

4. 剔除匹配噪声
   - 人物、主角、镜头、构图、景深、电影感
   - 压抑、宿命、紧绷、浪漫等情绪词
   - 站在、走向、回头、看向等动作词
   - 清晨、夜晚、雨后、黄昏等不应主导分组的词

### 4.3 当前分组效果预期

例如在同一集中：

- `王府回廊，雨后地面反光，气氛压抑`
- `王府回廊尽头，灯笼摇晃，宿命感逼近`

应归为同一组。

而：

- `地牢刑房，潮湿石墙与铁链`

应拆到另一组。

也就是：

```text
相同物理空间 + 部分相同环境道具 -> 合并
仅情绪/动作/抽象修辞不同 -> 不拆组
核心空间结构不同 -> 拆组
```

---

## 5. 当前资产结构

### 5.1 Story 级存储

当前正式资产结构是：

```json
{
  "meta": {
    "episode_reference_assets": {
      "ep01_env01": {
        "status": "ready",
        "environment_pack_key": "ep01_env01",
        "group_index": 1,
        "group_label": "环境组 1",
        "affected_scene_keys": ["ep01_scene01", "ep01_scene02"],
        "affected_scene_numbers": [1, 2],
        "summary_environment": "王府回廊",
        "summary_lighting": "冷色天光混合暖色灯笼侧光",
        "summary_mood": "压抑克制",
        "summary_visuals": ["朱红立柱与灯笼", "湿润青石地面"],
        "variants": {
          "scene": {
            "prompt": "...",
            "image_url": "/media/episodes/ep01_env01_scene_xxxx.png",
            "image_path": "media/episodes/ep01_env01_scene_xxxx.png"
          }
        },
        "reuse_signature": "...",
        "updated_at": "2026-03-27T12:00:00+00:00"
      }
    },
    "scene_reference_assets": {
      "ep01_scene01": { "...同组资产副本..." },
      "ep01_scene02": { "...同组资产副本..." }
    }
  }
}
```

### 5.2 关键字段说明

- `episode_reference_assets`
  - 按环境组存主资产

- `scene_reference_assets`
  - 按 `scene_key` 回填命中的环境组资产，方便前端按 scene 快速查

- `variants.scene`
  - 当前唯一正式环境图变体

- `reuse_signature`
  - 用于判断环境组是否与历史资产一致，若一致则直接复用

### 5.3 当前不兼容旧双图结构

当前方案已明确不再兼容旧 `wide / close` 双图结构作为正式运行时路径。

这意味着：

1. 新生成结果只会写 `variants.scene`
2. 文档不再保留旧双图结构作为目标态
3. 如果资产库中仍有旧双图数据，应重新生成本集环境图组

---

## 6. 当前前端表现

### 6.1 Step4 / Step5 展示方式

当前前端已统一为：

1. 每集一处环境图组面板
2. 展示该集全部环境组
3. 每组只显示 1 张主场景参考图
4. 单个 scene 不再重复展示按钮和缩略图
5. 单个 scene 只显示自己匹配到哪个环境组

当前主要落点：

- `frontend/src/components/SceneStream.vue`
- `frontend/src/views/Step4Preview.vue`
- `frontend/src/views/VideoGeneration.vue`

### 6.2 当前状态口径

前端仍保留统一状态枚举：

- `idle`
- `loading`
- `ready`
- `failed`
- `stale`

但当前 `stale` 的实际使用要服从后端复用逻辑，不再简单理解为“文本改一点就一定要全量重生”。

---

## 7. 当前后端接口

### 7.1 接口

当前已实现接口：

```text
POST /api/v1/story/{story_id}/scene-reference/generate
```

请求：

```json
{
  "episode": 1,
  "force_regenerate": false
}
```

响应：

```json
{
  "episode": 1,
  "groups": [
    {
      "environment_pack_key": "ep01_env01",
      "affected_scene_keys": ["ep01_scene01", "ep01_scene02"],
      "asset": {
        "status": "ready",
        "variants": {
          "scene": {
            "prompt": "...",
            "image_url": "/media/episodes/ep01_env01_scene_xxxx.png",
            "image_path": "media/episodes/ep01_env01_scene_xxxx.png"
          }
        }
      }
    }
  ]
}
```

### 7.2 图片存储

当前环境图写入：

- 目录：`media/episodes`
- URL 前缀：`/media/episodes`

---

## 8. 当前复用与重建规则

### 8.1 当前规则

当前不再采用“只要场景文本改了就整集重生”的粗暴逻辑。

而是：

1. 每次重新读取本集场景
2. 重新计算环境组
3. 为每个环境组计算 `reuse_signature`
4. 若与历史环境组签名一致，则直接复用旧图
5. 仅对新增环境组或签名明显变化的环境组重新生图

### 8.2 实际含义

以下情况通常不需要重生整组环境图：

1. 同一环境下的轻微文案微调
2. 抽象氛围词变化
3. 人物动作、表情、叙事描述变化
4. 分镜层的小范围调整

以下情况才应触发该组重生：

1. 物理空间变了
2. 核心环境锚点变了
3. 关键背景结构或环境道具变了
4. `art_style` 明显改变

---

## 9. 当前与主镜头链路的关系

### 9.1 已完成部分

当前已经完成的是“环境图组基础设施”，即：

```text
Episode scenes
  -> environment grouping
  -> scene reference generation
  -> asset persistence
  -> frontend display
```

### 9.2 当前主链路状态

当前已经接到核心 shot 主链路里：

```text
scene reference
  -> shot first frame image
  -> single-frame I2V
```

所以当前状态应理解为：

- Phase 1：已完成
- Phase 2：已完成并优化
- Phase 3：已完成
- Phase 4：已完成

---

## 10. 后续实施顺序

### Phase 3：将首帧图片生成逻辑接入场景参考图

这一阶段的目标是：

1. `Shot` 增加 `source_scene_key`
2. storyboard 生成链路补上 `shot -> scene` 映射
3. 图片生成时，按 `source_scene_key` 找到命中的环境组
4. 将 `variants.scene` 作为首帧图生成参考
5. 先走软参考：
   - 把环境图 prompt 锚点并入 `shot.image_prompt`
6. 若底层 provider 未来支持图像参考，再扩展硬参考

这一阶段的重点变化是：

```text
scene reference -> shot first frame
```

而不是：

```text
scene reference -> 直接生视频
```

### Phase 4：修复核心分镜双帧污染问题

这一阶段才处理当前主链路的核心异常：

1. 普通 shot 不再消费 `last_frame_url`
2. 普通 shot 不再依赖 `last_frame_prompt`
3. 主镜头视频链路统一收口成单帧 I2V
4. transition 相关字段不再污染主镜头

目标态是：

```text
scene reference
  -> shot first frame image
  -> motion-focused video prompt
  -> image-to-video
```

而不是：

```text
first frame + last frame
  -> 强行双帧约束主镜头
```

---

## 11. 当前验收结论

截至当前代码，已经满足：

1. 每一集都可以生成和重生成多组共享环境图
2. 相似场景能合并，差异大场景能拆组
3. 分组时不再被大量抽象词、情绪词、动作词误导
4. 每组只生成 1 张主场景参考图
5. 环境图 prompt 已明确排除主角及与环境无关内容
6. 微调不会默认触发整集环境图全量重生
7. 资产库按 episode / scene 双映射持久化
8. Step4 / Step5 前端都能正确展示当前环境组状态

尚未满足：

1. 过渡视频后端接入

---

## 12. 最终建议

接下来不要再把三种资产混在一起：

1. `SceneReferenceAsset`
   - 负责环境一致性
   - 当前已落地

2. `Shot First Frame`
   - 负责具体分镜内容
   - 下一阶段接入

3. `TransitionAsset`
   - 负责镜头间过渡
   - 本轮暂不实现后端

当前正确推进顺序应当是：

```text
先稳定 scene reference
再接 shot first frame
最后清理主镜头双帧链路
```

不要反过来先在视频层继续堆叠过渡和尾帧逻辑，否则只会重新把主链路污染回去。
