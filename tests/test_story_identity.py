import unittest

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


if __name__ == "__main__":
    unittest.main()
