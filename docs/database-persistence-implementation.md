# 数据库持久化实现现状

**更新日期**: 2026-04-01  
**文档目标**: 说明当前仓库里真正落地的 SQLite 持久化结构、写入路径、缓存更新策略与恢复口径。

---

## 一、当前结论

当前项目的持久化已经不再只是“把 Story 和 Pipeline 从内存改到 SQLite”。

现在真实的持久化主线是：

1. `stories` 表
   - 保存剧本正文、角色、关系、大纲、分集剧本、世界观问答、角色设定图、画风，以及 `meta` 下的一致性缓存和手动生成恢复态。
2. `pipelines` 表
   - 保存自动/手动视频链路的运行状态、进度细节和生成文件索引。
3. 局部 JSON 更新
   - 对 `character_images`、`meta.character_appearance_cache`、`meta.scene_style_cache`、`meta.storyboard_generation` 等并发敏感字段，已经不再只靠整条 `save_story()` 覆盖，而是使用 SQLite `json_set/json_remove` 原子更新。

旧文档里几处已经过时的点，需要先纠正：

- 当前 `stories` 表已经包含 `character_images` 和 `art_style` 字段，不再只是基础 Story 字段。
- 当前 `Story.meta` 中正式承载了 `character_appearance_cache`、`scene_style_cache`、`episode_reference_assets`、`scene_reference_assets`、`storyboard_generation`。
- 单镜头 `tts/image/video` 接口、手动 `storyboard/generate-assets/render-video`、过渡视频、拼接结果，都会参与持久化，不只是 `auto-generate`。
- 仓库里虽然还保留 `Project` model 和 `projects` router，但主应用当前没有挂载它；真实业务持久化主线已经收口到 `stories` / `pipelines`。

---

## 二、当前数据库模型

### 2.1 `stories` 表

当前 ORM 模型见 `app/models/story.py`。

```sql
CREATE TABLE stories (
    id VARCHAR PRIMARY KEY,
    idea TEXT NOT NULL,
    genre TEXT,
    tone TEXT,
    selected_setting TEXT,
    meta JSON,
    characters JSON,
    relationships JSON,
    outline JSON,
    scenes JSON,
    wb_history JSON,
    wb_turn INTEGER DEFAULT 0,
    character_images JSON,
    art_style TEXT DEFAULT '',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

当前字段口径：

| 字段 | 含义 |
|------|------|
| `idea` | 初始创意 |
| `genre / tone` | 题材与语气 |
| `selected_setting` | 世界观问答完成后的设定总结，当前也是 `world_summary` 真实主落点 |
| `meta` | 主题、缓存、环境图组、分镜恢复态等扩展数据 |
| `characters` | 角色列表，保存时会自动规范化 `id` |
| `relationships` | 角色关系，保存时会自动规范化 `source_id / target_id` |
| `outline` | 分集大纲 |
| `scenes` | Step 3 剧本结果 |
| `wb_history / wb_turn` | 世界观问答历史 |
| `character_images` | 角色设定图资产，主键已统一为 `character_id`，旧名字 key 不再兼容 |
| `art_style` | 故事级基线画风 |

### 2.2 `pipelines` 表

```sql
CREATE TABLE pipelines (
    id VARCHAR PRIMARY KEY,
    story_id VARCHAR NOT NULL,
    status ENUM(pending, storyboard, generating_assets, rendering_video, stitching, complete, failed),
    progress INTEGER DEFAULT 0,
    current_step TEXT,
    error TEXT,
    progress_detail JSON,
    generated_files JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pipelines_story_id ON pipelines(story_id);
CREATE INDEX idx_pipelines_status ON pipelines(status);
CREATE INDEX idx_pipelines_created_at ON pipelines(created_at);
```

当前 `PipelineStatus`：

- `pending`
- `storyboard`
- `generating_assets`
- `rendering_video`
- `stitching`
- `complete`
- `failed`

### 2.3 旧 `projects` 模型的当前状态

仓库里仍有：

- `app/models/project.py`
- `app/routers/projects.py`

但 `app/main.py` 当前并未挂载 `projects` router，所以这条老的内存 mock 访谈链路不是现网主路径。当前业务上真正持续写入和恢复的，是 `stories` 与 `pipelines`。

---

## 三、`Story.meta` 当前重点字段

当前 `meta` 不是简单的“主题附加信息”，而是一致性与恢复层的主要持久化容器。

| 字段 | 作用 |
|------|------|
| `theme` | 大纲/改稿阶段的主题字段 |
| `character_appearance_cache` | 角色外貌结构化缓存 |
| `scene_style_cache` | 场景风格结构化缓存 |
| `episode_reference_assets` | 每集环境组的主场景参考图资产 |
| `scene_reference_assets` | `scene_key -> 环境组资产` 映射 |
| `storyboard_generation` | 手动分镜与素材生成恢复态 |

### 3.1 `storyboard_generation` 当前会同步什么

`app/services/storyboard_state.py` 当前会把以下内容写入 `meta.storyboard_generation`：

- `shots`
- `usage`
- `generated_files`
- `project_id`
- `pipeline_id`
- `story_id`
- `final_video_url`
- `updated_at`

并且会把生成结果反投影回 `shots`：

- TTS -> `audio_url / audio_duration`
- 图片 -> `image_url / image_path`
- 视频 -> `video_url / video_path`

同时会主动过滤：

- 前端瞬时字段 `ttsLoading / imageLoading / videoLoading`
- 旧的 `last_frame_prompt / last_frame_url`

这意味着 `story.meta.storyboard_generation` 现在是“手动分镜页恢复态 + 运行资产镜像层”，但不是替代 `pipeline.generated_files` 的运行期主真相源。

---

## 四、Story 记录的规范化与迁移策略

### 4.1 `save_story()` 不是裸写入

`app/services/story_repository.py` 中的 `save_story()` 当前行为是：

1. 先读已有 story
2. 做 merge
3. 经过 `normalize_story_record()`
4. 再执行 SQLite upsert

因此当前持久化会自动完成这些规范化：

- 给角色补齐稳定 `character_id`
- 复用已有角色 ID，避免改稿时角色身份漂移
- 为关系补齐 `source_id / target_id`
- 将 `character_images` 统一映射到 `character_id`
- 将 `meta.character_appearance_cache` 统一映射到 `character_id`
- `meta` 采用受控 merge，而不是整块盲覆盖

### 4.2 已内建的轻量迁移

`app/core/database.py` 的 `init_db()` 除了 `create_all()` 之外，还会对旧库补列：

- 缺 `character_images` 时自动 `ALTER TABLE`
- 缺 `art_style` 时自动 `ALTER TABLE`

当前还没有引入 Alembic 之类的正式迁移框架，仍属于“轻量自举迁移”阶段。

---

## 五、当前 Story 持久化写入路径

### 5.1 剧本主线

| 入口 | 写入内容 |
|------|------|
| `POST /api/v1/story/analyze-idea` | 新建 `stories` 基础记录，写 `idea / genre / tone` |
| `POST /api/v1/story/generate-outline` | 写 `selected_setting / meta / characters / relationships / outline / scenes=[]` |
| `POST /api/v1/story/generate-script` | 写 `scenes` |
| `POST /api/v1/story/world-building/start` | 写 `wb_history / wb_turn` |
| `POST /api/v1/story/world-building/turn` | 追加 `wb_history / wb_turn`，完成时写 `selected_setting` |

### 5.2 改稿与局部更新

| 入口 | 写入内容 | 附加动作 |
|------|------|------|
| `POST /api/v1/story/patch` | 持久化 `characters / outline / art_style` | 改角色会清空 `scenes` 并失效外貌缓存；改大纲会清空 `scenes` 并失效场景风格缓存 |
| `POST /api/v1/story/refine` | LLM 局部改写后的 `characters / relationships / outline / meta.theme` | 角色/大纲变更后同样触发缓存失效 |
| `POST /api/v1/story/apply-chat` | 依变更类型写回 story 数据 | 走同一套 Story 真相源 |

### 5.3 角色设定图与画风

`POST /api/v1/character/generate` 与 `POST /api/v1/character/generate-all` 当前会：

1. 生成角色设定图
2. 用 `upsert_character_images()` 原子写入 `stories.character_images`
3. 如请求头中带 `X-Art-Style`，同步写回 `stories.art_style`

### 5.4 StoryContext 相关缓存

`prepare_story_context()` 当前会按需提取并持久化：

- `meta.character_appearance_cache`
- `meta.scene_style_cache`

并且当角色已经有设定图资产时，会把外貌缓存中的 `body` 单向投影回：

- `character_images[character_id].visual_dna`

### 5.5 场景参考图资产

`POST /api/v1/story/{story_id}/scene-reference/generate` 当前会把结果写入：

- `meta.episode_reference_assets`
- `meta.scene_reference_assets`

这部分已经是正式持久化资产，不再只是临时生成结果。

---

## 六、当前 Pipeline 持久化写入路径

### 6.1 `project_id` 与 `story_id` 的真实关系

当前持久化上真正关联的是 `story_id`。

`project_id` 更多是路由层和前端页面使用的运行时标识；`app/core/pipeline_runtime.py` 里会通过：

```python
resolve_tracking_story_id(project_id, story_id)
```

得到真正用于持久化追踪的 `story_id`。如果请求里没显式传 `story_id`，就退回用 `project_id`。

### 6.2 自动流水线

`POST /api/v1/pipeline/{project_id}/auto-generate` 当前会：

1. 先创建一条 `pipelines` 记录
2. 在后台任务里用独立 `AsyncSessionLocal()` 执行
3. 由 `PipelineExecutor._update_state()` 持续写回：
   - `status`
   - `progress`
   - `current_step`
   - `progress_detail`
   - `generated_files`

自动流水线会按阶段持续快照 `generated_files`。当前常见键包括：

- `storyboard`
- `tts`（仅 `separated / chained`）
- `images`
- `videos`
- `shots`
- `meta`

其中：

- `meta` 内通常会带运行策略信息，例如 integrated fallback note。
- 最终 snapshot 至少会包含 `storyboard / images / videos / shots / meta`。
- `integrated` fallback 不会产生独立 `tts` 结果。

### 6.3 手动分镜与素材链路

以下接口都会写 `pipelines`：

| 接口 | 持久化内容 |
|------|------|
| `POST /api/v1/pipeline/{project_id}/storyboard` | 保存 `status=storyboard`，并把分镜和 usage 写入 `generated_files.storyboard` |
| `POST /api/v1/pipeline/{project_id}/generate-assets` | 保存手动批量 TTS / 图片结果 |
| `POST /api/v1/pipeline/{project_id}/render-video` | 保存主镜头视频结果 |
| `POST /api/v1/pipeline/{project_id}/transitions/generate` | 保存过渡视频与 `timeline` |
| `POST /api/v1/pipeline/{project_id}/concat` | 保存最终成片 `final_video_url` |
| `GET /api/v1/pipeline/{project_id}/status` | 读取某条 pipeline，或按 `story_id` / `project_id` 回退到最新 pipeline |

### 6.4 单镜头接口也会联动持久化

当前单镜头接口不是“只返回结果给前端，不入库”。

以下接口在携带 `story_id` 时，都会同步更新 `storyboard_generation`；若还能解析出 `pipeline_id`，还会继续同步 `pipelines.generated_files`：

- `POST /api/v1/tts/{project_id}/generate`
- `POST /api/v1/image/{project_id}/generate`
- `POST /api/v1/video/{project_id}/generate`

---

## 七、`generated_files` 当前结构

`pipelines.generated_files` 当前可能包含：

| 键 | 含义 |
|------|------|
| `storyboard` | 分镜结果与 usage |
| `tts` | 按 `shot_id` 存音频结果 |
| `images` | 按 `shot_id` 存图片结果 |
| `videos` | 按 `shot_id` 存主镜头视频结果 |
| `transitions` | 按 `transition_id` 存过渡视频结果 |
| `timeline` | 输出顺序，包含 `shot` 与 `transition` |
| `final_video_url` | 拼接后的成片地址 |
| `meta` | 运行期策略说明、fallback note 等 |
| `shots` | 自动流水线最终汇总结果 |

这套结构与 `meta.storyboard_generation.generated_files` 大体同构，但职责不同：

- `pipelines.generated_files` 是运行期状态真相源
- `meta.storyboard_generation` 是恢复态与镜头级结果镜像

补充说明：

- 所有运行资产在使用前都应按当前 storyboard 边界裁剪，避免旧 `shot_id / transition_id` 串入。
- 当镜头图片或视频被重新生成时，相关 `transition` 与 `final_video_url` 会被失效，避免继续导出旧结果。

---

## 八、原子更新与并发策略

### 8.1 为什么不能只靠整条 `save_story()`

对 `meta` 与 `character_images` 这类字段，如果总是：

1. 先读整条 story
2. 在内存里 merge
3. 再整条写回

就会在并发生成角色图、提取缓存、写分镜恢复态时发生更新丢失。

### 8.2 当前已经落地的原子更新接口

`app/services/story_repository.py` 当前提供：

| 方法 | 用途 |
|------|------|
| `upsert_character_images()` | 用 `json_set()` 原子合并角色图资产 |
| `upsert_story_meta_cache()` | 用 `json_set()` 原子更新 `meta` 下单个 key |
| `remove_story_meta_keys()` | 用 `json_remove()` 原子移除多个 `meta` key |
| `invalidate_story_consistency_cache()` | 失效 `character_appearance_cache / scene_style_cache` |

### 8.3 SQLite `database is locked` 处理

`upsert_story_meta_cache()` 和 `remove_story_meta_keys()` 当前会走 `_execute_with_sqlite_retry()`：

- 最多重试 3 次
- 命中 `database is locked` 时 rollback + 退避重试

这已经是当前仓库里对 SQLite 并发写保护的正式做法。

---

## 九、后台任务与会话生命周期

当前数据库会话规则：

1. 请求内接口走 `get_db()`
2. 后台任务必须新建 `AsyncSessionLocal()`

原因：

- FastAPI 依赖注入创建的会话会在请求结束后关闭
- `auto-generate`、手动批量素材生成、手动批量视频生成的后台任务都不能复用请求会话

当前这套模式已经在：

- `pipeline.auto_generate`
- `pipeline.generate-assets`
- `pipeline.render-video`

中实际使用。

---

## 十、当前恢复口径

前端和后端现在恢复状态主要依赖两层：

### 10.1 Story 恢复

`GET /api/v1/story/{story_id}` 会返回完整 story，用于恢复：

- 角色
- 大纲
- 分集剧本
- 角色设定图
- 画风
- 一致性缓存
- 场景参考图资产
- `storyboard_generation`

### 10.2 Pipeline 恢复

`GET /api/v1/pipeline/{project_id}/status` 会返回：

- 指定 `pipeline_id` 的状态
- 或给定 `story_id` 的最新 pipeline
- 或默认按 `project_id` 查最新 pipeline

这使得页面刷新后仍可恢复：

- 当前进度
- 已生成素材
- 过渡视频
- 成片地址

---

## 十一、当前验证与测试覆盖

当前与持久化直接相关的测试主要集中在：

- `tests/test_story_context.py`
  - 覆盖 `prepare_story_context()`、缓存写回、`upsert_story_meta_cache()` 等路径
- `tests/test_storyboard_state.py`
  - 覆盖 `storyboard_generation` 的 merge、generated_files 回填、timeline 保存
- `tests/test_pipeline_runtime.py`
  - 覆盖手动 pipeline 运行期持久化与恢复路径
- `tests/test_story_router.py`
  - 覆盖 `story.patch` 与缓存失效逻辑

当前并没有独立的 `tests/test_story_repository.py`，repository 相关行为主要通过上述集成/半集成测试间接覆盖。

---

## 十二、当前非目标与后续缺口

以下能力当前仍未落地：

1. 正式数据库迁移框架
   - 仍以 `init_db()` 的轻量补列为主
2. 独立数字资产库
   - 现在仍是 `Story.character_images` + `Story.meta[...]`
3. Story 与 Pipeline 级联删除
   - `delete_story()` 当前只删 story，不会联动清理 pipelines
4. Pipeline 历史列表 API
   - repository 已有 `list_pipelines_by_story()`，但当前路由未暴露
5. 通用分页、搜索、清理策略
   - 还停留在后续扩展阶段

---

## 十三、推荐阅读

1. `app/models/story.py`
2. `app/services/story_repository.py`
3. `app/services/storyboard_state.py`
4. `app/services/story_context_service.py`
5. `app/routers/story.py`
6. `app/routers/pipeline.py`
7. `docs/feature-documentation.md`
8. `docs/video-pipeline.md`
