# AutoMedia

AI 驱动的短剧生成平台。输入一个故事创意，完成世界构建、角色设定、剧本生成、场景参考图、分镜解析、TTS、图片、视频、过渡视频与拼接，输出可预览、可导出的成片素材。

---

## 项目现状

当前仓库已经打通的主流程：

- Step 1：灵感输入与故事缺口分析
- Step 2：6 轮世界构建问答，结果写入 `selected_setting`
- Step 3：大纲、角色、关系、流式剧本、聊天修改、结构化联动修改
- Step 3 扩展：角色三视图设定图、`art_style` 持久化
- Step 4：剧本预览、导出、按集生成共享环境图组
- Video Generation：分镜解析、手动/自动流水线、TTS、图片、图生视频、过渡视频、拼接、状态恢复
- History：历史故事恢复，以及手动 pipeline 上下文延续

当前项目的几个关键运行规则：

- 普通主镜头统一走单首帧 I2V，`last_frame_prompt / last_frame_url` 不再参与主链路
- 场景参考图按“每集环境组”生成，每组只生成 1 张主场景图，并通过 `source_scene_key` 回接到 Shot
- 双帧能力只用于过渡视频，且锚点帧必须由后端从相邻主镜头视频中提取
- 手动分镜链路和单次 TTS/图片/视频接口会同时写入：
  - `story.meta.storyboard_generation`
  - `pipeline.generated_files`

当前已落地的 Phase 4 MVP：

- Outline、Storyboard、Character Appearance Cache、Scene Style Cache、Runtime Generation Payload、Scene Reference Prompt、Character Design Prompt 七个 prompt family 已接入可关闭的质量增强层
- 质量层支持离线 DSPy artifact、Judge shadow mode 和有限次 Feedback Loop
- 当前默认开启质量层；如需关闭，主链路行为仍可回退到原始模式

当前视频流水线策略：

- `separated`：TTS -> 图片 -> 图生视频 -> FFmpeg 合成
- `chained`：按场景分组执行，但主镜头仍是单首帧 I2V，不再做尾帧传递
- `integrated`：当前会降级为 image-to-video fallback，不包含真正的视频语音一体化生成

交接开发时，优先阅读本文末尾的“文档导航”。其中 `README.md`、`docs/feature-documentation.md`、`docs/video-pipeline.md`、`docs/prompt-framework.md`、`docs/database-persistence-implementation.md` 和 `docs/END_TO_END_CONSISTENCY_IMPLEMENTATION_PLAN.md` 共同构成当前实现口径。

---

## 技术栈

- 前端：Vue 3 + Vue Router + Pinia + Vite
- 后端：FastAPI + SQLAlchemy Async + SQLite
- 语音：Edge TTS
- 图片：SiliconFlow / 火山方舟兼容图片接口
- 视频：DashScope / Kling / 豆包
- 合成：FFmpeg

---

## 项目结构

```text
Auto_media/
├── app/
│   ├── main.py
│   ├── core/
│   │   ├── api_keys.py
│   │   ├── pipeline_runtime.py
│   │   ├── story_assets.py
│   │   └── story_context.py
│   ├── models/
│   ├── prompts/
│   │   ├── story.py
│   │   ├── storyboard.py
│   │   └── character.py
│   ├── routers/
│   │   ├── story.py
│   │   ├── pipeline.py
│   │   ├── image.py
│   │   ├── video.py
│   │   ├── tts.py
│   │   └── character.py
│   ├── schemas/
│   └── services/
│       ├── story_llm.py
│       ├── storyboard.py
│       ├── scene_reference.py
│       ├── storyboard_state.py
│       ├── pipeline_executor.py
│       ├── image.py
│       ├── video.py
│       ├── ffmpeg.py
│       ├── story_context_service.py
│       └── story_repository.py
├── frontend/
│   ├── src/views/
│   ├── src/components/
│   ├── src/stores/
│   └── src/api/
├── docs/
├── tests/
├── media/
├── pyproject.toml
├── start.py
└── README.md
```

---

## 快速开始

### 环境要求

- Python 3.12+
- Node.js 18+
- FFmpeg / FFprobe

### 一键启动

```bash
python start.py
```

`start.py` 会在启动前自动检查 `ffmpeg` / `ffprobe`：

- 已安装时会自动注入 `FFMPEG_PATH` / `FFPROBE_PATH` 给后端进程
- 缺失时会优先尝试使用本机可用的包管理器自动安装
- 若系统包管理器不可用，会退回到项目内 `.ffmpeg-tools` 的本地安装
- 如需无交互自动安装，可使用：

```bash
AUTOMEDIA_AUTO_INSTALL_FFMPEG=1 python start.py
```

默认地址：

- 后端：`http://localhost:8000`
- 前端：`http://localhost:5173`

### 手动启动

```bash
# 安装 Python 依赖
uv sync

# 安装 FFmpeg（任选一种）
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt-get install -y ffmpeg

# 项目内本地安装（无需全局 Homebrew）
npm --prefix .ffmpeg-tools install @ffmpeg-installer/ffmpeg @ffprobe-installer/ffprobe

# 启动后端
uv run uvicorn app.main:app --reload --reload-dir app

# 启动前端
cd frontend
npm install
npm run dev
```

### 环境变量

```bash
cp .env.example .env
```

常用配置：

```env
DEFAULT_LLM_PROVIDER=claude
DEFAULT_IMAGE_PROVIDER=siliconflow
DEFAULT_VIDEO_PROVIDER=dashscope

ANTHROPIC_API_KEY=
OPENAI_API_KEY=
QWEN_API_KEY=
ZHIPU_API_KEY=
GEMINI_API_KEY=

SILICONFLOW_API_KEY=
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1

SILICONFLOW_IMAGE_API_KEY=
SILICONFLOW_IMAGE_BASE_URL=https://api.siliconflow.cn/v1
SILICONFLOW_IMAGE_MODEL=black-forest-labs/FLUX.1-schnell

DOUBAO_IMAGE_API_KEY=
DOUBAO_IMAGE_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_IMAGE_MODEL=ep-xxxxxxxxxxxxxxxx

DASHSCOPE_VIDEO_API_KEY=
DASHSCOPE_VIDEO_BASE_URL=https://dashscope.aliyuncs.com/api/v1
DASHSCOPE_VIDEO_MODEL=wan2.6-i2v-flash

KLING_VIDEO_API_KEY=
KLING_VIDEO_BASE_URL=https://api.klingai.com
KLING_VIDEO_MODEL=kling-v2-master

MINIMAX_VIDEO_API_KEY=
MINIMAX_VIDEO_BASE_URL=https://api.minimaxi.chat
MINIMAX_VIDEO_MODEL=video-01

DOUBAO_VIDEO_API_KEY=
DOUBAO_VIDEO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_VIDEO_MODEL=ep-yyyyyyyyyyyyyyyy

# 可选：自定义 FFmpeg / FFprobe 路径
FFMPEG_PATH=
FFPROBE_PATH=

# 可选：Phase 4 质量增强层
QUALITY_LAYER_ENABLED=true
QUALITY_OUTLINE_ENABLED=true
QUALITY_STORYBOARD_ENABLED=true
QUALITY_CHARACTER_APPEARANCE_ENABLED=true
QUALITY_SCENE_STYLE_ENABLED=true
QUALITY_GENERATION_PAYLOAD_ENABLED=true
QUALITY_SCENE_REFERENCE_ENABLED=true
QUALITY_CHARACTER_DESIGN_ENABLED=true
QUALITY_DSPY_ENABLED=true
QUALITY_JUDGE_ENABLED=true
QUALITY_JUDGE_SHADOW_MODE=true
QUALITY_FEEDBACK_LOOP_ENABLED=true
QUALITY_FEEDBACK_MAX_RETRIES=1
QUALITY_JUDGE_PROVIDER=
QUALITY_JUDGE_MODEL=
QUALITY_JUDGE_API_KEY=
QUALITY_JUDGE_BASE_URL=
```

说明：

- 前端设置页支持配置全局 LLM、分镜专用 LLM、图片和视频服务
- `.env` 的图片和视频配置与前端分组对齐，豆包图片与豆包视频使用独立 API Key
- 浏览器未显式保存图片/视频设置时，后端会使用 `DEFAULT_IMAGE_PROVIDER` / `DEFAULT_VIDEO_PROVIDER`
- 后端优先读取请求 Header，其次回退到 `.env`
- `/media` 会自动挂载本地静态产物目录
- 若系统 PATH 未包含 Homebrew 目录，可直接在 `.env` 或 shell 中显式指定 `FFMPEG_PATH` / `FFPROBE_PATH`
- Judge 默认复用当前请求的 LLM 配置；`QUALITY_JUDGE_MODEL` / `QUALITY_JUDGE_API_KEY` / `QUALITY_JUDGE_BASE_URL` 可在保持同一 provider 时单独覆盖，`QUALITY_JUDGE_PROVIDER` 则用于切换到独立 Judge provider；切换后会优先使用 `QUALITY_JUDGE_*`，其中 `QUALITY_JUDGE_API_KEY` / `QUALITY_JUDGE_BASE_URL` 为空时会回退到该 provider 在 `.env` 中的默认配置，而 `QUALITY_JUDGE_MODEL` 不会自动从 `.env` 补默认值

---

## 核心工作流

```text
Step 1 灵感分析
  -> POST /api/v1/story/analyze-idea

Step 2 世界构建
  -> POST /api/v1/story/world-building/start
  -> POST /api/v1/story/world-building/turn

Step 3 大纲与剧本
  -> POST /api/v1/story/generate-outline
  -> POST /api/v1/story/chat
  -> POST /api/v1/story/generate-script
  -> POST /api/v1/story/refine
  -> POST /api/v1/story/apply-chat
  -> POST /api/v1/story/patch
  -> POST /api/v1/character/generate
  -> POST /api/v1/character/generate-all

Step 4 预览、导出与分镜输入
  -> POST /api/v1/story/{story_id}/scene-reference/generate
  -> POST /api/v1/story/{story_id}/finalize
  -> POST /api/v1/story/{story_id}/storyboard-script

Video Generation
  -> POST /api/v1/pipeline/{project_id}/storyboard
  -> POST /api/v1/pipeline/{project_id}/generate-assets
  -> POST /api/v1/pipeline/{project_id}/render-video
  -> POST /api/v1/image/{project_id}/generate
  -> POST /api/v1/video/{project_id}/generate
  -> POST /api/v1/tts/{project_id}/generate
  -> POST /api/v1/pipeline/{project_id}/transitions/generate
  -> POST /api/v1/pipeline/{project_id}/concat
  -> GET  /api/v1/pipeline/{project_id}/status
```

---

## API 概览

### Story API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/story/` | 历史故事列表 |
| `GET` | `/api/v1/story/{story_id}` | 获取完整 Story |
| `DELETE` | `/api/v1/story/{story_id}` | 删除 Story |
| `POST` | `/api/v1/story/analyze-idea` | 灵感审计 |
| `POST` | `/api/v1/story/world-building/start` | 开始世界构建 |
| `POST` | `/api/v1/story/world-building/turn` | 继续世界构建 |
| `POST` | `/api/v1/story/generate-outline` | 生成大纲、角色、关系 |
| `POST` | `/api/v1/story/chat` | SSE 对话式建议，支持 `character / episode / outline / generic` |
| `POST` | `/api/v1/story/generate-script` | SSE 剧本生成 |
| `POST` | `/api/v1/story/refine` | 结构化联动修改 |
| `POST` | `/api/v1/story/apply-chat` | 应用聊天修改 |
| `POST` | `/api/v1/story/patch` | 持久化 `characters / outline / art_style` |
| `POST` | `/api/v1/story/{story_id}/scene-reference/generate` | 生成本集共享环境图组 |
| `POST` | `/api/v1/story/{story_id}/finalize` | 导出第二阶段可消费剧本文本 |
| `POST` | `/api/v1/story/{story_id}/storyboard-script` | 按所选场景导出统一 storyboard 输入文本 |

### Pipeline API

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/pipeline/{project_id}/auto-generate` | 自动全流程 |
| `POST` | `/api/v1/pipeline/{project_id}/storyboard` | 剧本转结构化分镜 |
| `POST` | `/api/v1/pipeline/{project_id}/generate-assets` | 批量生成 TTS / 图片 |
| `POST` | `/api/v1/pipeline/{project_id}/render-video` | 批量生成视频 |
| `POST` | `/api/v1/pipeline/{project_id}/transitions/generate` | 生成相邻镜头过渡视频 |
| `POST` | `/api/v1/pipeline/{project_id}/concat` | 按时间线拼接视频 |
| `GET` | `/api/v1/pipeline/{project_id}/status` | 查询 pipeline 状态 |

### Asset API

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/character/generate` | 单角色设定图，要求 `character_id` |
| `POST` | `/api/v1/character/generate-all` | 批量角色设定图 |
| `GET` | `/api/v1/character/{story_id}/images` | 读取角色图资产 |
| `POST` | `/api/v1/image/{project_id}/generate` | 单镜头图片生成，可带 `story_id / pipeline_id` |
| `POST` | `/api/v1/video/{project_id}/generate` | 单镜头视频生成，可带 `story_id / pipeline_id` |
| `GET` | `/api/v1/tts/voices` | 语音列表 |
| `POST` | `/api/v1/tts/{project_id}/generate` | 单镜头 TTS，可带 `story_id / pipeline_id` |

---

## 当前关键能力

- Step 3 AI 聊天默认不允许修改角色名和 `role`
- 角色设定图资产统一写入 `story.character_images`
- `art_style` 会在角色图、图片、视频链路中透传并持久化
- `source_scene_key` 已接入分镜主链路，场景参考图可回灌到首帧生成
- 图片生成支持运行期 `reference_images`，优先使用角色图 + 场景参考图
- 普通主镜头统一单首帧 I2V，不再传播尾帧
- 过渡视频已接入主流程时间线，导出时可自动插入
- 手动分镜页会恢复最近一次 `storyboard_generation` 状态

---

## 当前数据口径

### Story

`Story` 是业务主载体，除 `idea / genre / tone / selected_setting / characters / outline / scenes / character_images / art_style` 外，当前重点使用的 `meta` 字段包括：

- `character_appearance_cache`
- `scene_style_cache`
- `episode_reference_assets`
- `scene_reference_assets`
- `storyboard_generation`

### Pipeline

`Pipeline.generated_files` 当前可能包含：

- `storyboard`
- `tts`
- `images`
- `videos`
- `transitions`
- `timeline`
- `final_video_url`
- `meta`

完整视频导出当前要求：

- 当前 storyboard 的主镜头视频必须全部存在
- 若 storyboard 含多个镜头，则相邻 `transitions` 也必须全部存在
- 当提供 `pipeline_id` 时，后端会按当前 storyboard 重新推导导出顺序，不再完全信任前端上送的 `video_urls`

---

## 当前边界

- `integrated` 仍是 fallback，不是实际的视频语音一体化生成
- 双帧能力当前只对 transition 暴露，普通镜头不会启用
- transition 目前有生成接口，但没有独立删除接口
- 更强的 DSPy 提取器、VLM 质检、独立数字资产库尚未落地
- 遗留 `projects` 相关文件仍在仓库中，但路由已不再挂载

---

## 验证

后端回归：

```bash
UV_CACHE_DIR=/tmp/uv-cache PYTHONPYCACHEPREFIX=/tmp/pycache uv run python -m unittest discover -s tests -q
```

前端构建：

```bash
npm --prefix frontend run build
```

前端现有 Node 单测：

```bash
node --test frontend/src/utils/storyChat.test.js frontend/src/utils/storyChat.multiline-sections.test.js frontend/src/utils/storyChat.numbering.test.js
```

---

## 文档导航

当前交接和继续开发时，优先以这些文档为准：

- [功能文档](./docs/feature-documentation.md)
- [视频生成与视觉一致性统一文档](./docs/video-pipeline.md)
- [Prompt Framework](./docs/prompt-framework.md)
- [数据库持久化实现现状](./docs/database-persistence-implementation.md)
- [画风设定链路说明](./docs/art-style-backend.md)
- [API Key 管理指南](./docs/api-key-management.md)
- [端到端一致性实施方案](./docs/END_TO_END_CONSISTENCY_IMPLEMENTATION_PLAN.md)
- [Phase 3 人工验收 Runbook](./docs/phase3-manual-acceptance-runbook.md)

以下文档保留为历史分析、专题讨论或部署参考，不作为当前实现真相源：

- [当前功能现状与本周进展总结（2026-03-27）](./docs/current-status-and-weekly-progress-2026-03-27.md)
- [I2V vs T2V 技术对比分析](./docs/I2V_VS_T2V_ANALYSIS.md)
- [分镜切分问题深度分析](./docs/SHOT_SPLITTING_ANALYSIS.md)
- [全流程自动化分析文档](./docs/automation-analysis.md)
- [手机 App 可行性分析](./docs/mobile-app-analysis.md)
- [完整视频导出防串片改造说明](./docs/full-video-export-guardrails-plan.md)
- [阿里云 ECS + FRP 单端口临时试用方案](./docs/aliyun-frp-public-access-plan.md)
