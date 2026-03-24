# AutoMedia

AI 驱动的短视频自动生成平台。输入一个故事创意，经过访谈问答、剧本生成、分镜解析、TTS、图片生成、图生视频、FFmpeg 合成，输出一条完整短视频。

---

## 项目结构

```
automedia/
├── .env.example              # 环境变量模板
├── pyproject.toml            # Python 依赖（uv）
├── start.py                  # 一键启动脚本
├── frontend/                 # Vue 3 前端
│   └── src/
│       ├── views/            # Step1~4 + VideoGeneration + Settings + History 页面
│       ├── stores/           # Pinia 状态管理
│       ├── api/story.js      # 后端 API 封装
│       └── components/       # UI 组件（角色图谱、分镜预览、导出面板等）
└── app/                      # FastAPI 后端
    ├── main.py               # 应用入口
    ├── core/
    │   ├── config.py         # 全局配置（读取 .env）
    │   ├── database.py       # SQLAlchemy async 引擎（SQLite）
    │   └── api_keys.py       # API Key 统一管理
    ├── models/               # ORM 模型（Story、Project）
    ├── schemas/              # Pydantic 模型（story、storyboard、pipeline、interview）
    ├── routers/              # API 路由
    │   ├── story.py          # Phase 1：故事创作
    │   ├── pipeline.py       # Phase 2：视频流水线
    │   ├── projects.py       # 项目管理 + 世界观构建
    │   ├── character.py      # 角色图片生成
    │   ├── image.py          # 场景图片生成
    │   ├── tts.py            # TTS 语音生成
    │   └── video.py          # 视频生成
    └── services/
        ├── story_llm.py      # 故事生成服务
        ├── storyboard.py     # 分镜解析（LLM Prompt）
        ├── tts.py            # Edge TTS 集成
        ├── image.py          # FLUX.1 图片生成
        ├── ffmpeg.py         # FFmpeg 音视频合成与拼接
        ├── pipeline_executor.py  # 流水线编排
        ├── story_repository.py   # 数据库操作
        ├── llm/              # 多 Provider LLM 抽象层
        │   ├── base.py / factory.py
        │   ├── claude.py / openai.py / qwen.py / zhipu.py / gemini.py
        └── video_providers/  # 多 Provider 视频生成
            ├── base.py / factory.py
            ├── dashscope.py / doubao.py / kling.py
```

---

## 快速开始

### 1. 环境要求

- Python 3.12+
- Node.js 16+
- FFmpeg（合成视频时需要，需加入系统 PATH）

### 2. 一键启动

```bash
python start.py
```

后端运行在 `http://localhost:8000`，前端运行在 `http://localhost:5173`。

### 3. 手动启动

```bash
# 后端
uv run uvicorn app.main:app --reload

# 前端（另开终端）
cd frontend && npm install && npm run dev
```

### 4. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入 API Key：

```env
# LLM Provider（必填其一）
DEFAULT_LLM_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
QWEN_API_KEY=...
ZHIPU_API_KEY=...
GEMINI_API_KEY=...

# 图片生成（必填其一）
SILICONFLOW_API_KEY=...      # FLUX.1 图片生成
DOUBAO_API_KEY=...           # 豆包 / 火山方舟（图片 + 视频）

# 所有 Provider 均支持中转站（可选）
ANTHROPIC_BASE_URL=https://api.anthropic.com
OPENAI_BASE_URL=https://api.openai.com/v1
# ...
```

---

## 完整数据流

```
前端 Step1  输入创意 + 选风格
    ↓ POST /api/v1/story/analyze-idea
前端 Step2  选故事设定，与 AI 对话（世界观构建）
    ↓ POST /api/v1/story/generate-outline（SSE）
前端 Step3  查看大纲 + 人物关系图，流式生成剧本
    ↓ POST /api/v1/story/generate-script（SSE）
前端 Step4  预览剧本 + 角色设计图，导出 JSON / Markdown
    ↓ POST /api/v1/story/{id}/finalize        ← 两阶段桥接点
    ↓ POST /api/v1/pipeline/{id}/storyboard   ← 剧本 → 分镜 JSON
    ↓ POST /api/v1/pipeline/{id}/generate-assets  ← TTS + 图片生成
    ↓ POST /api/v1/pipeline/{id}/render-video     ← 图生视频（异步）
    ↓ GET  /api/v1/pipeline/{id}/status           ← 轮询进度
    ↓ POST /api/v1/pipeline/{id}/concat           ← FFmpeg 拼接最终视频
      最终视频文件（前端支持直接导出）
```

---

## API 概览

### Phase 1 — 故事创作

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/story/analyze-idea` | 分析创意，返回故事设定选项 |
| POST | `/api/v1/story/generate-outline` | 生成大纲、人物、人物关系（SSE） |
| POST | `/api/v1/story/chat` | 与 AI 实时对话（SSE） |
| POST | `/api/v1/story/generate-script` | 流式生成剧本场景（SSE） |
| POST | `/api/v1/story/refine` | 优化剧本主题/风格 |
| POST | `/api/v1/story/patch` | 局部修改场景 |
| POST | `/api/v1/story/{id}/finalize` | 序列化剧本，供第二阶段使用 |

### Phase 2 — 视频流水线

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/pipeline/{id}/auto-generate` | 一键执行全流程 |
| POST | `/api/v1/pipeline/{id}/storyboard` | 剧本 → 分镜 JSON（调用 LLM） |
| POST | `/api/v1/pipeline/{id}/generate-assets` | 触发 TTS + 图片生成 |
| POST | `/api/v1/pipeline/{id}/render-video` | 触发图生视频（异步队列） |
| GET  | `/api/v1/pipeline/{id}/status` | 轮询渲染进度 |
| POST | `/api/v1/pipeline/{id}/concat` | FFmpeg 拼接最终视频 |
| POST | `/api/v1/pipeline/{id}/stitch` | 单镜头音视频合成 |

### 辅助接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/character/generate` | 生成单个角色设计图 |
| POST | `/api/v1/character/generate-all` | 批量生成全部角色设计图 |
| GET  | `/api/v1/character/{story_id}/images` | 查询角色图片 |
| POST | `/api/v1/image/{id}/generate` | 场景关键帧生成 |
| POST | `/api/v1/video/{id}/generate` | 视频片段生成 |
| GET  | `/api/v1/tts/voices` | 获取可用语音列表 |
| POST | `/api/v1/tts/{id}/generate` | TTS 语音生成 |

---

## 模块进度

| 模块 | 说明 | 状态 |
|------|------|------|
| Phase 1 | 故事创作（访谈、大纲、剧本、修改） | ✅ 完成 |
| 模块 A | 分镜引擎（升级版 LLM 解析，含镜头语言） | ✅ 完成 |
| 模块 B | TTS 语音生成（Edge TTS，18+ 中文音色） | ✅ 完成 |
| 模块 C | 关键帧图片生成（FLUX.1 / 豆包） | ✅ 完成 |
| 模块 D | 图生视频（DashScope / 豆包 / Kling） | ✅ 完成 |
| 模块 E | FFmpeg 合成与视频拼接 | ✅ 完成 |
| 角色设计 | AI 生成角色视觉提示词 + 参考图 | ✅ 完成 |
| 自动化流水线 | 一键生成 + 双策略支持 | ✅ 完成 |

### Phase 2 特性

- **一键生成**：`POST /api/v1/pipeline/{id}/auto-generate` 自动执行全流程
- **双策略支持**：
  - **分离式（separated）**：TTS → 图片 → 图生视频 → FFmpeg 合成
  - **一体式（integrated）**：图片 + 语音一体生成
- **实时进度追踪**：详细的步骤状态和进度信息
- **前端导出**：视频生成完成后可直接在浏览器下载

详见 [PIPELINE_API.md](./PIPELINE_API.md)

---

## LLM Provider 切换

前端通过设置页配置 API Key 和 provider，无需重启后端。后端也支持通过 `.env` 设置默认 provider：

```env
DEFAULT_LLM_PROVIDER=qwen  # claude / openai / qwen / zhipu / gemini
```

每个 provider 都有独立的 `*_BASE_URL` 配置项，直接替换为中转地址即可。

## 视频生成 Provider

视频生成同样支持多 Provider 切换，在环境变量中配置对应的 Key 即可：

| Provider | 说明 |
|----------|------|
| DashScope | 阿里云通义万象（默认） |
| 豆包 / 火山方舟 | 字节跳动 Ark 平台 |
| Kling | 快手可灵 AI |
