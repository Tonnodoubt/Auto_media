"""
FFmpeg 音视频合成服务 — 将无声视频与 TTS 音频合并为有声 MP4，以及视频拼接
"""
import asyncio
import logging
import tempfile
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

VIDEO_DIR = Path("media/videos")
IMAGE_DIR = Path("media/images")


async def extract_last_frame(video_path: str, shot_id: str) -> str:
    """
    从视频末尾提取最后一帧，保存为 PNG 图片。

    用于链式视频生成：将当前镜头的最后一帧作为下一镜头的参考图。

    Args:
        video_path: 视频文件本地路径
        shot_id: 镜头 ID，用于生成输出文件名

    Returns:
        输出图片的本地文件路径
    Raises:
        FileNotFoundError: 视频文件不存在
        RuntimeError: ffmpeg 执行失败
    """
    video = Path(video_path)
    if not video.exists():
        raise FileNotFoundError(f"视频文件不存在: {video_path}")

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    output_path = str(IMAGE_DIR / f"{shot_id}_lastframe.png")

    cmd = [
        "ffmpeg", "-y",
        "-sseof", "-0.1",
        "-i", str(video),
        "-frames:v", "1",
        "-q:v", "2",
        output_path,
    ]

    logger.info("FFmpeg 提取最后一帧: %s -> %s", video_path, output_path)

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

    logger.info("FFmpeg 提取最后一帧完成: %s", output_path)
    return output_path


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

    cmd = [
        "ffmpeg", "-y",
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
        "ffmpeg", "-y",
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


def _url_to_local_path(url: str, base_url: str) -> str:
    """将 URL 转换为本地相对路径。

    例如 http://localhost:8000/media/videos/x.mp4 → media/videos/x.mp4
    或者 /media/videos/x.mp4 → media/videos/x.mp4
    """
    path = url
    if base_url and path.startswith(base_url):
        path = path[len(base_url):]
    # 去掉前导斜杠
    return path.lstrip("/")
