import unittest

from app.prompts.storyboard import SYSTEM_PROMPT, USER_TEMPLATE


class StoryboardPromptTests(unittest.TestCase):
    def test_system_prompt_requires_preserving_explicit_orientation_cues(self):
        self.assertIn("orientation/view cue", SYSTEM_PROMPT)
        self.assertIn("front view, side profile, back view", SYSTEM_PROMPT)
        self.assertIn("DO NOT invent facing direction on your own", SYSTEM_PROMPT)

    def test_user_template_mentions_orientation_when_explicitly_needed(self):
        self.assertIn("front / side / back facing character orientation", USER_TEMPLATE)
        self.assertIn("orientation is not specified", USER_TEMPLATE)


if __name__ == "__main__":
    unittest.main()
