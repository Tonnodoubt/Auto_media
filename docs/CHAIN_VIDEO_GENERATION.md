# 链式视频生成 & 角色一致性方案

## 1. 问题背景

当前系统的视频生成流程中存在两个核心一致性问题：

### 1.1 镜头间视觉不连贯

当前流程中，每个镜头独立生成图片再独立生成视频，镜头之间没有视觉传递关系：

```
分镜1 → 独立生图1 → 独立生视频1 ─┐
分镜2 → 独立生图2 → 独立生视频2 ─┼─→ 拼接
分镜3 → 独立生图3 → 独立生视频3 ─┘
```

**结果**：即使提示词描述相同的场景和人物，每次生图的结果在色调、构图、人物外观上都会有差异，拼接后的视频观感割裂。

### 1.2 角色人设与视频脱节

系统在剧本大纲阶段已经生成了角色人设图（`media/characters/` 目录），存储在 `Story.character_images` 中。但这些人设图目前只在分镜解析（LLM 提示词层面）中被引用为文字描述，**没有作为视觉参考图传入图片/视频生成 API**。

```
当前数据流：
  角色人设图 → 提取文字描述 → 注入分镜提示词（纯文字）
                                    ↓
                    图片生成 API（只看文字，不看人设图）
```

文字描述无法精确控制外观细节（发型、服装纹理、面部特征等），导致每次生成的角色形象都不一致。

---

## 2. 链式视频生成方案

### 2.1 核心思路

在同一场景（Scene）内，用上一个镜头视频的最后一帧作为下一个镜头的起始图，形成视觉传递链：

```
场景 1:
  分镜1 → 生成首帧图片 → 图到视频1 → 提取最后一帧 ─┐
                                                      ↓
  分镜2 ← 用最后一帧作为起始图 → 图到视频2 → 提取最后一帧 ─┐
                                                            ↓
  分镜3 ← 用最后一帧作为起始图 → 图到视频3

场景 2:（链条重置，独立生成首帧）
  分镜4 → 生成首帧图片 → 图到视频4 → 提取最后一帧 ─┐
                                                      ↓
  ...
```

### 2.2 场景内链式 vs 跨场景独立

| 维度 | 场景内（同 Scene） | 跨场景 |
|------|-------------------|--------|
| 链式传帧 | ✅ 启用 | ❌ 不启用 |
| 首帧来源 | 上一个视频的最后一帧 | 独立生成新图片 |
| 原因 | 同场景内视觉连续性要求高 | 不同场景通常是不同空间/时间，视觉断开合理 |

**场景分组依据**：`shot_id` 中的 scene 编号。如 `scene1_shot1`、`scene1_shot2` 属于同一场景，`scene2_shot1` 开始新场景。

### 2.3 详细执行流程

```
输入：shots = [scene1_shot1, scene1_shot2, scene1_shot3, scene2_shot1, scene2_shot2, ...]

Step 1: 按 scene 分组
  scene_groups = {
    "scene1": [shot1, shot2, shot3],
    "scene2": [shot1, shot2],
    ...
  }

Step 2: 对每个 scene 串行执行链式生成
  for scene_id, scene_shots in scene_groups:
    last_frame = None

    for i, shot in enumerate(scene_shots):
      if i == 0:
        # 场景首个镜头：独立生成图片
        image = await generate_image(shot.visual_prompt, shot.shot_id)
      else:
        # 后续镜头：使用上一个视频的最后一帧
        image = last_frame  # 已经是本地文件路径

      # 图到视频
      video = await generate_video(image, shot.visual_prompt + shot.camera_motion)

      # 提取最后一帧（除了场景最后一个镜头可选跳过）
      if i < len(scene_shots) - 1:
        last_frame = await extract_last_frame(video.video_path, shot.shot_id)

Step 3: 不同 scene 之间可以并行执行（互不依赖）
```

### 2.4 各场景可并行优化

场景之间没有依赖关系，可以并行执行不同场景的链式流程，减少总耗时：

```
Scene 1: shot1 → shot2 → shot3     ─┐
Scene 2: shot4 → shot5              ─┼─→ 拼接
Scene 3: shot6 → shot7 → shot8     ─┘
        （三个场景并行，场景内串行）
```

**耗时估算**（假设每个视频生成 60 秒）：

| 模式 | 计算方式 | 8 镜头 / 3 场景(3+2+3) |
|------|---------|----------------------|
| 当前全并行 | max(所有镜头) | ~60 秒 |
| 全串行链式 | sum(所有镜头) | ~480 秒 |
| 场景间并行 + 场景内串行 | max(场景内镜头数) × 60 | ~180 秒 |

---

## 3. 角色一致性方案

### 3.1 现状分析

当前角色人设图的使用链路：

```
剧本大纲 → 生成角色信息(name, role, description)
                          ↓
         角色人设图生成 API（FLUX.1）
                          ↓
         保存到 Story.character_images = {
           "张三": {
             "image_url": "/media/characters/story_xxx_zhang_san_abc123.png",
             "image_path": "media/characters/story_xxx_zhang_san_abc123.png",
             "prompt": "Character portrait of 张三, protagonist, ..."
           }
         }
                          ↓
         分镜解析时 → 提取 portrait_prompt 文字 → 注入 LLM 提示词
                          ↓
         LLM 生成 visual_prompt（包含角色外观文字描述）
                          ↓
         图片/视频生成 API（只用文字 prompt，不用人设图）
```

**问题**：人设图只生成了，但从未作为视觉参考传递给图片/视频生成模型。

### 3.2 解决方案：人设图注入

根据图片/视频生成 API 的能力，有三个层级的方案：

#### 方案 A：IP Adapter / 角色参考图（最优，依赖 API 支持）

部分图片生成 API（如 FLUX 的 ControlNet/IP-Adapter 模式）支持传入参考图进行风格/角色迁移：

```
请求参数：
{
  "prompt": "...",
  "reference_image": "/media/characters/人设图.png",   ← 新增
  "reference_strength": 0.6                            ← 控制参考强度
}
```

**适用条件**：图片生成 API 支持 `reference_image` 或 `ip_adapter_image` 参数。
**当前状态**：SiliconFlow FLUX.1-schnell **不支持**此功能，但部分高级模型（如 FLUX.1-pro、Midjourney）支持。

#### 方案 B：人设图拼接到首帧（中等，当前可实现）

在生成场景首帧时，将角色人设图和场景提示词组合：

```
Step 1: 将人设图缩放并拼接到参考区域
  ┌──────────────────────────────────────┐
  │  目标场景图片 (1280x720)              │
  │                                      │
  │  根据 prompt 生成，prompt 中包含      │
  │  角色详细外观描述（来自人设图 prompt） │
  │                                      │
  └──────────────────────────────────────┘

Step 2: 在 visual_prompt 中强化角色外观描述
  将人设图的 prompt 字段直接拼接到 visual_prompt 中：

  原始 prompt: "Medium shot of a man walking..."
  增强 prompt: "Medium shot of a man walking...,
                the man looks exactly like: [portrait_prompt from character_images]"
```

**当前可用**：不需要 API 支持参考图，只需增强 prompt 工程。

#### 方案 C：链式传帧本身的一致性效果（基础，免费获得）

链式视频生成方案（第 2 节）本身就能提供角色一致性：

```
场景首帧（含角色 A）→ 视频1（角色 A 运动）→ 最后一帧（仍含角色 A）→ 视频2（继续角色 A）
```

由于帧传递，同一场景内的角色外观会自然保持一致。**但跨场景时一致性仍然依赖方案 A 或 B**。

### 3.3 推荐组合策略

```
                    ┌─────────────────┐
                    │ 角色人设图(已有)  │
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              ↓                             ↓
     增强 visual_prompt               未来：IP Adapter
     (方案 B - 立即可做)              (方案 A - 等 API 支持)
              │
              ↓
     场景首帧图片（含角色特征）
              │
              ↓
     ┌────────────────────┐
     │ 链式帧传递(方案 C)  │ ← 场景内自动保持一致
     │ shot1 → shot2 → ...│
     └────────────────────┘
```

**短期实施**：方案 B + 方案 C 组合
**中期增强**：方案 A（当 API 支持参考图时接入）

---

## 4. 实现计划

### 4.1 代码改动清单

| 序号 | 改动内容 | 涉及文件 | 优先级 |
|------|---------|---------|--------|
| 1 | 新增 FFmpeg 提取最后一帧函数 | `app/services/ffmpeg.py` | P0 |
| 2 | 新增链式视频生成函数 | `app/services/video.py` | P0 |
| 3 | 按 scene 分组工具函数 | `app/services/video.py` 或新建 `utils.py` | P0 |
| 4 | 增强 visual_prompt 注入角色外观 | `app/services/pipeline_executor.py` | P0 |
| 5 | 改造 PipelineExecutor 支持链式模式 | `app/services/pipeline_executor.py` | P0 |
| 6 | 新增生成策略选项 `chain` | `app/schemas/pipeline.py` | P1 |
| 7 | 前端进度展示适配 | `frontend/src/` | P1 |
| 8 | 断点续生支持 | `app/services/pipeline_executor.py` | P2 |

### 4.2 详细设计

#### 4.2.1 提取最后一帧 (`ffmpeg.py`)

```python
async def extract_last_frame(video_path: str, shot_id: str) -> str:
    """
    从视频中提取最后一帧，保存为 PNG。
    使用 ffmpeg -sseof -0.1 从视频末尾前 0.1 秒处截取。

    Returns: 保存的图片文件路径（本地路径）
    """
    output_path = f"media/images/{shot_id}_lastframe.png"
    cmd = [
        "ffmpeg", "-y",
        "-sseof", "-0.1",
        "-i", video_path,
        "-frames:v", "1",
        "-q:v", "2",
        output_path,
    ]
    # ... subprocess 执行 ...
    return output_path
```

#### 4.2.2 链式视频生成 (`video.py`)

```python
async def generate_videos_chained(
    shots: list[dict],
    base_url: str,
    model: str,
    video_api_key: str,
    video_base_url: str,
    video_provider: str,
    image_model: str,
    image_api_key: str,
    image_base_url: str,
    on_progress: Callable = None,     # 进度回调
) -> list[dict]:
    """
    链式视频生成：按 scene 分组，场景间并行，场景内串行。

    每个场景的首个镜头独立生成图片，后续镜头使用上一个视频的最后一帧。
    """
    # 1. 按 scene 分组
    scene_groups = group_shots_by_scene(shots)

    # 2. 定义单个场景的链式生成
    async def _generate_scene_chain(scene_id, scene_shots):
        results = []
        last_frame_path = None

        for i, shot in enumerate(scene_shots):
            if i == 0:
                # 场景首帧：独立生图
                img_result = await image.generate_image(
                    shot["visual_prompt"], shot["shot_id"],
                    image_model, image_api_key, image_base_url,
                )
                image_url = f"{base_url}{img_result['image_url']}"
            else:
                # 后续帧：使用上一个视频的最后一帧
                image_url = last_frame_path  # 本地文件 or 上传后的 URL

            # 图到视频
            video_result = await generate_video(
                image_url,
                f"{shot['visual_prompt']} {shot['camera_motion']}",
                shot["shot_id"], model, video_api_key, video_base_url, video_provider,
            )
            results.append(video_result)

            # 提取最后一帧（非最后一个镜头时）
            if i < len(scene_shots) - 1:
                last_frame_path = await ffmpeg.extract_last_frame(
                    video_result["video_path"], shot["shot_id"]
                )
                # 如果 provider 需要 URL，需上传或转为可访问路径
                last_frame_path = f"{base_url}/media/images/{shot['shot_id']}_lastframe.png"

            if on_progress:
                await on_progress(shot["shot_id"], i + 1, len(scene_shots))

        return results

    # 3. 不同场景并行执行
    scene_tasks = [
        _generate_scene_chain(scene_id, scene_shots)
        for scene_id, scene_shots in scene_groups.items()
    ]
    scene_results = await asyncio.gather(*scene_tasks)

    # 4. 按原始顺序合并结果
    return flatten_and_sort(scene_results, shots)
```

#### 4.2.3 角色外观增强 (`pipeline_executor.py`)

```python
def _enhance_prompt_with_character(
    visual_prompt: str,
    character_info: dict,
) -> str:
    """
    将角色人设图的 prompt 注入到 visual_prompt 中，增强角色外观一致性。

    从 character_images 中提取已生成人设图的 prompt 字段，
    拼接到 visual_prompt 尾部。
    """
    if not character_info:
        return visual_prompt

    character_images = character_info.get("character_images", {})
    # 检查 visual_prompt 中是否提及了任何角色
    portrait_prompts = []
    for char_name, char_data in character_images.items():
        if char_name in visual_prompt and char_data.get("prompt"):
            portrait_prompts.append(char_data["prompt"])

    if portrait_prompts:
        return f"{visual_prompt}, character reference: {', '.join(portrait_prompts)}"
    return visual_prompt
```

#### 4.2.4 场景分组工具

```python
def group_shots_by_scene(shots: list[dict]) -> dict[str, list[dict]]:
    """
    根据 shot_id 中的 scene 编号将镜头分组。
    shot_id 格式: "scene{N}_shot{M}"

    Returns: OrderedDict { "scene1": [shot1, shot2, ...], "scene2": [...] }
    """
    from collections import OrderedDict
    import re

    groups = OrderedDict()
    for shot in shots:
        match = re.match(r"(scene\d+)_shot\d+", shot["shot_id"])
        scene_id = match.group(1) if match else "scene_unknown"
        groups.setdefault(scene_id, []).append(shot)
    return groups
```

### 4.3 PipelineExecutor 改造

在 `_run_separated_strategy` 中新增链式模式分支：

```python
async def _run_separated_strategy(self, ...):
    # ... TTS 生成（不变）...

    # Step 3 + 4: 图片 + 视频（链式合并）
    if self.use_chain_mode:
        # 链式生成：图片和视频在同一循环中交替执行
        results = await video.generate_videos_chained(
            shots=[...],
            on_progress=self._chain_progress_callback,
            ...
        )
    else:
        # 原有模式：先并行生图，再并行生视频
        image_results = await image.generate_images_batch(...)
        video_results = await video.generate_videos_batch(...)
```

### 4.4 进度反馈设计

链式生成时，进度信息需更精细：

```json
{
  "step": "chain_generate",
  "current_scene": "scene1",
  "current_shot": 2,
  "scene_total": 3,
  "scenes_completed": 0,
  "scenes_total": 3,
  "message": "场景1: 正在生成第 2/3 个镜头..."
}
```

---

## 5. 风险与注意事项

### 5.1 图片 URL 问题

视频生成 API（DashScope/Kling/Doubao）需要可公网访问的图片 URL。提取的最后一帧保存在本地服务器，需要确保：

- 本地服务器的 `/media/images/` 路径对外可访问
- 或者将提取的帧上传到 CDN/对象存储
- DashScope 和 Kling 接受 HTTP URL，Doubao 支持 base64（最灵活）

### 5.2 视频质量累积衰减

链式传帧可能导致画质逐步下降：
- 视频压缩 → 解码最后一帧 → 重新作为输入 → 再次压缩
- 每经过一次链式传递，会有轻微的画质损失

**缓解**：
- 提取帧时使用高质量参数（`-q:v 2`）
- 限制同一场景内的链式长度（建议不超过 6-8 个镜头）
- 超长场景可在中间插入一次独立生图作为"锚点"

### 5.3 错误恢复

链式生成中，某个环节失败会阻塞后续镜头：

```
shot1 ✅ → shot2 ❌ → shot3 ⏸ → shot4 ⏸
```

**策略**：
- 失败时记录当前进度（已完成的镜头 + 最后一帧路径）
- 支持从断点续生：跳过已完成镜头，从最后一个成功帧继续
- 如果某个镜头连续失败 N 次，降级为独立生图模式继续

### 5.4 耗时增长

场景内串行不可避免地增加总耗时。通过场景间并行可部分缓解，但单场景镜头数越多，耗时越长。

---

## 6. 总结

| 维度 | 方案 |
|------|------|
| 镜头间连贯性 | 场景内链式帧传递（本文档第 2 节） |
| 角色跨场景一致性 | 人设图 prompt 注入 + 未来 IP Adapter（第 3 节） |
| 场景切换 | 独立生成首帧，链条自然重置 |
| 性能优化 | 场景间并行 + 场景内串行 |
| 保留兼容 | 原有并行模式保留为可选项 |
