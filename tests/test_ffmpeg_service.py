import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.services.ffmpeg import _resolve_image_output_path, extract_last_frame, resolve_media_binary

TMP_ROOT = Path(__file__).resolve().parents[1] / ".tmp" / "tests"
TMP_ROOT.mkdir(parents=True, exist_ok=True)


class ResolveMediaBinaryTests(unittest.TestCase):
    def tearDown(self):
        resolve_media_binary.cache_clear()

    def test_resolve_media_binary_uses_env_override(self):
        with tempfile.TemporaryDirectory(dir=TMP_ROOT) as tmpdir:
            binary_path = Path(tmpdir) / "ffmpeg"
            binary_path.write_text("", encoding="utf-8")
            binary_path.chmod(0o755)

            with patch.dict(os.environ, {"FFMPEG_PATH": str(binary_path)}, clear=False):
                resolve_media_binary.cache_clear()
                self.assertEqual(resolve_media_binary("ffmpeg"), str(binary_path))

    def test_resolve_media_binary_rejects_non_executable_env_override(self):
        with tempfile.TemporaryDirectory(dir=TMP_ROOT) as tmpdir:
            binary_path = Path(tmpdir) / "ffmpeg"
            binary_path.write_text("", encoding="utf-8")
            binary_path.chmod(0o644)

            with patch.dict(os.environ, {"FFMPEG_PATH": str(binary_path)}, clear=False):
                resolve_media_binary.cache_clear()
                with self.assertRaisesRegex(RuntimeError, "不是可执行文件"):
                    resolve_media_binary("ffmpeg")

    def test_resolve_media_binary_raises_clear_error_when_missing(self):
        with (
            patch.dict(os.environ, {"FFMPEG_PATH": "", "LOCALAPPDATA": ""}, clear=False),
            patch("app.services.ffmpeg.shutil.which", return_value=None),
            patch("app.services.ffmpeg._COMMON_BINARY_DIRS", ()),
        ):
            resolve_media_binary.cache_clear()
            with self.assertRaisesRegex(RuntimeError, "未找到 ffmpeg 可执行文件"):
                resolve_media_binary("ffmpeg")
    def test_resolve_media_binary_finds_winget_binary_on_windows(self):
        with tempfile.TemporaryDirectory(dir=TMP_ROOT) as tmpdir:
            packages_dir = Path(tmpdir) / "Microsoft" / "WinGet" / "Packages" / "Gyan.FFmpeg" / "bin"
            packages_dir.mkdir(parents=True)
            binary_path = packages_dir / "ffmpeg.exe"
            binary_path.write_text("", encoding="utf-8")
            binary_path.chmod(0o755)

            with (
                patch.dict(os.environ, {"LOCALAPPDATA": tmpdir, "FFMPEG_PATH": ""}, clear=False),
                patch("app.services.ffmpeg.platform.system", return_value="Windows"),
                patch("app.services.ffmpeg.shutil.which", return_value=None),
                patch("app.services.ffmpeg._COMMON_BINARY_DIRS", ()),
            ):
                resolve_media_binary.cache_clear()
                self.assertEqual(resolve_media_binary("ffmpeg"), str(binary_path))


class ExtractFramePathTests(unittest.IsolatedAsyncioTestCase):
    def test_resolve_image_output_path_rejects_path_traversal_default_name(self):
        with self.assertRaisesRegex(ValueError, "非法 default_name"):
            _resolve_image_output_path(None, "../escape.png")

    async def test_extract_last_frame_rejects_path_traversal_output_name(self):
        with self.assertRaisesRegex(ValueError, "非法 output_name"):
            await extract_last_frame("media/videos/input.mp4", "scene1_shot1", "../escape.png")

    async def test_extract_last_frame_uses_tighter_seek_window_near_video_end(self):
        with patch(
            "app.services.ffmpeg._extract_frame",
            new=AsyncMock(return_value="media/images/scene1_shot1_lastframe.png"),
        ) as extract_mock:
            result = await extract_last_frame("media/videos/input.mp4", "scene1_shot1")

        self.assertEqual(result, "media/images/scene1_shot1_lastframe.png")
        self.assertEqual(extract_mock.await_args.args[2:], ("-sseof", "-0.04"))
