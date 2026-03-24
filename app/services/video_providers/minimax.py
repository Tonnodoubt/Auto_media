import asyncio

import httpx

from app.services.video_providers.base import BaseVideoProvider

DEFAULT_BASE_URL = "https://api.minimaxi.chat"
_SUBMIT_PATH = "/v1/video_generation"
_POLL_PATH = "/v1/query/video_generation"
_FILE_PATH = "/v1/files/retrieve"


class MinimaxVideoProvider(BaseVideoProvider):
    """
    MiniMax 海螺视频 图生视频（Hailuo Video）。

    文档: https://platform.minimaxi.com/document/video-01
    API Key 在 MiniMax 开放平台获取。
    """

    async def generate(self, image_url: str, prompt: str, model: str, api_key: str, base_url: str) -> str:
        effective_base = (base_url or DEFAULT_BASE_URL).rstrip("/")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=60) as client:
            task_id = await self._submit(client, image_url, prompt, model or "video-01", headers, effective_base)
            file_id = await self._poll(client, task_id, headers, effective_base)
            return await self._retrieve_url(client, file_id, headers, effective_base)

    async def _submit(self, client: httpx.AsyncClient, image_url: str, prompt: str, model: str, headers: dict, base_url: str) -> str:
        # 如果是本地地址，先转 base64
        from app.services.video_providers.doubao import _to_data_url
        resolved_image = await _to_data_url(image_url)

        url = f"{base_url}{_SUBMIT_PATH}"
        resp = await client.post(
            url,
            headers=headers,
            json={
                "model": model,
                "prompt": prompt,
                "first_frame_image": resolved_image,
            },
        )
        print(f"[VIDEO MINIMAX SUBMIT] status={resp.status_code} base={base_url}")
        if not resp.is_success:
            raise RuntimeError(f"MiniMax 视频任务提交错误 {resp.status_code}: {resp.text[:200]}")
        try:
            body = resp.json()
        except Exception as e:
            raise RuntimeError(f"MiniMax 提交响应 JSON 解析失败: {e!r} | 原始响应: {resp.text[:200]}") from e
        if body.get("base_resp", {}).get("status_code", 0) != 0:
            raise RuntimeError(f"MiniMax 提交失败: {body.get('base_resp', {}).get('status_msg', body)}")
        task_id = body.get("task_id")
        if not task_id:
            raise RuntimeError(f"MiniMax 提交响应缺少 task_id: {resp.text[:200]}")
        return task_id

    async def _poll(self, client: httpx.AsyncClient, task_id: str, headers: dict, base_url: str, timeout: int = 300) -> str:
        url = f"{base_url}{_POLL_PATH}"
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            await asyncio.sleep(5)
            resp = await client.get(url, params={"task_id": task_id}, headers=headers)
            if not resp.is_success:
                raise RuntimeError(f"MiniMax 视频任务查询错误 {resp.status_code}: {resp.text[:200]}")
            try:
                data = resp.json()
            except Exception as e:
                raise RuntimeError(f"MiniMax 响应 JSON 解析失败: {e!r} | 原始响应: {resp.text[:200]}") from e
            status = data.get("status")
            if not status:
                raise RuntimeError(f"MiniMax 响应缺少 status 字段: {resp.text[:200]}")
            if status == "Success":
                file_id = data.get("file_id")
                if not file_id:
                    raise RuntimeError(f"MiniMax 任务成功但缺少 file_id: {resp.text[:200]}")
                return file_id
            if status == "Fail":
                raise RuntimeError(f"MiniMax 视频任务失败: {data.get('base_resp', {}).get('status_msg', status)}")
        raise TimeoutError(f"MiniMax 视频任务超时: {task_id}")

    async def _retrieve_url(self, client: httpx.AsyncClient, file_id: str, headers: dict, base_url: str) -> str:
        url = f"{base_url}{_FILE_PATH}"
        resp = await client.get(url, params={"file_id": file_id}, headers=headers)
        if not resp.is_success:
            raise RuntimeError(f"MiniMax 文件获取错误 {resp.status_code}: {resp.text[:200]}")
        try:
            data = resp.json()
        except Exception as e:
            raise RuntimeError(f"MiniMax 文件响应 JSON 解析失败: {e!r} | 原始响应: {resp.text[:200]}") from e
        download_url = data.get("file", {}).get("download_url")
        if not download_url:
            raise RuntimeError(f"MiniMax 文件响应缺少 download_url: {resp.text[:200]}")
        return download_url
