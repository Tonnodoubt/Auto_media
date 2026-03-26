# AutoMedia 功能文档

> 更新日期：2026-03-26
>
> 当前口径：按仓库现有代码、路由挂载情况与测试结果同步，不把设计态能力写成已落地能力。

---

## 一、项目概览

| 项目项 | 说明 |
|------|------|
| 项目名称 | AutoMedia |
| 技术栈 | Vue 3 + Pinia + FastAPI + SQLAlchemy Async + SQLite |
| 核心目标 | 从故事创意生成可预览、可导出的分镜、素材与视频产物 |
| 当前架构 | 前后端分离，FastAPI 负责编排 Story / Pipeline / Asset 主链路 |

当前已验证的主链路：

1. 灵感分析
2. 世界构建 6 轮问答
3. 大纲与剧本生成
4. 角色设定图与画风持久化
5. 剧本导出为分镜可消费文本
6. 手动/自动视频流水线
7. 历史恢复与基于数据库的状态追踪

---

## 二、当前功能状态

### 2.1 主流程

| 阶段 | 页面 / 模块 | 当前能力 |
|------|------|------|
| Step 1 | 灵感输入 | 创意输入、要素审计、返回建议追问维度 |
| Step 2 | 世界构建 | 6 轮引导式问答，写入 `selected_setting` |
| Step 3 | 故事生成 | 大纲、角色、关系、对话式修改建议、流式剧本、结构化 refine、apply-chat |
| Step 3 扩展 | 角色与画风 | 角色三视图设定图、`art_style` 持久化 |
| Step 4 | 预览导出 | 剧本预览、导出 JSON / 文本、`/story/{story_id}/finalize` |
| Video | 视频生成 | 分镜、TTS、图片、图生视频、拼接、状态查询 |
| History | 历史恢复 | Story 恢复、进入分镜、延续手动 pipeline 上下文 |

### 2.2 后端能力

| 模块 | 状态 | 说明 |
|------|------|------|
| Story API | ✅ | 主链路完整 |
| Pipeline API | ✅ | 手动步进与自动全流程可用 |
| Character API | ✅ | 单角色 / 批量角色图可用 |
| TTS / Image / Video API | ✅ | 已接通 |
| Story / Pipeline 持久化 | ✅ | 当前状态真相源 |
| `StoryContext` 主链路 | ✅ | 手动与自动视频链路均已接入 |
| `integrated` 真一体生成 | 🔶 | 接口可选，但运行期降级为图生视频 fallback |
| `/api/v1/projects/*` 路由 | ❌ | 已不再挂载到主应用 |
| `/pipeline/{project_id}/stitch` | ❌ | 占位入口已移除，正式拼接只保留 `/concat` |

### 2.3 前端能力

| 页面 | 路由 | 状态 | 说明 |
|------|------|------|------|
| 灵感输入 | `/step1` | ✅ | 输入创意、调用分析 |
| 世界构建 | `/step2` | ✅ | 6 轮问答 |
| 剧本生成 | `/step3` | ✅ | 大纲、关系、角色图、画风 |
| 预览导出 | `/step4` | ✅ | SceneStream + ExportPanel |
| 视频生成 | `/video-generation` | ✅ | 手动 / 自动流水线 |
| 设置页 | `/settings` | ✅ | LLM / 图片 / 视频配置 |
| 历史剧本 | `/history` | ✅ | 恢复、删除、继续进入分镜 |

---

## 三、API 状态

### 3.1 Story API

| 端点 | 方法 | 状态 | 说明 |
|------|------|------|------|
| `/api/v1/story/` | `GET` | ✅ | 历史故事列表 |
| `/api/v1/story/{story_id}` | `GET` | ✅ | 获取完整 Story |
| `/api/v1/story/{story_id}` | `DELETE` | ✅ | 删除 Story |
| `/api/v1/story/analyze-idea` | `POST` | ✅ | 灵感审计 |
| `/api/v1/story/world-building/start` | `POST` | ✅ | 开始世界构建 |
| `/api/v1/story/world-building/turn` | `POST` | ✅ | 继续世界构建 |
| `/api/v1/story/generate-outline` | `POST` | ✅ | 生成大纲 / 角色 / 关系 |
| `/api/v1/story/chat` | `POST` | ✅ | SSE 对话式修改建议，支持 `character / episode / outline` |
| `/api/v1/story/generate-script` | `POST` | ✅ | SSE 剧本生成 |
| `/api/v1/story/refine` | `POST` | ✅ | 结构化联动修改 |
| `/api/v1/story/apply-chat` | `POST` | ✅ | 应用对话式局部修改 |
| `/api/v1/story/patch` | `POST` | ✅ | 持久化 `characters / outline / art_style` |
| `/api/v1/story/{story_id}/finalize` | `POST` | ✅ | 导出给分镜阶段消费的文本 |

### 3.2 Pipeline API

| 端点 | 方法 | 状态 | 说明 |
|------|------|------|------|
| `/api/v1/pipeline/{project_id}/auto-generate` | `POST` | ✅ | 自动全流程 |
| `/api/v1/pipeline/{project_id}/storyboard` | `POST` | ✅ | 剧本转分镜 |
| `/api/v1/pipeline/{project_id}/generate-assets` | `POST` | ✅ | 手动生成 TTS / 图片 |
| `/api/v1/pipeline/{project_id}/render-video` | `POST` | ✅ | 手动生成视频 |
| `/api/v1/pipeline/{project_id}/status` | `GET` | ✅ | 查询状态 |
| `/api/v1/pipeline/{project_id}/concat` | `POST` | ✅ | 合并视频 |

### 3.3 Asset API

| 端点 | 方法 | 状态 | 说明 |
|------|------|------|------|
| `/api/v1/character/generate` | `POST` | ✅ | 单角色设定图 |
| `/api/v1/character/generate-all` | `POST` | ✅ | 批量角色设定图 |
| `/api/v1/character/{story_id}/images` | `GET` | ✅ | 读取角色图资产 |
| `/api/v1/image/{project_id}/generate` | `POST` | ✅ | 手动图片生成 |
| `/api/v1/video/{project_id}/generate` | `POST` | ✅ | 手动视频生成 |
| `/api/v1/tts/voices` | `GET` | ✅ | 语音列表 |
| `/api/v1/tts/{project_id}/generate` | `POST` | ✅ | TTS 生成 |

---

## 四、当前数据口径

### 4.1 Story

`Story` 是主业务载体，当前关键字段：

| 字段 | 含义 |
|------|------|
| `id` | 稳定 `story_id` |
| `idea / genre / tone` | Step 1 输入 |
| `selected_setting` | 世界构建完成后的总结 |
| `meta` | 标题、主题与一致性缓存 |
| `characters` | 角色列表，持久化后自动补齐 `id` |
| `relationships` | 角色关系，自动规范化 `source_id / target_id` |
| `outline` | 分集大纲 |
| `scenes` | 剧本生成结果 |
| `character_images` | 角色图资产，主键口径按 `character_id` |
| `art_style` | 全局画风设定 |

### 4.2 Pipeline

`Pipeline` 是视频生成阶段的状态真相源：

| 字段 | 含义 |
|------|------|
| `id` | `pipeline_id` |
| `story_id` | 关联的稳定 `story_id` |
| `status` | 当前阶段 |
| `progress / current_step` | 进度 |
| `progress_detail` | 步进信息 |
| `generated_files` | 分镜 / TTS / 图片 / 视频 / 最终视频等产物索引 |

### 4.3 当前关键数据约束

- 角色在持久化时会规范化并自动补齐 `id`
- 人物关系会补齐 `source_id / target_id`
- `character_images` 当前主口径为 `character_id -> asset`
- `Character` 相关 API 已要求传入 `character_id`，禁止按角色名覆盖人设图
- 手动 pipeline 当前依赖 `story_id + pipeline_id` 恢复状态，不再只靠前端内存
- Step 3 AI 聊天默认不允许修改角色名字与主角/配角等 `role` 标签
- 角色聊天应用只回写 `description`，剧情聊天只回写 `title / summary`
- 前端手动修改角色描述或剧情大纲时，会先调用 `/story/patch` 落库，再调用 `/story/refine` 处理联动变更

---

## 五、当前已落地的一致性与资产层

### 5.1 StoryContext

当前主链路已统一走 `StoryContext`：

- 分镜生成前会按 `story_id` 加载上下文
- 手动 `storyboard / generate-assets / render-video` 链路会消费同一套上下文
- 自动 `PipelineExecutor` 也会先准备同样的上下文

### 5.2 当前已实现的缓存资产

| 资产 | 存储位置 | 说明 |
|------|------|------|
| 画风资产 | `stories.art_style` | 全局画风设定 |
| 角色图资产 | `stories.character_images[*]` | `design_prompt / prompt / visual_dna / image_url` |
| 角色外貌缓存 | `stories.meta["character_appearance_cache"]` | 结构化 `body / clothing / negative_prompt` |
| 场景风格缓存 | `stories.meta["scene_style_cache"]` | `keywords / image_extra / video_extra / negative_prompt` |

### 5.3 当前真实口径

- 项目已经具备“以 Story 为中心的提示词资产层”
- 这层资产已能持久化并复用角色图、Visual DNA、外貌缓存、场景风格缓存、全局画风
- 当前还没有独立的 `digital_assets` 表、资产版本管理、标签检索和跨故事通用复用体系

---

## 六、视频流水线现状

### 6.1 当前策略

| 策略 | 状态 | 说明 |
|------|------|------|
| `separated` | ✅ | TTS -> 图片 -> 图生视频 -> 拼接 |
| `chained` | ✅ | 场景内尾帧连续性增强 |
| `integrated` | 🔶 | 当前会显式降级为 `integrated_image_to_video_fallback` |

### 6.2 已落地能力

- 分镜输出为结构化 `Shot`
- `image_prompt` 与 `final_video_prompt` 已分离
- `last_frame_prompt / last_frame_url` 已进入 schema 和部分 provider 链路
- `negative_prompt` 与 `art_style` 已解耦
- `PipelineStatus` 能回显 `generated_files` 与 runtime note

### 6.3 当前边界

- `integrated` 目前不包含真正的“视频语音一体化生成”
- 不同视频 provider 对尾帧能力支持不完全一致
- 当前没有 VLM 质检、自动重试、选择性抽检闭环

---

## 七、当前边界与未落地项

| 项目 | 当前情况 |
|------|------|
| DSPy 角色提取器 | 仅有计划文档，未接入主链路 |
| VLM 反馈闭环 | 未落地 |
| Prompt Caching 优化闭环 | 未形成完整产品能力 |
| 独立数字资产库 | 未落地独立表与跨故事复用 |
| 真实 integrated 一体生成 | 未落地 |
| 遗留 `projects` 文件清理 | 路由已卸载，文件仍在仓库中 |

---

## 八、与当前实现同步的重要说明

- 文档中不再把 `/stitch` 视为正式入口
- 文档中不再把 `/api/v1/projects/*` 视为主应用的一部分
- 文档中不再把“真正 integrated 一体生成”写成已实现
- 文档中明确说明 `scene_intensity` 是分镜阶段字段，不是当前 Step 3 剧本阶段默认输出字段
- 文档中明确说明角色图生成已强制要求 `character_id`

---

## 九、建议阅读顺序

1. `README.md`
2. 本文档
3. `docs/prompt-framework.md`
4. `docs/art-style-backend.md`
5. `docs/digital-asset-library-design.md`
6. `app/routers/` 与 `app/services/`
