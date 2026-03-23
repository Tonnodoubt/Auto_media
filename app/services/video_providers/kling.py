import asyncio
import time

import httpx
import jwt

from app.services.video_providers.base import BaseVideoProvider

DEFAULT_BASE_URL = "https://api.klingai.com"
_SUBMIT_PATH = "/v1/videos/image2video"
_POLL_PATH = "/v1/videos/image2video/{task_id}"


class KlingVideoProvider(BaseVideoProvider):
    """
    快手可灵 Kling 图生视频。

    API Key 格式：access_key_id:access_key_secret
    （在可灵开放平台 → API Key 管理页面获取两个字段，用冒号拼接）
    """

    def _make_token(self, api_key: str) -> str:
        if ":" not in api_key:
            raise ValueError("Kling API Key 格式应为 access_key_id:access_key_secret")
        access_key_id, secret_key = api_key.split(":", 1)
        payload = {
            "iss": access_key_id,
            "exp": int(time.time()) + 1800,
            "nbf": int(time.time()) - 5,
        }
        return jwt.encode(payload, secret_key, algorithm="HS256")

    async def generate(self, image_url: str, prompt: str, model: str, api_key: str, base_url: str) -> str:
        token = self._make_token(api_key)
        effective_base = base_url or DEFAULT_BASE_URL
        async with httpx.AsyncClient(timeout=30) as client:
            task_id = await self._submit(client, image_url, prompt, model, token, effective_base)
        async with httpx.AsyncClient(timeout=30) as client:
            return await self._poll(client, task_id, token, effective_base)

    async def _submit(self, client: httpx.AsyncClient, image_url: str, prompt: str, model: str, token: str, base_url: str) -> str:
        url = f"{base_url}{_SUBMIT_PATH}"
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "model_name": model or "kling-v2-master",
                "image": image_url,
                "prompt": prompt,
                "duration": 5,
                "mode": "std",
            },
        )
        print(f"[VIDEO KLING SUBMIT] status={resp.status_code} base={base_url}")
        if not resp.is_success:
            raise RuntimeError(f"Kling 视频任务提交错误 {resp.status_code}: {resp.text[:200]}")
        return resp.json()["data"]["task_id"]

    async def _poll(self, client: httpx.AsyncClient, task_id: str, token: str, base_url: str, timeout: int = 300) -> str:
        url = f"{base_url}{_POLL_PATH.format(task_id=task_id)}"
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            await asyncio.sleep(5)
            resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
            if not resp.is_success:
                raise RuntimeError(f"Kling 视频任务查询错误 {resp.status_code}: {resp.text[:200]}")
            try:
                body = resp.json()
            except Exception as e:
                raise RuntimeError(f"Kling 响应 JSON 解析失败: {e!r} | 原始响应: {resp.text[:200]}") from e
            data = body.get("data")
            if not isinstance(data, dict):
                raise RuntimeError(f"Kling 响应缺少 data 字段: {resp.text[:200]}")
            status = data.get("task_status")
            if not status:
                raise RuntimeError(f"Kling 响应缺少 task_status 字段: {resp.text[:200]}")
            if status == "succeed":
                task_result = data.get("task_result")
                videos = task_result.get("videos") if isinstance(task_result, dict) else None
                if not isinstance(videos, list) or not videos:
                    raise RuntimeError(f"Kling 任务成功但 videos 为空或缺失: {resp.text[:200]}")
                video_url = videos[0].get("url")
                if not video_url:
                    raise RuntimeError(f"Kling 任务成功但缺少 video url: {resp.text[:200]}")
                return video_url
            if status == "failed":
                raise RuntimeError(f"Kling 视频任务失败: {data.get('task_status_msg', status)}")
        raise TimeoutError(f"Kling 视频任务超时: {task_id}")
