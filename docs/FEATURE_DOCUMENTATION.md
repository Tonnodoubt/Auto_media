# AutoMedia AI 短剧项目 - 功能文档

> 更新日期：2026-03-24 | 项目状态：MVP 完成，视频合成全链路可用

---

## 一、项目概览

| 项目信息 | 详情 |
|---------|------|
| **项目名称** | AutoMedia - AI 短剧自动生成系统 |
| **技术栈** | Vue 3 (前端) + FastAPI (后端) + SQLite (SQLAlchemy 异步) |
| **架构模式** | BFF (Backend for Frontend) |
| **核心目标** | 通过 AI 自动化完成短剧从灵感到视频的全流程生成 |

### 核心流程

| Step | 阶段 | 功能 |
|------|------|------|
| Step 1 | 灵感输入 | 灵感捕获 + 风格选择 |
| Step 2 | 世界构建 | 6 轮引导式问答 |
| Step 3 | 剧本生成 | 大纲 + 流式剧本 + AI 修改 |
| Video | 视频生成 | 分镜 → TTS → 图片 → 视频 → 合成 |
| Step 4 | 导出预览 | 分镜预览 + 导出 |

---

## 二、功能实现状态

### 2.1 核心架构

| 模块 | 状态 | 备注 |
|------|------|------|
| 前端架构 (Vue 3 + Pinia) | ✅ | 响应式状态管理，路由守卫完善 |
| 后端架构 (FastAPI + 异步) | ✅ | BackgroundTasks 异步任务 |
| 多模型网关 | ✅ | 支持 5 个 LLM 提供商 |
| JSON 契约 (Schema) | ✅ | story.py 定义完整数据结构 |
| 数据库持久化 (SQLAlchemy + SQLite) | ✅ | Story / Pipeline 模型，异步 ORM |
| API Key 统一管理 | ✅ | 统一走 HTTP Header，支持双 Key 回退链 |
| Celery 任务队列 | ⏳ | 计划中，当前用 BackgroundTasks |

### 2.2 四阶段功能

#### 阶段 1：灵感捕获 (Step 1)

| 功能 | 状态 | 组件 / API |
|------|------|------------|
| 灵感输入 | ✅ | Step1Inspire.vue |
| 风格标签选择 | ✅ | StyleSelector.vue |
| 灵感盲盒 🎲 | ✅ | IdeaGenerator.vue（6 维度随机） |
| 引导式追问 | ✅ | FollowUpOptions.vue |
| 6 轮世界构建问答 | ✅ | `/world-building/start` + `/world-building/turn` |
| 要素分析 | ✅ | `/analyze-idea` |

#### 阶段 2：剧本生成 (Step 2–3)

| 功能 | 状态 | 组件 / API |
|------|------|------------|
| 大纲生成 | ✅ | `/generate-outline` |
| 角色生成 + 关系图 | ✅ | CharacterGraph.vue（SVG 动画） |
| 大纲预览 / 修改 | ✅ | OutlinePreview.vue |
| AI 修改助手 (SSE) | ✅ | OutlineChatPanel.vue + `/chat` |
| 章节专属 AI 对话 | ✅ | EpisodeChatPanel.vue |
| 角色专属 AI 对话 | ✅ | CharacterChatPanel.vue |
| 流式剧本生成 | ✅ | `/generate-script`（SSE） |
| 结构化 JSON 输出 | ✅ | ScriptScene Schema |

#### 阶段 3：视觉资产

| 功能 | 状态 | 备注 |
|------|------|------|
| 角色形象设计 UI | ✅ | CharacterDesign.vue，已对接后端 |
| 角色图像生成 (FLUX.1) | ✅ | `/api/v1/character/generate` + generate-all |
| 角色图像存储（数据库） | ✅ | 存入 `story.character_images` 字段 |
| 特征提取 → Prompt | ✅ | 后端自动构建 visual_prompt |
| 场景图像生成 (FLUX.1-schnell) | ✅ | 1280×720，SiliconFlow API |
| **人物一致性** | ⏳ | 需要 LoRA / IP-Adapter；平替：physical_description 注入 |

#### 阶段 4：预览导出 (Step 4)

| 功能 | 状态 | 组件 / API |
|------|------|------------|
| 视觉分镜预览 | ✅ | SceneStream.vue |
| JSON / Markdown 导出 | ✅ | ExportPanel.vue |
| 完整视频导出 | ✅ | 前端导出按钮，调用 `/concat` 拼接后下载 |

### 2.3 视频流水线

| 功能 | 状态 | 备注 |
|------|------|------|
| 分镜解析（LLM，升级版） | ✅ | storyboard.py，支持所有 provider，含镜头语言增强 |
| TTS 语音（Edge TTS） | ✅ | 18+ 中文语音，生成 MP3 |
| 场景图片生成（FLUX.1） | ✅ | 1280×720，异步批处理 |
| 图生视频（Wan2.6-i2v） | ✅ | DashScope 异步任务轮询，下载 MP4 |
| FFmpeg 音视频合成（auto-generate） | ✅ | `_stitch_videos()` → `ffmpeg.stitch_batch()` 真实实现 |
| FFmpeg 视频拼接（/concat） | ✅ | stream copy 不重编码，速度快 |
| 手动步进 `/stitch` | ⚠️ | 仍为 `asyncio.sleep(2)` 占位，建议改用 `/concat` |
| INTEGRATED 策略 | 🔶 | 代码框架已有，实际仍复用 image-to-video API，未对接真正的视频语音一体 API |
| 一键自动生成 | ✅ | `/{id}/auto-generate`，后台执行全流程 |
| 实时进度（轮询） | ✅ | `/{id}/status`，数据库持久化状态 |
| 任务持久化（数据库） | ✅ | Pipeline 状态写入 SQLite，重启不丢失 |
| 双策略支持 | ✅ | SEPARATED / INTEGRATED |
| 断点续传 | ⏳ | 未实现 |

### 2.4 数据持久化

| 数据 | 模型 | 状态 |
|------|------|------|
| 故事 / 剧本 | `Story` (SQLAlchemy) | ✅ |
| 流水线状态 | `Pipeline` (SQLAlchemy) | ✅ |
| 角色图像 URL | `story.character_images`（JSON 字段） | ✅ |
| 旧 Project 模型 | `Project` | ⚠️ 遗留，与现有流程脱节，待清理 |

---

## 三、前端详情

### 3.1 页面路由

| 页面 | 路由 | 状态 | 核心功能 |
|------|------|------|----------|
| Step 1 灵感输入 | /step1 | ✅ | 灵感输入 + 盲盒 + 风格选择 |
| Step 2 世界构建 | /step2 | ✅ | 6 轮引导式问答 |
| Step 3 剧本生成 | /step3 | ✅ | 大纲 + 关系图 + 流式剧本 + AI 修改 |
| Step 4 预览导出 | /step4 | ✅ | 场景预览 + 导出 |
| 视频生成 | /video-generation | ✅ | 分镜 + TTS / 图 / 视频生成 |
| 设置页 | /settings | ✅ | 全局 + 文本/图片/视频专用 API 配置（开关切换） |

### 3.2 组件清单

| 组件 | 功能 | 状态 |
|------|------|------|
| StepIndicator | 步骤进度指示 | ✅ |
| ApiKeyModal | API Key 提示弹窗 | ✅ |
| IdeaGenerator | 灵感盲盒生成器 | ✅ |
| OutlinePreview | 大纲预览 | ✅ |
| CharacterGraph | 角色关系图（SVG） | ✅ |
| CharacterDesign | 角色设计 + 图像生成 | ✅ |
| SceneStream | 场景流式展示 | ✅ |
| OutlineChatPanel | AI 大纲修改面板 | ✅ |
| EpisodeChatPanel | 章节专属 AI 对话 | ✅ |
| CharacterChatPanel | 角色专属 AI 对话 | ✅ |
| ExportPanel | 导出按钮 | ✅ |
| StyleSelector | 风格选择器 | ✅ |
| FollowUpOptions | 追问选项 | ✅ |

### 3.3 API Key 管理（前端）

前端采用**全局 + 专用（可开关）**三层配置体系，存储于 `settings` store（localStorage）：

**全局配置（必填）：**

| 字段 | 作用 |
|------|------|
| `provider` | 全局服务商选择 |
| `apiKey` | 全局 API Key（所有未开专用的服务均使用此 Key） |
| `llmBaseUrl` | 全局 Base URL |

**专用配置（开关控制，关闭时继承全局）：**

| 开关 | 字段 | 作用 |
|------|------|------|
| `textEnabled` | `textProvider` / `textApiKey` / `textBaseUrl` / `textModel` | 文本/LLM 专用 |
| `imageEnabled` | `imageApiKey` / `imageBaseUrl` / `imageModel` | 图片生成专用 |
| `videoEnabled` | `videoApiKey` / `videoBaseUrl` / `videoModel` | 视频生成专用 |

**有效值 Getter（实际使用）：**

| Getter | 逻辑 |
|--------|------|
| `effectiveLlmApiKey` | `textEnabled && textApiKey` ? textApiKey : apiKey |
| `effectiveLlmProvider` | `textEnabled && textProvider` ? textProvider : provider |
| `effectiveLlmBaseUrl` | `textEnabled && textBaseUrl` ? textBaseUrl : llmBaseUrl |
| `effectiveImageApiKey` | `imageEnabled && imageApiKey` ? imageApiKey : apiKey |
| `effectiveImageBaseUrl` | `imageEnabled && imageBaseUrl` ? imageBaseUrl : llmBaseUrl |
| `effectiveImageModel` | imageEnabled ? imageModel : '' |
| `effectiveVideoApiKey` | `videoEnabled && videoApiKey` ? videoApiKey : apiKey |
| `effectiveVideoBaseUrl` | `videoEnabled && videoBaseUrl` ? videoBaseUrl : llmBaseUrl |
| `effectiveVideoModel` | videoEnabled ? videoModel : '' |

所有 HTTP 请求通过 `story.js` 的 `getHeaders()` 统一注入对应的 effective 值。

### 3.4 请求头规范

| Header | 对应值 |
|--------|--------|
| `X-LLM-API-Key` | effectiveLlmApiKey |
| `X-LLM-Base-URL` | effectiveLlmBaseUrl |
| `X-LLM-Provider` | effectiveLlmProvider |
| `X-Image-API-Key` | effectiveImageApiKey |
| `X-Image-Base-URL` | effectiveImageBaseUrl |
| `X-Video-API-Key` | effectiveVideoApiKey |
| `X-Video-Base-URL` | effectiveVideoBaseUrl |

---

## 四、后端详情

### 4.1 API 端点

#### Story API (`/api/v1/story`)

| 端点 | 方法 | 状态 |
|------|------|------|
| /analyze-idea | POST | ✅ |
| /generate-outline | POST SSE | ✅ 流式输出（防 ReadError） |
| /generate-script | POST SSE | ✅ |
| /chat | POST SSE | ✅ |
| /refine | POST | ✅ 保留原有 meta 字段 |
| /patch | POST | ✅ |
| /apply-chat | POST | ✅ |
| /world-building/start | POST | ✅ |
| /world-building/turn | POST | ✅ |
| /{story_id}/finalize | POST | ✅ |

#### Pipeline API (`/api/v1/pipeline`)

| 端点 | 方法 | 状态 | 模式 |
|------|------|------|------|
| /{id}/auto-generate | POST | ✅ | 自动：后台全流程，DB 持久化状态 |
| /{id}/storyboard | POST | ✅ | 手动步进：分镜解析（升级版） |
| /{id}/generate-assets | POST | ✅ | 手动步进：TTS + 图片，内存状态 |
| /{id}/render-video | POST | ✅ | 手动步进：图生视频，内存状态 |
| /{id}/concat | POST | ✅ | 多镜头视频拼接（真实 FFmpeg，stream copy） |
| /{id}/stitch | POST | ⚠️ | 手动步进：FFmpeg 占位（asyncio.sleep），建议改用 /concat |
| /{id}/status | GET | ✅ | 自动模式状态查询（DB） |

> **注意**：`generate-assets`、`render-video` 为手动步进端点，使用进程内存状态（重启丢失）。自动模式 `auto-generate` 使用数据库持久化状态。

#### Character API (`/api/v1/character`)

| 端点 | 方法 | 状态 |
|------|------|------|
| /generate | POST | ✅ |
| /generate-all | POST | ✅ |
| /{story_id}/images | GET | ✅ |

#### TTS / Image / Video API

| 端点 | 方法 | 状态 |
|------|------|------|
| /api/v1/tts/voices | GET | ✅ |
| /api/v1/tts/{id}/generate | POST | ✅ |
| /api/v1/image/{id}/generate | POST | ✅ |
| /api/v1/video/{id}/generate | POST | ✅ |

#### Projects API (`/api/v1/projects`) — 遗留

| 端点 | 方法 | 状态 |
|------|------|------|
| /init | POST | ⚠️ Mock，返回硬编码模板 |
| /{id}/chat | POST | ⚠️ Mock |
| /{id}/script | GET | ⚠️ Mock |

### 4.2 API Key 管理（后端）

| 模块 | 来源 | 状态 |
|------|------|------|
| `app/core/api_keys.py` | — | ✅ 统一提取、校验、脱敏模块 |
| LLM Key | Header `X-LLM-API-Key` → 回退 `.env` 各 provider key | ✅ |
| Image Key | Header `X-Image-API-Key` → 回退 `.env` `SILICONFLOW_API_KEY` | ✅ |
| Image Base URL | Header `X-Image-Base-URL` → 回退 `.env` `SILICONFLOW_BASE_URL` | ✅ |
| Video Key | Header `X-Video-API-Key` → 回退 `.env` `DASHSCOPE_API_KEY` | ✅ |
| Video Base URL | Header `X-Video-Base-URL` → 回退 `.env` `DASHSCOPE_BASE_URL` | ✅ |
| Key 脱敏（日志） | `mask_key()` — 仅显示首4尾4位 | ✅ |
| Key 缺失时行为 | 返回 HTTP 400，不发起外部请求 | ✅ |
| Query Param 传 Key | 已清除 | ✅ |

### 4.3 LLM 集成

| 提供商 | 状态 | 模型 | 接入方式 |
|--------|------|------|----------|
| Anthropic Claude | ✅ | claude-sonnet-4-6 / claude-opus-4-6 / claude-haiku-4-5 | 原生 SDK |
| OpenAI | ✅ | gpt-4o / gpt-4o-mini / gpt-4-turbo | 原生 SDK |
| 阿里通义千问 | ✅ | qwen-plus / qwen-max / qwen-turbo | OpenAI 兼容 |
| 智谱 GLM | ✅ | glm-4 / glm-4-flash / glm-3-turbo | OpenAI 兼容 |
| Google Gemini | ✅ | gemini-2.0-flash / gemini-2.0-pro | OpenAI 兼容 |
| Kimi / 月之暗面 | ⏳ | — | 可快速接入 |

所有 Provider 均支持 `api_key or settings.xxx_api_key` 回退逻辑（`factory.py`）。

### 4.4 数据契约（JSON Schema）

| 结构 | 字段 |
|------|------|
| story_id | 唯一标识 |
| meta | title, logline, genre, theme |
| characters | id, name, role, personality, visual_prompt |
| relationships | source, target, label |
| outline | act, title, description |
| scenes | scene_id, setting, visual_prompt, actions, dialogues |
| character_images | {character_name: {image_url, image_path, prompt}} |

---

## 五、技术风险

| 风险项 | 级别 | 现状 |
|--------|------|------|
| 手动 `/stitch` 仍为 Mock | 🟠 中 | `asyncio.sleep(2)` 占位，前端应改用 `/concat` |
| 人物一致性 | 🔴 高 | 各 shot 独立生成图片，人物外观不一致 |
| INTEGRATED 策略未完成 | 🟠 中 | 代码框架有，实际复用 image-to-video API，未对接真正的视频语音一体 API |
| 手动步进内存状态 | 🟠 中 | generate-assets / render-video 用进程内存，重启后丢失 |
| SSE 并发限制 | 🟡 中 | Chrome HTTP/1.1 同域 6 连接上限 |
| Projects 模型遗留 | 🟡 中 | 旧 interview 模式，与现有流程脱节 |
| 无断点续传 | 🟡 中 | 视频流水线失败须重跑全流程 |
| 前端 Key 存 localStorage | 🟡 中 | 明文，XSS 可读取；sessionStorage 为更安全选项 |

---

## 六、TODO 清单

### ✅ 已完成（原 P0）

- [x] **FFmpeg 音视频合成** — `ffmpeg.stitch_batch()` + `/concat` 端点已实现
- [x] **前端视频导出** — VideoGeneration 页面支持直接下载最终视频
- [x] **分镜引擎升级** — 新版 storyboard 含镜头语言增强，提升视频生成质量
- [x] **`generate-outline` SSE 流式** — 防止长响应触发 ReadError

### 🟠 P1 — 重要，影响用户体验

- [ ] **修复手动 `/stitch` 占位**
  - `pipeline.py` `stitch_video()` 仍为 `asyncio.sleep(2)` + TODO
  - 接入 `ffmpeg.stitch_batch()` 或统一引导前端改用 `/concat`

- [ ] **INTEGRATED 策略完成**
  - `pipeline_executor.py` INTEGRATED 分支目前复用 image-to-video API
  - 需对接真正的视频语音一体生成 API

- [ ] **断点续传**
  - 长任务失败后可从失败步骤恢复，而非重新执行全流程

- [ ] **WebSocket / SSE 实时进度推送**
  - 当前 `/status` 接口为轮询模式
  - 改为 WebSocket 或 SSE 主动推送，减少轮询开销

- [ ] **前端 Key 改用 sessionStorage**
  - `settings.js` 中所有 API Key 从 `localStorage` 改为 `sessionStorage`
  - Tab 关闭即清除，缩小 XSS 暴露窗口

### 🟡 P2 — 优化

- [ ] **发布前：开启 DNS-based SSRF 防护**
  - `app/core/api_keys.py` 的 `validate_user_base_url()` 已实现 DNS 解析 + 内网 IP 拦截
  - 开发环境默认关闭（境外域名在国内可能无法解析）
  - 正式部署时在 `.env` 中加入 `VALIDATE_BASE_URL_DNS=true`

- [ ] **发布前：移除 Mock 模式**
  - `app/services/story_llm.py` 中各函数在 `api_key` 为空时直接 fallback 到 `mock_*` 函数（`analyze_idea`、`generate_outline`、`generate_script`、`chat`、`refine`、`world_building_start`、`world_building_turn`）
  - `app/services/story_mock.py` 整个文件及 `mock_world_building_start` / `mock_world_building_turn` 等函数均需删除或加守卫
  - 建议：正式发布时将 fallback 改为直接抛出 400，强制要求用户填写 API Key

- [ ] **清理 Projects 遗留模块**
  - `app/routers/projects.py` 返回硬编码 Mock 数据，`Project` 模型与 Story+Pipeline 流程脱节

- [ ] **人物一致性方案**
  - 方案 A：LoRA / IP-Adapter（高成本）
  - 方案 B：在每个 shot 的 `visual_prompt` 中强制注入 `physical_description` 字段（低成本平替）

- [ ] **降级兜底**
  - TTS / 图片 / 视频任一步骤失败时，提供占位内容而非整体中断
  - 视频生成超时（>300s）时给出友好提示

- [ ] **移动端适配**
  - 响应式 CSS 媒体查询改造
  - 按钮最小 44×44px，支持滑动手势

- [ ] **陪伴式等待 UI**
  - 长时间生成中展示动态进度说明

- [ ] **图片/视频 API Key 智能继承全局配置**
  - 当前：未启用专用配置时图片/视频 key 和 base URL 均返回空，后端读 `.env` 默认值
  - 问题：若用户全局配的是 OpenAI / SiliconFlow 这类同时支持 LLM + 图片生成的统一供应商，应当能继承全局 key 和 base URL（同根不同枝）
  - 方案：在 `settings.js` 中维护 `IMAGE_CAPABLE_PROVIDERS`（如 `siliconflow`、`openai`、`custom`），仅当全局 provider 在此列表中时才 fallback 到 `state.apiKey` / `state.llmBaseUrl`；Claude 等 LLM 专用供应商不继承

### 🟢 P3 — 长期规划

- [ ] **Celery 任务队列**
  - 替换 BackgroundTasks，支持生产级并发任务管理、任务重试、优先级队列

- [ ] **HTTP/2 支持**
  - 解决 Chrome HTTP/1.1 同域 6 连接 SSE 并发限制

- [ ] **双模式切换（普通 / 专业）**
  - 当前 MVP 冻结，待核心功能稳定后实现

---

*文档更新于 2026-03-24，基于项目代码实际分析*
