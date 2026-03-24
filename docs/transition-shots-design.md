# 过渡分镜设计方案 — 双向锚点受控生成 (Bi-Anchor Controlled Generation)

> 目标：通过插入过渡分镜 + 首尾帧物理约束，使场景内镜头切换和跨场景衔接丝滑无跳切。
> 相关文件：`app/schemas/storyboard.py`、`app/prompts/storyboard.py`、`app/services/video.py`、`app/services/pipeline_executor.py`
> 更新日期：2026-03-24

---

## 一、核心架构：3+2+1 序列

每个场景拆解为三层结构：

| 层级 | 镜头类型 | 每场景数量 | 生成模式 | 核心任务 |
| :--- | :--- | :--- | :--- | :--- |
| **骨架** | 主镜 (Main Shot) | 3 | I2V / T2V | 交代核心剧情、台词、关键动作 |
| **肌肉** | 场景内过渡镜 (Internal Transition) | 2 | Dual-Frame I2V | 利用前镜尾帧 + 后镜首帧补全动作位移 |
| **皮肤** | 跨场景桥接镜 (Scene Bridge) | 1（每两个场景之间） | I2V / T2V | 处理时空/环境切换，提供视觉呼吸 |

最终播放序列：

```text
scene1_shot1 → [scene1_trans1] → scene1_shot2 → [scene1_trans2] → scene1_shot3
                                                                        ↓
                                                          [trans_scene1_scene2]  ← 跨场景桥接
                                                                        ↓
scene2_shot1 → [scene2_trans1] → scene2_shot2 → [scene2_trans2] → scene2_shot3
```

---

## 二、过渡分镜生成原理：双帧补全法

### 2.1 物理约束

过渡分镜不再"凭空想象"，而是用前后主镜的帧作为物理锚点：

- **输入**：前镜最后一帧 (A_end) + 后镜第一帧 (B_start) + 文本辅助指令 (Text Aid)
- **原理**：AI 从 A 状态演变到 B 状态的最短物理路径，首尾帧锁死起止位置，形变被压缩在极短时间内

### 2.2 两阶段生成流程

```text
Phase 1：并行生成主镜
  scene1_shot1、scene1_shot2、scene1_shot3 同时生成（场景间并行）

Phase 2：串行生成过渡镜
  主镜全部完成后 → FFmpeg 提取 A_end / B_start
  → 将首尾帧 + transition_text_aid 送入 Dual-Frame I2V API
  → 生成过渡片段
```

### 2.3 文本辅助指令 (Text Aid)

有了首尾帧约束后，文本不再需要描述主体外观，只需描述 **"力的相互作用"**，分为三类：

| 类别 | 用途 | 指令词 |
| :--- | :--- | :--- |
| 动力学 (Dynamics) | 补全动作惯性 | `Momentum interpolation`, `Kinetic flow`, `Action completion` |
| 运镜 (Camera) | 景别/焦点平滑切换 | `Focal shift`, `Dynamic reframing`, `Parallax` |
| 遮效 (Masking) | 首尾帧差异过大时掩盖形变 | `Visual obscuration`, `Light manipulation` |

---

## 三、高级视觉优化策略

### 3.1 动量匹配 (Motion Matching)

- 如果主镜 A 以高速运动结束，过渡镜必须带有运动模糊
- 自动计算两个主镜的"视觉位移矢量"，位移越大，过渡镜的动作幅度 (Motion Bucket) 参数越高

### 3.2 相似性转场 (Match Cut)

- **场景内**：利用首尾帧中重合度最高的物体（如手中的杯子、角色面部）作为视觉锚点，补帧时强制锁定这些像素不产生剧烈位移
- **场景间**：寻找颜色、形状相似的物体进行桥接过渡（例如：圆形的表盘 → 圆形的井盖）

### 3.3 光影色彩对齐

- 后端提取 A_end 和 B_start 的平均色调，差异过大时自动在辅助文本中追加 `"Light-to-dark transition"` 或 `"Lens flare flash"` 消解色偏
- 如果 I2V API 支持 `color_reference`，传入主镜 A 的图片防止过渡镜变色

### 3.4 安全原则：宁模糊，不扭曲

模糊看起来像摄影技术，扭曲看起来像系统崩溃。当首尾帧差异过大时，优先使用运动模糊、光晕闪白、前景遮挡等手法掩盖。

---

## 四、数据结构变更

### 4.1 Shot Schema 新增字段

**文件**：`app/schemas/storyboard.py`

```python
is_transition: bool = Field(default=False, description="是否为过渡分镜")
transition_type: Optional[str] = Field(
    default=None,
    description="过渡类型: 'intra_scene'（场景内）| 'inter_scene'（跨场景桥接）"
)
transition_logic: Optional[str] = Field(
    default=None,
    description="过渡逻辑: 'motion_matching' | 'cinematic_camera' | 'masking' | 'scene_bridge'"
)
transition_text_aid: Optional[str] = Field(
    default=None,
    description="过渡辅助指令，描述力/运镜/遮效，直接拼入视频生成 prompt"
)
reference_frames: Optional[dict] = Field(
    default=None,
    description="首尾帧引用: { 'start_frame': 前镜尾帧路径, 'end_frame': 后镜首帧路径 }"
)
```

### 4.2 shot_id 命名约定

| 类型 | 格式示例 | 说明 |
|------|----------|------|
| 主镜头 | `scene1_shot1` | 现有格式不变 |
| 场景内过渡 | `scene1_trans1` | `trans` 代替 `shot`，编号从 1 起 |
| 跨场景桥接 | `trans_scene1_scene2` | 标明连接的两个场景 |

---

## 五、分镜 Prompt 变更

### 5.1 SYSTEM_PROMPT 新增 Law 6

**文件**：`app/prompts/storyboard.py`

```text
**Law 6 — 3+2+1 分镜结构规范**

每个场景必须包含且仅包含 **3 个主镜头**（scene{N}_shot1/2/3）。

除主镜头外，按如下规则同时输出过渡分镜：

**场景内过渡分镜**（transition_type: "intra_scene"）：
- 每个场景生成 2 个，插入在 shot1→shot2 和 shot2→shot3 之间
- shot_id 格式：scene{N}_trans1、scene{N}_trans2
- 约束：
  - estimated_duration：2 秒
  - scene_intensity：固定 "low"
  - is_transition：true
  - transition_logic：根据前后主镜的物理差异选择：
    "motion_matching"（动作连续）| "cinematic_camera"（景别变化）| "masking"（差异过大需遮效）
  - transition_text_aid：只描述力/运动/遮效指令，不描述主体外观（首尾帧已约束外观）
  - final_video_prompt：组合过渡运动描述 + transition_text_aid
  - camera_setup.movement：优先 "Slow Dolly in" / "Dolly out" / "Pan" 等平滑运动

**跨场景桥接分镜**（transition_type: "inter_scene"）：
- 在两个相邻场景之间各生成 1 个
- shot_id 格式：trans_scene{N}_scene{N+1}
- 约束：
  - estimated_duration：2 秒
  - scene_intensity：固定 "low"
  - is_transition：true
  - transition_logic：固定 "scene_bridge"
  - transition_text_aid：以时空过渡意象为主（时间流逝、空镜、氛围叠化）
  - final_video_prompt：以上一场景末镜视觉元素渐出、下一场景首镜视觉元素渐入为重点
```

### 5.2 USER_TEMPLATE 输出格式约束

```text
输出 JSON 数组按最终播放顺序排列所有镜头（含过渡），顺序如下：
  scene1_shot1 → scene1_trans1 → scene1_shot2 → scene1_trans2 → scene1_shot3
  → trans_scene1_scene2
  → scene2_shot1 → scene2_trans1 → ...
```

### 5.3 `_parse_shots` 兼容处理

**文件**：`app/services/storyboard.py`

```python
# 兜底：从 shot_id 自动推断 is_transition（防止 LLM 遗漏）
if "is_transition" not in item:
    shot_id = item.get("shot_id", "")
    item["is_transition"] = ("_trans" in shot_id) or shot_id.startswith("trans_")
if item.get("is_transition") and "transition_type" not in item:
    shot_id = item.get("shot_id", "")
    item["transition_type"] = "inter_scene" if shot_id.startswith("trans_") else "intra_scene"
```

---

## 六、过渡辅助指令库

LLM 在生成过渡分镜的 `transition_text_aid` 时，根据 `transition_logic` 从以下指令库中选用：

### 6.1 动力学衔接类 (motion_matching)

用于同一场景内两个主镜动作之间的物理补全。

| 场景 | 推荐指令 |
| :--- | :--- |
| 手部动作 | `Seamlessly interpolate the hand reaching motion, maintain anatomical consistency.` |
| 起身/跳跃 | `Execute the upward explosive force, matching the velocity of the previous shot.` |
| 行走步态 | `Continue the walking gait with natural rhythmic swaying of the torso.` |

### 6.2 电影感运镜类 (cinematic_camera)

用于景别切换或视觉焦点改变时的平滑过渡。

| 场景 | 推荐指令 |
| :--- | :--- |
| 甩镜头转场 | `Fast cinematic whip pan, creating directional motion blur to bridge the two positions.` |
| 快速推近 | `Aggressive dolly-in to the subject's eyes, matching the start frame of the next shot.` |
| 环绕运镜 | `360-degree orbital rotation, maintaining the subject at the center of the frame.` |

### 6.3 遮效类 (masking)

首尾帧差异过大、AI 可能产生形变时，用特效掩盖瑕疵。

| 场景 | 推荐指令 |
| :--- | :--- |
| 重度模糊 | `Apply heavy directional motion blur to mask any potential anatomical morphing.` |
| 光晕闪白 | `Intense lens flare flash, blooming from the center to create an optical transition.` |
| 前景遮挡 | `A dark foreground object passes quickly across the camera, creating a natural wipe.` |

### 6.4 跨场桥接类 (scene_bridge)

两个完全不同场景之间的意象衔接。

| 场景 | 推荐指令 |
| :--- | :--- |
| 时间流逝 | `Time-lapse shadow movement across the wall, fading from day to night.` |
| 微粒过渡 | `Ethereal dust particles floating in a light beam, transitioning the viewer's focus.` |
| 极简空镜 | `Extreme close-up of a ticking clock/flickering neon sign, symbolizing the scene shift.` |

---

## 七、视频生成变更

### 7.1 场景分组逻辑

**文件**：`app/services/video.py` — `group_shots_by_scene`

```python
def group_shots_by_scene(shots: list[dict]) -> OrderedDict:
    """
    - scene{N}_shot{M} / scene{N}_trans{M}  → scene{N}
    - trans_scene{N}_scene{N+1}             → 独立分组，key 为 shot_id
    """
    groups: OrderedDict[str, list[dict]] = OrderedDict()
    for shot in shots:
        sid = shot["shot_id"]
        if sid.startswith("trans_scene"):
            groups[sid] = [shot]
        else:
            match = re.match(r"(scene\d+)", sid)
            scene_key = match.group(1) if match else "scene0"
            groups.setdefault(scene_key, []).append(shot)
    return groups
```

### 7.2 链式生成两阶段改造（目标设计，待实现）

**文件**：`app/services/video.py` — `generate_videos_chained`

目标设计（待实现）：

```text
Phase 1：场景间并行，场景内串行生成主镜头
  for each scene (并行):
    for each main shot (串行):
      首镜头 → generate_image() → generate_video() → extract_last_frame()
      后续镜头 → 复用 prev_frame → generate_video() → extract_last_frame()

Phase 2：生成过渡分镜
  主镜头全部完成后：
  for each transition shot:
    FFmpeg 提取 A_end（前镜最后一帧）
    FFmpeg 提取 B_start（后镜第一帧）
    prompt = transition_text_aid（不含主体描述，仅力/运镜/遮效）
    generate_video(image=A_end, prompt=prompt)  # Dual-Frame I2V（如 API 支持则同时传 B_start）
```

```python
async def _process_scene(scene_key: str, scene_shots: list[dict]) -> list[dict]:
    ...
    for idx, shot in enumerate(scene_shots):
        is_transition = shot.get("is_transition", False)

        if is_transition:
            # 过渡分镜强制使用前镜尾帧
            if prev_frame_path is None:
                logger.warning("过渡分镜 %s 缺少前置帧，将跳过", shot["shot_id"])
                continue
            # prompt 使用 transition_text_aid（力/运镜/遮效），不重复描述主体
            prompt = shot.get("transition_text_aid") or shot.get("final_video_prompt", "")
        else:
            # 主镜头正常逻辑
            prompt = f"{visual_prompt} {camera_motion}"
        ...
```

### 7.3 `generate_videos_batch` 兼容

已在 2026-03-24 修复 `.get()` 回退，过渡分镜和主镜头共用同一逻辑，无需额外修改。

---

## 八、流水线执行变更

**文件**：`app/services/pipeline_executor.py`

### 8.1 TTS 过滤过渡分镜

```python
# 在 _run_separated_strategy / _run_chained_strategy 的 TTS 步骤：
tts_shots = [s for s in self.shots if not s.is_transition]
tts_results = await tts.generate_tts_batch(tts_shots, ...)
```

### 8.2 FFmpeg 合成：过渡分镜透传无声视频

```python
for result in results:
    shot = shot_map.get(result["shot_id"])
    if shot and shot.get("is_transition"):
        result["final_video_url"] = result["video_url"]  # 无声直接用
        continue
    # 正常 stitch（音视频合成）
    ...
```

### 8.3 播放顺序保证

LLM 按播放顺序输出 JSON → `_parse_shots` 保持顺序 → `generate_videos_chained` 按 `shot_order` 展平。前端 concat 同样按 shot 顺序传入 `video_urls`，无需额外排序。

---

## 九、前端变更

**文件**：`frontend/src/views/VideoGeneration.vue`

- 过渡分镜卡片通过 `shot.is_transition` 区分，默认折叠收起，样式灰显
- 过渡分镜不展示台词 / TTS 控件
- "生成视频"按钮对过渡分镜和主镜头均生效

---

## 十、变更文件清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `app/schemas/storyboard.py` | 新增字段 | `is_transition`, `transition_type`, `transition_logic`, `transition_text_aid`, `reference_frames` |
| `app/prompts/storyboard.py` | Prompt 追加 | Law 6（3+2+1 结构 + 指令库引用） |
| `app/services/storyboard.py` | 兼容补丁 | `_parse_shots` 自动推断 `is_transition` |
| `app/services/video.py` | 核心改造 | `group_shots_by_scene` 支持跨场景分组；链式生成两阶段改造 |
| `app/services/pipeline_executor.py` | 过滤逻辑 | TTS 跳过过渡分镜；stitch 透传无声视频 |
| `app/services/ffmpeg.py` | 新增函数 | `extract_first_frame()` 提取首帧（Phase 2 用） |
| `frontend/src/views/VideoGeneration.vue` | UI 区分 | 过渡分镜卡片折叠 + 样式差异化 |

---

## 十一、最终视频结构示意

以 2 个场景为例：

```text
[scene1_shot1]          4s  主镜头
[scene1_trans1]         2s  ← 场景内过渡（A_end + B_start 约束）
[scene1_shot2]          4s  主镜头
[scene1_trans2]         2s  ← 场景内过渡（A_end + B_start 约束）
[scene1_shot3]          4s  主镜头
[trans_scene1_scene2]   2s  ← 跨场景桥接（空镜/意象衔接）
[scene2_shot1]          4s  主镜头
[scene2_trans1]         2s  ← 场景内过渡
[scene2_shot2]          4s  主镜头
[scene2_trans2]         2s  ← 场景内过渡
[scene2_shot3]          4s  主镜头

总时长：2×(3×4 + 2×2) + 1×2 = 34s
```

---

## 十二、落地注意事项

1. **帧率匹配**：过渡视频与主镜视频 FPS 必须一致（统一 24 或 30），否则 concat 后有明显卡顿
2. **色彩对齐**：如果 I2V API 支持 `color_reference`，传入前镜图片防止过渡镜变色
3. **API 能力适配**：Dual-Frame I2V（同时接受首尾帧）是理想方案；如果当前 API 仅支持单图 I2V，退化为仅使用 A_end 作为参考图，prompt 中显式描述向 B_start 的运动方向

---

## 十三、已知冲突与待解决项

> 以下为代码审计发现的问题，实施前必须逐项处理。

### 13.1 已修复的 BUG (2026-03-24)

`_run_chained_strategy` 中有 3 处字段名与 Shot schema 不一致，已修复：

| 原错误代码 | 修复为 | 说明 |
|------------|--------|------|
| `s.dialogue` | `s.audio_reference.content`（含 type 判断） | Shot 无 `dialogue` 字段 |
| `s.visual_prompt` | `s.final_video_prompt` | Shot 无 `visual_prompt` 字段 |
| `s.camera_motion` | `s.camera_setup.movement` | Shot 无 `camera_motion` 字段 |

### 13.2 两阶段 vs 单阶段：现状单阶段，需迁移

当前 `generate_videos_chained` 是**单阶段**（场景内串行遍历所有 shot，尚不区分主镜头与过渡分镜）。实现文档中的两阶段需要以下额外工作：

1. Phase 1 入口需要**过滤掉** `is_transition=True` 的 shot，仅处理主镜头
2. Phase 1 完成后，对所有主镜头视频提取首帧和尾帧
3. Phase 2 遍历过渡分镜，匹配前后主镜头的帧作为输入
4. 最终按原始 shot 顺序**重组**主镜头 + 过渡镜头结果

建议实施方案：在 `generate_videos_chained` 内部拆分而非改签名，对外接口不变。

```python
async def generate_videos_chained(shots, ...):
    main_shots = [s for s in shots if not s.get("is_transition")]
    transition_shots = [s for s in shots if s.get("is_transition")]

    # Phase 1: 链式生成主镜头（现有逻辑）
    main_results = await _generate_main_shots(main_shots, ...)
    main_map = {r["shot_id"]: r for r in main_results}

    # Phase 2: 生成过渡镜头
    trans_results = await _generate_transitions(transition_shots, main_map, ...)

    # 按原始顺序合并
    all_results = main_results + trans_results
    return _reorder_by_original(shots, all_results)
```

### 13.3 `group_shots_by_scene` 修改范围

在两阶段方案下，`group_shots_by_scene` 仅在 Phase 1 被调用（只处理主镜头），不需要识别 `trans_scene*` 前缀。跨场景过渡在 Phase 2 中单独处理。

因此 `group_shots_by_scene` 的改动可简化为：仅确保 `scene{N}_trans{M}` 正确归入 `scene{N}`（Phase 1 过滤后实际不会出现，但作为防御）。

### 13.4 `generate_video()` 需支持可选双帧输入

当前签名只接受单张 `image_url`。为支持 Dual-Frame I2V，需：

```python
async def generate_video(
    image_url: str,
    prompt: str,
    shot_id: str,
    end_frame_url: Optional[str] = None,  # 新增：后镜首帧（可选）
    ...
) -> dict:
```

同时 video provider 接口需适配：

```python
# app/services/video_providers/base.py 或 factory.py
class VideoProvider:
    async def generate(self, image_url, prompt, model, ..., end_frame_url=None):
        ...
```

降级策略：`end_frame_url` 为 None 时走现有单帧逻辑。

### 13.5 `ffmpeg.py` 新增 `extract_first_frame()`

Phase 2 需要后镜首帧 (B_start)，需新增：

```python
async def extract_first_frame(video_path: str, shot_id: str) -> str:
    """提取视频第一帧，输出到 media/images/{shot_id}_firstframe.png"""
    output = IMAGE_DIR / f"{shot_id}_firstframe.png"
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-frames:v", "1",
        "-q:v", "2",
        str(output),
    ]
    ...
    return str(output)
```

### 13.6 `VisualElements` 对过渡分镜不适用

当前 `visual_elements: VisualElements` 是 Shot 的 **required** 字段（含 4 个子字段）。过渡分镜没有主体描述，需要处理：

**方案 A**（推荐）：将 `visual_elements` 改为 Optional

```python
visual_elements: Optional[VisualElements] = Field(default=None, ...)
```

**方案 B**：在 Prompt Law 6 中指定过渡分镜的 `visual_elements` 填写规范（如环境描述复用前镜）。

### 13.7 `transition_from_previous` 字段与新字段关系

Shot schema 已有 `transition_from_previous: Optional[str]`（描述与前镜的过渡关系）。新增的 `is_transition` / `transition_type` / `transition_text_aid` 服务于**独立的过渡分镜**。

明确分工：
- `transition_from_previous`：保留，用于**主镜头**描述与前一主镜头的叙事衔接（供 LLM 保持连贯性）
- `is_transition` 等新字段：仅用于**过渡分镜**的生成控制

### 13.8 SEPARATED / INTEGRATED 策略的过渡分镜处理

LLM 输出统一包含过渡分镜（不区分策略），因此三种策略都需要处理：

| 策略 | 过渡分镜处理方式 |
|------|-----------------|
| **CHAINED** | 两阶段：Phase 1 主镜头链式 → Phase 2 双帧约束生成过渡（完整能力） |
| **SEPARATED** | 降级：过渡分镜与主镜头一起并行生成图片和视频，不做双帧约束（无链式帧传递） |
| **INTEGRATED** | 降级：同 SEPARATED |

所有策略通用：
- TTS 步骤跳过 `is_transition=True` 的 shot
- stitch 步骤过渡分镜透传无声视频
- concat 步骤按原始 shot 顺序拼接

### 13.9 Prompt Law 6 需补充的字段约束

当前 Law 6 未规定过渡分镜的 `audio_reference` 和 `visual_elements`，LLM 可能会乱填。需追加：

```
过渡分镜字段约束：
- audio_reference：必须为 null（过渡分镜无台词/旁白）
- visual_elements：可省略或复用前一主镜头的环境描述，subject_and_clothing 留空
- mood：可选，与前后主镜头保持一致
- storyboard_description：简要描述过渡效果（如"快速推近过渡到下一镜头"）
```

### 13.10 遗漏的变更文件

| 文件 | 需要修改 | 说明 |
|------|----------|------|
| `app/routers/video.py` | 是 | 前端单镜头视频生成入口，当前直接调 `generate_videos_batch()`，不走 Dual-Frame 逻辑；需对 `is_transition` 的 shot 走独立路径或标注为仅支持降级模式 |
| `app/services/video_providers/*.py` | 是 | Provider 接口需新增 `end_frame_url` 可选参数（dashscope / minimax 等） |
| `app/services/tts.py` | 确认 | `generate_tts_batch` 需确认对 `dialogue=None` 的 shot 是否安全跳过 |
| `app/routers/pipeline.py` | 是 | `render_video`、`generate_assets` 等手动端点也需跳过过渡分镜的 TTS，透传无声视频 |
| `app/schemas/pipeline.py` | 可选 | `ShotResult` 可新增 `is_transition` 字段，便于前端区分 |
