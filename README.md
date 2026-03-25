# AutoMedia

AI 驱动的短剧自动生成平台。输入一个故事创意，经过世界观构建、角色设计、剧本生成、分镜解析、TTS、图片生成、图生视频与 FFmpeg 合成，输出可预览、可导出的完整视频素材。

---

## 项目现状

当前项目已经具备以下主流程能力：

- Step 1：灵感输入与要素分析
- Step 2：6 轮世界观构建问答
- Step 3：大纲、角色关系、流式剧本生成
- Step 3 扩展：角色设计图生成、画风设定持久化
- Step 4：剧本预览、导出
- Step 5 / Video Generation：分镜解析、TTS、图片生成、图生视频、拼接导出

当前视频流水线支持 3 种策略：

- `separated`：TTS → 图片 → 图生视频 → FFmpeg 合成
- `integrated`：图片 → 视频生成（当前仍复用图生视频接口，未对接真正“视频语音一体”服务）
- `chained`：场景内串行生成，利用前一镜头末帧增强镜头连续性

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
│   ├── core/                      # 配置、数据库、API Key、Header 解析
│   ├── models/                    # Story / Pipeline ORM
│   ├── prompts/                   # story / storyboard / character prompt
│   ├── routers/                   # story / pipeline / image / video / tts / character
│   ├── schemas/                   # Pydantic 数据契约
│   └── services/
│       ├── story_llm.py           # 故事生成与世界观构建
│       ├── storyboard.py          # 剧本 -> 分镜
│       ├── pipeline_executor.py   # 自动流水线编排
│       ├── image.py               # 图片生成
│       ├── video.py               # 视频生成与链式编排
│       ├── ffmpeg.py              # 音视频合成 / 拼接
│       ├── story_repository.py    # Story / Pipeline 持久化
│       └── video_providers/       # dashscope / kling / doubao provider
├── frontend/
│   ├── src/views/                 # Step1~4、VideoGeneration、History、Settings
│   ├── src/components/            # CharacterDesign、ArtStyleSelector 等组件
│   ├── src/stores/                # story / settings store
│   └── src/api/                   # 前端 API 封装
├── docs/                          # 设计文档、功能文档、专项实现说明
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

- 前端设置页支持填写全局 LLM / 图片 / 视频专用配置
- 后端会优先读取请求 Header，其次回退到 `.env`

---

## 核心数据流

```text
Step1 灵感输入
  -> POST /api/v1/story/analyze-idea

Step2 世界观构建
  -> POST /api/v1/story/world-building/start
  -> POST /api/v1/story/world-building/turn

Step3 大纲与剧本
  -> POST /api/v1/story/generate-outline
  -> POST /api/v1/story/generate-script (SSE)
  -> POST /api/v1/story/refine
  -> POST /api/v1/story/apply-chat

Step4 预览与导出
  -> POST /api/v1/story/{story_id}/finalize

Video Generation
  -> POST /api/v1/pipeline/{project_id}/storyboard
  -> POST /api/v1/pipeline/{project_id}/generate-assets
  -> POST /api/v1/pipeline/{project_id}/render-video
  -> POST /api/v1/pipeline/{project_id}/auto-generate
  -> GET  /api/v1/pipeline/{project_id}/status
  -> POST /api/v1/pipeline/{project_id}/concat
  -> POST /api/v1/pipeline/{project_id}/stitch
```

---

## API 概览

### Story API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/story/` | 历史故事列表 |
| `GET` | `/api/v1/story/{story_id}` | 获取完整故事 |
| `DELETE` | `/api/v1/story/{story_id}` | 删除故事 |
| `POST` | `/api/v1/story/analyze-idea` | 分析创意 |
| `POST` | `/api/v1/story/generate-outline` | 生成大纲、角色、关系 |
| `POST` | `/api/v1/story/generate-script` | 流式生成剧本 |
| `POST` | `/api/v1/story/chat` | AI 对话修改 |
| `POST` | `/api/v1/story/refine` | 结构化修改 |
| `POST` | `/api/v1/story/patch` | 持久化局部更新（含 `art_style`） |
| `POST` | `/api/v1/story/apply-chat` | 应用对话修改结果 |
| `POST` | `/api/v1/story/world-building/start` | 开始世界观问答 |
| `POST` | `/api/v1/story/world-building/turn` | 继续世界观问答 |
| `POST` | `/api/v1/story/{story_id}/finalize` | 导出第二阶段可消费的剧本文本 |

### Pipeline API

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/pipeline/{project_id}/auto-generate` | 自动执行全流程 |
| `POST` | `/api/v1/pipeline/{project_id}/storyboard` | 剧本转分镜 |
| `POST` | `/api/v1/pipeline/{project_id}/generate-assets` | 手动生成 TTS + 图片 |
| `POST` | `/api/v1/pipeline/{project_id}/render-video` | 手动生成视频 |
| `GET` | `/api/v1/pipeline/{project_id}/status` | 查询状态 |
| `POST` | `/api/v1/pipeline/{project_id}/concat` | 合并多镜头视频 |
| `POST` | `/api/v1/pipeline/{project_id}/stitch` | 单镜头音视频合成接口（当前仍为占位实现） |

### Asset API

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/character/generate` | 单角色设计图 |
| `POST` | `/api/v1/character/generate-all` | 批量角色设计图 |
| `GET` | `/api/v1/character/{story_id}/images` | 角色图片查询 |
| `POST` | `/api/v1/image/{project_id}/generate` | 手动图片生成 |
| `POST` | `/api/v1/video/{project_id}/generate` | 手动视频生成 |
| `GET` | `/api/v1/tts/voices` | 语音列表 |
| `POST` | `/api/v1/tts/{project_id}/generate` | TTS 生成 |

---

## 当前已落地的关键能力

- 多 LLM provider 配置与 Header 透传
- 世界观问答结果持久化到 `selected_setting`
- 角色设计图存储到 `story.character_images`
- `art_style` 前后端透传与持久化
- 手动生图 / 生视频复用共享请求头
- 自动流水线与手动流水线并存
- 历史剧本加载与恢复
- 链式视频生成（场景内末帧传递）

---

## 当前边界

- `integrated` 仍是接口占位语义，底层尚未接入真正的“视频语音一体”服务
- 手动步进的 `/generate-assets`、`/render-video` 状态仍以内存为主，重启后丢失
- 视频 provider 在用户侧当前以 `dashscope / kling / doubao` 为主；代码中虽有 `minimax` provider 类，但后端校验链路尚未完整开放
- 更强的一致性方案（`StoryContext`、结构化外貌缓存、Prompt Caching）目前主要体现在设计文档，尚未完全实现

---

## 相关文档

- [功能文档](./docs/feature-documentation.md)
- [画风设定后端说明](./docs/art-style-backend.md)
- [视觉一致性引擎设计](./docs/digital-asset-library-design.md)
- [Prompt Framework](./docs/prompt-framework.md)
- [Pipeline API](./PIPELINE_API.md)

---

## License

项目当前未单独声明 License，如需开源请补充。
