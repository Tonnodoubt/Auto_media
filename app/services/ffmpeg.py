"""
FFmpeg 音视频合成服务 — 将无声视频与 TTS 音频合并为有声 MP4，以及视频拼接
"""
import asyncio
import logging
import os
import platform
import shutil
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from app.paths import IMAGE_DIR, MEDIA_DIR, VIDEO_DIR

logger = logging.getLogger(__name__)

_COMMON_BINARY_DIRS = (
    Path("/opt/homebrew/bin"),
    Path("/usr/local/bin"),
    Path("/opt/local/bin"),
    Path.home() / ".local/bin",
)
_LAST_FRAME_SEEK_SECONDS = 0.04


def _binary_candidates(binary_name: str) -> tuple[str, ...]:
    if platform.system().lower() == "windows" and not binary_name.lower().endswith(".exe"):
        return (binary_name, f"{binary_name}.exe")
    return (binary_name,)


def _find_winget_binary(binary_name: str) -> str | None:
    if platform.system().lower() != "windows":
        return None

    local_app_data = os.getenv("LOCALAPPDATA", "").strip()
    if not local_app_data:
        return None

    packages_dir = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
    if not packages_dir.exists():
        return None

    for candidate_name in _binary_candidates(binary_name):
        matches = sorted(packages_dir.glob(f"**/{candidate_name}"), reverse=True)
        for match in matches:
            if match.is_file() and os.access(str(match), os.X_OK):
                return str(match)

    return None


@lru_cache(maxsize=None)
def resolve_media_binary(binary_name: str) -> str:
    """解析 ffmpeg / ffprobe 可执行文件路径。"""
    def _is_executable_file(path: Path) -> bool:
        return path.is_file() and os.access(str(path), os.X_OK)

    env_name = f"{binary_name.upper()}_PATH"
    configured = os.getenv(env_name, "").strip()
    if configured:
        configured_path = Path(configured).expanduser()
        if _is_executable_file(configured_path):
            return str(configured_path)
        resolved_configured = shutil.which(configured)
        if resolved_configured:
            return resolved_configured
        if configured_path.exists():
            raise RuntimeError(f"环境变量 {env_name} 指向的路径不是可执行文件: {configured}")
        raise RuntimeError(f"环境变量 {env_name} 指向的 {binary_name} 不存在: {configured}")

    for candidate_name in _binary_candidates(binary_name):
        resolved = shutil.which(candidate_name)
        if resolved:
            return resolved

    for candidate_name in _binary_candidates(binary_name):
        for directory in _COMMON_BINARY_DIRS:
            candidate = directory / candidate_name
            if _is_executable_file(candidate):
                return str(candidate)

    winget_binary = _find_winget_binary(binary_name)
    if winget_binary:
        return winget_binary

    raise RuntimeError(
        f"未找到 {binary_name} 可执行文件，请先安装 FFmpeg，或通过环境变量 {env_name} 指定路径。"
    )


async def _extract_frame(video_path: str, output_path: str, *frame_args: str) -> str:
    """从视频中提取单帧。"""
    video = Path(video_path)
    if not video.exists():
        raise FileNotFoundError(f"视频文件不存在: {video_path}")

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    ffmpeg_bin = resolve_media_binary("ffmpeg")

    cmd = [
        ffmpeg_bin, "-y",
        *frame_args,
        "-i", str(video),
        "-frames:v", "1",
        "-q:v", "2",
        output_path,
    ]

    logger.info("FFmpeg 提取单帧: %s -> %s", video_path, output_path)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        err_msg = stderr.decode(errors="replace")
        logger.error("FFmpeg 提取帧失败 (code %d): %s", proc.returncode, err_msg)
        raise RuntimeError(f"FFmpeg 提取帧失败: {err_msg}")

    logger.info("FFmpeg 提取单帧完成: %s", output_path)
    return output_path


def _sanitize_image_output_name(raw_name: str | None, *, field_name: str) -> str:
    raw_name = str(raw_name or "").strip()
    if not raw_name:
        raise ValueError(f"{field_name} 不能为空")

    candidate = Path(raw_name)
    if (
        candidate.is_absolute()
        or "/" in raw_name
        or "\\" in raw_name
        or ".." in candidate.parts
        or "." in candidate.parts[:-1]
    ):
        raise ValueError(f"非法 {field_name}: {raw_name}")

    sanitized_name = candidate.name
    if not sanitized_name or sanitized_name in {".", ".."}:
        raise ValueError(f"非法 {field_name}: {raw_name}")

    return sanitized_name


def _resolve_image_output_path(output_name: str | None, default_name: str) -> str:
    sanitized_name = _sanitize_image_output_name(
        output_name if output_name is not None else default_name,
        field_name="output_name" if output_name is not None else "default_name",
    )
    return str(IMAGE_DIR / sanitized_name)


async def extract_last_frame(video_path: str, shot_id: str, output_name: str | None = None) -> str:
    """
    从视频末尾提取最后一帧，保存为 PNG 图片。

    用于链式视频生成：将当前镜头的最后一帧作为下一镜头的参考图。

    Args:
        video_path: 视频文件本地路径
        shot_id: 镜头 ID，用于生成输出文件名
        output_name: 可选输出文件名，用于 transition 定向命名

    Returns:
        输出图片的本地文件路径
    Raises:
        FileNotFoundError: 视频文件不存在
        RuntimeError: ffmpeg 执行失败
    """
    output_path = _resolve_image_output_path(output_name, f"{shot_id}_lastframe.png")
    # Seek inside the final frame interval instead of 100ms earlier; this reduces
    # visible seam risk when the last shot is still moving near the cut point.
    return await _extract_frame(video_path, output_path, "-sseof", f"-{_LAST_FRAME_SEEK_SECONDS:.2f}")


async def extract_first_frame(video_path: str, shot_id: str, output_name: str | None = None) -> str:
    """
    从视频开头提取第一帧，保存为 PNG 图片。

    Args:
        video_path: 视频文件本地路径
        shot_id: 镜头 ID，用于生成输出文件名
        output_name: 可选输出文件名，用于 transition 定向命名

    Returns:
        输出图片的本地文件路径
    """
    output_path = _resolve_image_output_path(output_name, f"{shot_id}_firstframe.png")
    return await _extract_frame(video_path, output_path)


async def stitch_audio_video(
    video_path: str,
    audio_path: str,
    output_path: str,
) -> str:
    """
    将单个镜头的视频和音频合成为有声 MP4。

    使用 -c:v copy（不重编码视频）和 -c:a aac 编码音频，
    -shortest 以较短流为准截断。

    Returns:
        合成后的文件路径
    Raises:
        RuntimeError: ffmpeg 执行失败
    """
    video = Path(video_path)
    audio = Path(audio_path)

    if not video.exists():
        raise FileNotFoundError(f"视频文件不存在: {video_path}")
    if not audio.exists():
        raise FileNotFoundError(f"音频文件不存在: {audio_path}")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_bin = resolve_media_binary("ffmpeg")

    cmd = [
        ffmpeg_bin, "-y",
        "-i", str(video),
        "-i", str(audio),
        "-c:v", "copy",
        "-c:a", "aac",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-shortest",
        str(output_path),
    ]

    logger.info("FFmpeg 合成: %s + %s -> %s", video_path, audio_path, output_path)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        err_msg = stderr.decode(errors="replace")
        logger.error("FFmpeg 合成失败 (code %d): %s", proc.returncode, err_msg)
        raise RuntimeError(f"FFmpeg 合成失败: {err_msg}")

    logger.info("FFmpeg 合成完成: %s", output_path)
    return output_path


async def stitch_batch(
    results: List[dict],
    base_url: str = "",
) -> List[dict]:
    """
    批量并发合成：遍历 results，对每个同时拥有 video_url 和 audio_url 的镜头
    调用 stitch_audio_video，生成 {shot_id}_final.mp4。

    Args:
        results: pipeline 中组装的 shot result 列表
        base_url: 用于拼接文件 URL 的服务地址

    Returns:
        更新后的 results 列表（新增 final_video_url 字段）
    """

    async def _process_one(result: dict) -> dict:
        video_url: Optional[str] = result.get("video_url")
        audio_url: Optional[str] = result.get("audio_url")

        if not video_url or not audio_url:
            logger.warning(
                "镜头 %s 缺少视频或音频，跳过合成", result.get("shot_id")
            )
            return result

        # 从 URL 还原本地路径：/media/videos/xxx.mp4 → media/videos/xxx.mp4
        video_path = _url_to_local_path(video_url, base_url)
        audio_path = _url_to_local_path(audio_url, base_url)

        # 输出路径：原视频文件名去掉 .mp4 加 _final.mp4
        video_stem = Path(video_path).stem
        output_path = str(VIDEO_DIR / f"{video_stem}_final.mp4")

        try:
            await stitch_audio_video(video_path, audio_path, output_path)
            # 构造可访问的 URL
            relative = str(Path(output_path))  # media/videos/xxx_final.mp4
            final_url = f"{base_url}/{relative}" if base_url else f"/{relative}"
            result["final_video_url"] = final_url
        except (FileNotFoundError, RuntimeError) as exc:
            logger.error("镜头 %s 合成失败: %s", result.get("shot_id"), exc)

        return result

    updated = await asyncio.gather(*[_process_one(r) for r in results])
    return list(updated)


async def concat_videos(
    video_paths: List[str],
    output_path: str,
) -> str:
    """
    将多个视频按顺序拼接为一个完整 MP4（stream copy，不重编码）。

    Args:
        video_paths: 有序的本地视频文件路径列表
        output_path: 输出文件路径

    Returns:
        输出文件路径
    Raises:
        FileNotFoundError: 某个视频文件不存在
        ValueError: 视频列表为空
        RuntimeError: ffmpeg 执行失败
    """
    if not video_paths:
        raise ValueError("视频列表为空，无法拼接")

    for p in video_paths:
        if not Path(p).exists():
            raise FileNotFoundError(f"视频文件不存在: {p}")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_bin = resolve_media_binary("ffmpeg")

    # 生成临时 concat list 文件
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False
    ) as tmp:
        for p in video_paths:
            # ffmpeg concat 要求用单引号包裹路径并转义内部单引号
            escaped = str(Path(p).resolve()).replace("'", "'\\''")
            tmp.write(f"file '{escaped}'\n")
        concat_list_path = tmp.name

    cmd = [
        ffmpeg_bin, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_list_path,
        "-c", "copy",
        str(output_path),
    ]

    logger.info("FFmpeg 拼接 %d 个视频 -> %s", len(video_paths), output_path)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            err_msg = stderr.decode(errors="replace")
            logger.error("FFmpeg 拼接失败 (code %d): %s", proc.returncode, err_msg)
            raise RuntimeError(f"FFmpeg 拼接失败: {err_msg}")

        logger.info("FFmpeg 拼接完成: %s", output_path)
        return output_path
    finally:
        # 清理临时文件
        Path(concat_list_path).unlink(missing_ok=True)


def url_to_local_path(url: str, base_url: str) -> str:
    """将 URL 转换为本地媒体绝对路径。"""
    path = url
    if base_url and path.startswith(base_url):
        path = path[len(base_url):]
    normalized = f"/{path.lstrip('/')}"
    if normalized.startswith("/media/"):
        return str((MEDIA_DIR.parent / normalized.lstrip("/")).resolve(strict=False))
    return str(Path(path).expanduser().resolve(strict=False))


_url_to_local_path = url_to_local_path
