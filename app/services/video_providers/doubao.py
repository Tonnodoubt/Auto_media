import asyncio
import base64
import ipaddress
import mimetypes
import re
import socket
from pathlib import Path

import httpx

from app.core.api_keys import mask_key
from app.paths import MEDIA_DIR
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
_IDENTITY_HINTS = (
    "identity", "canon", "same face", "face", "hairstyle", "hair", "same person", "same character",
    "same appearance", "outfit", "clothing", "costume", "wardrobe", "silhouette", "accessories",
    "primary outfit", "signature accessories", "same outfit", "unchanged", "consistent appearance",
    "同一张脸", "同一人物", "同一角色", "同一发型", "衣物", "服装", "配饰", "主衣物", "外观一致",
)
_MOTION_GUIDANCE_HINTS = (
    "visible", "readable", "body travel", "cloth", "follow-through", "anatomy", "limb", "hand",
    "camera move", "camera movement", "motion amplitude", "smooth easing", "interpolate", "middle frames",
    "gradually", "动作幅度", "清晰可见", "主体位移", "布料", "解剖", "四肢", "手部", "运镜", "中段", "中间帧", "渐进",
)
_NEGATIVE_GUARDRAIL_RULES = (
    (("identity drift", "wrong face"), "identity drift"),
    (("changed hairstyle",), "hairstyle drift"),
    (("different primary outfit", "changed costume colors", "changed costume material", "outfit drift", "modern clothing"), "outfit drift"),
    (("missing signature accessories",), "missing accessories"),
    (("warped anatomy", "limb distortion", "extra limbs"), "warped anatomy"),
    (("background morphing", "wrong location layout", "environment swap"), "background morphing"),
    (("prop teleportation",), "prop teleportation"),
    (("lighting flicker",), "lighting flicker"),
    (("camera jitter", "snap zoom", "abrupt cut"), "camera jitter"),
)


def _collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _data_url_from_bytes(content: bytes, name: str = "", content_type: str = "") -> str:
    mime = (
        (content_type or "").split(";")[0].strip()
        or mimetypes.guess_type(name)[0]
        or "image/png"
    )
    encoded = base64.b64encode(content).decode()
    return f"data:{mime};base64,{encoded}"


def _resolve_allowed_media_path(path_like: str | Path) -> Path | None:
    try:
        candidate = Path(path_like).expanduser()
        resolved = candidate.resolve() if candidate.is_absolute() else (MEDIA_DIR.parent / candidate).resolve()
        media_root = MEDIA_DIR.resolve(strict=False)
        if resolved.is_file() and resolved.is_relative_to(media_root):
            return resolved
    except (OSError, RuntimeError, ValueError):
        return None
    return None


def _resolve_local_media_data_url(path_like: str) -> str:
    normalized = str(path_like or "").strip()
    if not normalized:
        return ""

    for candidate in (normalized, normalized.lstrip("/")):
        local_path = _resolve_allowed_media_path(candidate)
        if local_path:
            return _data_url_from_bytes(local_path.read_bytes(), name=local_path.name)
    return ""


def _is_private_or_local_host(host: str) -> bool:
    normalized = str(host or "").strip().rstrip(".").lower()
    if not normalized or normalized.endswith(".local"):
        return True
    if normalized in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return True
    try:
        ip = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


async def _resolve_hostname_ips(host: str) -> list[str]:
    normalized_host = str(host or "").strip().rstrip(".")
    if not normalized_host:
        return []
    try:
        ipaddress.ip_address(normalized_host)
        return [normalized_host]
    except ValueError:
        pass

    try:
        loop = asyncio.get_running_loop()
        addrinfo = await loop.getaddrinfo(
            normalized_host,
            None,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except OSError:
        return []

    resolved_ips: list[str] = []
    seen: set[str] = set()
    for entry in addrinfo:
        sockaddr = entry[4]
        if not sockaddr:
            continue
        ip = str(sockaddr[0]).strip()
        if not ip or ip in seen:
            continue
        seen.add(ip)
        resolved_ips.append(ip)
    return resolved_ips


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


def _pick_best_segment(
    segments: list[str],
    keywords: tuple[str, ...],
    *,
    exclude: tuple[str, ...] = (),
) -> str:
    ranked: list[tuple[int, int, str]] = []
    excluded = {segment for segment in exclude if segment}
    for segment in segments:
        if segment in excluded or not _contains_any(segment, keywords):
            continue
        lowered = segment.lower()
        keyword_hits = sum(1 for keyword in keywords if keyword.lower() in lowered)
        ranked.append((keyword_hits, len(segment.split()), segment))
    if not ranked:
        return ""
    return max(ranked)[2]


def _negative_guardrail_text(negative_prompt: str) -> str:
    lowered = (negative_prompt or "").lower()
    selected: list[str] = []
    for matches, label in _NEGATIVE_GUARDRAIL_RULES:
        if any(match in lowered for match in matches) and label not in selected:
            selected.append(label)
        if len(selected) >= 4:
            break
    if not selected:
        return ""
    return f"Avoid {', '.join(selected)}"


def optimize_doubao_prompt(prompt: str, has_last_frame: bool = False, negative_prompt: str = "") -> str:
    """
    Seedance 更适合短、明确、单动作的提示词。
    这里把 storyboard 产出的长 prompt 压缩成更适合 I2V/F1F2V 的版本。
    """
    segments = _split_prompt_segments(prompt)
    if not segments:
        base = "Single subject performs one clear continuous motion with visible movement."
        if has_last_frame:
            fallback_parts = [
                base,
                "Bridge smoothly from the first anchor frame to the exact last anchor frame.",
                "Keep identity, outfit, props, background, and anatomy stable.",
            ]
        else:
            fallback_parts = [
                base,
                "Keep the same person and outfit from the first frame.",
                "Make the motion and camera change clearly readable on screen.",
            ]
        negative_guardrail = _negative_guardrail_text(negative_prompt)
        if negative_guardrail:
            fallback_parts.append(negative_guardrail)
        return _trim_words(". ".join(fallback_parts), 90)

    camera = _extract_camera_phrase(" ".join(segments[:4]) or " ".join(segments))
    action = next((seg for seg in segments if _contains_any(seg, _ACTION_HINTS)), "")
    candidates = [
        seg for seg in segments[1:]
        if not _contains_any(seg, _ENV_HINTS) and not _contains_any(seg, _LIGHT_HINTS) and not _contains_any(seg, _IDENTITY_HINTS)
    ]
    if not action or (camera and action == segments[0] and candidates):
        action = max(candidates, key=lambda seg: len(seg.split()), default=segments[1] if camera and len(segments) > 1 else segments[0])
    identity = _pick_best_segment(segments, _IDENTITY_HINTS, exclude=(action,))
    motion_guidance = _pick_best_segment(segments, _MOTION_GUIDANCE_HINTS, exclude=(action, identity))
    environment = next((seg for seg in segments if seg != action and _contains_any(seg, _ENV_HINTS)), "")
    lighting = next((seg for seg in segments if seg not in (action, environment) and _contains_any(seg, _LIGHT_HINTS)), "")
    negative_guardrail = _negative_guardrail_text(negative_prompt)

    pieces = []
    if camera:
        pieces.append(_trim_words(camera, 10))
    pieces.append(_trim_words(action, 22))
    if identity:
        pieces.append(_trim_words(identity, 22))
    if motion_guidance:
        pieces.append(_trim_words(motion_guidance, 22))
    if environment:
        pieces.append(_trim_words(environment, 14))
    if lighting:
        pieces.append(_trim_words(lighting, 10))

    if has_last_frame:
        pieces.append("Bridge continuously from the first anchor frame to the exact last anchor frame with smooth easing through the middle frames.")
        pieces.append("Keep the same face, outfit, props, background, lighting, and stable anatomy.")
    else:
        if camera and "static" not in camera.lower():
            pieces.append("Make both the subject motion and camera move clearly readable on screen, not tiny or hesitant.")
        else:
            pieces.append("Even on a static camera, keep the action clearly visible on screen instead of tiny barely visible motion.")
        pieces.append("Keep the same face, hairstyle, outfit silhouette, costume colors, and signature accessories from the first frame.")
        pieces.append("Keep anatomy natural with stable limbs and hands.")
    if negative_guardrail:
        pieces.append(negative_guardrail)

    optimized = ". ".join(piece.strip(" ,.;") for piece in pieces if piece).strip()
    optimized = _collapse_spaces(optimized)
    return _trim_words(optimized, 100 if has_last_frame else 95)


async def _to_data_url(image_url: str) -> str:
    """将允许的本地媒体路径转成 data URL，并拒绝未映射的内网地址。"""
    from urllib.parse import urlparse

    normalized = str(image_url or "").strip()
    if not normalized:
        raise ValueError("Doubao frame URL is empty")
    if normalized.startswith("data:"):
        return normalized

    direct_local = _resolve_local_media_data_url(normalized)
    if direct_local:
        return direct_local

    parsed = urlparse(normalized)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            "Doubao frame URL must be a data URL, an http(s) URL, or a file under MEDIA_DIR"
        )

    host = str(parsed.hostname or "").strip().rstrip(".").lower()
    if not host:
        raise ValueError(f"Doubao frame URL must include a hostname: {normalized!r}")

    local_media = _resolve_local_media_data_url(parsed.path)
    if _is_private_or_local_host(host):
        if local_media:
            return local_media
        raise ValueError(
            f"Doubao frame URL points to a private/local host and must map to MEDIA_DIR: {normalized}"
        )

    resolved_ips = await _resolve_hostname_ips(host)
    if not resolved_ips:
        raise ValueError(f"Doubao frame hostname could not be resolved safely: {host}")
    if any(_is_private_or_local_host(ip) for ip in resolved_ips):
        if local_media:
            return local_media
        raise ValueError(
            f"Doubao frame URL resolves to a private/local address and must map to MEDIA_DIR: {normalized}"
        )

    return normalized

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
                negative_prompt=negative_prompt,
                duration_seconds=duration_seconds,
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
        negative_prompt: str = "",
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
        optimized_prompt = optimize_doubao_prompt(
            prompt,
            has_last_frame=bool(last_frame_url),
            negative_prompt=negative_prompt,
        )

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
