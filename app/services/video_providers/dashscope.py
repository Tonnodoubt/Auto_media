import asyncio

import httpx

from app.core.api_keys import mask_key
from app.services.video_providers.base import BaseVideoProvider

DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"
_SUBMIT_PATH = "/services/aigc/image2video/video-synthesis"
_TASK_PATH = "/tasks/{task_id}"


class DashScopeVideoProvider(BaseVideoProvider):
    """阿里云 DashScope 图生视频（Wan 系列）。

    注意：当前不支持双帧过渡模式，last_frame_url 参数将被忽略。
    """

    async def generate(
        self,
        image_url: str,
        prompt: str,
        model: str,
        api_key: str,
        base_url: str,
        last_frame_url: str = "",
        negative_prompt: str = "",
        duration_seconds: int | None = None,
    ) -> str:
        """生成视频。

        Args:
            image_url: 首帧图片URL
            prompt: 动作描述
            model: 模型名称
            api_key: API密钥
            base_url: API基础URL
            last_frame_url: 尾帧图片URL（暂不支持，将被忽略）

        Returns:
            视频URL
        """
        # 注意：DashScope 暂不支持双帧过渡，忽略 last_frame_url
        effective_base = base_url or DEFAULT_BASE_URL
        async with httpx.AsyncClient(timeout=30) as client:
            task_id = await self._submit(
                client,
                image_url,
                prompt,
                model,
                api_key,
                effective_base,
                negative_prompt,
                duration_seconds,
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
        negative_prompt: str = "",
        duration_seconds: int | None = None,
    ) -> str:
        input_payload = {"image_url": image_url, "prompt": prompt}
        if negative_prompt:
            input_payload["negative_prompt"] = negative_prompt
        url = f"{base_url}{_SUBMIT_PATH}"
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "X-DashScope-Async": "enable",
            },
            json={
                "model": model,
                "input": input_payload,
                "parameters": {"duration": duration_seconds or 5},
            },
        )
        print(f"[VIDEO DASHSCOPE SUBMIT] status={resp.status_code} key={mask_key(api_key)} base={base_url}")
        if not resp.is_success:
            raise RuntimeError(f"DashScope 视频任务提交错误 {resp.status_code}: {resp.text[:200]}")
        return resp.json()["output"]["task_id"]

    async def _poll(self, client: httpx.AsyncClient, task_id: str, api_key: str, base_url: str, timeout: int = 300) -> str:
        url = f"{base_url}{_TASK_PATH.format(task_id=task_id)}"
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            await asyncio.sleep(5)
            resp = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
            if not resp.is_success:
                raise RuntimeError(f"DashScope 视频任务查询错误 {resp.status_code}: {resp.text[:200]}")
            try:
                data = resp.json()
            except Exception as e:
                raise RuntimeError(f"DashScope 响应 JSON 解析失败: {e!r} | 原始响应: {resp.text[:200]}") from e
            output = data.get("output", {})
            status = output.get("task_status")
            if not status:
                raise RuntimeError(f"DashScope 响应缺少 task_status 字段: {resp.text[:200]}")
            if status == "SUCCEEDED":
                video_url = output.get("video_url")
                if not video_url:
                    raise RuntimeError(f"DashScope 任务成功但缺少 video_url: {resp.text[:200]}")
                return video_url
            if status in ("FAILED", "CANCELED"):
                raise RuntimeError(f"DashScope 视频任务失败: {output.get('message', status)}")
        raise TimeoutError(f"DashScope 视频任务超时: {task_id}")
