import asyncio
import os
import tempfile
from pathlib import Path

import edge_tts

import re
from app.services.ffmpeg import resolve_media_binary

# Output directory for audio files
AUDIO_DIR = Path("media/audio")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# Good Chinese voices
VOICES = {
    # 普通话女声
    "zh-CN-XiaoxiaoNeural": "晓晓（女·温柔自然）",
    "zh-CN-XiaoyiNeural":   "晓伊（女·活泼可爱）",
    "zh-CN-XiaohanNeural":  "晓涵（女·沉稳知性）",
    "zh-CN-XiaomengNeural": "晓梦（女·甜美）",
    "zh-CN-XiaoqiuNeural":  "晓秋（女·成熟优雅）",
    "zh-CN-XiaoruiNeural":  "晓睿（女·老年）",
    "zh-CN-XiaoshuangNeural": "晓双（女·儿童）",
    "zh-CN-XiaoxuanNeural": "晓萱（女·轻松随意）",
    "zh-CN-XiaoyanNeural":  "晓颜（女·专业播报）",
    # 普通话男声
    "zh-CN-YunxiNeural":    "云希（男·自然流畅）",
    "zh-CN-YunjianNeural":  "云健（男·磁性低沉）",
    "zh-CN-YunyangNeural":  "云扬（男·新闻播报）",
    "zh-CN-YunxiaNeural":   "云夏（男·阳光少年）",
    "zh-CN-YunzeNeural":    "云泽（男·老年）",
    # 粤语
    "zh-HK-HiuMaanNeural":  "晓曼（粤语·女）",
    "zh-HK-HiuGaaiNeural":  "晓佳（粤语·女）",
    "zh-HK-WanLungNeural":  "云龙（粤语·男）",
    # 台湾中文
    "zh-TW-HsiaoChenNeural": "晓臻（台湾·女）",
    "zh-TW-HsiaoYuNeural":   "晓雨（台湾·女）",
    "zh-TW-YunJheNeural":    "云哲（台湾·男）",
}
DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"


def clean_dialogue(text: str) -> str:
    """Remove stage directions like （旁白）（画外音）【旁白】 etc. before TTS."""
    # Remove （xxx） and 【xxx】 prefixes
    text = re.sub(r'^[（(【\[][^）)】\]]{0,10}[）)】\]]\s*', '', text.strip())
    return text.strip()


async def generate_tts(
    text: str,
    shot_id: str,
    voice: str = DEFAULT_VOICE,
) -> dict:
    """
    Generate TTS audio for a single shot.
    Returns: { shot_id, audio_path, duration_seconds }
    """
    output_path = AUDIO_DIR / f"{shot_id}.mp3"

    communicate = edge_tts.Communicate(clean_dialogue(text), voice)
    await communicate.save(str(output_path))

    duration = await _get_audio_duration(output_path)

    return {
        "shot_id": shot_id,
        "audio_path": str(output_path),
        "audio_url": f"/media/audio/{shot_id}.mp3",
        "duration_seconds": duration,
    }


async def generate_tts_batch(
    shots: list[dict],
    voice: str = DEFAULT_VOICE,
) -> list[dict]:
    """
    Generate TTS for all shots with dialogue concurrently.
    Shots without dialogue are skipped.
    """
    tasks = []
    for shot in shots:
        if shot.get("dialogue"):
            tasks.append(generate_tts(shot["dialogue"], shot["shot_id"], voice))

    results = await asyncio.gather(*tasks)
    return list(results)


async def _get_audio_duration(path: Path) -> float:
    """Get audio duration in seconds using ffprobe if available, else estimate."""
    try:
        ffprobe_bin = resolve_media_binary("ffprobe")
        proc = await asyncio.create_subprocess_exec(
            ffprobe_bin, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return float(stdout.decode().strip())
    except Exception:
        # Fallback: estimate from file size (~128kbps mp3)
        size = path.stat().st_size
        return round(size / 16000, 2)
