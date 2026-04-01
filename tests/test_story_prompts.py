import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


_STORY_PROMPT_PATH = Path(__file__).resolve().parents[1] / "app" / "prompts" / "story.py"
_STORY_PROMPT_SPEC = spec_from_file_location("story_prompt_module", _STORY_PROMPT_PATH)
assert _STORY_PROMPT_SPEC and _STORY_PROMPT_SPEC.loader
_story_prompt_module = module_from_spec(_STORY_PROMPT_SPEC)
_STORY_PROMPT_SPEC.loader.exec_module(_story_prompt_module)

OUTLINE_PROMPT = _story_prompt_module.OUTLINE_PROMPT
REFINE_PROMPT = _story_prompt_module.REFINE_PROMPT
build_apply_chat_prompt = _story_prompt_module.build_apply_chat_prompt
build_chat_messages = _story_prompt_module.build_chat_messages


class StoryPromptTests(unittest.TestCase):
    def test_outline_prompt_blocks_micro_action_noise_in_character_description(self):
        self.assertIn("角色描述（`characters[].description`）额外要求", OUTLINE_PROMPT)
        self.assertIn("毫米级划痕", OUTLINE_PROMPT)
        self.assertIn("机关触发步骤", OUTLINE_PROMPT)

    def test_outline_prompt_defines_logic_layer_fields_and_boundaries(self):
        self.assertIn('"logline": "一句话核心冲突"', OUTLINE_PROMPT)
        self.assertIn('"beats": ["Beat 1", "Beat 2", "Beat 3"]', OUTLINE_PROMPT)
        self.assertIn('"scene_list": ["Scene 1: [夜] [室外] [天台] - 主角发现信封，内心动摇。"]', OUTLINE_PROMPT)
        self.assertIn("`summary` 只写剧情逻辑，不写对白，不写镜头语言，不写摄影机运动", OUTLINE_PROMPT)
        self.assertIn("`scene_list` 中相同地点应尽量使用同一命名", OUTLINE_PROMPT)

    def test_apply_chat_character_prompt_rejects_forensic_style_micro_details(self):
        prompt = build_apply_chat_prompt(
            "character",
            {"name": "阿月", "role": "配角", "description": "原始描述"},
            "用户: 给她补一点习惯",
        )

        self.assertIn("精确位置", prompt)
        self.assertIn("毫米级划痕", prompt)
        self.assertIn("镜头调度说明", prompt)

    def test_apply_chat_episode_prompt_requires_full_episode_fields(self):
        prompt = build_apply_chat_prompt(
            "episode",
            {
                "episode": 1,
                "title": "雨夜来客",
                "summary": "原始剧情",
                "beats": ["旧节拍1", "旧节拍2"],
                "scene_list": ["Scene 1: [夜] [室内] [回廊] - 主角发现线索"],
            },
            "用户: 给这一集增加反转",
        )

        self.assertIn("必须同时返回 title、summary、beats、scene_list 四个字段", prompt)
        self.assertIn("`summary`、`beats`、`scene_list` 必须互相一致", prompt)
        self.assertIn('"beats": ["Beat 1"]', prompt)
        self.assertIn('"scene_list": ["Scene 1: [夜] [室内] [地点] - 场景任务"]', prompt)

    def test_build_chat_messages_character_mode_only_allows_humanizing_habits(self):
        messages = build_chat_messages(
            "character",
            "补充她的习惯",
            {
                "character": {"name": "阿月", "role": "配角", "description": "原始描述"},
                "outline": [],
            },
        )

        prompt = messages[1]["content"]
        self.assertIn("只保留能体现人物性格或辨识度的稳定习惯", prompt)
        self.assertIn("毫米级痕迹", prompt)
        self.assertIn("机关触发步骤", prompt)

    def test_script_prompt_requires_stable_reusable_environment_and_story_fields(self):
        self.assertIn("本集节拍：", _story_prompt_module.SCRIPT_PROMPT)
        self.assertIn("{beats_text}", _story_prompt_module.SCRIPT_PROMPT)
        self.assertIn("场景切分参考：", _story_prompt_module.SCRIPT_PROMPT)
        self.assertIn("{scene_list_text}", _story_prompt_module.SCRIPT_PROMPT)
        self.assertIn('"scene_heading": "[夜] [室外] [天台]"', _story_prompt_module.SCRIPT_PROMPT)
        self.assertIn('"environment_anchor": "天台"', _story_prompt_module.SCRIPT_PROMPT)
        self.assertIn('"emotion_tags": [', _story_prompt_module.SCRIPT_PROMPT)
        self.assertIn('"key_props": ["关键物件1", "关键物件2"]', _story_prompt_module.SCRIPT_PROMPT)
        self.assertIn("只写稳定环境信息", _story_prompt_module.SCRIPT_PROMPT)
        self.assertIn("方便后续复用同一张环境图", _story_prompt_module.SCRIPT_PROMPT)

    def test_refine_prompt_requires_full_episode_outline_fields(self):
        self.assertIn("必须同时返回该集完整的 title、summary、beats、scene_list 四个字段", REFINE_PROMPT)
        self.assertIn("beats 与 scene_list 必须同步到修改后的剧情", REFINE_PROMPT)
        self.assertIn('"outline": null 或 [{{"episode": 1, "title": "标题", "summary": "概要", "beats": ["Beat 1"], "scene_list": ["Scene 1: [夜] [室内] [地点] - 场景任务"]}}]', REFINE_PROMPT)


if __name__ == "__main__":
    unittest.main()
