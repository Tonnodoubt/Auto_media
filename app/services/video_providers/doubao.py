import asyncio
import base64
import mimetypes
import re

import httpx

from app.core.api_keys import mask_key
from app.services.video_providers.base import BaseVideoProvider

_SHOT_SIZE_TERMS = ("Extreme Close-Up", "Close-Up", "Medium Close-Up", "Medium Shot", "Medium Wide Shot", "Wide Shot", "Extreme Wide Shot", "Over-the-shoulder")
_ANGLE_TERMS = ("Eye-level", "Low angle", "High angle", "Dutch angle", "Bird's eye", "Worm's eye")
_MOVEMENT_TERMS = ("Static", "Slow Dolly in", "Dolly out", "Pan left", "Pan right", "Tilt up", "Tilt down", "Tracking shot", "Handheld subtle shake", "Crane up", "Crane down")
_ACTION_HINTS = (
    "walk", "sit", "stand", "turn", "look", "reach", "open", "close", "raise", "lower",
    "move", "step", "enter", "leave", "lean", "pick", "put", "hold", "glance", "speak",
    "smile", "cry", "blink", "stare", "transition", "snap", "trembl", "constrict",
    "clench", "shake", "fall", "run",
)
_ENV_HINTS = (
    "office", "room", "street", "alley", "forest", "window", "desk", "door", "hall",
    "building", "background", "meeting", "kitchen", "bedroom", "corridor", "rain",
    "monitor", "city", "lobby", "pavement", "neon", "sky", "sofa", "chair",
)
_LIGHT_HINTS = (
    "light", "lighting", "shadow", "sunlight", "sun", "glow", "rim", "contrast", "warm",
    "cool", "blue", "golden", "dark", "bright", "chiaroscuro", "volumetric", "neon",
)


def _collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _trim_words(text: str, limit: int) -> str:
    words = text.split()
    if len(words) <= limit:
        return text.strip(" ,.;")
    return " ".join(words[:limit]).strip(" ,.;")


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _extract_camera_phrase(text: str) -> str:
    shot_size = next((term for term in _SHOT_SIZE_TERMS if term.lower() in text.lower()), "")
    angle = next((term for term in _ANGLE_TERMS if term.lower() in text.lower()), "")
    movement = next((term for term in _MOVEMENT_TERMS if term.lower() in text.lower()), "")
    parts = [part for part in (shot_size, angle, movement) if part]
    if not parts:
        return ""
    return ", ".join(parts)


def _split_prompt_segments(text: str) -> list[str]:
    normalized = _collapse_spaces(text)
    normalized = re.sub(r"\[[^\[\]]*\]", " ", normalized)
    normalized = re.sub(r"--ar\s+\S+", " ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(
        r"\b(?:Cinematic|Masterpiece|photorealistic|ultra-detailed|highly detailed|4k|8k|ARRI Alexa 65|macro lens|cinema lighting|professional color grading)\b[^.]*",
        " ",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = normalized.replace('"', " ").replace("'", " ")
    segments = [
        _collapse_spaces(seg)
        for seg in re.split(r"[.!?\n]+", normalized)
        if _collapse_spaces(seg)
    ]
    return segments


def optimize_doubao_prompt(prompt: str, has_last_frame: bool = False) -> str:
    """
    Seedance 更适合短、明确、单动作的提示词。
    这里把 storyboard 产出的长 prompt 压缩成更适合 I2V/F1F2V 的版本。
    """
    segments = _split_prompt_segments(prompt)
    if not segments:
        base = "Single subject performs one clear natural motion."
        if has_last_frame:
            return f"{base} End exactly at the provided last frame."
        return f"{base} Keep framing stable and consistent."

    camera = _extract_camera_phrase(segments[0])
    action = next((seg for seg in segments if _contains_any(seg, _ACTION_HINTS)), "")
    candidates = [
        seg for seg in segments[1:]
        if not _contains_any(seg, _ENV_HINTS) and not _contains_any(seg, _LIGHT_HINTS)
    ]
    if not action or (camera and action == segments[0] and candidates):
        action = max(candidates, key=lambda seg: len(seg.split()), default=segments[1] if camera and len(segments) > 1 else segments[0])
    environment = next((seg for seg in segments if seg != action and _contains_any(seg, _ENV_HINTS)), "")
    lighting = next((seg for seg in segments if seg not in (action, environment) and _contains_any(seg, _LIGHT_HINTS)), "")

    pieces = []
    if camera:
        pieces.append(_trim_words(camera, 8))
    pieces.append(_trim_words(action, 18))
    if environment:
        pieces.append(_trim_words(environment, 14))
    if lighting:
        pieces.append(_trim_words(lighting, 10))

    if has_last_frame:
        pieces.append("Smoothly transition from the first frame to the exact last-frame pose.")
        pieces.append("Keep identity, clothing, and composition consistent.")
    else:
        pieces.append("Keep one clear natural motion only.")
        pieces.append("No extra movement or scene changes.")

    optimized = ". ".join(piece.strip(" ,.;") for piece in pieces if piece).strip()
    optimized = _collapse_spaces(optimized)
    return _trim_words(optimized, 65)


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
    """字节跳动豆包 Seedance 图生视频（火山方舟 Ark API）。

    支持两种模式：
    1. 单帧 I2V：只提供首帧图片
    2. 双帧过渡：提供首帧和尾帧图片，API会在两者之间生成过渡动画
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
            last_frame_url: 尾帧图片URL（可选），提供时启用双帧过渡模式

        Returns:
            视频URL
        """
        # Seedance does not provide a native negative prompt field. Keep this
        # parameter for provider compatibility but ignore it here.
        del negative_prompt
        effective_base = base_url or DEFAULT_BASE_URL
        async with httpx.AsyncClient(timeout=30) as client:
            task_id = await self._submit(
                client,
                image_url,
                last_frame_url,
                prompt,
                model,
                api_key,
                effective_base,
                duration_seconds,
            )
        async with httpx.AsyncClient(timeout=30) as client:
            return await self._poll(client, task_id, api_key, effective_base)

    async def _submit(
        self,
        client: httpx.AsyncClient,
        image_url: str,
        last_frame_url: str,
        prompt: str,
        model: str,
        api_key: str,
        base_url: str,
        duration_seconds: int | None = None,
    ) -> str:
        """提交视频生成任务。

        Args:
            client: HTTP客户端
            image_url: 首帧图片URL
            last_frame_url: 尾帧图片URL（可选）
            prompt: 动作描述
            model: 模型名称
            api_key: API密钥
            base_url: API基础URL

        Returns:
            任务ID
        """
        url = f"{base_url}{_SUBMIT_PATH}"
        optimized_prompt = optimize_doubao_prompt(prompt, has_last_frame=bool(last_frame_url))

        # 解析首帧图片
        resolved_first = await _to_data_url(image_url)

        # 构建content数组
        content = [
            {"type": "text", "text": optimized_prompt},
            {
                "type": "image_url",
                "image_url": {"url": resolved_first},
                "role": "first_frame",
            },
        ]

        # 如果提供了尾帧，添加尾帧
        if last_frame_url:
            resolved_last = await _to_data_url(last_frame_url)
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": resolved_last},
                    "role": "last_frame",
                }
            )

        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "content": content,
                "parameters": {"duration": duration_seconds or 5},
            },
        )
        print(f"[VIDEO DOUBAO SUBMIT] status={resp.status_code} key={mask_key(api_key)} base={base_url}")
        print(
            f"[VIDEO DOUBAO PROMPT] original_words={len(prompt.split())} "
            f"optimized_words={len(optimized_prompt.split())} has_last_frame={bool(last_frame_url)} "
            f"text={optimized_prompt[:220]}"
        )
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
