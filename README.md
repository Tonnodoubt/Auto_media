# AutoMedia

AI 驱动的短剧自动生成平台。输入一个故事创意，经过世界构建、角色设定、剧本生成、分镜解析、TTS、图片生成、图生视频与拼接，输出可预览、可导出的完整视频素材。

---

## 项目现状

当前仓库已经打通以下主流程：

- Step 1：灵感输入与要素审计
- Step 2：6 轮世界构建问答
- Step 3：大纲、角色、关系、流式剧本生成
- Step 3 扩展：角色三视图设定图、画风设定持久化
- Step 4：剧本预览与导出
- Video Generation：分镜、TTS、图片、图生视频、拼接、状态追踪
- History：历史故事恢复与手动 pipeline 上下文延续

当前视频流水线策略：

- `separated`：TTS -> 图片 -> 图生视频 -> 拼接
- `chained`：场景内串行生成，利用前一镜头尾帧增强连续性
- `integrated`：当前会降级为 image-to-video fallback，不包含真正的视频语音一体化生成

---

## 技术栈

- 前端：Vue 3 + Vue Router + Pinia + Vite
- 后端：FastAPI + SQLAlchemy Async + SQLite
- 语音：Edge TTS
- 图片：SiliconFlow / 豆包(火山方舟)
- 视频：DashScope / Kling / 豆包
- 合成：FFmpeg

---

## 项目结构

```text
Auto_media/
├── app/
│   ├── main.py                    # FastAPI 入口
│   ├── core/                      # 配置、数据库、API Key、StoryContext 等
│   ├── models/                    # Story / Pipeline ORM
│   ├── prompts/                   # story / storyboard / character prompt
│   ├── routers/                   # story / pipeline / image / video / tts / character
│   ├── schemas/                   # Pydantic 数据契约
│   └── services/
│       ├── story_llm.py           # 故事生成与世界构建
│       ├── storyboard.py          # 剧本 -> 分镜
│       ├── pipeline_executor.py   # 自动流水线编排
│       ├── image.py               # 图片生成
│       ├── video.py               # 视频生成与链式编排
│       ├── ffmpeg.py              # 音视频合成 / 拼接
│       ├── story_context_service.py
│       ├── story_repository.py    # Story / Pipeline 持久化
│       └── video_providers/       # dashscope / kling / doubao provider
├── frontend/
│   ├── src/views/                 # Step1~4、VideoGeneration、History、Settings
│   ├── src/components/            # CharacterDesign、ArtStyleSelector 等组件
│   ├── src/stores/                # story / settings store
│   └── src/api/                   # 前端 API 封装
├── docs/                          # 功能、Prompt、设计文档
├── tests/                         # 后端回归测试
├── pyproject.toml
├── start.py
└── README.md
```

---

## 快速开始

### 环境要求

- Python 3.12+
- Node.js 16+
- FFmpeg（加入系统 PATH）

### 一键启动

```bash
python start.py
```

默认地址：

- 后端：`http://localhost:8000`
- 前端：`http://localhost:5173`

### 手动启动

```bash
# 后端
uv run uvicorn app.main:app --reload

# 前端
cd frontend
npm install
npm run dev
```

### 环境变量

```bash
cp .env.example .env
```

示例：

```env
# 默认 LLM
DEFAULT_LLM_PROVIDER=claude

# LLM Keys
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
QWEN_API_KEY=
ZHIPU_API_KEY=
GEMINI_API_KEY=

# 图片
SILICONFLOW_API_KEY=
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1

# 视频
DASHSCOPE_API_KEY=
KLING_API_KEY=
DOUBAO_API_KEY=
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
```

说明：

- 前端设置页支持填写全局 LLM / 分镜专用 LLM / 图片 / 视频配置
- 后端优先读取请求 Header，其次回退到 `.env`
- 运行期 `debug` 配置兼容 `release / prod / dev / on / off`

---

## 核心数据流

```text
Step1 灵感输入
  -> POST /api/v1/story/analyze-idea

Step2 世界构建
  -> POST /api/v1/story/world-building/start
  -> POST /api/v1/story/world-building/turn

Step3 大纲与剧本
  -> POST /api/v1/story/generate-outline
  -> POST /api/v1/story/chat (SSE)
  -> POST /api/v1/story/generate-script (SSE)
  -> POST /api/v1/story/refine
  -> POST /api/v1/story/apply-chat
  -> POST /api/v1/story/patch

Step4 预览与导出
  -> POST /api/v1/story/{story_id}/finalize

Video Generation
  -> POST /api/v1/pipeline/{project_id}/storyboard
  -> POST /api/v1/pipeline/{project_id}/generate-assets
  -> POST /api/v1/pipeline/{project_id}/render-video
  -> POST /api/v1/pipeline/{project_id}/auto-generate
  -> GET  /api/v1/pipeline/{project_id}/status
  -> POST /api/v1/pipeline/{project_id}/concat
```

---

## API 概览

### Story API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/story/` | 历史故事列表 |
| `GET` | `/api/v1/story/{story_id}` | 获取完整故事 |
| `DELETE` | `/api/v1/story/{story_id}` | 删除故事 |
| `POST` | `/api/v1/story/analyze-idea` | 灵感审计 |
| `POST` | `/api/v1/story/world-building/start` | 开始世界构建 |
| `POST` | `/api/v1/story/world-building/turn` | 继续世界构建 |
| `POST` | `/api/v1/story/generate-outline` | 生成大纲、角色、关系 |
| `POST` | `/api/v1/story/chat` | SSE 对话式修改建议，支持 `character / episode / outline` 模式 |
| `POST` | `/api/v1/story/generate-script` | 流式生成剧本 |
| `POST` | `/api/v1/story/refine` | 结构化联动修改 |
| `POST` | `/api/v1/story/apply-chat` | 应用对话式局部修改 |
| `POST` | `/api/v1/story/patch` | 持久化 `characters / outline / art_style` |
| `POST` | `/api/v1/story/{story_id}/finalize` | 导出第二阶段可消费剧本文本 |

### Pipeline API

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/pipeline/{project_id}/auto-generate` | 自动执行全流程 |
| `POST` | `/api/v1/pipeline/{project_id}/storyboard` | 剧本转分镜 |
| `POST` | `/api/v1/pipeline/{project_id}/generate-assets` | 手动生成 TTS / 图片 |
| `POST` | `/api/v1/pipeline/{project_id}/render-video` | 手动生成视频 |
| `GET` | `/api/v1/pipeline/{project_id}/status` | 查询状态 |
| `POST` | `/api/v1/pipeline/{project_id}/concat` | 合并多镜头视频 |

### Asset API

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/character/generate` | 单角色设定图 |
| `POST` | `/api/v1/character/generate-all` | 批量角色设定图 |
| `GET` | `/api/v1/character/{story_id}/images` | 角色图片查询 |
| `POST` | `/api/v1/image/{project_id}/generate` | 手动图片生成 |
| `POST` | `/api/v1/video/{project_id}/generate` | 手动视频生成 |
| `GET` | `/api/v1/tts/voices` | 语音列表 |
| `POST` | `/api/v1/tts/{project_id}/generate` | TTS 生成 |

---

## 当前已落地的关键能力

- 世界构建结果持久化到 `selected_setting`
- 角色持久化时自动规范化 `id`
- 角色关系自动规范化 `source_id / target_id`
- 角色设定图资产统一写入 `story.character_images`
- `art_style` 前后端透传与持久化
- Step 3 AI 修改助手已收敛为短文本结构化回复，角色聊天固定返回“当前角色修改 / 对剧情的影响”
- AI 聊天不允许修改角色名字与主角/配角等标签，角色名仍以手动编辑为准
- 手动修改角色描述与剧情大纲时，前端会先调用 `/story/patch` 持久化，再调用 `/story/refine` 做联动更新
- `StoryContext` 已接入手动与自动视频主链路
- 运行期会复用 `character_appearance_cache`、`scene_style_cache`、`visual_dna`
- 手动与自动流水线共享数据库中的 `pipeline` 状态
- 历史剧本加载与恢复

---

## 当前边界

- `integrated` 当前仍不是实际的一体化视频语音生成
- `scene_intensity` 是分镜阶段字段，不是当前 Step 3 剧本阶段默认输出字段
- `last_frame_prompt / last_frame_url` 已进入 schema，但不同视频 provider 的支持程度不一致
- 更强的 DSPy 提取器、VLM 反馈闭环、独立数字资产库尚未落地
- 遗留 `projects` 文件仍在仓库中，但相关路由已不再挂载到主应用

---

## 测试

当前后端测试可以用：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m unittest discover -s tests -v
```

---

## 相关文档

- [功能文档](./docs/feature-documentation.md)
- [Prompt Framework](./docs/prompt-framework.md)
- [画风设定后端说明](./docs/art-style-backend.md)
- [视觉一致性引擎设计](./docs/digital-asset-library-design.md)
- [DSPy 反馈闭环计划](./docs/DSPY_FEEDBACK_LOOP_INTEGRATION_PLAN.md)
- [Pipeline API](./PIPELINE_API.md)

---

## License

项目当前未单独声明 License，如需开源请补充。
