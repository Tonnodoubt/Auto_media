# AutoMedia 功能文档

> 更新日期：2026-03-25
>
> 当前状态：MVP 可用，故事生成、角色设计、视频流水线、历史恢复与画风设定均已接通。

---

## 一、项目概览

| 项目项 | 说明 |
|------|------|
| 项目名称 | AutoMedia |
| 技术栈 | Vue 3 + Pinia + FastAPI + SQLAlchemy Async + SQLite |
| 核心目标 | 让用户从“一个故事创意”走到“可预览、可下载的视频素材” |
| 当前架构 | 前后端分离，FastAPI 作为 BFF / 任务编排后端 |

### 主流程

| 阶段 | 页面 / 模块 | 当前能力 |
|------|------|------|
| Step 1 | 灵感输入 | 创意输入、要素分析 |
| Step 2 | 世界构建 | 6 轮引导式问答，产出 `selected_setting` |
| Step 3 | 剧本生成 | 大纲、角色关系、流式剧本、角色设计图、画风设定 |
| Step 4 | 预览导出 | 剧本预览、导出 JSON / Markdown |
| Video | 视频生成 | 分镜解析、TTS、图片、视频、拼接、下载 |
| History | 历史剧本 | 加载、恢复、删除、直接进入分镜 |

---

## 二、当前功能状态

### 2.1 核心架构

| 模块 | 状态 | 说明 |
|------|------|------|
| Vue 3 + Pinia 前端 | ✅ | 路由、状态恢复、历史加载均可用 |
| FastAPI 后端 | ✅ | Story / Pipeline / Asset API 完整 |
| SQLAlchemy + SQLite | ✅ | Story / Pipeline 持久化 |
| API Key 统一管理 | ✅ | Header 优先，回退 `.env` |
| 多 LLM provider | ✅ | Claude / OpenAI / SiliconFlow / Qwen / Zhipu / Gemini |
| 图片 provider | ✅ | SiliconFlow / 豆包 |
| 视频 provider | ✅ | DashScope / Kling / 豆包 |
| BackgroundTasks 任务执行 | ✅ | 自动流水线可用 |
| Celery / 外部任务队列 | ⏳ | 未接入 |

### 2.2 故事创作链路

| 功能 | 状态 | 说明 |
|------|------|------|
| 灵感分析 | ✅ | `/api/v1/story/analyze-idea` |
| 世界观构建 | ✅ | `/world-building/start` + `/world-building/turn` |
| 大纲生成 | ✅ | `/generate-outline` |
| 角色关系图 | ✅ | `CharacterGraph.vue` |
| 流式剧本生成 | ✅ | `/generate-script`，SSE |
| AI 修改助手 | ✅ | `/chat` + `/refine` + `/apply-chat` |
| 历史剧本恢复 | ✅ | `HistoryView.vue` + `store.loadStory()` |
| 剧本序列化到视频阶段 | ✅ | `/story/{story_id}/finalize` |

### 2.3 视觉与资产链路

| 功能 | 状态 | 说明 |
|------|------|------|
| 角色设计图生成 | ✅ | `/api/v1/character/generate` / `generate-all` |
| 角色图片持久化 | ✅ | 存入 `story.character_images` |
| 画风设定 UI | ✅ | `ArtStyleSelector.vue` |
| 画风设定持久化 | ✅ | `stories.art_style` + `X-Art-Style` Header |
| 手动场景图片生成 | ✅ | `/api/v1/image/{project_id}/generate` |
| 手动视频生成 | ✅ | `/api/v1/video/{project_id}/generate` |
| 语音生成 | ✅ | `/api/v1/tts/{project_id}/generate` |
| 图片首尾帧 / 过渡辅助字段 | 🔶 | schema 与部分服务链路已支持相关字段，但主要是专项增强能力，不是默认全 provider 主路径 |
| 完整视觉一致性引擎 | ⏳ | 设计已完成，代码尚未完整落地 |

### 2.4 视频流水线

| 功能 | 状态 | 说明 |
|------|------|------|
| 分镜解析 | ✅ | `storyboard.py`，多 provider |
| 自动全流程生成 | ✅ | `/pipeline/{project_id}/auto-generate` |
| 手动分镜解析 | ✅ | `/pipeline/{project_id}/storyboard` |
| 手动生成 TTS + 图片 | ✅ | `/pipeline/{project_id}/generate-assets` |
| 手动视频渲染 | ✅ | `/pipeline/{project_id}/render-video` |
| 进度查询 | ✅ | `/pipeline/{project_id}/status` |
| 视频拼接 | ✅ | `/pipeline/{project_id}/concat` |
| 单镜头音视频合成 | 🔶 | `/pipeline/{project_id}/stitch` 接口已存在，但当前仍是占位模拟实现 |
| `separated` 策略 | ✅ | 全链路可用 |
| `chained` 策略 | ✅ | 场景内末帧传递，增强连续性 |
| `integrated` 策略 | 🔶 | 接口存在，但底层仍复用图生视频链路 |

---

## 三、前端现状

### 3.1 页面

| 页面 | 路由 | 状态 | 说明 |
|------|------|------|------|
| 灵感输入 | `/step1` | ✅ | 创意输入与分析 |
| 世界构建 | `/step2` | ✅ | 6 轮问答 |
| 剧本生成 | `/step3` | ✅ | 大纲、关系图、角色设计、画风设定 |
| 预览导出 | `/step4` | ✅ | SceneStream + ExportPanel |
| 视频生成 | `/video-generation` | ✅ | 手动 / 自动视频流水线入口 |
| 设置页 | `/settings` | ✅ | LLM / 图片 / 视频配置 |
| 历史剧本 | `/history` | ✅ | 恢复、删除、直接分镜 |

### 3.2 关键组件

| 组件 | 状态 | 说明 |
|------|------|------|
| `CharacterDesign.vue` | ✅ | 角色图像生成与展示 |
| `ArtStyleSelector.vue` | ✅ | 画风设定、持久化、错误回滚 |
| `CharacterGraph.vue` | ✅ | 角色关系展示 |
| `SceneStream.vue` | ✅ | 剧本场景流展示 |
| `ExportPanel.vue` | ✅ | 导出 JSON / 文本 |
| `ApiKeyModal.vue` | ✅ | API Key 缺失 / 无效提示 |

### 3.3 设置体系

当前前端设置页支持：

- 全局 LLM 配置
- 分镜专用 Script LLM 配置
- 图片 provider / model / key / base URL
- 视频 provider / model / key / base URL

用户侧可选 provider 现状：

| 类型 | Provider |
|------|------|
| LLM | Claude / OpenAI / SiliconFlow / Qwen / Zhipu / Gemini / Custom |
| 图片 | SiliconFlow / 豆包 / Custom |
| 视频 | DashScope / Kling / 豆包 / Custom |

说明：

- 前端设置中虽然保留了部分实验性 provider 配置项，但当前文档只记录已完整接通的主路径
- 请求 Header 统一由 `frontend/src/api/story.js` 的 `getHeaders()` 构建
- `X-Art-Style` 已在手动 / 自动视频链路中贯通

---

## 四、后端现状

### 4.1 Story API

| 端点 | 方法 | 状态 | 说明 |
|------|------|------|------|
| `/api/v1/story/` | `GET` | ✅ | 历史故事列表 |
| `/api/v1/story/{story_id}` | `GET` | ✅ | 获取完整 Story |
| `/api/v1/story/{story_id}` | `DELETE` | ✅ | 删除 Story |
| `/api/v1/story/analyze-idea` | `POST` | ✅ | 创意分析 |
| `/api/v1/story/generate-outline` | `POST` | ✅ | 生成大纲 |
| `/api/v1/story/generate-script` | `POST` | ✅ | SSE 剧本生成 |
| `/api/v1/story/chat` | `POST` | ✅ | SSE 对话修改 |
| `/api/v1/story/refine` | `POST` | ✅ | 结构化修改 |
| `/api/v1/story/patch` | `POST` | ✅ | 局部持久化，含 `art_style` |
| `/api/v1/story/apply-chat` | `POST` | ✅ | 应用聊天修改 |
| `/api/v1/story/world-building/start` | `POST` | ✅ | 开始世界构建 |
| `/api/v1/story/world-building/turn` | `POST` | ✅ | 世界构建追问 |
| `/api/v1/story/{story_id}/finalize` | `POST` | ✅ | 导出第二阶段剧本文本 |

### 4.2 Pipeline API

| 端点 | 方法 | 状态 | 说明 |
|------|------|------|------|
| `/api/v1/pipeline/{project_id}/auto-generate` | `POST` | ✅ | 自动全流程 |
| `/api/v1/pipeline/{project_id}/storyboard` | `POST` | ✅ | 手动分镜解析 |
| `/api/v1/pipeline/{project_id}/generate-assets` | `POST` | ✅ | 手动 TTS + 图片 |
| `/api/v1/pipeline/{project_id}/render-video` | `POST` | ✅ | 手动视频生成 |
| `/api/v1/pipeline/{project_id}/status` | `GET` | ✅ | 查询状态 |
| `/api/v1/pipeline/{project_id}/concat` | `POST` | ✅ | 多视频拼接 |
| `/api/v1/pipeline/{project_id}/stitch` | `POST` | 🔶 | 接口已保留，当前仍为占位模拟实现 |

说明：

- 自动模式状态写入数据库
- 手动步进模式的状态仍主要保存在进程内内存中

### 4.3 Asset API

| 端点 | 方法 | 状态 |
|------|------|------|
| `/api/v1/character/generate` | `POST` | ✅ |
| `/api/v1/character/generate-all` | `POST` | ✅ |
| `/api/v1/character/{story_id}/images` | `GET` | ✅ |
| `/api/v1/image/{project_id}/generate` | `POST` | ✅ |
| `/api/v1/video/{project_id}/generate` | `POST` | ✅ |
| `/api/v1/tts/voices` | `GET` | ✅ |
| `/api/v1/tts/{project_id}/generate` | `POST` | ✅ |

### 4.4 数据模型

| 模型 | 状态 | 说明 |
|------|------|------|
| `Story` | ✅ | 包含 `selected_setting`、`meta`、`characters`、`character_images`、`art_style` |
| `Pipeline` | ✅ | 保存自动流水线状态、进度与产物 |
| `Project` | ⚠️ | 遗留模块，仍保留但不属于主流程核心 |

当前 Story 相关关键字段：

| 字段 | 含义 |
|------|------|
| `selected_setting` | 世界观问答完成后的总结 |
| `meta` | 标题、主题等元数据 |
| `character_images` | 角色图像与 prompt 信息 |
| `art_style` | 画风设定 |

---

## 五、关键实现说明

### 5.1 画风设定

当前画风链路已打通：

- 前端 `ArtStyleSelector.vue` 负责确认式修改
- `story.patch` 持久化到 `stories.art_style`
- 请求 Header 通过 `X-Art-Style` 透传
- 手动图片 / 手动视频 / 自动流水线均可消费 `art_style`

相关设计说明见：

- [art-style-backend.md](./art-style-backend.md)

### 5.2 角色设计图

角色设计图已支持：

- 单角色生成
- 批量生成
- 保存到 `story.character_images`
- 历史剧本恢复时回显

### 5.3 视觉一致性引擎

当前仓库中：

- 画风透传已实现
- 角色 prompt 增强仍是运行期拼接方式
- 更完整的 `StoryContext` / Prompt Caching / 结构化外貌缓存方案尚未完全实现

设计文档见：

- [digital-asset-library-design.md](./digital-asset-library-design.md)

### 5.4 首尾帧 / 视频过渡

仓库内已经有针对豆包首尾帧能力的专项文档与探索实现，但该能力仍属于专项增强，不应在主功能文档中描述为“默认全 provider 已开启”。

当前更准确的口径是：

- `Shot` schema 与图片/视频服务层已经支持 `last_frame_prompt` / `last_frame_url` 等字段
- 豆包 provider 对双帧过渡支持最完整
- 其他 provider 对尾帧能力的支持程度不一致，部分链路会直接忽略相关参数

相关文档：

- [DOUBAO_FIRST_LAST_FRAME_DISCOVERY.md](./DOUBAO_FIRST_LAST_FRAME_DISCOVERY.md)
- [FIRST_LAST_FRAME_USAGE_GUIDE.md](./FIRST_LAST_FRAME_USAGE_GUIDE.md)

---

## 六、当前边界与风险

| 项目 | 级别 | 当前情况 |
|------|------|------|
| `integrated` 策略未真正一体化 | 中 | 仍复用图生视频链路 |
| 手动步进状态以内存保存 | 中 | 进程重启后丢失 |
| `/stitch` 仍为占位实现 | 中 | 接口存在，但尚未接入真实 FFmpeg 合成批处理 |
| 人物一致性仍非结构化缓存驱动 | 高 | `StoryContext` 方案尚未完全落地 |
| Prompt Caching 尚未接入 | 中 | 仅有设计文档 |
| 历史遗留 `projects` 模块 | 中 | 与主 Story / Pipeline 流程割裂 |
| 更强的断点续跑 | 中 | 尚未实现 |

---

## 七、推荐阅读顺序

如果你是新加入项目，建议按以下顺序阅读：

1. `README.md`
2. 本文档
3. [art-style-backend.md](./art-style-backend.md)
4. [digital-asset-library-design.md](./digital-asset-library-design.md)
5. `app/routers/` + `app/services/` 代码

---

## 八、后续重点 TODO

### P1

- [ ] 落地 `StoryContext` 一致性引擎
- [ ] 接入 Prompt Caching
- [ ] 完成真正的 `integrated` 视频语音一体策略
- [ ] 把手动步进状态从内存迁移到可恢复存储

### P2

- [ ] 清理 `projects` 遗留模块
- [ ] 优化多角色一致性
- [ ] 增强错误恢复与断点续跑
- [ ] 进一步完善首尾帧与过渡分镜能力

---

*本文档已根据当前仓库代码与现有设计文档同步更新。*
