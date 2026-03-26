# 画风设定 — 当前实现说明

## 1. 当前真实调用路径

画风现在需要覆盖的不是单一入口，而是下面几条实际会被前端或后端走到的链路：

| 场景 | 当前触发位置 | 后端端点 / 服务 | 状态 |
|------|-------------|----------------|------|
| 人设图生成 | `CharacterDesign.vue` | `POST /api/v1/character/generate[-all]` | ✅ 已支持 |
| 手动单镜头生图 | `VideoGeneration.vue` | `POST /api/v1/image/{id}/generate` | ✅ 已支持 |
| 手动单镜头生视频 | `VideoGeneration.vue` | `POST /api/v1/video/{id}/generate` | ✅ 已支持 |
| 手动批量素材生成 | 预留手动 pipeline 流程 | `POST /api/v1/pipeline/{id}/generate-assets` | ✅ 已支持 |
| 手动批量图生视频 | 预留手动 pipeline 流程 | `POST /api/v1/pipeline/{id}/render-video` | ✅ 已支持 |
| 一键自动流水线 | `pipeline/{id}/auto-generate` | `app/services/pipeline_executor.py` | ✅ 已支持 |

> `POST /api/v1/pipeline/{id}/storyboard` 仍然只是脚本转分镜，不直接生成图片/视频，本身不需要注入画风。

## 2. 前端

### 2.1 画风来源

- `ArtStyleSelector.vue` 负责确认式写入 `store.artStyle`
- `patchStory(..., { art_style })` 负责持久化到 `stories.art_style`
- `frontend/src/stores/story.js` 在历史剧本恢复时回填 `artStyle`

### 2.2 Header 透传

共享 header 构造函数现在定义在 `frontend/src/api/story.js`，并导出给其他页面复用：

```js
export function getHeaders() {
  const story = useStoryStore()
  // ...
  if (story.artStyle) headers['X-Art-Style'] = encodeURIComponent(story.artStyle)
  return headers
}
```

`VideoGeneration.vue` 已改为直接复用这个共享函数，不再维护一份本地副本，因此手动生图 / 生视频也会自动带上 `X-Art-Style`。

## 3. 后端注入点

### 3.1 公共工具

`app/core/api_keys.py`

```python
def get_art_style(request: Request) -> str:
    raw = request.headers.get("X-Art-Style", "")
    return unquote(raw).strip()

def inject_art_style(prompt: str, art_style: str) -> str:
    if not art_style or not prompt:
        return prompt
    return f"{prompt}, {art_style}"
```

### 3.2 人设图

- `app/routers/character.py` 读取 `get_art_style(request)`
- `app/services/image.py` 在 `generate_character_image()` 内将画风追加到标准三视图角色设定图 prompt

### 3.3 手动图片 / 视频接口

现在以下接口都已经支持从 header 读取画风：

- `app/routers/image.py`
- `app/routers/video.py`
- `app/routers/pipeline.py` 的 `generate-assets`
- `app/routers/pipeline.py` 的 `render-video`

其中：

- 图片阶段通过 `image.generate_images_batch(..., art_style=art_style)` 注入
- 视频阶段通过 `video.generate_videos_batch(..., art_style=art_style)` 注入

### 3.4 自动流水线

自动流水线已改为先统一构建镜头生成 prompt，再分别喂给图片和视频阶段：

```python
def _build_generation_prompt(self, shot: Shot) -> str:
    return inject_art_style(
        self._enhance_prompt_with_character(shot.final_video_prompt, self.character_info),
        self.art_style,
    )
```

当前顺序是：

1. `final_video_prompt`
2. `_enhance_prompt_with_character(...)`
3. `inject_art_style(...)`

这样 `separated`、`integrated`、`chained` 三条策略的图片/视频条件保持一致，不再出现“图片吃到了角色增强，视频只吃到 art_style”的分叉。

## 4. 当前已修复项

| 文件 | 修复内容 |
|------|---------|
| `frontend/src/api/story.js` | 导出共享 `getHeaders()`，统一透传 `X-Art-Style` |
| `frontend/src/views/VideoGeneration.vue` | 改为复用共享 header，修复手动 Step5 漏传画风 |
| `app/routers/image.py` | 手动单镜头生图支持读取 `X-Art-Style` |
| `app/routers/video.py` | 手动单镜头生视频支持读取 `X-Art-Style` |
| `app/routers/pipeline.py` | `generate-assets` / `render-video` 支持读取 `X-Art-Style` |
| `app/services/video.py` | `generate_videos_batch()` 支持统一追加画风 |
| `app/services/pipeline_executor.py` | 新增 `_build_generation_prompt()`，统一自动流水线图片/视频 prompt |

## 5. 仍需注意的边界

- 当前修复只解决“画风字段传递”和“自动链路 prompt 不一致”问题。
- 无 `StoryContext` 的 fallback 链路现在已改为注入清洗后的角色参考锚点，不再直接拼接原始三视图角色设定图 prompt。
- 主链路仍应优先依赖 `StoryContext` / `Visual DNA`，不要重新把原始角色设定图 prompt 挂回运行时注入点。
- `negative_prompt`、角色外貌结构化缓存、场景风格缓存仍属于后续一致性引擎设计范围，见 `docs/digital-asset-library-design.md`。
