import asyncio
import base64
import mimetypes

import httpx

from app.core.api_keys import mask_key
from app.services.video_providers.base import BaseVideoProvider


async def _to_data_url(image_url: str) -> str:
    """若 image_url 是本地/内网地址，先下载再转为 base64 data URL；否则原样返回。"""
    from urllib.parse import urlparse
    parsed = urlparse(image_url)
    host = parsed.hostname or ""
    is_local = host in ("localhost", "127.0.0.1", "0.0.0.0") or host.startswith("192.168.") or host.startswith("10.")
    if not is_local:
        return image_url
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(image_url)
        resp.raise_for_status()
    mime = resp.headers.get("content-type") or mimetypes.guess_type(parsed.path)[0] or "image/png"
    mime = mime.split(";")[0].strip()
    b64 = base64.b64encode(resp.content).decode()
    return f"data:{mime};base64,{b64}"

DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
_SUBMIT_PATH = "/contents/generations/tasks"
_POLL_PATH = "/contents/generations/tasks/{task_id}"


class DoubaoVideoProvider(BaseVideoProvider):
    """字节跳动豆包 Seedance 图生视频（火山方舟 Ark API）。"""

    async def generate(self, image_url: str, prompt: str, model: str, api_key: str, base_url: str) -> str:
        effective_base = base_url or DEFAULT_BASE_URL
        async with httpx.AsyncClient(timeout=30) as client:
            task_id = await self._submit(client, image_url, prompt, model, api_key, effective_base)
        async with httpx.AsyncClient(timeout=30) as client:
            return await self._poll(client, task_id, api_key, effective_base)

    async def _submit(self, client: httpx.AsyncClient, image_url: str, prompt: str, model: str, api_key: str, base_url: str) -> str:
        url = f"{base_url}{_SUBMIT_PATH}"
        resolved_image = await _to_data_url(image_url)
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": resolved_image}},
                ],
            },
        )
        print(f"[VIDEO DOUBAO SUBMIT] status={resp.status_code} key={mask_key(api_key)} base={base_url}")
        if not resp.is_success:
            raise RuntimeError(f"Doubao 视频任务提交错误 {resp.status_code}: {resp.text[:200]}")
        try:
            body = resp.json()
        except Exception as e:
            raise RuntimeError(f"Doubao 提交响应 JSON 解析失败: {e!r} | 原始响应: {resp.text[:200]}") from e
        task_id = body.get("id")
        if not task_id:
            raise RuntimeError(f"Doubao 提交响应缺少 id: {resp.text[:200]}")
        return task_id

    async def _poll(self, client: httpx.AsyncClient, task_id: str, api_key: str, base_url: str, timeout: int = 300) -> str:
        url = f"{base_url}{_POLL_PATH.format(task_id=task_id)}"
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            await asyncio.sleep(10)
            resp = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
            if not resp.is_success:
                raise RuntimeError(f"Doubao 视频任务查询错误 {resp.status_code}: {resp.text[:200]}")
            try:
                data = resp.json()
            except Exception as e:
                raise RuntimeError(f"Doubao 响应 JSON 解析失败: {e!r} | 原始响应: {resp.text[:200]}") from e
            status = data.get("status")
            if not status:
                raise RuntimeError(f"Doubao 响应缺少 status 字段: {resp.text[:200]}")
            if status == "succeeded":
                content = data.get("content")
                video_url = content.get("video_url") if isinstance(content, dict) else None
                if not video_url:
                    raise RuntimeError(f"Doubao 任务成功但缺少 video_url: {resp.text[:200]}")
                return video_url
            if status == "failed":
                raise RuntimeError(f"Doubao 视频任务失败: {data.get('error', status)}")
        raise TimeoutError(f"Doubao 视频任务超时: {task_id}")
