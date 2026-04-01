import unittest

from app.core.story_script import serialize_story_to_script
from app.schemas.story import StoryboardScriptRequest


class StoryScriptSerializerTests(unittest.TestCase):
    def test_serialize_story_to_script_includes_storyboard_input_fields(self):
        story = {
            "characters": [
                {
                    "id": "char_shen_yan",
                    "name": "沈砚",
                    "role": "主角",
                    "description": "青年男子，深色长袍，神情克制。",
                }
            ],
            "character_images": {
                "char_shen_yan": {
                    "visual_dna": "young man, dark robe, restrained expression",
                    "character_id": "char_shen_yan",
                    "character_name": "沈砚",
                }
            },
            "scenes": [
                {
                    "episode": 1,
                    "title": "雨夜来客",
                    "scenes": [
                        {
                            "scene_number": 1,
                            "scene_heading": "[夜] [室内] [王府回廊]",
                            "environment_anchor": "王府回廊",
                            "environment": "夜晚的王府回廊，朱红立柱、青石地面与灯笼构成稳定布局。",
                            "lighting": "雨夜天光混合灯笼暖光",
                            "mood": "压迫克制",
                            "emotion_tags": [
                                {"target": "沈砚", "emotion": "警惕", "intensity": 0.7},
                                {"target": "scene", "emotion": "压迫", "intensity": 0.6},
                            ],
                            "key_props": ["密信", "油纸灯笼"],
                            "visual": "沈砚沿回廊快步前行，手里攥着密信。",
                            "key_actions": ["沈砚沿回廊前行", "他低头看向手中密信"],
                            "transition_from_previous": "从庭院追入回廊，动作保持连续。",
                            "audio": [{"character": "沈砚", "line": "不能再等了。"}],
                        }
                    ],
                }
            ],
        }

        script = serialize_story_to_script(story)

        self.assertIn("# 角色信息", script)
        self.assertIn("Visual DNA:", script)
        self.assertIn("【场景标题】[夜] [室内] [王府回廊]", script)
        self.assertIn("【环境锚点】王府回廊", script)
        self.assertIn("【情感标尺】沈砚:警惕 0.7；scene:压迫 0.6", script)
        self.assertIn("【关键道具】密信；油纸灯笼", script)
        self.assertIn("【内容覆盖清单】", script)
        self.assertIn("- 画面主线：沈砚沿回廊快步前行，手里攥着密信。", script)
        self.assertIn("- 关键动作：沈砚沿回廊前行", script)
        self.assertIn("- 台词/旁白：沈砚：不能再等了。", script)
        self.assertIn("【动作拆解】", script)
        self.assertIn("【沈砚】不能再等了。", script)

    def test_serialize_story_to_script_prefers_appearance_cache_over_legacy_visual_dna(self):
        story = {
            "characters": [
                {
                    "id": "char_shen_yan",
                    "name": "Shen Yan",
                    "role": "lead",
                    "description": "young man, short black hair, slim build.",
                }
            ],
            "character_images": {
                "char_shen_yan": {
                    "visual_dna": "young man, brown cloak",
                    "character_id": "char_shen_yan",
                    "character_name": "Shen Yan",
                }
            },
            "meta": {
                "character_appearance_cache": {
                    "char_shen_yan": {
                        "body": "young man, short black hair, slim build",
                        "clothing": "dark robe",
                    }
                }
            },
            "scenes": [
                {
                    "episode": 1,
                    "title": "Rainy Night",
                    "scenes": [
                        {
                            "scene_number": 1,
                            "environment": "corridor",
                            "visual": "Shen Yan walks through the corridor.",
                            "audio": [],
                        }
                    ],
                }
            ],
        }

        script = serialize_story_to_script(story)

        self.assertIn("Visual DNA: young man, short black hair, slim build; dark robe", script)
        self.assertNotIn("brown cloak", script)

    def test_serialize_story_to_script_filters_to_selected_scenes(self):
        story = {
            "scenes": [
                {
                    "episode": 1,
                    "title": "测试集",
                    "scenes": [
                        {
                            "scene_number": 1,
                            "environment": "场景一环境",
                            "visual": "场景一画面",
                            "audio": [],
                        },
                        {
                            "scene_number": 2,
                            "environment": "场景二环境",
                            "visual": "场景二画面",
                            "audio": [],
                        },
                    ],
                }
            ],
        }

        script = serialize_story_to_script(
            story,
            selected_scene_numbers={"1": [2]},
        )

        self.assertNotIn("场景一环境", script)
        self.assertIn("场景二环境", script)
        self.assertIn("# 第1集 测试集", script)

    def test_serialize_story_to_script_accepts_boolean_selection_map(self):
        story = {
            "scenes": [
                {
                    "episode": 1,
                    "title": "测试集",
                    "scenes": [
                        {
                            "scene_number": 1,
                            "environment": "场景一环境",
                            "visual": "场景一画面",
                            "audio": [],
                        },
                        {
                            "scene_number": 2,
                            "environment": "场景二环境",
                            "visual": "场景二画面",
                            "audio": [],
                        },
                    ],
                }
            ],
        }

        script = serialize_story_to_script(
            story,
            selected_scene_numbers={"1": {"1": False, "2": True}},
        )

        self.assertNotIn("场景一环境", script)
        self.assertIn("场景二环境", script)

    def test_serialize_story_to_script_normalizes_string_scene_identifiers_for_selection(self):
        story = {
            "scenes": [
                {
                    "episode": "1",
                    "title": "测试集",
                    "scenes": [
                        {
                            "scene_number": "1",
                            "environment": "场景一环境",
                            "visual": "场景一画面",
                            "audio": [],
                        },
                        {
                            "scene_number": "2",
                            "environment": "场景二环境",
                            "visual": "场景二画面",
                            "audio": [],
                        },
                    ],
                }
            ],
        }

        script = serialize_story_to_script(
            story,
            selected_scene_numbers={1: [2]},
        )

        self.assertNotIn("场景一环境", script)
        self.assertIn("场景二环境", script)
        self.assertIn("# 第1集 测试集", script)

    def test_serialize_story_to_script_returns_empty_when_selection_matches_nothing(self):
        story = {
            "scenes": [
                {
                    "episode": 1,
                    "title": "测试集",
                    "scenes": [
                        {
                            "scene_number": 1,
                            "environment": "场景一环境",
                            "visual": "场景一画面",
                            "audio": [],
                        }
                    ],
                }
            ],
        }

        self.assertEqual(
            serialize_story_to_script(story, selected_scene_numbers={"1": [99]}),
            "",
        )

    def test_storyboard_script_request_normalizes_boolean_selection_map(self):
        request = StoryboardScriptRequest(
            selected_scenes={"1": {"1": False, "2": True}, "2": [3, "4"]},
        )

        self.assertEqual(
            request.selected_scenes,
            {"1": [2], "2": [3, 4]},
        )


if __name__ == "__main__":
    unittest.main()
