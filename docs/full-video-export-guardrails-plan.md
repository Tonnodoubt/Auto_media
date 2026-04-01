# 完整视频导出防串片改造说明

> 文档状态：改造方案留档。文中大部分 guardrail 已并入当前实现，交接开发时请优先以 `docs/feature-documentation.md`、`docs/database-persistence-implementation.md` 和 `docs/video-pipeline.md` 为准。

## 目标

解决两个问题：

1. 当前重新解析分镜时，如果这次只解析了部分场景，历史 `generated_files` 里的旧图片、旧视频、旧 transition 仍可能被继续复用。
2. “导出完整视频”现在只要能收集到一批 `video_url` 就会发起拼接，没有校验“当前这版分镜”的主镜头和过渡镜头是否全部生成完成。

期望结果：

1. 完整视频导出只允许使用“当前 storyboard 对应的素材”。
2. 导出前必须满足：
   - 当前 storyboard 的核心分镜全部有主视频
   - 当前 storyboard 的相邻分镜过渡视频全部生成
3. 如果只解析了部分场景，旧场景素材不能混入这次导出。

## 当前问题定位

### 1. 历史素材会被持续 merge

当前以下位置都采用“增量 merge”思路：

- `app/services/storyboard_state.py`
  - `_merge_generated_files`
  - `build_storyboard_generation_state`
- `app/routers/pipeline.py`
  - `_merge_generated_files`
  - `_persist_manual_pipeline_state`

这会导致新的 `generated_files` 写入时，旧的 `tts/images/videos/transitions/timeline/final_video_url` 默认被保留。

如果这次解析出来的 `shots` 变少了，或者只覆盖部分场景，但旧素材对应的 `shot_id / transition_id` 还留在状态里，它们后面仍可能被读取到。

### 2. 前端导出只做“收集 URL”，不做完整性校验

当前导出逻辑在 `frontend/src/views/VideoGeneration.vue` 的 `concatAllVideos()`：

1. 优先读取 `transitionTimeline`
2. 否则读取当前 `storyboardFlowItems`
3. 只要 `orderedVideoUrls.length > 0` 就调用 `/api/v1/pipeline/{project_id}/concat`

这里没有判断：

- 当前 storyboard 的每个核心分镜是否都有主视频
- 当前 storyboard 的每个相邻 transition 是否都有过渡视频
- `transitionTimeline` 是否只包含当前这版 storyboard 的条目

### 3. 后端 concat 接口也没有做“当前 storyboard 完整性”校验

当前 `app/routers/pipeline.py` 的 `concat_videos()` 只校验：

- `req.video_urls` 非空
- URL 是可信本地媒体路径

它不会校验：

- 这些 URL 是否对应当前 storyboard
- 当前 storyboard 是否已全部生成完毕
- 是否混入了旧 transition / 旧 shot 视频

## 实现方案

## 一、导出与校验的真相源

当前代码按下面的优先级工作：

1. 当前 storyboard 的镜头顺序，优先读取 `story.meta.storyboard_generation.shots`
2. 运行期素材结果，优先读取 `pipeline.generated_files`
3. story mirror 中的 `generated_files` 只作为恢复/兜底来源
4. 真正参与 transition 与 concat 的资产，会先按“当前 storyboard 边界”裁剪后再使用

也就是说：

- `pipeline.generated_files` 仍是运行态主真相源
- `storyboard_generation` 仍是恢复态镜像层
- 但导出和过渡生成都会强制回到“当前 storyboard 合法边界”内工作，避免旧素材串入

其中：

- 核心分镜：当前 `shots` 列表中的每一个 `shot_id`
- 过渡分镜：当前 `shots` 中每一对相邻镜头形成的 `transition_{from}__{to}`

如果当前只有 1 个 shot，则不需要 transition。

## 二、重新解析 storyboard 时清理旧素材

现已在 `generate_storyboard()` 成功后显式重置 story mirror，只保留当前 storyboard：

建议效果：

- 清空旧 `tts`
- 清空旧 `images`
- 清空旧 `videos`
- 清空旧 `transitions`
- 清空旧 `timeline`
- 清空旧 `final_video_url`
- 只保留新的 `generated_files.storyboard`

实现方式：

- `persist_storyboard_generation_state(...)` 现支持 `replace_generated_files`
- 重新解析分镜时会用新的 `generated_files.storyboard` 替换旧镜像
- 同时清空 story mirror 上的 `final_video_url`

## 三、所有 generated_files 在持久化时按当前 shot 集裁剪

现已统一按“当前完整 storyboard 的合法资产边界”裁剪，而不是按单次请求 body 的 shots 裁剪。

当前行为：

- `tts/images/videos` 只保留当前 `shot_ids`
- `transitions` 只保留当前相邻镜头的 transition
- `timeline` 只保留当前 storyboard 可推导出的时间线
- 单镜头重生图后，会额外失效：
  - 该镜头旧 `video`
  - 所有关联 `transition`
  - `final_video_url`
- 单镜头/批量重生视频后，会额外失效：
  - 所有关联 `transition`
  - `final_video_url`

落点：

- `app/services/storyboard_state.py`
  - `build_storyboard_generation_state`
  - `_apply_generated_files_to_shots`
- `app/routers/pipeline.py`
  - `_persist_manual_pipeline_state`

重点不是“继续叠加 merge”，而是“每次写入前先回到当前 storyboard 的合法边界，再处理增量结果和依赖失效”。

## 四、导出前必须做完整性校验

当前已实现为统一规则：

### 可导出条件

1. 当前 storyboard 至少有 1 个核心分镜
2. 每个核心分镜都存在 `video_url`
3. 如果核心分镜数量大于 1，则每一对相邻分镜都存在对应的 transition `video_url`
4. 导出顺序必须能由当前 storyboard 动态推导出来
5. `final_video_url` 不能作为“允许再次导出”的依据，它只是上一次结果，不代表本次素材完整

### 不可导出场景

- 少任意一个核心分镜视频
- 少任意一个相邻 transition 视频
- `timeline` 中出现不属于当前 storyboard 的旧 transition
- 当前 storyboard 已变化，但 `generated_files` 仍保留上一次解析结果

## 五、把导出顺序放到后端生成，不再完全信任前端 URL 列表

当前 `concat_videos()` 已升级为：

1. 当提供 `pipeline_id` 时，后端自行读取当前 pipeline/storyboard 状态
2. 后端根据当前 `shots` 生成预期顺序：
   - `shot-1`
   - `transition_shot-1__shot-2`
   - `shot-2`
   - `transition_shot-2__shot-3`
   - `shot-3`
3. 先校验主镜头视频和过渡视频是否齐全
4. 校验通过后再拼出最终 `orderedVideoUrls`
5. 当存在 `pipeline_id` 时，不再信任前端传入的 `req.video_urls`

这样可以避免两类问题：

1. 前端误把旧素材 URL 带进来
2. 用户刷新后本地状态滞后，仍能导出错误顺序

兼容策略：

- 旧模式：无 `pipeline_id` 时沿用 `req.video_urls`
- 新模式：有 `pipeline_id` 时以后端推导顺序为准

## 六、前端按钮也要同步禁用

当前前端已在 `frontend/src/views/VideoGeneration.vue` 增加 `exportReadiness` 计算属性，统一返回：

- `ready: boolean`
- `missingShotVideos: string[]`
- `missingTransitions: string[]`
- `message: string`

当前逻辑：

1. 从当前 `shots` 推导 `expectedTransitions`
2. 用当前 `transitionResults` 和 `shots[*].video_url` 校验完整性
3. 不满足时：
   - 禁用“导出完整视频”按钮
   - 在按钮旁展示明确原因

建议提示文案：

- `还有 2 个核心分镜未生成视频：scene1_shot2、scene1_shot3`
- `还有 1 个过渡分镜未生成：transition_scene1_shot2__scene1_shot3`
- `当前只解析了部分场景，禁止复用旧素材导出`

前端禁用只是交互层保护，真正兜底仍在后端 `concat`。

## 推荐修改文件

### 必改

- `app/services/storyboard_state.py`
- `app/routers/pipeline.py`
- `frontend/src/views/VideoGeneration.vue`

### 可能联动

- `tests/test_storyboard_state.py`
- `tests/test_pipeline_runtime.py`

## 建议测试用例

### 1. 新 storyboard 解析后清除旧资产

前置：

- 老 storyboard 有 `images/videos/transitions/timeline/final_video_url`

执行：

- 重新解析一个只包含部分场景的新 storyboard

预期：

- story meta 和 pipeline 中只保留新 storyboard 的 `storyboard`
- 旧 `videos/transitions/timeline/final_video_url` 被清空或裁剪掉

### 2. 缺主镜头视频时禁止导出

前置：

- 当前 storyboard 有 3 个 shots
- 只生成了 2 个主视频

预期：

- 前端按钮禁用
- 后端 `concat` 返回 400

### 3. 缺 transition 时禁止导出

前置：

- 当前 storyboard 有 3 个 shots
- 3 个主视频都存在
- 只生成了 1 个 transition

预期：

- 前端按钮禁用
- 后端 `concat` 返回 400

### 4. 旧 transition 不得混入新 storyboard

前置：

- 上一版 storyboard 有 `transition_a__b`
- 当前 storyboard 已变成 `shot-x -> shot-y`

预期：

- `transition_a__b` 不出现在当前 `timeline`
- 导出顺序只基于 `shot-x / shot-y`

### 5. 单镜头 storyboard 可直接导出

前置：

- 当前只有 1 个 shot
- 主视频已存在

预期：

- 不要求 transition
- 可以导出

## 建议验收标准

1. 重新解析 storyboard 后，旧素材不会再被当前导出流程读取。
2. “导出完整视频”只有在当前核心分镜和全部过渡分镜都生成完成时才可点击。
3. 后端即使收到错误的 `video_urls`，也不会导出不属于当前 storyboard 的素材。
4. 刷新页面、恢复历史状态后，导出判断仍与后端一致。

## 当前已完成

本次已落地：

- `frontend/src/views/VideoGeneration.vue`
  - 已隐藏“生成语音”相关前端入口
  - 已停止页面初始化时加载语音列表
  - 已在前端禁用未满足完整性条件的“导出完整视频”按钮
- `app/services/storyboard_state.py`
  - 已增加 storyboard 边界裁剪与依赖失效逻辑
- `app/routers/pipeline.py`
  - 已在导出前按当前 storyboard 做完整性校验
  - 已在提供 `pipeline_id` 时改为后端推导导出顺序
- `app/routers/image.py`
  - 单镜头生图后会失效相关视频、过渡和成片
- `app/routers/video.py`
  - 单镜头生视频后会失效相关过渡和成片
