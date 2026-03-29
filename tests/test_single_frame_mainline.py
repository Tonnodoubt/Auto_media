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
        dashscope_api_key="",
        dashscope_base_url="https://dashscope.aliyuncs.com/api/v1",
        kling_api_key="",
        kling_base_url="https://api.klingai.com",
        doubao_api_key="",
        doubao_base_url="https://ark.cn-beijing.volces.com/api/v3",
        validate_base_url_dns=False,
    )
    sys.modules["app.core.config"] = config_stub
    _INJECTED_CONFIG_STUB = True

from app.core.story_context import build_generation_payload
from app.schemas.storyboard import CameraSetup, Shot, VisualElements
from app.services.image import generate_images_batch
from app.services.storyboard_state import serialize_shot_for_storage
from app.services.video import generate_videos_batch


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


if __name__ == "__main__":
    unittest.main()
