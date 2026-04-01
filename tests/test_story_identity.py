import unittest

from app.core.consistency_cache import APPEARANCE_CACHE_SCHEMA_VERSION, SCENE_STYLE_CACHE_SCHEMA_VERSION
from app.core.story_identity import normalize_story_record


class StoryIdentityTests(unittest.TestCase):
    def test_normalize_story_record_preserves_existing_fields_when_omitted(self):
        existing_story = {
            "characters": [
                {"id": "char_li_ming", "name": "Li Ming", "role": "lead", "description": "young man"},
            ],
            "relationships": [
                {"source": "Li Ming", "target": "Boss Zhao", "source_id": "char_li_ming", "target_id": "char_boss_zhao", "label": "rival"},
            ],
            "character_images": {
                "char_li_ming": {
                    "character_id": "char_li_ming",
                    "character_name": "Li Ming",
                    "image_url": "/media/li-ming.png",
                }
            },
        }

        normalized = normalize_story_record({"idea": "new idea"}, existing_story=existing_story)

        self.assertEqual(normalized["characters"], existing_story["characters"])
        self.assertEqual(normalized["relationships"], existing_story["relationships"])
        self.assertEqual(normalized["character_images"], existing_story["character_images"])

    def test_normalize_story_record_merges_meta_with_existing_story(self):
        existing_story = {
            "characters": [
                {"id": "char_li_ming", "name": "Li Ming", "role": "lead", "description": "young man"},
            ],
            "meta": {
                "theme": "old theme",
                "character_appearance_cache": {
                    "Li Ming": {"body": "young man", "clothing": "dark blue robe"},
                },
            },
        }

        normalized = normalize_story_record(
            {"meta": {"theme": "new theme"}},
            existing_story=existing_story,
        )

        self.assertEqual(normalized["meta"]["theme"], "new theme")
        self.assertIn("character_appearance_cache", normalized["meta"])
        self.assertIn("char_li_ming", normalized["meta"]["character_appearance_cache"])

    def test_normalize_story_record_normalizes_cache_metadata_fields(self):
        normalized = normalize_story_record(
            {
                "characters": [
                    {"id": "char_li_ming", "name": "Li Ming", "role": "lead", "description": "young man"},
                ],
                "meta": {
                    "character_appearance_cache": {
                        "Li Ming": {
                            "body": " young man ",
                            "clothing": " dark blue robe ",
                            "schema_version": "1",
                            "source_provider": " openai ",
                            "source_model": " gpt-4o-mini ",
                            "updated_at": " 2026-03-31T12:00:00+00:00 ",
                        },
                    },
                    "scene_style_cache": [
                        {
                            "keywords": [" teahouse ", " "],
                            "image_extra": " jiangnan teahouse ",
                            "video_extra": " rain mist ",
                            "negative_prompt": " cars ",
                            "schema_version": "1",
                            "source_provider": " openai ",
                            "source_model": " gpt-4o-mini ",
                            "updated_at": " 2026-03-31T12:00:00+00:00 ",
                        }
                    ],
                },
            }
        )

        appearance = normalized["meta"]["character_appearance_cache"]["char_li_ming"]
        self.assertEqual(appearance["body"], "young man")
        self.assertEqual(appearance["clothing"], "dark blue robe")
        self.assertEqual(appearance["schema_version"], 1)
        self.assertEqual(appearance["source_provider"], "openai")
        self.assertEqual(appearance["source_model"], "gpt-4o-mini")
        self.assertEqual(appearance["updated_at"], "2026-03-31T12:00:00+00:00")

        scene_style = normalized["meta"]["scene_style_cache"][0]
        self.assertEqual(scene_style["keywords"], ["teahouse"])
        self.assertEqual(scene_style["image_extra"], "jiangnan teahouse")
        self.assertEqual(scene_style["video_extra"], "rain mist")
        self.assertEqual(scene_style["negative_prompt"], "cars")
        self.assertEqual(scene_style["schema_version"], 1)
        self.assertEqual(scene_style["source_provider"], "openai")
        self.assertEqual(scene_style["source_model"], "gpt-4o-mini")
        self.assertEqual(scene_style["updated_at"], "2026-03-31T12:00:00+00:00")

    def test_normalize_story_record_preserves_future_cache_schema_versions_for_refresh(self):
        normalized = normalize_story_record(
            {
                "meta": {
                    "character_appearance_cache": {
                        "char_li_ming": {
                            "body": "young man",
                            "schema_version": str(APPEARANCE_CACHE_SCHEMA_VERSION + 1),
                        },
                    },
                    "scene_style_cache": [
                        {
                            "image_extra": "jiangnan teahouse",
                            "schema_version": str(SCENE_STYLE_CACHE_SCHEMA_VERSION + 1),
                        }
                    ],
                }
            }
        )

        self.assertEqual(
            normalized["meta"]["character_appearance_cache"]["char_li_ming"]["schema_version"],
            APPEARANCE_CACHE_SCHEMA_VERSION + 1,
        )
        self.assertEqual(
            normalized["meta"]["scene_style_cache"][0]["schema_version"],
            SCENE_STYLE_CACHE_SCHEMA_VERSION + 1,
        )

    def test_normalize_story_record_strips_micro_action_noise_from_character_description(self):
        normalized = normalize_story_record(
            {
                "characters": [
                    {
                        "id": "char_a_yue",
                        "name": "阿月",
                        "role": "配角",
                        "description": (
                            "黑色短发，寡言谨慎，"
                            "每次出入地窖必以指甲刮擦第三级石阶东侧青砖，留下0.3mm深划痕"
                        ),
                    }
                ]
            }
        )

        self.assertEqual(
            normalized["characters"][0]["description"],
            "黑色短发，寡言谨慎",
        )


if __name__ == "__main__":
    unittest.main()
