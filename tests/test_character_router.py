import unittest
from unittest.mock import AsyncMock, patch

from fastapi import Request

from app.routers.character import (
    BatchCharacterRequest,
    CharacterImageRequest,
    generate_all,
    generate_single,
)


def _make_request() -> Request:
    return Request({"type": "http", "headers": []})


class CharacterRouterQualityPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_single_persists_quality_on_character_asset(self):
        quality_payload = {
            "enabled": True,
            "family": "character_design_prompt",
            "final_passed": True,
        }
        upsert_character_images = AsyncMock()

        with (
            patch("app.routers.character.get_art_style", return_value=""),
            patch("app.routers.character.resolve_image_model", return_value="test-model"),
            patch(
                "app.routers.character.generate_character_image",
                new=AsyncMock(
                    return_value={
                        "character_name": "李明",
                        "image_url": "/media/characters/li_ming.png",
                        "image_path": "media/characters/li_ming.png",
                        "prompt": "guarded character prompt",
                        "quality": quality_payload,
                    }
                ),
            ),
            patch("app.routers.character.repo.get_story", new=AsyncMock(return_value={"character_images": {}})),
            patch("app.routers.character.repo.upsert_character_images", new=upsert_character_images),
            patch("app.routers.character.repo.save_story", new=AsyncMock()),
        ):
            response = await generate_single(
                CharacterImageRequest(
                    story_id="story-character-quality",
                    character_id="char_li_ming",
                    character_name="李明",
                    role="主角",
                    description="短发，深蓝长袍",
                ),
                _make_request(),
                image_config={"image_api_key": "img-key", "image_base_url": "https://image.example.com"},
                db=None,
            )

        persisted_record = upsert_character_images.await_args.args[2]["char_li_ming"]
        self.assertEqual(persisted_record["quality"], quality_payload)
        self.assertEqual(persisted_record["design_prompt"], "guarded character prompt")
        self.assertEqual(response.character_name, "李明")

    async def test_generate_all_persists_quality_on_each_character_asset(self):
        quality_payload = {
            "enabled": True,
            "family": "character_design_prompt",
            "final_passed": True,
        }
        upsert_character_images = AsyncMock()

        with (
            patch("app.routers.character.get_art_style", return_value=""),
            patch("app.routers.character.resolve_image_model", return_value="test-model"),
            patch(
                "app.routers.character.generate_character_images_batch",
                new=AsyncMock(
                    return_value=[
                        {
                            "character_name": "李明",
                            "image_url": "/media/characters/li_ming.png",
                            "image_path": "media/characters/li_ming.png",
                            "prompt": "guarded Li Ming prompt",
                            "quality": quality_payload,
                        },
                        {
                            "character_name": "阿月",
                            "image_url": "/media/characters/a_yue.png",
                            "image_path": "media/characters/a_yue.png",
                            "prompt": "guarded A Yue prompt",
                            "quality": quality_payload,
                        },
                    ]
                ),
            ),
            patch("app.routers.character.repo.get_story", new=AsyncMock(return_value={"character_images": {}})),
            patch("app.routers.character.repo.upsert_character_images", new=upsert_character_images),
            patch("app.routers.character.repo.save_story", new=AsyncMock()),
        ):
            response = await generate_all(
                BatchCharacterRequest(
                    story_id="story-character-quality-batch",
                    characters=[
                        {"id": "char_li_ming", "name": "李明", "role": "主角", "description": "短发，深蓝长袍"},
                        {"id": "char_a_yue", "name": "阿月", "role": "配角", "description": "黑发，青衣"},
                    ],
                ),
                _make_request(),
                image_config={"image_api_key": "img-key", "image_base_url": "https://image.example.com"},
                db=None,
            )

        persisted_payload = upsert_character_images.await_args.args[2]
        self.assertEqual(persisted_payload["char_li_ming"]["quality"], quality_payload)
        self.assertEqual(persisted_payload["char_a_yue"]["quality"], quality_payload)
        self.assertEqual(len(response.results), 2)
