import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.ffmpeg import extract_last_frame, resolve_media_binary


class ResolveMediaBinaryTests(unittest.TestCase):
    def tearDown(self):
        resolve_media_binary.cache_clear()

    def test_resolve_media_binary_uses_env_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            binary_path = Path(tmpdir) / "ffmpeg"
            binary_path.write_text("", encoding="utf-8")
            binary_path.chmod(0o755)

            with patch.dict(os.environ, {"FFMPEG_PATH": str(binary_path)}, clear=False):
                resolve_media_binary.cache_clear()
                self.assertEqual(resolve_media_binary("ffmpeg"), str(binary_path))

    def test_resolve_media_binary_rejects_non_executable_env_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            binary_path = Path(tmpdir) / "ffmpeg"
            binary_path.write_text("", encoding="utf-8")
            binary_path.chmod(0o644)

            with patch.dict(os.environ, {"FFMPEG_PATH": str(binary_path)}, clear=False):
                resolve_media_binary.cache_clear()
                with self.assertRaisesRegex(RuntimeError, "不是可执行文件"):
                    resolve_media_binary("ffmpeg")

    def test_resolve_media_binary_raises_clear_error_when_missing(self):
        with (
            patch.dict(os.environ, {"FFMPEG_PATH": ""}, clear=False),
            patch("app.services.ffmpeg.shutil.which", return_value=None),
            patch("app.services.ffmpeg._COMMON_BINARY_DIRS", ()),
        ):
            resolve_media_binary.cache_clear()
            with self.assertRaisesRegex(RuntimeError, "未找到 ffmpeg 可执行文件"):
                resolve_media_binary("ffmpeg")


class ExtractFramePathTests(unittest.IsolatedAsyncioTestCase):
    async def test_extract_last_frame_rejects_path_traversal_output_name(self):
        with self.assertRaisesRegex(ValueError, "非法 output_name"):
            await extract_last_frame("media/videos/input.mp4", "scene1_shot1", "../escape.png")
