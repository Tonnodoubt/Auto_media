# AutoMedia 功能文档

> 更新日期：2026-04-01
>
> 当前口径：只写仓库中已经落地并通过回归验证的能力，不把设计态内容写成已实现功能。

---

## 一、项目概览

| 项目项 | 说明 |
|------|------|
| 项目名称 | AutoMedia |
| 目标 | 从故事创意生成可预览、可导出的分镜、素材与视频 |
| 架构 | Vue 3 前端 + FastAPI 后端 + SQLite 持久化 |
| 当前主线 | Story 生成链路 + Scene Reference + Manual/Auto Pipeline + History 恢复 |

当前已经验证的主链路：

1. 灵感分析
2. 世界构建 6 轮问答
3. 大纲、角色、关系、流式剧本
4. 角色设定图与画风持久化
5. 按集生成共享环境图组
6. 剧本导出、`storyboard-script` 序列化、分镜解析、手动视频生成
7. 过渡视频生成与时间线拼接
8. 历史恢复与数据库状态追踪

---

## 二、功能状态总览

### 2.1 页面与主流程

| 阶段 | 页面 / 模块 | 状态 | 当前能力 |
|------|------|------|------|
| Step 1 | 灵感输入 | ✅ | 创意输入、要素审计、建议追问 |
| Step 2 | 世界构建 | ✅ | 6 轮问答、写入 `selected_setting` |
| Step 3 | 故事生成 | ✅ | 大纲、角色、关系、剧本、聊天修改、refine、apply-chat |
| Step 3 扩展 | 角色与画风 | ✅ | 角色三视图设定图、`art_style` 持久化 |
| Step 4 | 预览导出 | ✅ | SceneStream、导出、环境图组生成 |
| Video Generation | 视频生成页 | ✅ | 分镜、TTS、图片、视频、过渡、拼接、恢复 |
| History | 历史恢复 | ✅ | 加载 Story、恢复手动 pipeline 上下文 |

### 2.2 后端模块

| 模块 | 状态 | 说明 |
|------|------|------|
| Story API | ✅ | 主链路完整 |
| Character API | ✅ | 单角色 / 批量人设图可用 |
| Scene Reference | ✅ | 已按集生成共享环境图组 |
| Pipeline API | ✅ | 手动步进与自动全流程可用 |
| Transition API | ✅ | 过渡视频可生成并写入 timeline |
| Story / Pipeline 持久化 | ✅ | Story 与 Pipeline 都是当前真相源 |
| `StoryContext` 运行期一致性层 | ✅ | 手动与自动链路均已接入 |
| `integrated` 真一体生成 | 🔶 | 当前降级为图生视频 fallback |
| `/api/v1/projects/*` | ❌ | 路由已不再挂载 |
| `/pipeline/{project_id}/stitch` | ❌ | 占位入口已移除，正式拼接只保留 `/concat` |

---

## 三、API 状态

### 3.1 Story API

| 方法 | 路径 | 状态 | 说明 |
|------|------|------|------|
| `GET` | `/api/v1/story/` | ✅ | 历史故事列表 |
| `GET` | `/api/v1/story/{story_id}` | ✅ | 获取完整 Story |
| `DELETE` | `/api/v1/story/{story_id}` | ✅ | 删除 Story |
| `POST` | `/api/v1/story/analyze-idea` | ✅ | 灵感审计 |
| `POST` | `/api/v1/story/world-building/start` | ✅ | 开始世界构建 |
| `POST` | `/api/v1/story/world-building/turn` | ✅ | 继续世界构建 |
| `POST` | `/api/v1/story/generate-outline` | ✅ | 生成大纲 / 角色 / 关系 |
| `POST` | `/api/v1/story/chat` | ✅ | SSE 聊天建议，支持 `character / episode / outline / generic` |
| `POST` | `/api/v1/story/generate-script` | ✅ | SSE 剧本生成 |
| `POST` | `/api/v1/story/refine` | ✅ | 结构化联动修改 |
| `POST` | `/api/v1/story/apply-chat` | ✅ | 应用聊天修改 |
| `POST` | `/api/v1/story/patch` | ✅ | 持久化角色、大纲、画风 |
| `POST` | `/api/v1/story/{story_id}/scene-reference/generate` | ✅ | 生成本集环境图组 |
| `POST` | `/api/v1/story/{story_id}/finalize` | ✅ | 导出分镜可消费文本 |
| `POST` | `/api/v1/story/{story_id}/storyboard-script` | ✅ | 按所选场景导出统一 storyboard 输入文本 |

### 3.2 Pipeline API

| 方法 | 路径 | 状态 | 说明 |
|------|------|------|------|
| `POST` | `/api/v1/pipeline/{project_id}/auto-generate` | ✅ | 自动全流程 |
| `POST` | `/api/v1/pipeline/{project_id}/storyboard` | ✅ | 剧本转结构化分镜 |
| `POST` | `/api/v1/pipeline/{project_id}/generate-assets` | ✅ | 批量生成 TTS / 图片 |
| `POST` | `/api/v1/pipeline/{project_id}/render-video` | ✅ | 批量生成视频 |
| `POST` | `/api/v1/pipeline/{project_id}/transitions/generate` | ✅ | 相邻镜头过渡视频 |
| `POST` | `/api/v1/pipeline/{project_id}/concat` | ✅ | 拼接主镜头与 transition |
| `GET` | `/api/v1/pipeline/{project_id}/status` | ✅ | 查询 pipeline 状态 |

### 3.3 Asset API

| 方法 | 路径 | 状态 | 说明 |
|------|------|------|------|
| `POST` | `/api/v1/character/generate` | ✅ | 单角色设定图，要求 `character_id` |
| `POST` | `/api/v1/character/generate-all` | ✅ | 批量角色设定图 |
| `GET` | `/api/v1/character/{story_id}/images` | ✅ | 读取角色图资产 |
| `POST` | `/api/v1/image/{project_id}/generate` | ✅ | 单镜头图片生成，支持 `story_id / pipeline_id` 持久化 |
| `POST` | `/api/v1/video/{project_id}/generate` | ✅ | 单镜头视频生成，支持 `story_id / pipeline_id` 持久化 |
| `GET` | `/api/v1/tts/voices` | ✅ | 语音列表 |
| `POST` | `/api/v1/tts/{project_id}/generate` | ✅ | 单镜头 TTS，支持 `story_id / pipeline_id` 持久化 |

---

## 四、当前数据口径

### 4.1 Story

`Story` 是主业务载体，当前关键字段：

| 字段 | 含义 |
|------|------|
| `id` | 稳定 `story_id` |
| `idea / genre / tone` | Step 1 输入 |
| `selected_setting` | 世界构建总结 |
| `meta` | 主题、缓存、环境图组、手动分镜状态 |
| `characters` | 角色列表，持久化时自动规范化 `id` |
| `relationships` | 角色关系，自动规范化 `source_id / target_id` |
| `outline` | 分集大纲 |
| `scenes` | Step 3 剧本结果 |
| `character_images` | 角色设定图资产 |
| `art_style` | 全局画风设定 |

### 4.2 Story.meta 当前重点字段

| 字段 | 作用 |
|------|------|
| `character_appearance_cache` | 角色外貌结构化缓存 |
| `scene_style_cache` | 场景风格结构化缓存 |
| `episode_reference_assets` | 按环境组存共享环境图资产 |
| `scene_reference_assets` | 按 `scene_key` 回填环境图命中结果 |
| `storyboard_generation` | 手动分镜与素材生成恢复态 |

`storyboard_generation` 当前会同步：

- `shots`
- `project_id`
- `pipeline_id`
- `story_id`
- `generated_files`
- `final_video_url`

它的职责是恢复态与镜头级结果镜像，不替代 `Pipeline.generated_files` 的运行期真相源角色。

### 4.3 Pipeline

`Pipeline` 是视频运行期状态真相源：

| 字段 | 含义 |
|------|------|
| `id` | `pipeline_id` |
| `story_id` | 关联的稳定 `story_id` |
| `status` | 当前阶段 |
| `progress / current_step` | 进度与步骤 |
| `progress_detail` | 步进详情 |
| `generated_files` | 分镜 / 音频 / 图片 / 视频 / 过渡 / timeline / 最终视频 |

### 4.4 `generated_files` 当前可能包含

| 键 | 含义 |
|------|------|
| `storyboard` | 分镜与 usage |
| `tts` | 按 `shot_id` 存音频结果 |
| `images` | 按 `shot_id` 存首帧图片结果 |
| `videos` | 按 `shot_id` 存主镜头视频结果 |
| `transitions` | 按 `transition_id` 存过渡视频与来源帧 |
| `timeline` | 导出顺序，包含 `shot` 与 `transition` |
| `final_video_url` | 拼接后成片 |
| `meta` | 运行期策略说明，如 integrated fallback note |

---

完整视频导出规则补充：

- 只有当前 storyboard 的主镜头视频全部存在时，才允许进入导出。
- 如果当前 storyboard 包含多个镜头，则相邻 `transition` 也必须全部存在。
- 后端会按当前 storyboard 动态推导导出顺序，不再在 `pipeline_id` 存在时完全信任前端上送的 `video_urls`。

## 五、场景参考图与首帧主链路

### 5.1 当前已落地能力

- 环境图按“每集环境组”生成，不是按单场景重复生成
- 后端会按环境锚点自动聚类相似场景
- 每个环境组只生成 1 张 `variants.scene`
- 结果持久化到：
  - `meta.episode_reference_assets`
  - `meta.scene_reference_assets`
- 分镜阶段会为每个 Shot 写入 `source_scene_key`
- 图片生成阶段会按 `source_scene_key` 命中环境图，并作为运行期参考

### 5.2 当前真实使用方式

图片生成时，运行期会优先组合两类参考：

1. 命中角色的设定图
2. 命中场景的环境图

这两类参考最终会进入 `reference_images`，并由图片服务在 provider 支持时传给生成接口；若 provider 拒绝，图片服务会自动退回无参考图请求。

---

## 六、视频流水线现状

### 6.1 策略状态

| 策略 | 状态 | 说明 |
|------|------|------|
| `separated` | ✅ | TTS -> 图片 -> 主镜头视频 -> 合成 |
| `chained` | ✅ | 按场景分组执行，但不再传递尾帧 |
| `integrated` | 🔶 | 当前降级为图生视频 fallback |

### 6.2 当前主线规则

- 普通主镜头统一单首帧 I2V
- `last_frame_prompt / last_frame_url` 只保留兼容字段，不参与主镜头运行期
- 主镜头图片只生成 `image_url`
- 主镜头视频只消费 `image_url + final_video_prompt`

### 6.3 过渡视频当前规则

- 入口：`POST /api/v1/pipeline/{project_id}/transitions/generate`
- 只允许 storyboard 顺序里的直接相邻镜头
- 必须要求两侧主镜头视频都已存在
- 后端只信任当前 pipeline 中的真实视频资产
- 会从前镜视频提取最后一帧、从后镜视频提取第一帧
- 双帧能力当前只允许支持双帧的 provider，默认要求豆包
- 结果写入 `generated_files.transitions` 和 `generated_files.timeline`

### 6.4 拼接逻辑

- 如果存在 `timeline`，导出时按 `timeline` 顺序拼接
- 如果没有 `timeline`，则回退到主镜头顺序
- transition 缺失时不会污染主镜头视频

---

## 七、持久化与恢复

### 7.1 当前已实现

- 分镜页恢复依赖 `story.meta.storyboard_generation`
- 手动 `storyboard / generate-assets / render-video`
- 单次 `tts / image / video`
- `transition / concat`

这些链路在带有 `story_id / pipeline_id` 时，会把结果同时写回：

1. `story.meta.storyboard_generation`
2. `pipeline.generated_files`

### 7.2 当前意义

- 前端刷新后仍可恢复分镜和素材状态
- transition 读取的是当前 pipeline 的真实资产，而不是前端临时状态
- History 页面恢复 Story 后，可继续进入手动分镜页延续上下文

### 7.3 当前边界

- `auto-generate` 仍以 `pipeline` 表为主要运行期状态源
- 手动分镜页的恢复逻辑当前更依赖 `storyboard_generation`

---

## 八、当前已落地的一致性层

### 8.1 已有缓存资产

| 资产 | 存储位置 | 说明 |
|------|------|------|
| 角色图资产 | `stories.character_images` | `design_prompt / visual_dna / image_url / image_path` |
| 角色外貌缓存 | `stories.meta["character_appearance_cache"]` | `body / clothing / negative_prompt` |
| 场景风格缓存 | `stories.meta["scene_style_cache"]` | `image_extra / video_extra / negative_prompt` |
| 环境图组资产 | `stories.meta["episode_reference_assets"]` | 每集环境组主资产 |
| 场景命中环境图 | `stories.meta["scene_reference_assets"]` | `scene_key -> 环境组资产` |

### 8.2 当前真实口径

- 项目已经具备以 Story 为中心的提示词与资产缓存层
- 这层能力已经参与图片和视频生成
- 当前还没有独立 `digital_assets` 表、跨故事资产版本管理和标签检索

---

## 九、当前边界与未落地项

| 项目 | 当前情况 |
|------|------|
| 真正 integrated 视频语音一体生成 | 未落地 |
| Transition 删除 / 重置接口 | 未落地 |
| VLM 质检与自动重试闭环 | 未落地 |
| 独立数字资产库 | 未落地 |
| DSPy 提取器 | 仅有设计文档 |
| 遗留 `projects` 文件清理 | 路由已卸载，文件仍在仓库 |

---

## 十、验证口径

当前已跑通的本地验证：

- `uv run python -m unittest discover -s tests -q`
- `node --test frontend/src/utils/storyChat.test.js frontend/src/utils/storyChat.multiline-sections.test.js frontend/src/utils/storyChat.numbering.test.js`
- `npm --prefix frontend run build`

当前仍待执行的人工验收：

- `docs/phase3-manual-acceptance-runbook.md`

---

## 十一、建议阅读顺序

1. `README.md`
2. 本文档
3. `docs/prompt-framework.md`
4. `docs/video-pipeline.md`
5. `app/routers/` 与 `app/services/`
