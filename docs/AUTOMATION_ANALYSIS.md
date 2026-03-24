# AutoMedia 全流程自动化分析文档

> 日期: 2026-03-23
> 目标: 分析从"剧本生成完成"到"视频最终输出"的全流程自动化方案，以及角色一致性问题

---

## 一、当前系统能力全景

### 已实现的完整链路

```
灵感输入 → 世界观构建 → 大纲生成 → 角色设计 → 分集剧本 → 人设图生成
                                                            ↓
                                              分镜解析 → TTS → 图片 → 视频 → (合成)
```

### 每个环节的自动化程度

| 环节 | 状态 | 人工操作 | 说明 |
|------|------|---------|------|
| 灵感 → 大纲 | 需手动 | 输入灵感、选风格、触发生成 | 创意阶段，人工参与合理 |
| 大纲 → 剧本 | 需手动 | 逐集点击生成、可选编辑 | SSE 流式，需要等待 |
| 人设图生成 | 需手动 | 点击"生成全部" | 可自动化 |
| 剧本 → 视频 | **半自动** | 选择场景 → 点"一键生成" | 单集内已自动化 |
| FFmpeg 合成 | **未实现** | N/A | 代码中是 `sleep(1)` mock |

### 核心问题：缺少"集级编排"和"项目级编排"

当前的自动化粒度是 **单次 pipeline 调用 = 一段剧本的所有镜头**，但：

1. **没有多集自动轮转** — 用户需要手动为每一集点击"一键生成"
2. **没有跨集状态管理** — 每次 pipeline 是独立的，不知道"第几集已完成"
3. **没有全局进度追踪** — 无法看到"全剧 12 集，已完成 7 集"这样的视图
4. **没有失败重试机制** — 某一集失败后，需要手动重新发起

---

## 二、自动化方案设计

### 2.1 总体架构：三层编排模型

```
┌─────────────────────────────────────────────────────┐
│                 Project Orchestrator                  │
│            （项目级编排器 — 全剧统筹）                    │
│                                                       │
│  输入: 完整剧本 (scenes[])                             │
│  输出: 全剧所有集的视频                                 │
│  职责: 按集分配任务、追踪全局进度、处理失败重试            │
├─────────────────────────────────────────────────────┤
│                                                       │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐    │
│  │ Episode      │ │ Episode      │ │ Episode      │    │
│  │ Pipeline     │ │ Pipeline     │ │ Pipeline     │    │
│  │ (第1集)      │ │ (第2集)      │ │ (第3集)      │    │
│  │              │ │              │ │              │    │
│  │ 分镜→TTS→   │ │ 分镜→TTS→   │ │ 分镜→TTS→   │    │
│  │ 图片→视频→  │ │ 图片→视频→  │ │ 图片→视频→  │    │
│  │ 合成        │ │ 合成        │ │ 合成        │    │
│  └─────────────┘ └─────────────┘ └─────────────┘    │
│                                                       │
├─────────────────────────────────────────────────────┤
│                 Shot-Level Executor                    │
│         （镜头级执行器 — 已有的 PipelineExecutor）       │
│                                                       │
│  并发生成 TTS / 图片 / 视频（asyncio.gather）           │
└─────────────────────────────────────────────────────┘
```

### 2.2 新增数据模型

```python
# 项目级自动化任务
class ProjectAutomation(Base):
    __tablename__ = "project_automations"

    id: String (PK)
    story_id: String (FK → stories)
    status: Enum  # pending / running / paused / completed / failed

    # 全局配置（创建时锁定）
    strategy: String           # separated / integrated
    voice: String              # TTS 语音
    image_model: String        # 图片模型
    video_model: String        # 视频模型
    video_provider: String     # dashscope / kling / doubao

    # 进度追踪
    total_episodes: Integer    # 总集数
    completed_episodes: Integer # 已完成集数
    current_episode: Integer   # 当前正在处理的集

    # 集级状态详情
    episode_states: JSON       # { "1": "complete", "2": "rendering", "3": "pending" }
    episode_pipelines: JSON    # { "1": "pipeline-uuid-1", "2": "pipeline-uuid-2" }

    # 角色一致性配置
    character_images: JSON     # 人设图引用 → 用于图片生成 prompt 注入
    style_config: JSON         # 全局风格配置

    created_at: DateTime
    updated_at: DateTime
```

### 2.3 核心 API 设计

```
# 启动全剧自动化
POST /api/v1/automation/{story_id}/start
Body: {
  "episodes": [1, 2, 3, ...],      # 要生成的集（可选部分集）
  "strategy": "separated",
  "voice": "zh-CN-XiaoxiaoNeural",
  "image_model": "FLUX.1-schnell",
  "video_model": "wan2.6-i2v-flash",
  "video_provider": "dashscope",
  "concurrency": 1,                 # 同时处理几集（默认串行）
  "use_character_images": true       # 是否使用人设图保持一致性
}
Response: { automation_id, message }

# 全局进度查询
GET /api/v1/automation/{automation_id}/status
Response: {
  "status": "running",
  "total_episodes": 12,
  "completed_episodes": 5,
  "current_episode": 6,
  "progress_percent": 45,
  "episodes": [
    { "episode": 1, "status": "complete", "pipeline_id": "xxx" },
    { "episode": 2, "status": "complete", "pipeline_id": "yyy" },
    { "episode": 6, "status": "rendering_video", "progress": 70 },
    { "episode": 7, "status": "pending" },
    ...
  ]
}

# 暂停 / 恢复 / 取消
POST /api/v1/automation/{automation_id}/pause
POST /api/v1/automation/{automation_id}/resume
POST /api/v1/automation/{automation_id}/cancel

# 重试失败的集
POST /api/v1/automation/{automation_id}/retry
Body: { "episodes": [3, 7] }
```

### 2.4 编排器核心逻辑

```python
class ProjectOrchestrator:
    """项目级编排器 — 自动化多集视频生成"""

    async def run(self, automation_id: str):
        automation = await self.load(automation_id)
        story = await self.load_story(automation.story_id)

        # 按集遍历
        for episode in automation.pending_episodes:
            # 检查是否暂停
            if await self.is_paused(automation_id):
                break

            # 获取该集的剧本内容
            episode_script = self.get_episode_script(story.scenes, episode)

            # 创建该集的 pipeline
            pipeline_id = create_pipeline(story_id, episode)

            # 注入角色一致性信息（关键！）
            enhanced_script = self.inject_character_context(
                episode_script,
                story.character_images,
                automation.style_config,
            )

            # 执行单集 pipeline（复用现有 PipelineExecutor）
            executor = PipelineExecutor(story_id, pipeline_id, db)
            try:
                await executor.run_full_pipeline(
                    script=enhanced_script,
                    strategy=automation.strategy,
                    ...
                )
                await self.mark_episode_complete(automation_id, episode)
            except Exception as e:
                await self.mark_episode_failed(automation_id, episode, str(e))
                # 可选：继续下一集 or 停止
                if automation.fail_strategy == "stop":
                    break

        # 全部完成后的处理
        await self.finalize(automation_id)
```

---

## 三、角色一致性问题深度分析

### 3.1 问题本质

你在大纲阶段设计人设图的初衷是对的 — 但**当前系统没有将人设图信息回注到后续的图片/视频生成环节**。

当前的数据流存在一个**断裂**：

```
Step 3: 生成人设图
  ↓
  character_images = {
    "牧之": { image_url: "/media/characters/xxx.png", prompt: "..." }
  }
  ↓
  存入 story.character_images（数据库 ✅）

  ↓ ❌ 断裂点 ❌

Step 5: 视频生成 pipeline
  ↓
  分镜 prompt: "A man standing in rain..."  ← 完全不知道"牧之"长什么样
  ↓
  图片生成: FLUX.1 根据 prompt 随机生成  ← 每张图的人物外貌都不同！
  ↓
  视频生成: 基于不一致的图片  ← 观众看到主角每个镜头换一张脸
```

### 3.2 一致性保持的三个层级

#### Level 1: Prompt 注入（最快实现，效果中等）

**原理**: 在分镜的 visual_prompt 中注入角色外貌的详细文字描述

```
当前:  "A man standing in the rain, cinematic lighting"
改后:  "A man standing in the rain, cinematic lighting.
        The man is Mu Zhi (牧之): tall athletic build, short black hair,
        sharp jawline, wearing dark leather jacket, determined expression,
        scar on left cheek"
```

**实现方式**:
```python
def inject_character_context(visual_prompt: str, characters: dict, character_images: dict):
    """在 visual_prompt 中注入角色外貌描述"""
    # 1. 从 visual_prompt 中识别出现的角色名
    mentioned_chars = []
    for char_name, char_info in characters.items():
        if char_name in visual_prompt or char_info.get("english_name", "") in visual_prompt:
            mentioned_chars.append(char_name)

    # 2. 获取角色的人设图生成时使用的 prompt（已有详细描述）
    char_descriptions = []
    for name in mentioned_chars:
        if name in character_images:
            # 复用人设图的 prompt，确保描述一致
            char_descriptions.append(
                f"Character [{name}]: {character_images[name]['prompt']}"
            )

    # 3. 注入到 visual_prompt
    if char_descriptions:
        return f"{visual_prompt}\n\nCharacter consistency reference:\n" + "\n".join(char_descriptions)
    return visual_prompt
```

**优点**: 零成本，立即可用
**缺点**: 文字描述无法精确控制面部特征，不同镜头仍有差异
**预估一致性**: ~60%

#### Level 2: IP-Adapter / Reference Image（中等难度，效果好）

**原理**: 在图片生成时，将人设图作为参考图传入，模型会保持面部/风格一致

```
当前 API 调用:
  POST /images/generations
  { "prompt": "...", "model": "FLUX.1" }

改为:
  POST /images/generations  (支持 reference image 的 API)
  {
    "prompt": "...",
    "model": "FLUX.1",
    "reference_images": ["/media/characters/muzi.png"],
    "reference_strength": 0.6   # 参考强度
  }
```

**需要的条件**:
- SiliconFlow 或其他图片 API 需要支持 `reference_image` / `ip_adapter` 参数
- 或切换到支持此功能的图片生成服务（如 ComfyUI API、Midjourney API）
- 部分开源模型（如 InstantID、IP-Adapter-FaceID）可以自部署

**预估一致性**: ~85%

#### Level 3: LoRA 微调 + 一致性 ID（最高难度，效果最好）

**原理**: 用角色人设图训练一个小型 LoRA，然后所有该角色的图片都使用这个 LoRA

```
训练流程:
  人设图 (3-5 张) → LoRA 训练 (15-30 min) → character_lora.safetensors

生成流程:
  base_model + character_lora → 生成该角色的任何姿态/场景
```

**需要的条件**:
- 自部署 Stable Diffusion / FLUX 推理服务
- 或使用支持在线 LoRA 训练的平台（如 Civitai、Replicate）
- 训练成本：每个角色 ~$0.5-2

**预估一致性**: ~95%

### 3.3 推荐的实施路径

```
Phase 1（立即可做）:
  ✅ Prompt 注入 — 在分镜解析时将角色描述注入 visual_prompt
  ✅ 全局风格锁定 — 确保所有镜头使用相同的 style suffix
  预期效果: 60% 一致性，但已经比现在好很多

Phase 2（短期优化）:
  🔧 接入支持 Reference Image 的图片 API
  🔧 或自部署 ComfyUI + IP-Adapter
  预期效果: 85% 一致性

Phase 3（长期方案）:
  🚀 为主要角色训练 LoRA
  🚀 或使用商业化的角色一致性服务
  预期效果: 95% 一致性
```

---

## 四、完整自动化流程蓝图

### 4.1 用户视角的理想体验

```
用户操作:
  1. 创建灵感 → 生成大纲 → 生成人设图 → 生成剧本  [手动，创意阶段]
  2. 点击 "全剧自动生成"                            [一键]
  3. 去喝杯咖啡 ☕
  4. 回来看到：
     ┌─────────────────────────────────────────┐
     │  全剧生成进度                              │
     │                                           │
     │  第1集  ████████████████████  完成 ✅      │
     │  第2集  ████████████████████  完成 ✅      │
     │  第3集  ████████████████████  完成 ✅      │
     │  第4集  ██████████████░░░░░░  视频生成 70% │
     │  第5集  ░░░░░░░░░░░░░░░░░░░░  等待中       │
     │  第6集  ░░░░░░░░░░░░░░░░░░░░  等待中       │
     │                                           │
     │  总进度: 58%  |  预计剩余: ~45 分钟         │
     │                                           │
     │  [暂停]  [取消]                             │
     └─────────────────────────────────────────┘
  5. 可以预览已完成的集、重试失败的集
```

### 4.2 技术实现路线图

```
Phase 1: 基础自动化（1-2 周）
├── 1.1 实现 FFmpeg 真实合成（替换 mock）
├── 1.2 实现 ProjectOrchestrator（多集串行编排）
├── 1.3 新增 ProjectAutomation 数据模型
├── 1.4 实现全局进度 API
└── 1.5 前端：全剧自动化页面 + 进度面板

Phase 2: 角色一致性（1 周）
├── 2.1 在分镜解析 prompt 中注入角色描述
├── 2.2 在图片生成 prompt 中注入角色外貌
├── 2.3 全局风格配置（确保画风统一）
└── 2.4 人设图预览 → 图片生成的数据打通

Phase 3: 可靠性提升（1-2 周）
├── 3.1 失败重试机制（单集/单镜头级别）
├── 3.2 断点续传（从上次中断处恢复）
├── 3.3 WebSocket 实时推送（替代轮询）
└── 3.4 并发控制（可配置同时处理几集）

Phase 4: 高级一致性（未来）
├── 4.1 接入 IP-Adapter / Reference Image API
├── 4.2 或自部署 ComfyUI 推理服务
└── 4.3 角色 LoRA 训练流水线
```

---

## 五、关键技术挑战与解决方案

### 5.1 API 配额与并发控制

**问题**: 图片/视频 API 都有并发限制和配额

**方案**:
```python
# 使用信号量控制并发
class RateLimitedExecutor:
    def __init__(self, max_concurrent: int = 3):
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def execute(self, tasks):
        async def limited_task(task):
            async with self.semaphore:
                return await task
        return await asyncio.gather(*[limited_task(t) for t in tasks])
```

配置建议:
- SiliconFlow 图片: 并发 5-10
- DashScope 视频: 并发 2-3（视频生成较慢，队列有限）
- Kling 视频: 并发 2-3
- 豆包视频: 并发 2-3
- TTS (Edge TTS): 并发 10+（本地生成，无限制）

### 5.2 长时间任务的可靠性

**问题**: 全剧生成可能需要 2-6 小时，BackgroundTasks 在进程重启后丢失

**方案**: 状态持久化 + 恢复机制

```
当前: BackgroundTasks（内存，不持久）
  ↓
改进:
  1. 每步完成后将状态写入数据库
  2. 服务重启后扫描 "running" 状态的任务
  3. 从最后完成的步骤恢复执行

  长期: 引入 Celery + Redis（可选，当任务量增大时）
```

### 5.3 费用估算

以 **6 集短剧，每集 8 个镜头** 为例:

| 环节 | 单价 | 数量 | 费用 |
|------|------|------|------|
| LLM 分镜解析 | ~¥0.05/次 | 6 次 | ¥0.3 |
| TTS 语音 | 免费 (Edge TTS) | 48 个 | ¥0 |
| 图片生成 (FLUX.1) | ~¥0.02/张 | 48 张 | ¥1.0 |
| 视频生成 (DashScope) | ~¥0.5/个 | 48 个 | ¥24.0 |
| **总计** | | | **~¥25** |

视频生成是最大的成本项。可以通过选择更便宜的 provider 或降低分辨率来控制。

### 5.4 生成时间估算

| 环节 | 单个耗时 | 48 个镜头（并发） |
|------|---------|------------------|
| 分镜解析 | 10-30s/集 | ~2 分钟（6 集串行） |
| TTS | 1-3s/个 | ~30 秒（高并发） |
| 图片 | 3-10s/张 | ~1 分钟（高并发） |
| 视频 | 60-300s/个 | ~20-40 分钟（低并发） |
| FFmpeg | 5-10s/个 | ~2 分钟 |
| **总计** | | **~30-50 分钟** |

---

## 六、关于"人设图 → 角色一致性"的数据流修复

### 6.1 当前断裂点

```
story.character_images = {
  "牧之": {
    "image_url": "/media/characters/story_muzi_a1b2c3d4.png",
    "prompt": "Character portrait of 牧之, protagonist, determined expression,
               heroic bearing, character description: 28岁青年, 短发,
               穿黑色皮衣, 左脸有疤痕..."
  }
}
```

这些数据已经存在数据库里，但在 `pipeline_executor.py` 的图片生成环节完全没有使用。

### 6.2 修复方案（具体代码改动点）

**改动 1**: `storyboard.py` — 分镜解析时注入角色外貌

在调用 LLM 解析分镜的 prompt 中，增加角色描述:

```python
# 在 parse_script_to_storyboard() 中
# 新增参数: character_descriptions
# prompt 末尾追加:

"""
Character Appearance Guide (MUST follow for visual consistency):
- 牧之: 28-year-old male, short black hair, sharp jawline, athletic build,
         dark leather jacket, scar on left cheek, determined expression
- 小雨: 25-year-old female, long straight hair, gentle features,
         white dress, soft expression
...
"""
```

**改动 2**: `image.py` — 图片生成时注入角色描述

```python
# 在 generate_image() 中
# 接收额外参数: character_context

async def generate_image(
    visual_prompt: str,
    shot_id: str,
    model: str,
    character_context: str = "",  # 新增
    ...
):
    enhanced_prompt = f"{visual_prompt}. {character_context}" if character_context else visual_prompt
    # ... 其余逻辑不变
```

**改动 3**: `pipeline_executor.py` — 传递角色信息

```python
# 在 run_full_pipeline() 中新增参数
character_images: dict = None  # 从 story.character_images 获取

# 在生成图片时使用
image_results = await image.generate_images_batch(
    shots=[{
        "shot_id": s.shot_id,
        "visual_prompt": s.visual_prompt,
        "character_context": self._build_character_context(s, character_images),
    } for s in self.shots],
    ...
)
```

---

## 七、总结与优先级建议

### 最高优先级（解决核心体验问题）

1. **实现 FFmpeg 合成** — 目前是 mock，视频无法真正输出
2. **Prompt 级角色一致性** — 零成本，立即提升画面一致性
3. **多集自动编排** — 实现 ProjectOrchestrator，一键生成全剧

### 中等优先级（提升可靠性）

4. 状态持久化 + 断点续传
5. 失败重试机制
6. 并发控制（信号量限流）

### 低优先级（体验优化）

7. WebSocket 实时推送
8. Reference Image 接入
9. 前端全局进度面板

### 总结

你的直觉是对的 — **人设图就是为了角色一致性而设计的**。目前的问题是这个数据没有被后续流程消费。修复这个数据断裂（将 character_images 的描述注入到图片生成 prompt），加上实现多集自动编排，就能让整个系统从"手动逐集操作"进化为"一键全自动"。

技术上没有任何阻塞项，所有基础设施已经就绪，只需要在现有架构上增加一层编排逻辑。
