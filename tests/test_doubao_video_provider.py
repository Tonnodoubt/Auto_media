import base64
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from app.services.video_providers.doubao import DoubaoVideoProvider, _to_data_url, optimize_doubao_prompt


class _FakeAsyncClientContext:
    def __init__(self, client):
        self.client = client

    async def __aenter__(self):
        return self.client

    async def __aexit__(self, exc_type, exc, tb):
        return False


class DoubaoPromptOptimizerTests(unittest.TestCase):
    def test_main_shot_prompt_keeps_camera_motion_identity_and_readable_action(self):
        prompt = (
            "Medium shot. Eye-level. Slow Dolly in. Li Ming steps toward the desk. "
            "Keep the same face, hairstyle, primary outfit silhouette, colors, and signature accessories throughout the clip. "
            "Make the action clearly readable on screen with visible body travel, natural cloth follow-through, and stable limb and hand anatomy. "
            "Wooden room with a desk. Soft overcast light."
        )

        optimized = optimize_doubao_prompt(prompt)

        self.assertIn("Slow Dolly in", optimized)
        self.assertIn("Li Ming steps toward the desk", optimized)
        self.assertIn("same face", optimized)
        self.assertIn("clearly readable", optimized)

    def test_negative_prompt_guardrails_are_folded_into_text_when_provider_has_no_native_negative(self):
        optimized = optimize_doubao_prompt(
            "Medium shot. Static camera. Li Ming raises his head.",
            negative_prompt="identity drift, outfit drift, limb distortion, background morphing, camera jitter",
        )

        self.assertIn("Avoid identity drift", optimized)
        self.assertIn("outfit drift", optimized)
        self.assertIn("warped anatomy", optimized)
        self.assertIn("background morphing", optimized)

    def test_transition_prompt_keeps_middle_frame_continuity_guidance(self):
        prompt = (
            "Short cinematic transition between two adjacent storyboard shots. "
            "Start from the exact ending frame of Li Ming at the doorway. "
            "Arrive at the exact opening frame of Li Ming by the desk. "
            "The middle frames must interpolate pose, body orientation, clothing folds, prop placement, and camera perspective gradually instead of morphing suddenly halfway. "
            "Keep identity, outfit, props, environment logic, lighting direction, and camera continuity consistent."
        )

        optimized = optimize_doubao_prompt(prompt, has_last_frame=True)

        self.assertIn("exact last anchor frame", optimized)
        self.assertIn("middle frames", optimized)
        self.assertIn("same face", optimized)


class DoubaoProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_to_data_url_reads_local_media_file_without_http_roundtrip(self):
        image_bytes = b"\x89PNG\r\n\x1a\nlocal-frame"

        with TemporaryDirectory() as tmpdir:
            media_dir = Path(tmpdir) / "media"
            image_path = media_dir / "images" / "frame.png"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image_path.write_bytes(image_bytes)

            with (
                patch("app.services.video_providers.doubao.MEDIA_DIR", media_dir),
                patch("app.services.video_providers.doubao.httpx.AsyncClient") as client_cls,
            ):
                result = await _to_data_url("http://localhost:8000/media/images/frame.png")

        client_cls.assert_not_called()
        self.assertEqual(result, f"data:image/png;base64,{base64.b64encode(image_bytes).decode()}")

    async def test_to_data_url_rejects_private_host_without_media_mapping(self):
        with patch("app.services.video_providers.doubao.httpx.AsyncClient") as client_cls:
            with self.assertRaisesRegex(ValueError, "private/local host"):
                await _to_data_url("http://localhost:8000/not-media/frame.png")

        client_cls.assert_not_called()

    async def test_to_data_url_rejects_hostname_that_resolves_to_private_ip(self):
        with (
            patch("app.services.video_providers.doubao.httpx.AsyncClient") as client_cls,
            patch(
                "app.services.video_providers.doubao._resolve_hostname_ips",
                new=AsyncMock(return_value=["127.0.0.1"]),
            ),
        ):
            with self.assertRaisesRegex(ValueError, "resolves to a private/local address"):
                await _to_data_url("https://public.example.com/internal/frame.png")

        client_cls.assert_not_called()

    async def test_generate_passes_negative_prompt_into_submit(self):
        provider = DoubaoVideoProvider()
        submit_mock = AsyncMock(return_value="task-1")
        poll_mock = AsyncMock(return_value="https://files.example.com/video.mp4")

        with (
            patch(
                "app.services.video_providers.doubao.httpx.AsyncClient",
                return_value=_FakeAsyncClientContext(object()),
            ),
            patch.object(provider, "_submit", submit_mock),
            patch.object(provider, "_poll", poll_mock),
        ):
            result = await provider.generate(
                image_url="https://files.example.com/frame.png",
                prompt="Medium shot. Li Ming steps forward.",
                model="doubao-seedance-1-0-pro-250528",
                api_key="test-key",
                base_url="https://ark.example.com",
                negative_prompt="identity drift, outfit drift",
            )

        self.assertEqual(result, "https://files.example.com/video.mp4")
        self.assertEqual(submit_mock.await_args.kwargs["negative_prompt"], "identity drift, outfit drift")
        self.assertEqual(submit_mock.await_args.kwargs["duration_seconds"], None)
        self.assertEqual(poll_mock.await_args.args[1], "task-1")
