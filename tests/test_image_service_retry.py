import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from app.services.image import generate_character_image, generate_image, generate_images_batch

TMP_ROOT = Path(__file__).resolve().parents[1] / ".tmp" / "tests" / "image_service_retry"
TMP_ROOT.mkdir(parents=True, exist_ok=True)


class _FakeResponse:
    def __init__(self, *, status_code=200, json_data=None, content=b"", text=""):
        self.status_code = status_code
        self._json_data = json_data
        self.content = content
        self.text = text

    @property
    def is_success(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.is_success:
            return
        request = httpx.Request("GET", "https://files.example.com/generated.png")
        response = httpx.Response(self.status_code, request=request, text=self.text)
        raise httpx.HTTPStatusError(f"status={self.status_code}", request=request, response=response)


class _FakeAsyncClient:
    def __init__(self, planned_results):
        self.planned_results = list(planned_results)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        result = self.planned_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class CharacterImageRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_character_image_retries_transient_read_error(self):
        request = httpx.Request("POST", "https://api.example.com/images/generations")
        fake_client = _FakeAsyncClient(
            [
                httpx.ReadError("", request=request),
                _FakeResponse(
                    status_code=200,
                    json_data={"images": [{"url": "https://files.example.com/generated.png"}]},
                    content=b'{"images":[{"url":"https://files.example.com/generated.png"}]}',
                ),
                _FakeResponse(status_code=200, content=b"png-bytes"),
            ]
        )
        target_dir = TMP_ROOT / "characters_ok"
        target_dir.mkdir(parents=True, exist_ok=True)

        with (
            patch("app.services.image.httpx.AsyncClient", return_value=fake_client),
            patch("app.services.image.CHARACTER_DIR", target_dir),
        ):
            result = await generate_character_image(
                character_name="hero",
                role="lead",
                description="brave",
                story_id="story_retry_ok",
                model="test-model",
                image_api_key="test-key",
                image_base_url="https://api.example.com",
            )

        post_calls = [call for call in fake_client.calls if call[0] == "POST"]
        self.assertEqual(len(post_calls), 2)
        self.assertEqual(result["character_name"], "hero")
        self.assertTrue(result["image_url"].startswith("/media/characters/"))

    async def test_generate_character_image_reports_upstream_target_after_retries(self):
        request = httpx.Request("POST", "https://api.example.com/images/generations")
        fake_client = _FakeAsyncClient(
            [
                httpx.ReadError("", request=request),
                httpx.ReadError("", request=request),
                httpx.ReadError("", request=request),
            ]
        )
        target_dir = TMP_ROOT / "characters_fail"
        target_dir.mkdir(parents=True, exist_ok=True)

        with (
            patch("app.services.image.httpx.AsyncClient", return_value=fake_client),
            patch("app.services.image.CHARACTER_DIR", target_dir),
        ):
            with self.assertRaisesRegex(RuntimeError, "https://api.example.com/images/generations"):
                await generate_character_image(
                    character_name="hero",
                    role="lead",
                    description="brave",
                    story_id="story_retry_fail",
                    model="test-model",
                    image_api_key="test-key",
                    image_base_url="https://api.example.com",
                )


class ImageReferenceRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_image_marks_when_reference_images_are_dropped_on_retry(self):
        fake_client = _FakeAsyncClient(
            [
                _FakeResponse(status_code=400, text="reference images rejected"),
                _FakeResponse(
                    status_code=200,
                    json_data={"images": [{"url": "https://files.example.com/generated.png"}]},
                    content=b'{"images":[{"url":"https://files.example.com/generated.png"}]}',
                ),
                _FakeResponse(status_code=200, content=b"png-bytes"),
            ]
        )
        target_dir = TMP_ROOT / "images_reference_retry"
        target_dir.mkdir(parents=True, exist_ok=True)

        with (
            patch("app.services.image.httpx.AsyncClient", return_value=fake_client),
            patch("app.services.image.IMAGE_DIR", target_dir),
            patch("app.services.image._resolve_reference_image_value", new=AsyncMock(return_value="data:image/png;base64,AAA")),
        ):
            result = await generate_image(
                visual_prompt="Medium shot. Hero at doorway.",
                shot_id="scene1_shot1",
                model="test-model",
                image_api_key="test-key",
                image_base_url="https://api.example.com",
                reference_images=[{"image_url": "/media/characters/hero.png"}],
                output_dir=target_dir,
            )

        self.assertFalse(result["reference_images_applied"])
        self.assertEqual(result["dropped_reference_count"], 1)

    async def test_generate_images_batch_preserves_reference_retry_flags(self):
        with patch(
            "app.services.image.generate_image",
            new=AsyncMock(
                return_value={
                    "shot_id": "scene1_shot1",
                    "image_path": "media/images/scene1_shot1.png",
                    "image_url": "/media/images/scene1_shot1.png",
                    "reference_images_applied": False,
                    "dropped_reference_count": 2,
                }
            ),
        ):
            results = await generate_images_batch(
                [{"shot_id": "scene1_shot1", "image_prompt": "Medium shot. Hero at doorway."}],
                model="test-model",
            )

        self.assertEqual(results[0]["dropped_reference_count"], 2)
        self.assertFalse(results[0]["reference_images_applied"])

    async def test_generate_images_batch_chains_previous_image_within_same_scene_only(self):
        async def _fake_generate_image(**kwargs):
            shot_id = kwargs["shot_id"]
            return {
                "shot_id": shot_id,
                "image_path": f"media/images/{shot_id}.png",
                "image_url": f"/media/images/{shot_id}.png",
                "reference_images_applied": bool(kwargs.get("reference_images")),
                "dropped_reference_count": 0,
            }

        with patch("app.services.image.generate_image", new=AsyncMock(side_effect=_fake_generate_image)) as generate_mock:
            results = await generate_images_batch(
                [
                    {"shot_id": "scene1_shot1", "image_prompt": "Shot 1"},
                    {"shot_id": "scene1_shot2", "image_prompt": "Shot 2"},
                    {"shot_id": "scene2_shot1", "image_prompt": "Shot 3"},
                ],
                model="test-model",
            )

        calls_by_shot_id = {
            call.kwargs["shot_id"]: call.kwargs
            for call in generate_mock.await_args_list
        }

        self.assertIsNone(calls_by_shot_id["scene1_shot1"]["reference_images"])
        self.assertEqual(
            calls_by_shot_id["scene1_shot2"]["reference_images"],
            [
                {
                    "kind": "previous_shot_image",
                    "image_url": "/media/images/scene1_shot1.png",
                    "image_path": "media/images/scene1_shot1.png",
                    "weight": 0.38,
                }
            ],
        )
        self.assertIsNone(calls_by_shot_id["scene2_shot1"]["reference_images"])
        self.assertEqual([result["shot_id"] for result in results], ["scene1_shot1", "scene1_shot2", "scene2_shot1"])
