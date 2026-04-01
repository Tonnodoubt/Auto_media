import unittest

from app.prompts.character import build_character_prompt, build_character_section


class CharacterPromptTests(unittest.TestCase):
    def test_build_character_prompt_uses_standard_three_view_sheet(self):
        prompt = build_character_prompt("李明", "主角", "青年男子，黑色短发，身形清瘦，穿着深蓝长衫。")  # noqa: RUF001

        self.assertIn("Standard three-view character turnaround sheet for 李明", prompt)
        self.assertIn("front view, side profile, and back view", prompt)
        self.assertIn("full body in all three views", prompt)
        self.assertIn("head-to-toe visible in every view", prompt)
        self.assertIn("no text, no captions, no labels, no watermark, no logo", prompt)
        self.assertIn("no foreground obstruction", prompt)
        self.assertIn("same wearing position across all three views", prompt)
        self.assertIn("non-negotiable identity constraints", prompt)
        self.assertIn("same exact moment", prompt)
        self.assertIn("one frozen instant seen from three camera positions", prompt)
        self.assertNotIn("photorealistic", prompt)

    def test_build_character_prompt_includes_explicit_style_lock(self):
        prompt = build_character_prompt(
            "李明",
            "主角",
            "青年男子，黑色短发，身形清瘦，穿着深蓝长衫。",  # noqa: RUF001
            art_style="国风工笔重彩插画，克制冷色调，电影级轮廓光",  # noqa: RUF001
        )

        self.assertIn("style lock: 国风工笔重彩插画，克制冷色调，电影级轮廓光", prompt)  # noqa: RUF001
        self.assertIn("follow this exact art style consistently across all three views", prompt)

    def test_build_character_prompt_strips_micro_precision_noise_from_description(self):
        prompt = build_character_prompt(
            "阿月",
            "配角",
            (
                "黑色短发，寡言谨慎，"
                "每次出入地窖必以指甲刮擦第三级石阶东侧青砖，留下0.3mm深划痕"
            ),  # noqa: RUF001
        )

        self.assertIn("黑色短发", prompt)
        self.assertNotIn("寡言谨慎", prompt)
        self.assertNotIn("第三级石阶东侧青砖", prompt)
        self.assertNotIn("0.3mm", prompt)

    def test_build_character_prompt_prefers_visual_details_over_personality_and_ability(self):
        prompt = build_character_prompt(
            "李明",
            "主角",
            "年轻男性，黑色短发，身形清瘦，穿着深蓝长袍。性格孤僻但内心善良，拥有解开时间循环秘密的能力。",  # noqa: RUF001
        )

        self.assertIn("年轻男性", prompt)
        self.assertIn("黑色短发", prompt)
        self.assertIn("穿着深蓝长袍", prompt)
        self.assertNotIn("性格孤僻", prompt)
        self.assertNotIn("时间循环秘密", prompt)
        self.assertIn("ignore personality, backstory, habits, abilities", prompt)

    def test_build_character_section_prefers_visual_dna(self):
        section = build_character_section(
            {
                "characters": [
                    {"id": "char_li_ming", "name": "李明", "role": "主角", "description": "青年男子，黑色短发。"},  # noqa: RUF001
                ],
                "character_images": {
                    "char_li_ming": {
                        "visual_dna": "young man, short black hair, slim build",
                        "design_prompt": "Standard three-view character turnaround sheet for 李明, dark blue robe",
                        "character_id": "char_li_ming",
                        "character_name": "李明",
                    }
                },
            }
        )

        self.assertIn("Visual DNA: young man, short black hair, slim build", section)
        self.assertNotIn("Standard three-view character turnaround sheet", section)

    def test_build_character_section_prefers_appearance_cache_over_legacy_visual_dna(self):
        section = build_character_section(
            {
                "characters": [
                    {"id": "char_li_ming", "name": "李明", "role": "主角", "description": "青年男子，黑色短发，穿着深蓝长衫。"},  # noqa: RUF001
                ],
                "character_images": {
                    "char_li_ming": {
                        "visual_dna": "young man, short black hair, brown cloak",
                        "character_id": "char_li_ming",
                        "character_name": "李明",
                    }
                },
                "meta": {
                    "character_appearance_cache": {
                        "char_li_ming": {
                            "body": "young man, short black hair, slim build",
                            "clothing": "dark blue robe",
                        }
                    }
                },
            }
        )

        self.assertIn("Visual DNA: young man, short black hair, slim build; dark blue robe", section)
        self.assertNotIn("brown cloak", section)

    def test_build_character_section_visual_dna_keeps_clothing_fallback(self):
        section = build_character_section(
            {
                "characters": [
                    {"id": "char_li_ming", "name": "李明", "role": "主角", "description": "青年男子，黑色短发，穿着深蓝长衫。"},  # noqa: RUF001
                ],
                "character_images": {
                    "char_li_ming": {
                        "visual_dna": "young man, short black hair, slim build",
                        "design_prompt": (
                            "Standard three-view character turnaround sheet for 李明, protagonist, determined expression, heroic bearing, "
                            "character description: 青年男子，黑色短发，穿着深蓝长衫。, "  # noqa: RUF001
                            "show front view, side profile, and back view of the same character on one sheet"
                        ),
                        "character_id": "char_li_ming",
                        "character_name": "李明",
                    }
                },
            }
        )

        self.assertIn("Visual DNA: young man, short black hair, slim build; 穿着深蓝长衫", section)

    def test_build_character_section_falls_back_to_design_prompt(self):
        section = build_character_section(
            {
                "characters": [
                    {"id": "char_li_ming", "name": "李明", "role": "主角", "description": "青年男子，黑色短发，穿着深蓝长衫。"},  # noqa: RUF001
                ],
                "character_images": {
                    "char_li_ming": {
                        "design_prompt": (
                            "Standard three-view character turnaround sheet for 李明, protagonist, determined expression, heroic bearing, "
                            "character description: 青年男子，黑色短发，穿着深蓝长衫。, "  # noqa: RUF001
                            "show front view, side profile, and back view of the same character on one sheet, "
                            "full body in all three views, neutral standing pose, clear silhouette, "
                            "consistent facial features and costume details across views, clean neutral backdrop, "
                            "production-ready character turnaround sheet, costume construction details, fabric texture, "
                            "accessories, highly detailed, photorealistic"
                        ),
                        "character_id": "char_li_ming",
                        "character_name": "李明",
                    }
                },
            }
        )

        self.assertIn("Visual DNA: 青年男子, 黑色短发, 穿着深蓝长衫", section)
        self.assertNotIn("front view", section)
        self.assertNotIn("turnaround sheet", section)

    def test_build_character_section_falls_back_to_legacy_prompt(self):
        section = build_character_section(
            {
                "characters": [
                    {"id": "char_li_ming", "name": "李明", "role": "主角", "description": "青年男子，黑色短发，穿着深蓝长衫。"},  # noqa: RUF001
                ],
                "character_images": {
                    "char_li_ming": {
                        "prompt": "Legacy character turnaround prompt for 李明, dark blue robe",
                        "character_id": "char_li_ming",
                        "character_name": "李明",
                    }
                },
            }
        )

        self.assertIn("Visual DNA: 青年男子, 黑色短发, 穿着深蓝长衫", section)

    def test_build_character_section_uses_prompt_anchor_source_for_body_fallback(self):
        section = build_character_section(
            {
                "characters": [
                    {"id": "char_li_ming", "name": "李明", "role": "主角", "description": "主角。"},
                ],
                "character_images": {
                    "char_li_ming": {
                        "prompt": (
                            "Legacy character turnaround prompt for 李明, 青年男子，黑色短发，身形清瘦，穿着深蓝长衫"  # noqa: RUF001
                        ),
                        "character_id": "char_li_ming",
                        "character_name": "李明",
                    }
                },
            }
        )

        self.assertIn("Visual DNA:", section)
        self.assertIn("青年男子", section)
        self.assertIn("黑色短发", section)
        self.assertIn("身形清瘦", section)
        self.assertIn("穿着深蓝长衫", section)


if __name__ == "__main__":
    unittest.main()
