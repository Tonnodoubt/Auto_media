import unittest

from app.core.story_context import (
    _clean_design_prompt_anchor_source,
    _extract_design_prompt_description,
)
from app.prompts.character import build_character_prompt, build_character_section


class StoryContextAnchorBoundaryTests(unittest.TestCase):
    def test_extract_design_prompt_description_stops_before_template_lock_tokens(self):
        prompt = (
            "Full-body character design sheet for Li Ming, "
            "character description: young man, short black hair, slim build, "
            "identity_lock: keep the face shape fixed, "
            "style lock: ink wash illustration, "
            "show front view, side profile, and back view of the same character on one sheet"
        )

        self.assertEqual(
            _extract_design_prompt_description(prompt),
            "young man, short black hair, slim build",
        )

    def test_clean_anchor_source_strips_current_identity_and_style_lock_sections(self):
        prompt = build_character_prompt(
            "Li Ming",
            "lead",
            "young man, short black hair, slim build, wearing a dark blue robe",
            art_style="ink wash illustration",
        )

        cleaned = _clean_design_prompt_anchor_source(prompt)

        self.assertIn("young man", cleaned)
        self.assertIn("short black hair", cleaned)
        self.assertIn("dark blue robe", cleaned)
        self.assertNotIn("identity constraints", cleaned.lower())
        self.assertNotIn("style lock", cleaned.lower())
        self.assertNotIn("follow this exact art style", cleaned.lower())
        self.assertNotIn("show front view", cleaned.lower())

    def test_build_character_section_ignores_lock_sections_in_design_prompt(self):
        section = build_character_section(
            {
                "characters": [
                    {
                        "id": "char_li_ming",
                        "name": "Li Ming",
                        "role": "lead",
                        "description": "lead character",
                    }
                ],
                "character_images": {
                    "char_li_ming": {
                        "design_prompt": build_character_prompt(
                            "Li Ming",
                            "lead",
                            "young man, short black hair, slim build, wearing a dark blue robe",
                            art_style="ink wash illustration",
                        ),
                        "character_id": "char_li_ming",
                        "character_name": "Li Ming",
                    }
                },
            }
        )

        self.assertIn("Visual DNA:", section)
        self.assertIn("young man", section)
        self.assertIn("short black hair", section)
        self.assertIn("dark blue robe", section)
        self.assertNotIn("identity constraints", section.lower())
        self.assertNotIn("style lock", section.lower())
        self.assertNotIn("follow this exact art style", section.lower())
        self.assertNotIn("show front view", section.lower())

    def test_build_character_section_keeps_description_as_final_fallback(self):
        section = build_character_section(
            {
                "characters": [
                    {
                        "id": "char_li_ming",
                        "name": "Li Ming",
                        "role": "lead",
                        "description": "young man, short black hair, slim build, wearing a dark blue robe",
                    }
                ],
                "character_images": {
                    "char_li_ming": {
                        "design_prompt": "Legacy character turnaround prompt for Li Ming, wearing a dark blue robe",
                        "character_id": "char_li_ming",
                        "character_name": "Li Ming",
                    }
                },
            }
        )

        self.assertIn("Visual DNA:", section)
        self.assertIn("young man", section)
        self.assertIn("short black hair", section)
        self.assertIn("slim build", section)
        self.assertIn("dark blue robe", section)


if __name__ == "__main__":
    unittest.main()
