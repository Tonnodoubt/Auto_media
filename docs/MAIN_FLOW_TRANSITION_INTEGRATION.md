# 主流程接入过渡视频说明

> 更新日期：2026-03-27
> 适用范围：基于当前仓库真实实现，规划下一阶段后端接入
> 当前前提：前端过渡插槽 UI 已完成，下一步开始搭建后端

---

## 1. 本次重构后的结论

这次接入方案要明确三条硬规则：

1. 双帧能力只用于“过渡视频”这一类运行时资产
2. 普通主镜头继续保持当前单首帧 I2V 链路，不回退到 `Shot.last_frame_*`
3. 过渡视频使用的两张锚点图，必须从相邻两个主镜头视频中提取对应帧，不接受前端随意传入其他图片

一句话总结：

**过渡视频是独立资产，不是 storyboard 里的普通 Shot；双帧是 transition 专用能力，不污染主链路。**

---

## 2. 需要先和当前代码对齐的真实现状

### 2.1 当前主镜头链路已经统一为单首帧 I2V

当前仓库已经明确把普通主镜头收口到“单首帧 I2V”：

- `app/schemas/storyboard.py`
  - `Shot.last_frame_prompt`
  - `Shot.last_frame_url`
  都已标记为“主镜头链路不再消费”

- `app/services/storyboard.py`
  - `_postprocess_shot()` 会主动把普通 shot 的 `last_frame_prompt` 和 `last_frame_url` 清空
  - 代码注释已经写明：避免 dual-frame 污染主镜头 payload

- `app/services/image.py`
  - `generate_images_batch()` 当前只生成主镜头首帧 `image_url`
  - 不再为普通 shot 生成 `last_frame_url`

- `app/services/video.py`
  - `generate_videos_batch()` 对普通 storyboard shots 固定走单帧 I2V
  - `last_frame_url=""`

这意味着：

**当前项目已经天然满足“不要让双帧影响其他视频”的大方向。**

### 2.2 前端已完成 transition slot 占位

`frontend/src/views/VideoGeneration.vue` 当前已经完成：

- 在相邻主镜头之间插入 `transition slot`
- 展示前后镜头状态
- 展示“Ready / Pending”
- 预留“生成过渡视频”按钮

但当前仍然只是 UI 占位：

- 没有后端 transition 生成接口
- 没有 transition 持久化结构
- `concatAllVideos()` 仍然只按 `shot_id` 排序拼接主镜头

### 2.3 豆包 provider 具备双帧能力，但现在没有被主流程安全封装

`app/services/video_providers/doubao.py` 已支持：

- `first_frame`
- `last_frame`

也就是说 API 能力已经在底层具备，但主流程还缺：

1. transition 专用请求/返回结构
2. 只作用于 transition 的服务层封装
3. 帧提取与帧来源校验
4. transition 的持久化和拼接顺序

---

## 3. 本轮后端接入的目标

本轮不是去改 LLM 输出更多“过渡分镜”，而是补齐运行时能力闭环：

1. 用户先照常生成主镜头图片和主镜头视频
2. 在两个相邻主镜头之间，手动触发“生成过渡视频”
3. 后端只根据相邻主镜头的真实资产生成 transition
4. 生成后的 transition 可以单独重试、单独删除、单独拼接
5. 如果某个 transition 不存在，主镜头链路和最终导出仍然可正常工作

---

## 4. 核心原则

### 4.1 transition 是独立运行时资产，不是 Shot 扩展字段

不建议把 transition 塞回 `Shot`：

- 会污染 storyboard 主结构
- 会让普通镜头也卷入双帧字段
- 会让现有 `generate_images_batch()` / `generate_videos_batch()` 变复杂

推荐做法：

- `Shot` 继续只代表主镜头
- `TransitionResult` 代表运行时新增过渡资产
- transition 的生成、存储、重试、删除全部独立处理

### 4.2 前端不传“任意图片 URL”，后端自己解析相邻资产

这是本次设计最重要的安全原则。

前端按钮触发时，只应传：

- `pipeline_id`
- `story_id`
- `from_shot_id`
- `to_shot_id`
- 可选 `transition_prompt`

前端**不要**直接传：

- `from_image_url`
- `to_image_url`
- `last_frame_url`
- 任意本地文件路径

原因：

1. 前端传 URL 很容易把其他图片、旧图、错误场景图带进来
2. 用户要求必须读取“前后视频的对应帧”
3. 只有后端知道当前 storyboard 顺序、pipeline 状态、真实资产归属

### 4.3 双帧只存在于 `generate_transition_video()`

普通视频继续走现有：

```text
shot.image_url -> generate_video(..., last_frame_url="")
```

过渡视频单独走：

```text
extract from_shot last frame
extract to_shot first frame
-> generate_transition_video(..., last_frame_url=to_first_frame_url)
```

这样可以把双帧能力限制在 transition 服务内部，不影响现有批量主镜头生成逻辑。

---

## 5. 推荐的数据结构

### 5.1 `app/schemas/pipeline.py`

建议新增：

```python
class TransitionGenerateRequest(BaseModel):
    pipeline_id: str
    story_id: Optional[str] = None
    from_shot_id: str
    to_shot_id: str
    transition_prompt: Optional[str] = None
    duration_seconds: int = 2


class TransitionFrameSource(BaseModel):
    shot_id: str
    video_url: str
    frame_role: Literal["from_last", "to_first"]
    extracted_image_url: str


class TransitionResult(BaseModel):
    transition_id: str
    from_shot_id: str
    to_shot_id: str
    prompt: Optional[str] = None
    duration_seconds: int = 2
    video_url: str
    first_frame_source: TransitionFrameSource
    last_frame_source: TransitionFrameSource


class TimelineItem(BaseModel):
    item_type: Literal["shot", "transition"]
    item_id: str
```

### 5.2 持久化位置

建议先复用现有 pipeline/generated_files 结构：

```json
{
  "storyboard": {...},
  "images": {...},
  "videos": {...},
  "transitions": {
    "transition_scene1_shot1__scene1_shot2": {
      "transition_id": "transition_scene1_shot1__scene1_shot2",
      "from_shot_id": "scene1_shot1",
      "to_shot_id": "scene1_shot2",
      "video_url": "/media/videos/transition_scene1_shot1__scene1_shot2_xxx.mp4",
      "first_frame_source": {...},
      "last_frame_source": {...}
    }
  },
  "timeline": [
    {"item_type": "shot", "item_id": "scene1_shot1"},
    {"item_type": "transition", "item_id": "transition_scene1_shot1__scene1_shot2"},
    {"item_type": "shot", "item_id": "scene1_shot2"}
  ]
}
```

这样不会影响已有 `shots/images/videos/final_video_url` 结构，只是额外扩展。

---

## 6. transition 生成的正确后端流程

### 6.1 调用入口

建议新增接口：

```text
POST /api/v1/pipeline/{project_id}/transitions/generate
```

职责：

1. 校验两个 shot 是否相邻
2. 校验两侧主镜头视频是否已存在
3. 从前后两个视频提取对应帧
4. 调用双帧视频生成 provider
5. 保存 transition 结果
6. 回写 pipeline `generated_files.transitions`

### 6.2 后端只接受“相邻 shot_id”

请求只允许：

- `from_shot_id`
- `to_shot_id`

后端必须自己从当前 storyboard 顺序里验证：

```text
index(to_shot_id) == index(from_shot_id) + 1
```

如果不相邻，直接拒绝：

- `400 Bad Request`
- `"Only adjacent shots can create a transition"`

这一步可以杜绝：

- 跨场景错连
- 跳着连镜头
- 把错误图片拼到错误位置

### 6.3 必须要求两侧主镜头视频都已生成

为了满足“读取前后视频的对应帧”，后端第一版应强制：

- `from_shot.video_url` 存在
- `to_shot.video_url` 存在

不建议第一版用 `to_shot.image_url` 代替目标帧。

原因：

1. 用户要求的是“前后视频的对应帧”
2. 用 next shot 的 image 虽然通常是首帧来源，但并不等于“从视频读取”
3. 如果后续 video provider 对首帧有裁切、重构、轻微构图偏移，直接读视频首帧更安全

因此前端 `ready` 状态在后端接入时也应同步收紧为：

```text
fromShot.video_url && toShot.video_url
```

### 6.4 精确帧提取规则

建议在 `app/services/ffmpeg.py` 新增一个首帧提取方法：

```python
async def extract_first_frame(video_path: str, output_stem: str) -> str:
    ...
```

然后 transition 流程固定采用：

1. 前镜锚点：
   - 从 `from_shot.video_url` 提取最后一帧
   - 输出路径：`media/images/{transition_id}_from_last.png`

2. 后镜锚点：
   - 从 `to_shot.video_url` 提取第一帧
   - 输出路径：`media/images/{transition_id}_to_first.png`

推荐命令语义：

- 前镜最后一帧：沿用现有 `extract_last_frame()` 思路
- 后镜第一帧：从视频开头截取第 1 帧

### 6.5 transition prompt 的来源

第一版 prompt 推荐由三部分组成：

1. `from_shot.transition_from_previous` 不参与
2. 主要使用 `to_shot.transition_from_previous`
3. 用户可在 UI 额外补一句 `transition_prompt`

推荐拼装方式：

```text
Base transition intent:
- connect the exact ending state of {from_shot_id}
- reach the exact opening state of {to_shot_id}
- preserve identity, outfit, lighting, and camera logic

Narrative bridge:
- {to_shot.transition_from_previous}

User hint:
- {transition_prompt}
```

注意：

- 不要把主镜头的长 prompt 直接整段塞进去
- 过渡视频建议 1-2 秒，只描述“衔接动作/衔接运镜”

### 6.6 只在 transition 服务里使用双帧

建议新增：

```python
async def generate_transition_video(
    *,
    transition_id: str,
    first_frame_url: str,
    last_frame_url: str,
    prompt: str,
    model: str,
    video_provider: str,
    video_api_key: str,
    video_base_url: str,
) -> dict:
    ...
```

内部调用仍可复用 `app/services/video.py::generate_video()`，但只在 transition 场景下传入 `last_frame_url`。

这样主镜头和过渡视频的边界会非常清晰：

- 主镜头：`generate_videos_batch()`，固定单帧
- 过渡视频：`generate_transition_video()`，固定双帧

---

## 7. 如何保证“不是其他图片或者错误内容”

这是本设计最关键的一节。

### 7.1 不信任前端传入的素材地址

后端不能直接消费前端传来的图片 URL。

必须通过以下路径反查真实资产：

1. 根据 `pipeline_id` 读取 `generated_files.storyboard.shots`
2. 找到 `from_shot_id` 和 `to_shot_id`
3. 再从 `generated_files.videos` 里找到这两个 shot 的 `video_url`
4. 从这两个 `video_url` 提取帧

这样 transition 所用帧只会来自当前 pipeline 当前 storyboard 当前相邻镜头。

### 7.2 强制做“相邻镜头关系校验”

只允许：

```text
scene1_shot1 -> scene1_shot2
scene1_shot2 -> scene1_shot3
scene2_shot1 -> scene2_shot2
```

不允许：

```text
scene1_shot1 -> scene1_shot3
scene1_shot2 -> scene2_shot2
```

只要不是 storyboard 顺序里的直接相邻项，就拒绝生成。

### 7.3 强制做“来源回写”

每个 transition 结果里都保存：

- 来源 shot_id
- 来源 video_url
- 提取帧角色
- 提取出的图片 URL

例如：

```json
{
  "first_frame_source": {
    "shot_id": "scene1_shot1",
    "video_url": "/media/videos/scene1_shot1_abcd1234.mp4",
    "frame_role": "from_last",
    "extracted_image_url": "/media/images/transition_scene1_shot1__scene1_shot2_from_last.png"
  }
}
```

这样后续排查“是否读错图”时可以直接追溯。

### 7.4 文件命名必须带 shot 归属

不建议输出泛化名字如：

- `first_frame.png`
- `last_frame.png`

应使用确定性命名：

```text
transition_{from_shot_id}__{to_shot_id}_from_last.png
transition_{from_shot_id}__{to_shot_id}_to_first.png
```

这样即使目录里存在很多图片，也不会串源。

### 7.5 transition 生成失败不能污染主镜头

如果 transition 失败：

- 不修改 `shots[*].video_url`
- 不回写到 `generated_files.videos`
- 只更新 `generated_files.transitions[transition_id]` 为失败状态，或直接不写入成功结果

这样能保证：

**过渡资产失败，不影响已有主镜头视频。**

---

## 8. 前端对接时要同步调整的点

### 8.1 `ready` 判定要改严

当前 `VideoGeneration.vue` 的占位逻辑是：

```js
ready: !!shot.video_url && !!(nextShot.video_url || nextShot.image_url)
```

后端接入后应改为：

```js
ready: !!shot.video_url && !!nextShot.video_url
```

原因不是功能实现难度，而是产品约束已经变了：

**我们要保证读取的是前后两个视频的对应帧。**

### 8.2 按钮只传 shot 对，不传素材 URL

前端按钮点击时应只发：

```json
{
  "pipeline_id": "...",
  "story_id": "...",
  "from_shot_id": "scene1_shot1",
  "to_shot_id": "scene1_shot2",
  "transition_prompt": "镜头轻微推近，人物动作自然接续"
}
```

### 8.3 前端展示 transition 结果

生成成功后，slot 中应展示：

- transition video 预览
- 来源说明：`scene1_shot1 -> scene1_shot2`
- 重试按钮
- 删除按钮

而不是把 transition 假装成普通 shot card。

---

## 9. 拼接逻辑如何接入主流程

### 9.1 当前问题

`concatAllVideos()` 目前只做了：

1. 过滤有 `video_url` 的主镜头
2. 按 `shot_id` 排序
3. 直接传给 `/concat`

这会导致：

- transition 即使生成成功，也不会参与导出
- 后续如果 transition 单独存在，排序也会混乱

### 9.2 推荐做法：引入 timeline

最终导出顺序不应再从 `shot_id` 推断，而应读取显式时间线：

```json
[
  {"item_type": "shot", "item_id": "scene1_shot1"},
  {"item_type": "transition", "item_id": "transition_scene1_shot1__scene1_shot2"},
  {"item_type": "shot", "item_id": "scene1_shot2"}
]
```

拼接时规则如下：

1. timeline 中 `shot` 项取 `generated_files.videos[shot_id].video_url`
2. timeline 中 `transition` 项取 `generated_files.transitions[transition_id].video_url`
3. 若某个 transition 不存在，则跳过该 transition 项，但保留两侧 shot

这样可以保证：

- 有 transition 就插入
- 没有 transition 也不影响导出
- 主镜头永远是主链路，transition 是可选增强层

---

## 10. 推荐改动文件

后端第一阶段建议改这些文件：

- `app/schemas/pipeline.py`
  - 新增 `TransitionGenerateRequest`
  - 新增 `TransitionResult`
  - 可选新增 `TimelineItem`

- `app/services/ffmpeg.py`
  - 新增 `extract_first_frame()`
  - 保留现有 `extract_last_frame()`

- `app/services/video.py`
  - 新增 `generate_transition_video()`
  - 不修改普通 `generate_videos_batch()` 的单帧逻辑

- `app/routers/pipeline.py`
  - 新增 `/transitions/generate`
  - 后续更新 `/concat` 支持 timeline

- `app/services/storyboard_state.py`
  - 允许持久化 `generated_files.transitions`
  - 允许持久化 `timeline`

- `frontend/src/views/VideoGeneration.vue`
  - 把 transition slot 从 UI 占位改成真实调用
  - `ready` 条件收紧为“两边视频都存在”

---

## 11. 第一阶段实施顺序

### Phase 1：后端生成接口

目标：

- 能单独生成 transition
- 能记录 transition 来源帧
- 不改普通主镜头链路

交付物：

- `/transitions/generate`
- `extract_first_frame()`
- `generate_transition_video()`

### Phase 2：前端接真实接口

目标：

- 点击 slot 可以生成 transition
- 卡片显示 transition 结果
- 支持失败重试

### Phase 3：导出拼接接入 timeline

目标：

- 导出时自动把 transition 插入主镜头之间
- 没有 transition 时维持现在的主镜头导出行为

---

## 12. 本方案最终回答了什么问题

### 12.1 双帧只用于过渡视频

通过把双帧封装进 `generate_transition_video()`，普通 shot 继续单帧 I2V，不会影响其他视频。

### 12.2 读取的是前后视频的对应帧

通过强制要求：

- 前镜必须有 `video_url`
- 后镜必须有 `video_url`
- 前镜取最后一帧
- 后镜取第一帧
- 后端自行解析，不接受前端乱传图片

就能确保 transition 用到的是相邻两个主镜头视频的真实对应帧，而不是其他图片或错误内容。

### 12.3 过渡失败不会拖垮主流程

因为 transition 是独立运行时资产，不写回 `Shot`，也不改变主镜头 `videos`，所以失败只影响该 transition 本身。

---

## 13. 最终建议

这次后端接入不要再沿用旧思路：

- 不要恢复 `Shot.last_frame_prompt`
- 不要让 storyboard 生成过渡 shot
- 不要把前端 image/video URL 直接传给 provider

应该采用当前项目最稳妥的路线：

**主镜头保持现状，transition 独立建模；双帧只在 transition 服务里启用；所有锚点帧一律由后端从相邻主镜头视频中提取并回写来源。**
