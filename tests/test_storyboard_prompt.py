import unittest

from app.prompts.storyboard import SYSTEM_PROMPT, USER_TEMPLATE


def _render_user_template() -> str:
    return USER_TEMPLATE.format(
        character_section="",
        scene_mapping_section="",
        script="[SCRIPT]",
    )


class StoryboardPromptTests(unittest.TestCase):
    def test_system_prompt_requires_preserving_explicit_orientation_cues(self):
        self.assertIn("orientation/view cue", SYSTEM_PROMPT)
        self.assertIn("front view, side profile, back view", SYSTEM_PROMPT)
        self.assertIn("DO NOT invent facing direction on your own", SYSTEM_PROMPT)

    def test_system_prompt_enforces_opening_frame_and_shot_to_shot_continuity(self):
        self.assertIn("Sentence 1 of `storyboard_description` defines the canonical opening frame", SYSTEM_PROMPT)
        self.assertIn("must begin from the same opening frame as `image_prompt`", SYSTEM_PROMPT)
        self.assertIn("The first frame of Shot N+1 should look like the same moment a camera would capture immediately after Shot N", SYSTEM_PROMPT)
        self.assertIn("`transition_from_previous` should record carried-over pose, prop state, background layout, and lighting logic", SYSTEM_PROMPT)

    def test_system_prompt_enforces_layer_boundaries_and_reusable_environment_rules(self):
        self.assertIn("Respect Layer Boundaries", SYSTEM_PROMPT)
        self.assertIn("Reusable Environment Discipline", SYSTEM_PROMPT)
        self.assertIn("same reusable base location", SYSTEM_PROMPT)
        self.assertIn("stable environment elements visible in this shot", SYSTEM_PROMPT)
        self.assertIn("Mapping from script emotion tags", SYSTEM_PROMPT)

    def test_prompts_enforce_three_core_shots_and_no_transition_shots(self):
        rendered = _render_user_template()
        self.assertIn("exactly 3 core shots per source scene", SYSTEM_PROMPT)
        self.assertIn("Never exceed 3 shots for one source scene", SYSTEM_PROMPT)
        self.assertIn("Do NOT create extra transition / bridge shots", SYSTEM_PROMPT)
        self.assertIn("plan only 3 core shots total", rendered)
        self.assertIn("Do NOT add dedicated transition shots", rendered)

    def test_user_template_mentions_orientation_when_explicitly_needed(self):
        rendered = _render_user_template()
        self.assertIn("front / side / back facing character orientation", rendered)
        self.assertIn("orientation is not specified", rendered)

    def test_user_template_requires_opening_frame_alignment_between_description_and_prompts(self):
        rendered = _render_user_template()
        self.assertIn("Sentence 1 = the opening frame canon", rendered)
        self.assertIn("`image_prompt` must restage that exact opening frame", rendered)
        self.assertIn("`final_video_prompt` starts from the same frame and only adds motion after it", rendered)
        self.assertIn("sentence 1 defines the exact opening frame", rendered)

    def test_prompts_require_structured_character_resolution_without_mixing_extras(self):
        self.assertIn("Every shot must also populate a `characters` field", SYSTEM_PROMPT)
        self.assertIn('Do NOT list unnamed extras, crowds, passersby', SYSTEM_PROMPT)
        self.assertIn("Primary wardrobe lock", SYSTEM_PROMPT)
        rendered = _render_user_template()
        self.assertIn("Every shot MUST fill `characters`", rendered)
        self.assertIn("resolve it and write the actual canonical name in `characters`", rendered)
        self.assertIn("Do NOT put unnamed crowd, passersby, extras, or background strangers into `characters`", rendered)
        self.assertIn("Lock the main outfit strictly", rendered)

    def test_prompts_require_audio_speaker_and_narration_mapping(self):
        rendered = _render_user_template()
        self.assertIn("`audio_reference.speaker`", rendered)
        self.assertIn("speaker` must be `旁白` and `type` must be `narration`", rendered)
        self.assertIn('"speaker":', rendered)
        self.assertIn("旁白", rendered)

    def test_user_template_consumes_scene_anchor_props_and_emotion_tags(self):
        rendered = _render_user_template()
        self.assertIn("`【环境锚点】`", rendered)
        self.assertIn("`【内容覆盖清单】`", rendered)
        self.assertIn("`【关键道具】`", rendered)
        self.assertIn("`【情感标尺】`", rendered)
        self.assertIn("never paste the full environment paragraph into every shot", rendered)
        self.assertIn("The same `【环境锚点】` keeps the same reusable location identity", rendered)
        self.assertIn("STEP 1.5", rendered)
        self.assertIn("reuse the same value for shots that stay inside the same source scene", rendered)

    def test_prompts_require_scene_coverage_without_silent_omission(self):
        rendered = _render_user_template()
        self.assertIn("Scene Coverage Completeness", SYSTEM_PROMPT)
        self.assertIn("Do not silently drop any checklist item", SYSTEM_PROMPT)
        self.assertIn("compression over omission", SYSTEM_PROMPT)
        self.assertIn("collectively cover every mandatory item from `【内容覆盖清单】`", rendered)
        self.assertIn("nothing important from the source scene was silently dropped", rendered)

    def test_user_template_renders_without_format_key_errors(self):
        rendered = _render_user_template()
        self.assertIn('"audio_reference": {"type": "narration", "speaker": "旁白", "content": "..."}', rendered)


if __name__ == "__main__":
    unittest.main()
