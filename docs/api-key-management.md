# API Key 管理指南

> 更新日期：2026-03-21

---

## 概述

AutoMedia 采用**三段式 Key 回退链**：

```
前端 Header → .env 环境变量 → HTTP 400 错误
```

前端设置页面提供**全局 + 专用（开关）**配置体系，让不同服务（文本/图片/视频）可以使用独立的 API Key 和服务商，也可以全部共用同一个全局 Key。

---

## 前端配置体系

### 全局配置（必填）

| 字段 | 说明 |
|------|------|
| **服务商** | 从预设列表选择（Claude、OpenAI、SiliconFlow 等）或自定义 |
| **API Key** | 全局 API Key，所有未开专用开关的服务均使用此 Key |
| **Base URL** | 全局 API 地址，支持中转/代理地址 |

### 专用配置（可选，默认关闭）

每类服务有独立开关，**关闭时继承全局配置，开启后使用专用配置**：

| 服务 | 开关 | 专用字段 |
|------|------|---------|
| **文本 / LLM** | `textEnabled` | textProvider、textApiKey、textBaseUrl、textModel |
| **图片生成** | `imageEnabled` | imageApiKey、imageBaseUrl、imageModel |
| **视频生成** | `videoEnabled` | videoApiKey、videoBaseUrl、videoModel |

### 继承逻辑

| 有效值 Getter | 逻辑 |
|--------------|------|
| `effectiveLlmApiKey` | textEnabled 且有值 → textApiKey；否则 → apiKey |
| `effectiveLlmBaseUrl` | textEnabled 且有值 → textBaseUrl；否则 → llmBaseUrl |
| `effectiveLlmProvider` | textEnabled 且有值 → textProvider；否则 → provider |
| `effectiveImageApiKey` | imageEnabled 且有值 → imageApiKey；否则 → apiKey |
| `effectiveImageBaseUrl` | imageEnabled 且有值 → imageBaseUrl；否则 → llmBaseUrl |
| `effectiveVideoApiKey` | videoEnabled 且有值 → videoApiKey；否则 → apiKey |
| `effectiveVideoBaseUrl` | videoEnabled 且有值 → videoBaseUrl；否则 → llmBaseUrl |

---

## 请求头规范

前端所有请求通过 `story.js` 的 `getHeaders()` 统一注入：

| HTTP Header | 对应 Getter | 说明 |
|-------------|-------------|------|
| `X-LLM-API-Key` | effectiveLlmApiKey | LLM 服务 Key |
| `X-LLM-Base-URL` | effectiveLlmBaseUrl | LLM 服务地址 |
| `X-LLM-Provider` | effectiveLlmProvider | LLM 服务商名称 |
| `X-Image-API-Key` | effectiveImageApiKey | 图片生成 Key |
| `X-Image-Base-URL` | effectiveImageBaseUrl | 图片生成服务地址 |
| `X-Video-API-Key` | effectiveVideoApiKey | 视频生成 Key |
| `X-Video-Base-URL` | effectiveVideoBaseUrl | 视频生成服务地址 |

空值字段不发送 header，由后端回退到 `.env`。

---

## 后端三段式回退链

后端通过 `app/core/api_keys.py` 统一处理，各类 Key 的完整回退链：

### LLM Key

```
X-LLM-API-Key header → 无自动回退（各 provider factory 自行回退 .env key）
```

LLM Key 的回退在 `app/services/llm/factory.py` 中处理：
- `api_key or settings.anthropic_api_key`（Claude）
- `api_key or settings.openai_api_key`（OpenAI）
- 以此类推

### Image Key

```
X-Image-API-Key header → .env SILICONFLOW_API_KEY → HTTP 400
```

### Image Base URL

```
X-Image-Base-URL header → .env SILICONFLOW_BASE_URL（https://api.siliconflow.cn/v1）
```

### Video Key

```
X-Video-API-Key header → .env DASHSCOPE_API_KEY → HTTP 400
```

### Video Base URL

```
X-Video-Base-URL header → .env DASHSCOPE_BASE_URL（https://dashscope.aliyuncs.com/api/v1）
```

---

## .env 配置参考

```bash
# LLM providers
ANTHROPIC_API_KEY=sk-ant-xxx
OPENAI_API_KEY=sk-xxx
QWEN_API_KEY=sk-xxx
ZHIPU_API_KEY=xxx
GEMINI_API_KEY=xxx

# 图片生成（SiliconFlow）
SILICONFLOW_API_KEY=sk-xxx
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1   # 可选，有默认值

# 视频生成（DashScope）
DASHSCOPE_API_KEY=sk-xxx
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/api/v1  # 可选，有默认值
```

---

## FastAPI Depends 模式

后端 router 统一通过 `Depends` 注入 Key，无需每个端点重复提取：

```python
# 图片生成端点
@router.post(...)
async def generate_image(image_config: dict = Depends(image_config_dep)):
    results = await generate_images_batch(..., **image_config)

# 视频生成端点
@router.post(...)
async def generate_video(video_config: dict = Depends(video_config_dep)):
    results = await generate_videos_batch(..., **video_config)

# LLM 端点
@router.post(...)
async def generate_outline(llm: dict = Depends(llm_config_dep)):
    provider = llm["provider"] or "claude"
    shots, usage = await parse_script_to_storyboard(..., api_key=llm["api_key"], base_url=llm["base_url"])
```

各 dep 函数返回的 dict：

| Dep 函数 | 返回字段 |
|----------|---------|
| `image_config_dep` | `image_api_key`, `image_base_url` |
| `video_config_dep` | `video_api_key`, `video_base_url` |
| `llm_config_dep` | `api_key`, `base_url`, `provider` |

---

## Key 安全措施

- **日志脱敏**：`mask_key()` 函数，只显示 `sk-a...xxxx` 格式，不泄露完整 Key
- **前置校验**：Key 缺失时在服务调用前返回 HTTP 400，不发起外部 API 请求
- **Header 传输**：所有 Key 通过 HTTP Header 传输，不经过 URL Query Param（避免被日志记录）

---

## 典型配置场景

### 场景 1：全部用 SiliconFlow

在设置页：
- 全局：服务商选 SiliconFlow，填写 SiliconFlow API Key 和 `https://api.siliconflow.cn/v1`
- 所有专用开关关闭

所有服务（文本/图片/视频）均使用同一个 Key 和 Base URL，由各自的后端服务适配接口路径。

> **注意**：SiliconFlow 不提供视频生成，视频服务需在 `.env` 配置 `DASHSCOPE_API_KEY` 或开启视频专用配置。

### 场景 2：文本用 Claude，图片用 SiliconFlow，视频用 DashScope

- 全局：服务商 Claude，填写 Anthropic Key
- 图片专用：开启开关，填写 SiliconFlow Key + `https://api.siliconflow.cn/v1`
- 视频专用：开启开关，填写 DashScope Key + `https://dashscope.aliyuncs.com/api/v1`

### 场景 3：全部使用 .env 配置（生产环境）

前端设置页不填写任何 Key，在 `.env` 中配置所有服务的 Key，前端 Header 为空，后端自动回退到 `.env`。

---

## 故障排查

| 错误 | 原因 | 解决 |
|------|------|------|
| HTTP 400：图片生成 API Key 未配置 | 前端未填图片 Key 且 `.env` 无 `SILICONFLOW_API_KEY` | 在设置页开启图片专用并填写 Key，或配置 `.env` |
| HTTP 400：视频生成 API Key 未配置 | 同上，视频 Key 缺失 | 在设置页开启视频专用并填写 Key，或配置 `.env` |
| HTTP 401：Api key is invalid | Key 正确格式但服务商拒绝（Key 与 Base URL 不匹配） | 确认 Key 与 Base URL 属于同一服务商 |
| 使用了错误的 Key | 全局 Key 是 Anthropic Key，但图片服务收到了它 | 开启图片专用开关，填写正确的图片服务 Key |

---

## 相关文件

| 文件 | 作用 |
|------|------|
| `app/core/api_keys.py` | Key 提取、resolve、脱敏、Depends 函数 |
| `app/core/config.py` | `.env` 配置映射（pydantic Settings） |
| `app/services/llm/factory.py` | LLM Provider 工厂，含 Key 回退 |
| `app/services/image.py` | 图片生成服务，接受 `image_api_key`/`image_base_url` |
| `app/services/video.py` | 视频生成服务，接受 `video_api_key`/`video_base_url` |
| `frontend/src/stores/settings.js` | 前端 Pinia store，含全局/专用配置 + getters |
| `frontend/src/views/SettingsView.vue` | 设置页面 UI |
| `frontend/src/api/story.js` | `getHeaders()` 统一注入 7 个 Key headers |
