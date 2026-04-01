# Phase 3 人工验收 Runbook

这份 runbook 用来补齐 [END_TO_END_CONSISTENCY_IMPLEMENTATION_PLAN.md](./END_TO_END_CONSISTENCY_IMPLEMENTATION_PLAN.md) 里仍未实际执行的 Phase 3 人工收官。

当前状态不是“还没思路”，而是：

- 自动化最小基线已经通过
- 后端全流程模拟测试已经覆盖 scene -> storyboard -> image -> video -> transition -> concat
- 还缺一轮基于真实 provider 和真实故事样本的人工串行验收

这份 runbook 的目标，就是把那轮人工验收固定成可重复执行的步骤。

## 1. 固定样本

固定样本文件：

- `docs/phase3_manual_acceptance_story.json`
- `scripts/manual/seed_phase3_manual_story.py`

推荐固定 ID：

- `story_id=manual-acceptance-rainy-teahouse`
- `project_id=manual-phase3`
- `auto_project_id=auto-phase3`

样本特征：

- 单集单场景，但设计成“两段连续主动作”而不是多段松散事件，正常应由 2 个核心主镜头就能覆盖
- 第一段动作明确要求看见上半身、双手、木门边、湿油纸伞和密封信，专门压测“首帧图不能只剩脸”
- 第二段动作要求沿同一空间轴线推进到柜台边放信，专门压测同场景连续性，而不是把下一镜重新拍成独立海报图
- 这个样本也能顺手检验 storyboard 是否会把简单连续动作错误拆成纯脸部特写或纯手部特写
- 已自带 `character_appearance_cache` 与 `scene_style_cache`，避免人工验收被缓存提取问题干扰

## 2. 前置条件

开始前先确认：

- 后端服务能正常启动
- `ffmpeg` 可用
- LLM、图片、视频 provider 的 key 都已配置好
- 若图片或视频 provider 需要回拉本地 `/media/*` 资源，必须准备一个可公网访问的 `base_url`
- 若要把“参考图链路”也纳入这轮人工验收，建议先为该 story 补齐真实可访问的角色设定图和场景环境图；没有的话，也可以先用当前 fixture 跑第一轮主链路验收

建议先跑一遍最小基线，避免把环境问题误判成业务问题：

```bash
env UV_CACHE_DIR=/tmp/uv-cache uv run python -m unittest discover -s tests -q
node --test frontend/src/utils/storyChat.test.js frontend/src/utils/storyChat.multiline-sections.test.js frontend/src/utils/storyChat.numbering.test.js
npm --prefix frontend run build
```

## 3. 写入固定样本 story

```bash
env UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/manual/seed_phase3_manual_story.py
```

如果想改 story id：

```bash
env UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/manual/seed_phase3_manual_story.py manual-acceptance-rainy-teahouse-2
```

写入后建议先确认 story 存在：

```bash
curl -s http://127.0.0.1:8000/api/v1/story/manual-acceptance-rainy-teahouse
```

此时应看到：

- `characters`
- `scenes`
- `meta.character_appearance_cache`
- `meta.scene_style_cache`

## 4. 先取 storyboard 输入文本

```bash
curl -s \
  -X POST \
  http://127.0.0.1:8000/api/v1/story/manual-acceptance-rainy-teahouse/storyboard-script \
  -H 'Content-Type: application/json' \
  -d '{}' \
  | tee /tmp/manual_phase3_storyboard_script.json
```

建议至少人工检查这几件事：

- 角色块里的 `Visual DNA` 优先来自 `character_appearance_cache.body / clothing`
- 不应回退成被设定图模板污染的大段 `design_prompt`
- 场景块里应包含 `场景标题 / 环境锚点 / 情感标尺 / 关键道具 / 动作拆解 / 台词`
- 文本本身读起来已经像一个连续剧情段落，而不是互相割裂的字段堆砌

## 5. 手动主链路验收

### 5.1 生成 storyboard

```bash
SCRIPT_TEXT=$(jq -r '.script' /tmp/manual_phase3_storyboard_script.json)

curl -s \
  -X POST \
  "http://127.0.0.1:8000/api/v1/pipeline/manual-phase3/storyboard" \
  -H 'Content-Type: application/json' \
  -H "X-LLM-Provider: openai" \
  -H "X-LLM-Model: gpt-4o-mini" \
  -H "X-LLM-API-Key: $OPENAI_API_KEY" \
  -d "$(jq -n --arg script "$SCRIPT_TEXT" --arg story_id "manual-acceptance-rainy-teahouse" '{script:$script, story_id:$story_id}')" \
  | tee /tmp/manual_phase3_storyboard.json
```

人工检查：

- 同一场景不应被拆成互相断开的海报式镜头
- 这个样本正常应优先收敛成 2 个核心主镜头；如果被拆出纯脸部特写或纯手部特写，应优先记为可疑过度拆分
- 镜头 1 应保留门口停顿、右手扶门、左手握伞和信的起始状态
- 镜头 2 应自然承接“推进到柜台边放信 -> 赵掌柜抬眼回应”
- `image_prompt` 不应与 `final_video_prompt` 打架
- 如果 `camera_setup.shot_size` 是 `MS / MWS / WS`，就不应把首帧描述收缩成只剩头部的纯肖像视角

### 5.2 生成图片

```bash
PIPELINE_ID=$(jq -r '.pipeline_id' /tmp/manual_phase3_storyboard.json)

curl -s \
  -X POST \
  "http://127.0.0.1:8000/api/v1/pipeline/manual-phase3/generate-assets?pipeline_id=${PIPELINE_ID}&story_id=manual-acceptance-rainy-teahouse&generate_tts=false&generate_images=true&image_model=black-forest-labs/FLUX.1-schnell" \
  -H 'Content-Type: application/json' \
  -H "X-Image-API-Key: $SILICONFLOW_IMAGE_API_KEY" \
  --data @/tmp/manual_phase3_storyboard.json \
  | tee /tmp/manual_phase3_images_response.json
```

取一次状态：

```bash
curl -s \
  "http://127.0.0.1:8000/api/v1/pipeline/manual-phase3/status?pipeline_id=${PIPELINE_ID}&story_id=manual-acceptance-rainy-teahouse" \
  | tee /tmp/manual_phase3_status_after_images.json
```

人工检查：

- 镜头 1 的首帧图不能是只剩脸的特写；至少要能看见右手扶门、左手信件或油纸伞、上半身和门边
- 镜头 2 的首帧图不能重置成独立人像；应像同场景连续时刻，并且柜台、信件位置和人物朝向有清晰承接
- 两张图的人脸、发型、主衣物轮廓和颜色应保持一致
- 若这轮验收额外接入了角色图 / 场景图参考资产，要检查参考图是否真的帮助了构图，而不是把画面锁死成错误裁切

### 5.3 生成主镜头视频

先把 `image_url` 合并回 storyboard shots：

```bash
jq --argfile status /tmp/manual_phase3_status_after_images.json '
  [.shots[] | . + {image_url: $status.generated_files.images[.shot_id].image_url}]
' /tmp/manual_phase3_storyboard.json > /tmp/manual_phase3_shots_with_images.json
```

然后渲染视频：

```bash
curl -s \
  -X POST \
  "http://127.0.0.1:8000/api/v1/pipeline/manual-phase3/render-video?pipeline_id=${PIPELINE_ID}&story_id=manual-acceptance-rainy-teahouse&video_model=wan2.6-i2v-flash&base_url=${PUBLIC_BASE_URL}" \
  -H 'Content-Type: application/json' \
  -H "X-Video-Provider: dashscope" \
  -H "X-Video-API-Key: $DASHSCOPE_VIDEO_API_KEY" \
  --data @/tmp/manual_phase3_shots_with_images.json \
  | tee /tmp/manual_phase3_video_response.json
```

人工检查：

- 视频动作必须从首帧自然长出来，不能突然冒出首帧没有建立的手、信件、油纸伞或更宽的身体裁切
- 镜头 1 的门口停顿到推门推进动作应完整可读，而不是只有轻微抖动
- 镜头 2 应该像镜头 1 的后续，而不是重新开始摆 pose；放信动作和柜台关系要成立
- 角色脸、头发、主衣物、门口与柜台环境不应发生明显漂移

### 5.4 生成 transition

先确认相邻主镜头视频都已完成，再生成过渡视频。

如果 storyboard 实际产出超过 2 个核心主镜头：

- 先记录这是否属于合理拆分，还是“把简单连续动作拆成了纯脸部/手部特写”
- 若仍继续完成本轮导出验收，需要把所有相邻 shot 的 transition 都补齐后再 concat
- 下面示例先按最理想的 2-shot 样本写法展示

```bash
curl -s \
  -X POST \
  "http://127.0.0.1:8000/api/v1/pipeline/manual-phase3/transitions/generate" \
  -H 'Content-Type: application/json' \
  -H "X-Video-Provider: doubao" \
  -H "X-Video-API-Key: $DOUBAO_VIDEO_API_KEY" \
  -d "$(jq -n \
    --arg pipeline_id "$PIPELINE_ID" \
    --arg story_id "manual-acceptance-rainy-teahouse" \
    '{pipeline_id:$pipeline_id, story_id:$story_id, from_shot_id:"scene1_shot1", to_shot_id:"scene1_shot2", transition_prompt:"镜头衔接保持克制，不要跳出当前剧情。", duration_seconds:2}')" \
  | tee /tmp/manual_phase3_transition.json
```

人工检查：

- transition 应只发生在相邻镜头之间
- 过渡动作应从镜头 1 的尾态自然进入镜头 2 的首态
- 不应突然换衣、换脸、换环境
- 若抽帧失败回退到 storyboard 图，返回结果里应能看到明确诊断信息

### 5.5 导出完整视频

```bash
curl -s \
  -X POST \
  "http://127.0.0.1:8000/api/v1/pipeline/manual-phase3/concat?pipeline_id=${PIPELINE_ID}&story_id=manual-acceptance-rainy-teahouse" \
  -H 'Content-Type: application/json' \
  -d '{"video_urls":[]}' \
  | tee /tmp/manual_phase3_concat.json
```

人工检查：

- 导出顺序必须是 `shot1 -> transition -> shot2`
- 若 transition 缺失，concat 应拒绝而不是静默跳过
- `final_video_url` 应回写到 pipeline 和 story 的恢复态镜像里

## 6. single asset 入口验收

图片单入口：

```bash
curl -s \
  -X POST \
  "http://127.0.0.1:8000/api/v1/image/manual-phase3/generate" \
  -H 'Content-Type: application/json' \
  -H "X-Image-API-Key: $SILICONFLOW_IMAGE_API_KEY" \
  -H "X-LLM-Provider: openai" \
  -H "X-LLM-Model: gpt-4o-mini" \
  -H "X-LLM-API-Key: $OPENAI_API_KEY" \
  -d "$(jq -n --arg story_id 'manual-acceptance-rainy-teahouse' '{story_id:$story_id, shots:[{shot_id:"scene1_shot1", final_video_prompt:"Medium shot. Static camera. Li Ming pushes the wooden door open with one hand and steps inside.", image_prompt:"Medium shot. Li Ming pauses at the doorway with one hand braced on the wooden door."}] }')" \
  | tee /tmp/manual_phase3_single_image.json
```

视频单入口：

- 先把图片入口产出的 `image_url` 填回 shot
- 再调用 `/api/v1/video/{project_id}/generate`

这里要重点看：

- single asset 是否仍走 `StoryContext`
- single asset 的 prompt 是否和 manual pipeline 口径一致
- single asset 是否也带上同样的身份锁、服装锁、动作连续性约束

## 7. auto 入口验收

```bash
curl -s \
  -X POST \
  "http://127.0.0.1:8000/api/v1/pipeline/auto-phase3/auto-generate" \
  -H 'Content-Type: application/json' \
  -d "$(jq -n \
    --arg script "$SCRIPT_TEXT" \
    --arg story_id "manual-acceptance-rainy-teahouse" \
    --arg base_url "$PUBLIC_BASE_URL" \
    '{script:$script, story_id:$story_id, strategy:"chained", provider:"openai", model:"gpt-4o-mini", image_model:"black-forest-labs/FLUX.1-schnell", video_model:"wan2.6-i2v-flash", base_url:$base_url}')" \
  | tee /tmp/auto_phase3_start.json
```

轮询状态：

```bash
AUTO_PIPELINE_ID=$(jq -r '.pipeline_id' /tmp/auto_phase3_start.json)

curl -s \
  "http://127.0.0.1:8000/api/v1/pipeline/auto-phase3/status?pipeline_id=${AUTO_PIPELINE_ID}&story_id=manual-acceptance-rainy-teahouse"
```

人工检查：

- `pipeline.generated_files` 是否按阶段持续增长
- 至少应看到 `storyboard / tts / images / videos / meta`
- chained 模式下，同场景后一张图片是否延续上一张图的状态，而不是重新起 pose

## 8. restore / history 验收

分别取 pipeline 状态和 story：

```bash
curl -s \
  "http://127.0.0.1:8000/api/v1/pipeline/manual-phase3/status?pipeline_id=${PIPELINE_ID}&story_id=manual-acceptance-rainy-teahouse" \
  | tee /tmp/manual_phase3_final_status.json

curl -s \
  "http://127.0.0.1:8000/api/v1/story/manual-acceptance-rainy-teahouse" \
  | tee /tmp/manual_phase3_story.json
```

人工检查：

- `pipeline.generated_files` 是运行期主真相源
- `story.meta.storyboard_generation` 是恢复态镜像层
- `story.meta.storyboard_generation.pipeline_id` 应等于本轮 pipeline id
- `story.meta.storyboard_generation.generated_files.timeline` 应和 pipeline 里的 timeline 一致
- `story.meta.storyboard_generation.final_video_url` 应和 concat 结果一致

## 9. 通过标准

这一轮人工收官建议至少满足：

- auto、manual、single asset、transition、concat、restore 六个入口都实际走过一次
- 首帧图不再频繁出现“只剩脸，但视频又要求半身或手部动作”的冲突
- 手部动作相关道具在首帧里就已经建立，不会等视频开始后再突然出现
- 同场景相邻镜头看起来像连续剧情，而不是两张互不相干的独立宣传图
- 视频动作、服装、脸、环境延续性没有出现一眼可见的突变
- 运行态写回和恢复态镜像在关键字段上保持一致

## 10. 失败记录模板

建议每次人工验收至少记录这几个字段：

- 日期
- story_id
- pipeline_id
- provider / model 组合
- 失败入口
- 失败镜头 id
- 失败类型
- 复现步骤
- 关键截图或视频 URL
- 是否是提示词问题、provider 波动、状态写回问题、还是 restore 问题

只有这份 runbook 被真实执行并留下结论，Phase 3 才能从“最小基线已完成”推进到“人工收官已完成”。
