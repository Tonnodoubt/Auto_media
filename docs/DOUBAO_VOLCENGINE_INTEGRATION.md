# 接入豆包（字节跳动）图片 & 视频生成 — 火山方舟 Ark API

本文档描述如何将字节跳动的 **豆包 Doubao** 图片生成（Seedream）和视频生成（Seedance）能力通过 **火山引擎 · 火山方舟 Ark 平台** 接入 Auto_media 项目。

---

## 1. 平台概览

| 项目 | 说明 |
|------|------|
| 平台名称 | 火山方舟（Volcano Ark） |
| 提供方 | 字节跳动 · 火山引擎 |
| Base URL | `https://ark.cn-beijing.volces.com/api/v3` |
| 鉴权方式 | `Authorization: Bearer <ARK_API_KEY>` |
| 兼容协议 | OpenAI 兼容（图片生成走 `/images/generations`） |
| 控制台 | https://console.volcengine.com/ark/ |
| API Key 管理 | https://console.volcengine.com/ark/region:ark+cn-beijing/apikey |
| 官方文档 | https://www.volcengine.com/docs/82379?lang=zh |

---

## 2. 前置准备

1. 注册火山引擎账号：https://www.volcengine.com/
2. 进入 **火山方舟控制台** → **API Key 管理** 创建 API Key
3. 记录 `ARK_API_KEY`，后续所有请求均使用此 Key

---

## 3. 图片生成 — Seedream

### 3.1 可用模型

| 模型 | 模型 ID | 说明 |
|------|---------|------|
| Seedream 3.0 | `doubao-seedream-3-0-t2i` | 基础版 |
| Seedream 4.0 | `doubao-seedream-4-0-250828` | |
| Seedream 4.5 | `doubao-seedream-4-5-251128` | 推荐 |
| Seedream 5.0 Lite | `doubao-seedream-5-0-lite` | 最新 |

> 模型 ID 可能随版本迭代更新，请以 [模型列表文档](https://www.volcengine.com/docs/82379/1330310) 为准。

### 3.2 API 接口

**Endpoint:** `POST https://ark.cn-beijing.volces.com/api/v3/images/generations`

**请求：**
```json
{
  "model": "doubao-seedream-4-5-251128",
  "prompt": "一只可爱的小猫坐在花园里，阳光明媚",
  "n": 1,
  "size": "1280x720",
  "response_format": "url"
}
```

**响应（OpenAI 标准格式）：**
```json
{
  "data": [
    { "url": "https://ark-content-generation-xxx/image.png" }
  ]
}
```

### 3.3 尺寸参数

- 简写：`1K` / `2K` / `4K`
- 精确像素：`1280x720`、`1024x1024`、`2048x2048` 等
- 宽高比范围 `[1/16, 16]`，总像素范围 `[1024×1024, 4096×4096]`

### 3.4 ⚠️ 与现有系统的兼容性问题

**当前项目的图片生成系统存在以下架构限制，必须先解决才能正确接入：**

1. **响应格式不兼容：** `app/services/image.py:38` 硬编码了 SiliconFlow 的响应格式
   `resp.json()["images"][0]["url"]`，火山方舟返回的是 OpenAI 标准格式
   `resp.json()["data"][0]["url"]`，直接使用会报 `KeyError`。

2. **没有 Image Provider 抽象：** 与视频模块不同，图片生成没有工厂模式、没有
   `X-Image-Provider` header、没有 provider 路由。后端无法区分不同的图片供应商。

3. **前端 IMAGE_PROVIDERS 只做 UI 填充：** 前端的 provider 下拉框只自动填入
   `baseUrl`、`apiKey`、`model`，不会发送 provider 标识到后端。

**结论：仅在前端 `IMAGE_PROVIDERS` 添加 doubao 选项是不够的，还需要修改后端 `image.py` 的响应解析逻辑。**

### 3.5 Python 示例

```python
# 方式一：OpenAI SDK
from openai import AsyncOpenAI

client = AsyncOpenAI(
    api_key="YOUR_ARK_API_KEY",
    base_url="https://ark.cn-beijing.volces.com/api/v3"
)

response = await client.images.generate(
    model="doubao-seedream-4-5-251128",
    prompt="一只可爱的小猫",
    n=1,
    size="1280x720"
)
image_url = response.data[0].url

# 方式二：httpx 直接调用（项目现有风格）
import httpx

async with httpx.AsyncClient(timeout=60) as client:
    resp = await client.post(
        "https://ark.cn-beijing.volces.com/api/v3/images/generations",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "doubao-seedream-4-5-251128",
            "prompt": "一只可爱的小猫",
            "n": 1,
            "image_size": "1280x720"
        },
    )
    # 注意：火山方舟用 data[].url，不是 images[].url
    image_url = resp.json()["data"][0]["url"]
```

---

## 4. 视频生成 — Seedance

### 4.1 可用模型

| 模型 | 模型 ID | 说明 |
|------|---------|------|
| Seedance 1.0 Lite | `seedance-1-0-lite` | 轻量 |
| Seedance 1.5 Pro | `doubao-seedance-1-5-pro-251215` | |
| Seedance 2.0 | `seedance-2.0` | 最新旗舰 |

### 4.2 API 接口 — 异步任务模式

视频生成采用 **提交 → 轮询** 的异步模式，与项目中 DashScope / Kling 的模式完全一致。

#### 提交任务

**Endpoint:** `POST https://ark.cn-beijing.volces.com/api/v3/contents/generations`

> ⚠️ 此端点路径来自社区文档和第三方教程，官方文档页面内容未完全渲染。
> 实际接入时请以 [官方视频生成 API 文档](https://www.volcengine.com/docs/82379/1520757) 为准确认。

**图生视频请求：**
```json
{
  "model": "seedance-2.0",
  "content": [
    {
      "type": "image_url",
      "image_url": { "url": "https://example.com/input.png" }
    },
    {
      "type": "text",
      "text": "让画面中的猫缓慢走动，阳光微微变化"
    }
  ],
  "duration": 5,
  "aspect_ratio": "16:9"
}
```

**文生视频请求：**
```json
{
  "model": "seedance-2.0",
  "content": [
    {
      "type": "text",
      "text": "一只金毛犬在沙滩上奔跑，海浪拍打岸边"
    }
  ],
  "duration": 5,
  "aspect_ratio": "16:9"
}
```

**提交响应：**
```json
{
  "id": "cgt-20250704191750-xxxxx",
  "model": "seedance-2.0",
  "status": "queued"
}
```

#### 查询任务状态

**Endpoint:** `GET https://ark.cn-beijing.volces.com/api/v3/contents/generations/{task_id}`

**完成响应：**
```json
{
  "id": "cgt-20250704191750-xxxxx",
  "status": "completed",
  "content": {
    "video_url": "https://ark-content-generation-xxx/video.mp4"
  }
}
```

**状态枚举：** `queued` → `processing` → `completed` / `failed`

### 4.3 与现有系统的兼容性

**视频模块已有完善的 Provider 工厂模式，接入顺畅：**

- `BaseVideoProvider` 接口 → 新建 `DoubaoVideoProvider` 实现
- `get_video_provider()` 工厂 → 添加 `"doubao"` 分支
- `video_config_dep()` → 添加 `"doubao"` 到合法 provider 列表
- 前端 `VIDEO_PROVIDERS` → 添加选项，`X-Video-Provider: doubao` 自动传递

**数据流完整路径（已验证可行）：**
```
前端选择 doubao → X-Video-Provider: doubao (header)
→ video_config_dep() 识别 doubao，回退到 .env DOUBAO_API_KEY
→ video.generate_videos_batch() 传入 video_provider="doubao"
→ get_video_provider("doubao") 返回 DoubaoVideoProvider
→ provider.generate() 调用火山方舟 API
→ 下载视频到 media/videos/
```

### 4.4 轮询最佳实践

- 推荐轮询间隔：**10 秒**（项目现有 provider 为 5 秒，Seedance 通常需 30-120 秒）
- 超时上限 **300 秒**（与现有 provider 一致）

---

## 5. 项目接入实施步骤

### 5.1 后端 — 配置层

**`app/core/config.py`** — 在 `Settings` 类中添加：
```python
# 豆包 / 火山方舟 (图片 + 视频生成)
doubao_api_key: str = ""
doubao_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
```

**`.env.example`** — 添加：
```bash
# 豆包 / 火山方舟 Ark (图片生成 + 视频生成)
DOUBAO_API_KEY=
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
```

---

### 5.2 后端 — 视频 Provider 实现（新建文件）

**新建 `app/services/video_providers/doubao.py`：**

```python
import asyncio
import httpx
from app.core.api_keys import mask_key
from app.services.video_providers.base import BaseVideoProvider

DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
_SUBMIT_PATH = "/contents/generations"
_POLL_PATH = "/contents/generations/{task_id}"


class DoubaoVideoProvider(BaseVideoProvider):
    """字节跳动豆包 Seedance 图生视频（火山方舟 Ark API）。"""

    async def generate(
        self, image_url: str, prompt: str, model: str, api_key: str, base_url: str
    ) -> str:
        effective_base = base_url or DEFAULT_BASE_URL
        async with httpx.AsyncClient(timeout=30) as client:
            task_id = await self._submit(
                client, image_url, prompt, model, api_key, effective_base
            )
        async with httpx.AsyncClient(timeout=30) as client:
            return await self._poll(client, task_id, api_key, effective_base)

    async def _submit(
        self,
        client: httpx.AsyncClient,
        image_url: str,
        prompt: str,
        model: str,
        api_key: str,
        base_url: str,
    ) -> str:
        url = f"{base_url}{_SUBMIT_PATH}"
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model or "seedance-2.0",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": prompt},
                ],
                "duration": 5,
            },
        )
        print(
            f"[VIDEO DOUBAO SUBMIT] status={resp.status_code} "
            f"key={mask_key(api_key)} base={base_url}"
        )
        if not resp.is_success:
            raise RuntimeError(
                f"Doubao 视频任务提交错误 {resp.status_code}: {resp.text[:200]}"
            )
        try:
            body = resp.json()
        except Exception as e:
            raise RuntimeError(
                f"Doubao 提交响应 JSON 解析失败: {e!r} | 原始响应: {resp.text[:200]}"
            ) from e
        task_id = body.get("id")
        if not task_id:
            raise RuntimeError(f"Doubao 提交响应缺少 id: {resp.text[:200]}")
        return task_id

    async def _poll(
        self,
        client: httpx.AsyncClient,
        task_id: str,
        api_key: str,
        base_url: str,
        timeout: int = 300,
    ) -> str:
        url = f"{base_url}{_POLL_PATH.format(task_id=task_id)}"
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            await asyncio.sleep(10)
            resp = await client.get(
                url, headers={"Authorization": f"Bearer {api_key}"}
            )
            if not resp.is_success:
                raise RuntimeError(
                    f"Doubao 视频任务查询错误 {resp.status_code}: {resp.text[:200]}"
                )
            try:
                data = resp.json()
            except Exception as e:
                raise RuntimeError(
                    f"Doubao 响应 JSON 解析失败: {e!r} | 原始响应: {resp.text[:200]}"
                ) from e
            status = data.get("status")
            if not status:
                raise RuntimeError(
                    f"Doubao 响应缺少 status 字段: {resp.text[:200]}"
                )
            if status == "completed":
                content = data.get("content")
                video_url = content.get("video_url") if isinstance(content, dict) else None
                if not video_url:
                    raise RuntimeError(
                        f"Doubao 任务成功但缺少 video_url: {resp.text[:200]}"
                    )
                return video_url
            if status == "failed":
                raise RuntimeError(
                    f"Doubao 视频任务失败: {data.get('error', status)}"
                )
        raise TimeoutError(f"Doubao 视频任务超时: {task_id}")
```

---

### 5.3 后端 — 注册视频 Provider 工厂

**`app/services/video_providers/factory.py`** — 添加 doubao 分支：

```python
def get_video_provider(provider: str) -> BaseVideoProvider:
    name = (provider or "dashscope").lower()

    if name == "kling":
        from app.services.video_providers.kling import KlingVideoProvider
        return KlingVideoProvider()

    if name == "doubao":                                          # ← 新增
        from app.services.video_providers.doubao import DoubaoVideoProvider
        return DoubaoVideoProvider()

    from app.services.video_providers.dashscope import DashScopeVideoProvider
    return DashScopeVideoProvider()
```

---

### 5.4 后端 — API Key 路由

**`app/core/api_keys.py`** — `video_config_dep()` 函数中修改两处：

```python
# 1. 扩展 provider 白名单（第 211 行附近）
if video_provider not in ("dashscope", "kling", "doubao"):   # ← 加 "doubao"
    raise HTTPException(...)

# 2. 添加 provider-specific .env 回退（第 224 行附近 elif 链）
elif video_provider == "doubao":                              # ← 新增
    api_key = keys.video_api_key or _cfg.doubao_api_key
    base_url = _cfg.doubao_base_url
```

---

### 5.5 后端 — 图片生成响应格式兼容

**`app/services/image.py`** — 修改 `generate_image()` 和 `generate_character_image()` 中的响应解析。

**当前代码（第 38 行、第 95 行）：**
```python
image_url = resp.json()["images"][0]["url"]
```

**改为兼容两种格式：**
```python
body = resp.json()
if "images" in body:
    image_url = body["images"][0]["url"]       # SiliconFlow 格式
elif "data" in body:
    image_url = body["data"][0]["url"]         # OpenAI 标准格式（火山方舟等）
else:
    raise RuntimeError(f"图片生成 API 响应格式未知: {list(body.keys())}")
```

> **需要改两处：** `generate_image()` 第 38 行 和 `generate_character_image()` 第 95 行。

---

### 5.6 前端 — 添加 Provider 选项

**`frontend/src/stores/settings.js`：**

在 `IMAGE_PROVIDERS` 数组中（`custom` 之前）添加：
```javascript
{
  id: 'doubao', label: '豆包 Doubao (火山方舟)',
  baseUrl: 'https://ark.cn-beijing.volces.com/api/v3',
  models: [
    { id: 'doubao-seedream-5-0-lite',    label: 'Seedream 5.0 Lite（最新）' },
    { id: 'doubao-seedream-4-5-251128',  label: 'Seedream 4.5' },
    { id: 'doubao-seedream-4-0-250828',  label: 'Seedream 4.0' },
    { id: 'custom', label: '自定义...' },
  ],
},
```

在 `VIDEO_PROVIDERS` 数组中（`custom` 之前）添加：
```javascript
{
  id: 'doubao', label: '豆包 Seedance (火山方舟)',
  baseUrl: 'https://ark.cn-beijing.volces.com/api/v3',
  models: [
    { id: 'seedance-2.0',                     label: 'Seedance 2.0（旗舰）' },
    { id: 'doubao-seedance-1-5-pro-251215',   label: 'Seedance 1.5 Pro' },
    { id: 'seedance-1-0-lite',                label: 'Seedance 1.0 Lite（轻量）' },
    { id: 'custom', label: '自定义...' },
  ],
},
```

---

## 6. 需修改文件清单

| # | 文件 | 操作 | 说明 | 阻塞等级 |
|---|------|------|------|----------|
| 1 | `app/core/config.py` | 修改 | 添加 `doubao_api_key` / `doubao_base_url` | 必须 |
| 2 | `.env.example` | 修改 | 添加 `DOUBAO_API_KEY` / `DOUBAO_BASE_URL` | 必须 |
| 3 | `app/services/video_providers/doubao.py` | **新建** | Seedance 视频 provider 实现 | 必须 |
| 4 | `app/services/video_providers/factory.py` | 修改 | 注册 doubao provider | 必须 |
| 5 | `app/core/api_keys.py` | 修改 | `video_config_dep` 添加 doubao 分支 | 必须 |
| 6 | `app/services/image.py` | 修改 | **兼容 `data[].url` 响应格式**（改两处） | **必须** |
| 7 | `frontend/src/stores/settings.js` | 修改 | 添加 doubao 到 IMAGE/VIDEO_PROVIDERS | 必须 |

### 端到端数据流验证

#### 视频生成链路 ✅

```
用户选择 video provider = doubao
→ 前端 settings.videoProvider = "doubao"
→ getHeaders() 发送 X-Video-Provider: doubao
→ video_config_dep() 匹配 "doubao"，读取 DOUBAO_API_KEY
→ video.generate_videos_batch(video_provider="doubao")
→ get_video_provider("doubao") → DoubaoVideoProvider
→ provider.generate(image_url, prompt, model, api_key, base_url)
→ POST /contents/generations → 轮询 → 返回 video_url
→ 下载到 media/videos/{shot_id}.mp4 ✅
```

#### 图片生成链路 ⚠️ (需 5.5 步修复后才能工作)

```
用户选择 image provider = doubao
→ 前端 settings.imageProvider = "doubao"
→ 前端自动填入 imageBaseUrl = https://ark.cn-beijing.volces.com/api/v3
→ getHeaders() 发送 X-Image-Base-URL + X-Image-API-Key
→ image_config_dep() 返回 {image_api_key, image_base_url}
  （注意：后端不知道这是 doubao，只看到自定义 base_url）
→ image.generate_image() POST {base_url}/images/generations
→ 火山方舟返回 {"data": [{"url": "..."}]}
→ ❌ resp.json()["images"][0]["url"] → KeyError!  （未修复时）
→ ✅ 兼容解析后正常工作                              （修复后）
```

---

## 7. 参考链接

- [火山方舟文档中心](https://www.volcengine.com/docs/82379?lang=zh)
- [Seedream 图片生成 API](https://www.volcengine.com/docs/82379/1541523)
- [Seedream 4.5 SDK 示例](https://www.volcengine.com/docs/82379/1824121)
- [视频生成 API](https://www.volcengine.com/docs/82379/1366799)
- [创建视频生成任务 API](https://www.volcengine.com/docs/82379/1520757)
- [模型列表](https://www.volcengine.com/docs/82379/1330310)
- [快速入门](https://www.volcengine.com/docs/82379/1399008)
- [Seedance 2.0 API Guide (NxCode)](https://www.nxcode.io/resources/news/seedance-2-0-api-guide-pricing-setup-2026)
- [Seedance 2.0 API (LaoZhang)](https://blog.laozhang.ai/en/posts/seedance-2-api)
