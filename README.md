# AutoMedia

一个面向 AI 短剧创作与视频生产的本地项目。  
从一句灵感开始，逐步完成世界观构建、角色与大纲生成、剧本流式输出、视觉素材生成，以及后续的分镜、配音、图生视频与成片拼接。

## 项目亮点

- Step 1 灵感阶段支持：
  - 故事题材约束
  - `组合灵感生成器`
  - `AI 定向改写`
- Step 2 世界观阶段支持：
  - 6 轮世界观问答
  - 完成后手动进入剧本生成
  - 重新构建世界观
- Step 3 剧本阶段支持：
  - 自定义集数
  - 流式剧本生成
  - 剧本中断后继续生成
  - `视觉风格` 设置与 AI 整理风格描述
  - 角色关系图、角色设定图、场景参考图
- Step 4 支持预览与导出
- Video Generation 页支持：
  - 剧本转分镜
  - TTS
  - 图片生成
  - 图生视频
  - 过渡视频
  - FFmpeg 拼接

## 当前工作流

```text
Step 1 灵感输入
  -> 组合灵感生成器
  -> AI 定向改写
  -> 故事题材同步到主流程

Step 2 世界观构建
  -> 6 轮问答
  -> 生成完整 world summary
  -> 手动前往剧本生成

Step 3 剧本生成
  -> 用户先确认集数
  -> 生成或重建大纲
  -> 流式生成剧本
  -> 角色图 / 场景参考图 / 视觉风格辅助

Step 4 预览导出
  -> 按所选内容导出

Video Generation
  -> 分镜解析
  -> TTS / 图片 / 视频 / 过渡视频 / 拼接
```

## 技术栈

- 前端：Vue 3 + Vue Router + Pinia + Vite
- 后端：FastAPI + SQLAlchemy Async + SQLite
- 语音：Edge TTS
- 图片：SiliconFlow / 豆包图片接口
- 视频：DashScope / Kling / MiniMax / 豆包
- 媒体处理：FFmpeg / FFprobe

## 快速开始

### 环境要求

- Python 3.12+
- Node.js 20+
- `uv`
- `npm`
- FFmpeg / FFprobe

### 1. 配置环境变量

```bash
cp .env.example .env
```

最少只需要准备你会用到的那组 API Key，不需要一次配满所有服务商。

### 2. 一键启动

```bash
python3 start.py
```

`start.py` 会做几件事：

- 检查 `ffmpeg` / `ffprobe`
- 必要时尝试协助安装 FFmpeg
- 安装前端依赖
- 启动后端和前端开发服务

默认地址：

- 前端：`http://localhost:5173`
- 后端：`http://localhost:8000`

### 3. 手动启动

如果你希望前后端分开跑，可以这样启动：

```bash
# 安装 Python 依赖
uv sync

# 安装前端依赖
npm --prefix frontend install

# 启动后端
uv run uvicorn app.main:app --reload --reload-dir app

# 启动前端
npm --prefix frontend run dev
```

## 环境变量说明

示例配置见 [`.env.example`](./.env.example)。

常用分组如下：

- 文本生成：Claude / OpenAI / Qwen / 智谱 / Gemini / SiliconFlow
- 图片生成：SiliconFlow / 豆包
- 视频生成：DashScope / Kling / MiniMax / 豆包
- FFmpeg 路径：`FFMPEG_PATH` / `FFPROBE_PATH`

说明：

- 前端设置页里填写的配置优先级高于 `.env`
- 浏览器端没有填写时，后端会回退到 `.env`
- 图片和视频 provider 可以分别配置
- 豆包图片和豆包视频建议使用独立 Key

## 目录结构

```text
auto_media/
├── app/
│   ├── core/                # 配置、数据库、上下文与运行时规则
│   ├── models/              # SQLAlchemy 模型
│   ├── prompts/             # 各阶段提示词
│   ├── routers/             # FastAPI 路由
│   ├── schemas/             # Pydantic 请求/响应结构
│   └── services/            # 业务服务层
├── frontend/
│   ├── src/components/      # UI 组件
│   ├── src/views/           # 主要页面
│   ├── src/stores/          # Pinia 状态
│   ├── src/api/             # 前端 API 封装
│   └── src/utils/           # 前端工具函数
├── docs/                    # 过程文档与专题说明
├── media/                   # 本地生成媒体目录（默认不提交）
├── tests/                   # 回归测试
├── .env.example
├── pyproject.toml
├── start.py
└── README.md
```

## 重要页面说明

- [Step1Inspire.vue](./frontend/src/views/Step1Inspire.vue)
  - 灵感输入、故事题材约束、AI 改写、组合灵感生成器
- [Step2Settings.vue](./frontend/src/views/Step2Settings.vue)
  - 6 轮世界观问答、完成后前往剧本生成、重新构建世界观
- [Step3Script.vue](./frontend/src/views/Step3Script.vue)
  - 集数确认、流式剧本、继续生成、视觉风格、角色图与大纲联动
- [VideoGeneration.vue](./frontend/src/views/VideoGeneration.vue)
  - 分镜与素材生成、视频流水线
- [story.py](./app/routers/story.py)
  - 故事主流程 API
- [pipeline.py](./app/routers/pipeline.py)
  - 分镜和视频流水线 API

## 当前项目状态

当前仓库更适合：

- 本地开发
- 产品验证
- 个人或小团队协作

当前已经可用，但也有几个边界需要提前知道：

- 多服务商配置较多，第一次接入需要自己准备 API Key
- 视频生成速度和稳定性高度依赖外部 provider
- 豆包、DashScope、Kling、MiniMax 这类视频接口若账户欠费或配额不足，会直接在任务提交阶段失败
- 媒体资产默认保存到本地 `media/` 目录，不是对象存储方案
- 独立“资料库”能力目前还在规划中，仓库现阶段还没有完整落地

## 验证命令

后端语法检查：

```bash
PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile app/main.py
```

前端构建：

```bash
npm --prefix frontend run build
```

测试：

```bash
UV_CACHE_DIR=/tmp/uv-cache PYTHONPYCACHEPREFIX=/tmp/pycache uv run python -m unittest discover -s tests -q
```

## 文档导航

如果你想继续开发，建议优先看这些文档：

- [功能文档](./docs/feature-documentation.md)
- [视频生成与视觉一致性统一文档](./docs/video-pipeline.md)
- [Prompt Framework](./docs/prompt-framework.md)
- [数据库持久化实现现状](./docs/database-persistence-implementation.md)
- [画风链路说明](./docs/art-style-backend.md)
- [API Key 管理指南](./docs/api-key-management.md)
- [端到端一致性实施方案](./docs/END_TO_END_CONSISTENCY_IMPLEMENTATION_PLAN.md)

## 开源发布前建议

提交到 GitHub 前，建议确认下面几项：

- `.env` 没有被提交
- 本地数据库 `automedia.db` 没有被提交
- `media/` 下生成的图片、音频、视频没有被提交
- 浏览器本地保存的 API Key 仅留在本机，不会进仓库
- README 与当前功能口径一致

当前仓库默认已经忽略本地数据库、媒体产物、缓存目录和虚拟环境。
