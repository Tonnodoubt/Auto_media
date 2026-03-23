import asyncio

import httpx

from app.core.api_keys import mask_key
from app.services.video_providers.base import BaseVideoProvider

DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
_SUBMIT_PATH = "/contents/generations"
_POLL_PATH = "/contents/generations/{task_id}"


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
                "aspect_ratio": "16:9",
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
            if status == "completed":
                content = data.get("content")
                video_url = content.get("video_url") if isinstance(content, dict) else None
                if not video_url:
                    raise RuntimeError(f"Doubao 任务成功但缺少 video_url: {resp.text[:200]}")
                return video_url
            if status == "failed":
                raise RuntimeError(f"Doubao 视频任务失败: {data.get('error', status)}")
        raise TimeoutError(f"Doubao 视频任务超时: {task_id}")
