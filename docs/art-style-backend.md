# 画风设定链路说明

> 更新日期：2026-03-27
>
> 本文档只描述仓库当前已落地的真实实现，不把计划态能力写成现状。

---

## 一、当前结论

- `art_style` 现在是“故事级持久化基线画风”，存储在 `stories.art_style`。
- 真正驱动运行时生成的直接输入不是数据库字段本身，而是每次请求里的 `X-Art-Style`。
- 前端主链路已经统一通过 `frontend/src/api/story.js` 的 `getHeaders()` 发送 `X-Art-Style`，即使用户没手动选择，也会发送默认画风。
- 后端运行期主组装入口是 `build_generation_payload()`；`inject_art_style()` 仍然保留为低层兜底 helper。
- `art_style` 与 `negative_prompt`、角色外貌锁、场景风格缓存、场景参考图资产是分离字段，不再混写成一个大 prompt。

---

## 二、主数据源与优先级

### 2.1 持久化主数据源

当前故事级画风真相源是：

- `stories.art_style`

写入来源主要有两类：

- `POST /api/v1/story/patch`
- `POST /api/v1/character/generate` 与 `POST /api/v1/character/generate-all`

这意味着画风会跟随 Story 一起进入历史恢复，而不是只停留在前端内存。

### 2.2 前端运行时来源

前端当前统一使用 `frontend/src/api/story.js`：

```js
headers['X-Art-Style'] = encodeURIComponent((story.artStyle || DEFAULT_ART_STYLE_PROMPT).trim())
```

这带来两个现实效果：

- 只要走前端主链路，请求里几乎总会带 `X-Art-Style`
- 即使 `store.artStyle` 为空，也会自动回退到 `DEFAULT_ART_STYLE_PROMPT`

当前前后端默认值保持一致，默认内容都是：

```text
写实摄影风格，电影级画质，自然光影，高清细节，真实质感
```

### 2.3 后端解析优先级

后端统一通过 `app/core/api_keys.py`：

```python
def get_art_style(request: Request) -> str:
    raw = request.headers.get("X-Art-Style", "")
    normalized = unquote(raw).strip()
    return normalized or DEFAULT_ART_STYLE
```

以及：

```python
def inject_art_style(prompt: str, art_style: str) -> str:
    if not art_style or not prompt:
        return prompt
    normalized_prompt = prompt.rstrip()
    normalized_style = art_style.strip()
    if not normalized_style:
        return normalized_prompt
    if normalized_prompt.endswith(normalized_style):
        return normalized_prompt
    if f", {normalized_style}" in normalized_prompt:
        return normalized_prompt
    return f"{normalized_prompt}, {normalized_style}"
```

当前真实优先级应理解为：

1. 请求显式传入的 `X-Art-Style`
2. `get_art_style()` 的后端默认值 `DEFAULT_ART_STYLE`
3. 仅当调用方绕过 `get_art_style()` 且向 `build_generation_payload(..., art_style="")` 传空串时，`StoryContext.base_art_style` 才会作为组装 fallback 生效

这点很重要：当前路由层不会“自动从数据库读出 `stories.art_style` 作为缺省请求值”。前端主链路之所以没有问题，是因为历史恢复后会先把 `stories.art_style` 回填到 store，再由 `getHeaders()` 重新透传。

---

## 三、实际请求链路

### 3.1 会直接消费画风的入口

| 场景 | 前端 / 调用方 | 后端入口 | 当前行为 |
|------|------|------|------|
| 角色三视图设定图 | Step 3 角色设计 | `POST /api/v1/character/generate[-all]` | 读取 `X-Art-Style`，生成后会把画风写回 `stories.art_style` |
| 单镜头生图 | 视频生成页 | `POST /api/v1/image/{project_id}/generate` | 读取 `X-Art-Style`，走 `build_generation_payload()` |
| 单镜头生视频 | 视频生成页 | `POST /api/v1/video/{project_id}/generate` | 读取 `X-Art-Style`，走 `build_generation_payload()` |
| 手动批量素材 | 手动 pipeline | `POST /api/v1/pipeline/{project_id}/generate-assets` | 读取 `X-Art-Style`，批量图片生成 |
| 手动批量视频 | 手动 pipeline | `POST /api/v1/pipeline/{project_id}/render-video` | 读取 `X-Art-Style`，批量视频生成 |
| 自动全流程 | 自动 pipeline | `POST /api/v1/pipeline/{project_id}/auto-generate` | 优先用请求体 `req.art_style`，否则读取 `X-Art-Style` |
| 分集环境参考图 | Step 4/5 环境参考 | `POST /api/v1/story/{story_id}/scene-reference/generate` | 读取 `X-Art-Style`，用于环境 key art 生成 |

### 3.2 不直接消费画风的入口

以下链路虽然前端也会带 `X-Art-Style`，但当前不是实际消费点：

- `POST /api/v1/pipeline/{project_id}/storyboard`
- 文本生成相关的 `story` 路由

原因很简单：这些入口本身不直接调用图片/视频生成，也不负责环境 key art 产出。

---

## 四、后端消费位置

### 4.1 角色设定图链路

角色图生成当前路径是：

```text
router.character
  -> get_art_style(request)
  -> generate_character_image()
  -> build_character_prompt(..., art_style=art_style)
```

这里的画风不是在 service 末端硬拼一个后缀，而是在 `build_character_prompt()` 内进入 `style lock` 语义：

- 三视图必须保持统一媒介语言
- 保持同一线条/笔触/渲染方式
- 保持同一色彩与光影语言

这条链路是当前项目里画风约束最强、最显式的一条。

### 4.2 场景参考图链路

环境参考图当前路径是：

```text
router.story.generate_scene_reference
  -> get_art_style(request)
  -> generate_episode_scene_reference()
  -> build_episode_environment_prompts(..., art_style=art_style)
  -> inject_art_style(...)
```

这里的目标不是角色图，而是“纯环境参考 key art”。当前实现中：

- prompt 会明确要求 `Pure environment plate only`
- `negative_prompt` 会单独压制人物、面部、服装、字幕、水印、拼贴等污染项
- 生成结果写入 `meta["episode_reference_assets"]` 与 `meta["scene_reference_assets"]`

这条链路在旧文档里是缺失的，但现在已经是正式运行路径的一部分。

### 4.3 图片生成链路

手动图片与手动 pipeline 图片生成当前都会优先走：

```text
build_generation_payload()
  -> image_prompt
  -> negative_prompt
  -> reference_images
  -> generate_images_batch()
  -> inject_art_style() 低层兜底
```

`build_generation_payload()` 当前会把下面几类内容拆字段组装：

- 镜头原始 `image_prompt` / `final_video_prompt`
- `StoryContext.character_locks` 提供的角色外貌约束
- `StoryContext.scene_styles` 提供的场景风格 extra
- 环境参考图带来的 `scene_reference_extra`
- 独立字段 `negative_prompt`
- 独立字段 `reference_images`

也就是说，画风只是最终 image prompt 的一个组成部分，不再承担“顺便塞角色一致性和污染排除”的职责。

### 4.4 视频生成链路

手动视频、手动 pipeline 视频和自动 pipeline 视频在运行期也都遵循同样原则：

- 先产出结构化 `final_video_prompt`
- 再把 `negative_prompt` 独立传给视频 provider
- `art_style` 作为正向风格基线注入，不和负向污染词混写

`app/services/video.py` 中 `generate_videos_batch()` 仍然会对 `final_video_prompt` 再调用一次 `inject_art_style()`。这不是逻辑重复错误，而是低层兜底策略，因为：

- 主链路调用 `build_generation_payload()` 时，prompt 往往已经带上画风
- 兼容直传 `shots`、fallback payload 或未来新入口时，service 仍能保证风格后缀存在
- `inject_art_style()` 内部带去重判断，不会无限重复追加同一画风短语

### 4.5 自动流水线链路

自动 pipeline 当前不是旧版 `_build_generation_prompt()` 单点逻辑，而是：

```text
PipelineExecutor._build_generation_payload()
  -> build_generation_payload(...)
  -> image.generate_images_batch(...)
  -> video.generate_videos_batch(...)
```

只有在“没有 `story_id` / 没有 `StoryContext`”的 legacy fallback 情况下，`PipelineExecutor` 才会退回旧式角色增强 + `inject_art_style()` 路径。

因此当前应把自动流水线理解为：

- 主链路：`StoryContext` + `build_generation_payload()`
- 兼容兜底：legacy enhancement path

而不是相反。

---

## 五、与一致性系统的关系

当前 `art_style` 在一致性体系中的定位是“全局风格基线”，不是总控字段。

它和以下资产各自独立：

- `meta["character_appearance_cache"]`
- `meta["scene_style_cache"]`
- `character_images`
- `meta["episode_reference_assets"]`
- `meta["scene_reference_assets"]`
- `negative_prompt`

当前正确理解应是：

- `art_style` 解决“整体媒介语言和审美方向”
- `character_appearance_cache` 解决“角色长相与默认服装”
- `scene_style_cache` 解决“场景层可复用风格关键词和 image/video extra”
- `negative_prompt` 解决“污染排除”
- `scene_reference_assets` 与 `character_images` 解决“参考图像约束”

这也是为什么现在主链路已经收口到 `build_generation_payload()`，而不是重新回到“把所有东西拼成一个超长 prompt”。

---

## 六、当前边界与注意事项

### 6.1 `stories.art_style` 不是后端路由默认读取值

这是当前实现里最容易被误解的一点。

在纯后端代码顺序上：

- 路由默认取的是 `get_art_style(request)`
- `get_art_style()` 空 header 时回退 `DEFAULT_ART_STYLE`
- 不是自动从当前 story 的 `art_style` 补默认

因此如果未来存在绕开前端的外部调用方，又没有显式传 `X-Art-Style`，最终使用的是后端默认写实摄影风格，而不是故事里已保存的自定义风格。

### 6.2 修改画风不会自动重生成旧资产

当前修改 `stories.art_style` 后：

- 不会自动重生角色图
- 不会自动重生环境参考图
- 不会自动重生已生成的镜头图片和视频

它只会影响后续新的生成请求。

### 6.3 画风变化当前不会单独失效一致性缓存

`POST /api/v1/story/patch` 当前在更新 `art_style` 时：

- 不会清空 `character_appearance_cache`
- 不会清空 `scene_style_cache`
- 不会清空 `scenes`

这符合当前实现，因为这些缓存被视为“结构化内容层”，不是纯画风字段本身。

### 6.4 文本分镜阶段不负责消费画风

`/storyboard` 只负责脚本转 `Shot`，并不直接生成图像或视频。当前画风的真正生效点仍然在素材生成阶段，而不是分镜文本生成阶段。

---

## 七、建议阅读顺序

如果要继续维护这条链路，建议按下面顺序阅读代码：

1. `frontend/src/api/story.js`
2. `app/core/api_keys.py`
3. `app/prompts/character.py`
4. `app/core/story_context.py`
5. `app/services/image.py`
6. `app/services/video.py`
7. `app/services/scene_reference.py`
8. `app/routers/character.py`
9. `app/routers/image.py`
10. `app/routers/video.py`
11. `app/routers/pipeline.py`
12. `app/routers/story.py`

---

## 八、与其他文档的分工

- `docs/prompt-framework.md`
  负责解释完整 prompt 体系、`StoryContext`、`build_generation_payload()` 的主组装逻辑

- `docs/feature-documentation.md`
  负责描述当前 API、页面、数据结构和模块能力全景

- `docs/END_TO_END_CONSISTENCY_IMPLEMENTATION_PLAN.md`
  负责后续一致性治理与主链路优化方案，不作为“当前已实现行为”的事实来源
