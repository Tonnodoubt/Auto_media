import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


_CHARACTER_PROMPT_PATH = Path(__file__).resolve().parents[1] / "app" / "prompts" / "character.py"
_CHARACTER_PROMPT_SPEC = spec_from_file_location("character_prompt_module", _CHARACTER_PROMPT_PATH)
assert _CHARACTER_PROMPT_SPEC and _CHARACTER_PROMPT_SPEC.loader
_character_prompt_module = module_from_spec(_CHARACTER_PROMPT_SPEC)
_CHARACTER_PROMPT_SPEC.loader.exec_module(_character_prompt_module)

build_character_prompt = _character_prompt_module.build_character_prompt


class CharacterDesignPromptTests(unittest.TestCase):
    def test_prompt_uses_visual_anchors_only(self):
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

    def test_prompt_enforces_same_moment_turnaround_consistency(self):
        prompt = build_character_prompt(
            "阿月",
            "配角",
            "黑色短发，穿着灰青色短打。",
        )

        self.assertIn("same exact person at the same exact moment", prompt)
        self.assertIn("only the viewing angle changes", prompt)
        self.assertIn("one frozen instant seen from three camera positions", prompt)

    def test_prompt_removes_micro_precision_noise_and_personality(self):
        prompt = build_character_prompt(
            "阿月",
            "配角",
            "黑色短发，寡言谨慎，每次出入地窖必以指甲刮擦第三级石阶东侧青砖，留下0.3mm深划痕",
        )

        self.assertIn("黑色短发", prompt)
        self.assertNotIn("寡言谨慎", prompt)
        self.assertNotIn("第三级石阶东侧青砖", prompt)
        self.assertNotIn("0.3mm", prompt)


if __name__ == "__main__":
    unittest.main()
