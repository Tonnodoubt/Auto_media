import unittest

import sys
import types

llm_factory_stub = types.ModuleType("app.services.llm.factory")
llm_factory_stub.get_llm_provider = lambda *args, **kwargs: None
sys.modules.setdefault("app.services.llm.factory", llm_factory_stub)

from app.services.storyboard import (
    _build_minimal_valid_shot_item,
    _limit_core_shot_items,
    _normalize_shot_item,
)


class StoryboardNormalizationTests(unittest.TestCase):
    def test_normalize_shot_item_backfills_narration_speaker(self):
        shot = _normalize_shot_item(
            {
                "characters": ["李明"],
                "storyboard_description": "他停在门口，旁白落下。",
                "audio_reference": {
                    "type": "narration",
                    "content": "他知道，门后的一切都会改变。",
                },
            },
            shot_number=1,
        )

        self.assertEqual(shot["audio_reference"]["type"], "narration")
        self.assertEqual(shot["audio_reference"]["speaker"], "旁白")

    def test_normalize_shot_item_backfills_single_character_dialogue_speaker(self):
        shot = _normalize_shot_item(
            {
                "characters": ["李明"],
                "storyboard_description": "他停在门口，说出一句提醒。",
                "audio_reference": {
                    "type": "dialogue",
                    "content": "别进去。",
                },
            },
            shot_number=1,
        )

        self.assertEqual(shot["audio_reference"]["type"], "dialogue")
        self.assertEqual(shot["audio_reference"]["speaker"], "李明")

    def test_normalize_shot_item_rewrites_generic_pronoun_speaker_to_single_character(self):
        shot = _normalize_shot_item(
            {
                "characters": ["李明"],
                "storyboard_description": "他停在门口，说出一句提醒。",
                "audio_reference": {
                    "type": "dialogue",
                    "speaker": "他",
                    "content": "别进去。",
                },
            },
            shot_number=1,
        )

        self.assertEqual(shot["audio_reference"]["speaker"], "李明")

    def test_normalize_shot_item_does_not_guess_dialogue_speaker_with_multiple_characters(self):
        shot = _normalize_shot_item(
            {
                "characters": ["李明", "老板"],
                "storyboard_description": "两人对峙，其中一人先开口。",
                "audio_reference": {
                    "type": "dialogue",
                    "speaker": "他",
                    "content": "别进去。",
                },
            },
            shot_number=1,
        )

        self.assertIsNone(shot["audio_reference"]["speaker"])

    def test_build_minimal_valid_shot_item_uses_same_audio_backfill_rules(self):
        shot = _build_minimal_valid_shot_item(
            {
                "characters": ["李明"],
                "storyboard_description": "他停在门口，说出一句提醒。",
                "dialogue": "别进去。",
            },
            shot_number=1,
        )

        self.assertEqual(shot["audio_reference"]["type"], "dialogue")
        self.assertEqual(shot["audio_reference"]["speaker"], "李明")

    def test_limit_core_shot_items_keeps_only_three_shots_per_scene(self):
        limited = _limit_core_shot_items(
            [
                {
                    "shot_id": "scene1_shot1",
                    "source_scene_key": "ep01_scene01",
                    "storyboard_description": "镜头一",
                    "scene_position": "establishing",
                    "characters": ["李明"],
                },
                {
                    "shot_id": "scene1_shot2",
                    "source_scene_key": "ep01_scene01",
                    "storyboard_description": "镜头二",
                    "scene_position": "development",
                },
                {
                    "shot_id": "scene1_shot3",
                    "source_scene_key": "ep01_scene01",
                    "storyboard_description": "镜头三",
                    "scene_position": "development",
                    "scene_intensity": "high",
                    "audio_reference": {"type": "dialogue", "speaker": "李明", "content": "别进去。"},
                    "characters": ["李明"],
                },
                {
                    "shot_id": "scene1_shot4",
                    "source_scene_key": "ep01_scene01",
                    "storyboard_description": "镜头四",
                    "scene_position": "development",
                },
                {
                    "shot_id": "scene1_shot5",
                    "source_scene_key": "ep01_scene01",
                    "storyboard_description": "镜头五",
                    "scene_position": "resolution",
                    "characters": ["李明"],
                },
            ]
        )

        self.assertEqual(len(limited), 3)
        self.assertEqual([item["shot_id"] for item in limited], ["scene1_shot1", "scene1_shot2", "scene1_shot3"])
        self.assertEqual(limited[0]["storyboard_description"], "镜头一")
        self.assertEqual(limited[1]["storyboard_description"], "镜头三")
        self.assertEqual(limited[2]["storyboard_description"], "镜头五")
        self.assertIsNone(limited[0]["transition_from_previous"])
        self.assertIn("主衣物", limited[1]["transition_from_previous"])
        self.assertIn("主衣物", limited[2]["transition_from_previous"])

    def test_limit_core_shot_items_merges_omitted_content_into_retained_shots(self):
        limited = _limit_core_shot_items(
            [
                {
                    "shot_id": "scene1_shot1",
                    "source_scene_key": "ep01_scene01",
                    "storyboard_description": "镜头一展示走廊入口",
                    "scene_position": "establishing",
                },
                {
                    "shot_id": "scene1_shot2",
                    "source_scene_key": "ep01_scene01",
                    "storyboard_description": "镜头二里李明推门进入回廊",
                    "visual_elements": {
                        "subject_and_clothing": "李明，深色长袍",
                        "action_and_expression": "推门进入回廊",
                        "environment_and_props": "木门与回廊立柱",
                        "lighting_and_color": "暖色灯笼光",
                    },
                    "characters": ["李明"],
                    "scene_position": "development",
                },
                {
                    "shot_id": "scene1_shot3",
                    "source_scene_key": "ep01_scene01",
                    "storyboard_description": "镜头三展示他停步观察",
                    "scene_position": "development",
                },
                {
                    "shot_id": "scene1_shot4",
                    "source_scene_key": "ep01_scene01",
                    "storyboard_description": "镜头四里桌上密信被展开",
                    "visual_elements": {
                        "subject_and_clothing": "",
                        "action_and_expression": "伸手展开密信",
                        "environment_and_props": "木桌上的密信",
                        "lighting_and_color": "",
                    },
                    "audio_reference": {"type": "narration", "speaker": "旁白", "content": "密信内容终于暴露。"},
                    "scene_position": "development",
                },
                {
                    "shot_id": "scene1_shot5",
                    "source_scene_key": "ep01_scene01",
                    "storyboard_description": "镜头五展示李明的最终反应",
                    "scene_position": "resolution",
                },
            ]
        )

        self.assertEqual(len(limited), 3)
        self.assertIn("镜头二里李明推门进入回廊", limited[1]["storyboard_description"])
        self.assertIn("镜头四里桌上密信被展开", limited[1]["storyboard_description"])
        self.assertIn("李明", limited[1]["characters"])


if __name__ == "__main__":
    unittest.main()
