import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

_PREVIOUS_CONFIG_MODULE = sys.modules.get("app.core.config")
_INJECTED_CONFIG_STUB = False

if "app.core.config" not in sys.modules:
    config_stub = types.ModuleType("app.core.config")
    config_stub.settings = types.SimpleNamespace(
        database_url="sqlite+aiosqlite:///:memory:",
        debug=False,
        default_llm_provider="claude",
        anthropic_api_key="",
        anthropic_base_url="https://api.anthropic.com",
        openai_api_key="",
        openai_base_url="https://api.openai.com/v1",
        qwen_api_key="",
        qwen_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        zhipu_api_key="",
        zhipu_base_url="https://open.bigmodel.cn/api/paas/v4/",
        gemini_api_key="",
        gemini_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        siliconflow_api_key="",
        siliconflow_base_url="https://api.siliconflow.cn/v1",
        siliconflow_image_base_url="https://api.siliconflow.cn/v1",
        siliconflow_image_model="black-forest-labs/FLUX.1-schnell",
        dashscope_api_key="",
        dashscope_base_url="https://dashscope.aliyuncs.com/api/v1",
        dashscope_video_base_url="https://dashscope.aliyuncs.com/api/v1",
        dashscope_video_model="wan2.6-i2v-flash",
        kling_api_key="",
        kling_base_url="https://api.klingai.com",
        kling_video_base_url="https://api.klingai.com",
        kling_video_model="kling-v2-master",
        minimax_video_api_key="",
        minimax_video_base_url="https://api.minimaxi.chat/v1",
        minimax_video_model="video-01",
        doubao_api_key="",
        doubao_base_url="https://ark.cn-beijing.volces.com/api/v3",
        doubao_image_base_url="https://ark.cn-beijing.volces.com/api/v3",
        doubao_video_base_url="https://ark.cn-beijing.volces.com/api/v3",
        doubao_image_model="ep-test-image",
        doubao_video_model="ep-test-video",
        default_image_model="black-forest-labs/FLUX.1-schnell",
        default_video_model="wan2.6-i2v-flash",
        validate_base_url_dns=False,
    )
    sys.modules["app.core.config"] = config_stub
    _INJECTED_CONFIG_STUB = True

from app.core.story_context import build_generation_payload
from app.schemas.storyboard import CameraSetup, Shot, VisualElements
from app.services.image import generate_images_batch
from app.services.storyboard_state import serialize_shot_for_storage
from app.services.video import generate_videos_batch, generate_videos_chained


def tearDownModule():
    if _INJECTED_CONFIG_STUB:
        sys.modules.pop("app.core.config", None)
        if _PREVIOUS_CONFIG_MODULE is not None:
            sys.modules["app.core.config"] = _PREVIOUS_CONFIG_MODULE


class SingleFrameMainlineTests(unittest.IsolatedAsyncioTestCase):
    def test_build_generation_payload_omits_last_frame_prompt(self):
        payload = build_generation_payload(
            {
                "shot_id": "scene1_shot1",
                "storyboard_description": "李明停在门口。",
                "image_prompt": "Medium shot. Li Ming pauses at the doorway.",
                "final_video_prompt": "Medium shot. Static camera. Li Ming steps forward.",
                "last_frame_prompt": "Medium shot. Li Ming has already entered the room.",
            },
            ctx=None,
            art_style="cinematic watercolor",
        )

        self.assertIn("image_prompt", payload)
        self.assertIn("final_video_prompt", payload)
        self.assertNotIn("last_frame_prompt", payload)

    def test_serialize_shot_for_storage_drops_deprecated_last_frame_fields(self):
        shot = Shot(
            shot_id="scene1_shot1",
            storyboard_description="李明推门进入房间。",
            camera_setup=CameraSetup(shot_size="MS", camera_angle="Eye-level", movement="Static"),
            visual_elements=VisualElements(
                subject_and_clothing="李明穿深蓝长衫",
                action_and_expression="推门进入",
                environment_and_props="木门与室内桌案",
                lighting_and_color="柔和室内暖光",
            ),
            image_prompt="Medium shot. Li Ming pauses with one hand on the door.",
            final_video_prompt="Medium shot. Static camera. Li Ming pushes the door open and steps inside.",
            last_frame_prompt="Medium shot. Li Ming is already inside the room.",
            last_frame_url="/media/images/scene1_shot1_last.png",
        )

        serialized = serialize_shot_for_storage(shot)

        self.assertNotIn("last_frame_prompt", serialized)
        self.assertNotIn("last_frame_url", serialized)

    async def test_generate_images_batch_ignores_last_frame_prompt(self):
        mock_result = {
            "shot_id": "scene1_shot1",
            "image_path": "media/images/scene1_shot1.png",
            "image_url": "/media/images/scene1_shot1.png",
        }

        with patch("app.services.image.generate_image", new=AsyncMock(return_value=mock_result)) as mock_generate:
            results = await generate_images_batch(
                [
                    {
                        "shot_id": "scene1_shot1",
                        "image_prompt": "Medium shot. Li Ming pauses at the doorway.",
                        "last_frame_prompt": "Deprecated ending pose prompt.",
                    }
                ]
            )

        self.assertEqual(mock_generate.await_count, 1)
        self.assertEqual(results[0]["image_url"], "/media/images/scene1_shot1.png")
        self.assertNotIn("last_frame_url", results[0])

    async def test_generate_videos_batch_forces_single_frame_mode(self):
        with patch(
            "app.services.video.generate_video",
            new=AsyncMock(return_value={"shot_id": "scene1_shot1", "video_path": "media/videos/scene1_shot1.mp4", "video_url": "/media/videos/scene1_shot1.mp4"}),
        ) as mock_generate:
            results = await generate_videos_batch(
                [
                    {
                        "shot_id": "scene1_shot1",
                        "image_url": "/media/images/scene1_shot1.png",
                        "final_video_prompt": "Medium shot. Static camera. Li Ming steps forward.",
                        "last_frame_url": "/media/images/legacy_last_frame.png",
                    }
                ],
                base_url="http://localhost:8000",
            )

        self.assertEqual(results[0]["video_url"], "/media/videos/scene1_shot1.mp4")
        self.assertEqual(mock_generate.await_args.kwargs["last_frame_url"], "")

    async def test_generate_videos_chained_reuses_previous_image_within_same_scene_only(self):
        async def _fake_generate_image(**kwargs):
            shot_id = kwargs["shot_id"]
            return {
                "shot_id": shot_id,
                "image_path": f"media/images/{shot_id}.png",
                "image_url": f"/media/images/{shot_id}.png",
            }

        async def _fake_generate_video(**kwargs):
            shot_id = kwargs["shot_id"]
            return {
                "shot_id": shot_id,
                "video_path": f"media/videos/{shot_id}.mp4",
                "video_url": f"/media/videos/{shot_id}.mp4",
            }

        with (
            patch("app.services.image.generate_image", new=AsyncMock(side_effect=_fake_generate_image)) as image_mock,
            patch("app.services.video.generate_video", new=AsyncMock(side_effect=_fake_generate_video)),
        ):
            results = await generate_videos_chained(
                [
                    {
                        "shot_id": "scene1_shot1",
                        "image_prompt": "Shot 1",
                        "final_video_prompt": "Video 1",
                    },
                    {
                        "shot_id": "scene1_shot2",
                        "image_prompt": "Shot 2",
                        "final_video_prompt": "Video 2",
                    },
                    {
                        "shot_id": "scene2_shot1",
                        "image_prompt": "Shot 3",
                        "final_video_prompt": "Video 3",
                    },
                ],
                base_url="http://localhost:8000",
            )

        calls_by_shot_id = {
            call.kwargs["shot_id"]: call.kwargs
            for call in image_mock.await_args_list
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


if __name__ == "__main__":
    unittest.main()
