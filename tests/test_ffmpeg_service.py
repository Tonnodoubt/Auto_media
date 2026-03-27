import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.ffmpeg import resolve_media_binary


class ResolveMediaBinaryTests(unittest.TestCase):
    def tearDown(self):
        resolve_media_binary.cache_clear()

    def test_resolve_media_binary_uses_env_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            binary_path = Path(tmpdir) / "ffmpeg"
            binary_path.write_text("", encoding="utf-8")

            with patch.dict(os.environ, {"FFMPEG_PATH": str(binary_path)}, clear=False):
                resolve_media_binary.cache_clear()
                self.assertEqual(resolve_media_binary("ffmpeg"), str(binary_path))

    def test_resolve_media_binary_raises_clear_error_when_missing(self):
        with (
            patch.dict(os.environ, {"FFMPEG_PATH": ""}, clear=False),
            patch("app.services.ffmpeg.shutil.which", return_value=None),
            patch("app.services.ffmpeg._COMMON_BINARY_DIRS", ()),
        ):
            resolve_media_binary.cache_clear()
            with self.assertRaisesRegex(RuntimeError, "未找到 ffmpeg 可执行文件"):
                resolve_media_binary("ffmpeg")
