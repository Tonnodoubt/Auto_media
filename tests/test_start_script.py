import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import start


class StartScriptTests(unittest.TestCase):
    def test_build_runtime_env_injects_common_binary_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch.object(start, "COMMON_BINARY_DIRS", (Path(tmpdir),)),
                patch.dict(os.environ, {"PATH": "/usr/bin"}, clear=False),
            ):
                env = start.build_runtime_env()

        self.assertEqual(env["PATH"].split(os.pathsep)[0], tmpdir)

    def test_detect_ffmpeg_install_command_uses_homebrew_on_macos(self):
        def fake_which(name, path=None):
            if name == "brew":
                self.assertEqual(path, "/custom/bin")
                return "/opt/homebrew/bin/brew"
            return None

        with (
            patch("start.platform.system", return_value="Darwin"),
            patch("start.shutil.which", side_effect=fake_which),
        ):
            cmd, installer_name = start.detect_ffmpeg_install_command({"PATH": "/custom/bin"})

        self.assertEqual(cmd, ["brew", "install", "ffmpeg"])
        self.assertEqual(installer_name, "Homebrew")

    def test_ensure_ffmpeg_exports_binary_paths(self):
        env = {"PATH": "/usr/bin"}
        with patch("start.resolve_binary", side_effect=["/tmp/ffmpeg", "/tmp/ffprobe"]):
            updated = start.ensure_ffmpeg(env)

        self.assertEqual(updated["FFMPEG_PATH"], "/tmp/ffmpeg")
        self.assertEqual(updated["FFPROBE_PATH"], "/tmp/ffprobe")
        self.assertEqual(updated["PATH"].split(os.pathsep)[:3], ["/tmp", "/usr/bin"])

    def test_resolve_binary_rejects_non_executable_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            binary_path = Path(tmpdir) / "ffmpeg"
            binary_path.write_text("", encoding="utf-8")
            binary_path.chmod(0o644)

            with self.assertRaisesRegex(RuntimeError, "不是可执行文件"):
                start.resolve_binary("ffmpeg", {"FFMPEG_PATH": str(binary_path), "PATH": "/usr/bin"})
