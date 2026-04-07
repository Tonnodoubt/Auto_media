import unittest
from unittest.mock import AsyncMock, patch

from app.services.quality import (
    JudgeResult,
    run_quality_guarded_generation,
    run_quality_guarded_prompt_payload,
    run_quality_guarded_runtime_payload,
)
from app.services.story_context_service import (
    extract_character_appearance,
    extract_scene_style_cache,
    prepare_story_context,
)
from app.services.storyboard import parse_script_to_storyboard
from app.services.story_llm import generate_outline


class QualityRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_quality_guarded_generation_runs_once_when_disabled(self):
        calls: list[tuple[str, int]] = []

        async def generate_candidate(prompt_suffix: str, attempt: int):
            calls.append((prompt_suffix, attempt))
            return {"attempt": attempt}, {"prompt_tokens": 10, "completion_tokens": 5}

        with patch("app.services.quality.settings.quality_layer_enabled", False):
            candidate, usage, quality = await run_quality_guarded_generation(
                family="story_outline",
                provider="claude",
                model="claude-sonnet-4-6",
                api_key="test-key",
                base_url="https://example.com",
                generate_candidate=generate_candidate,
            )

        self.assertEqual(candidate["attempt"], 1)
        self.assertEqual(usage["prompt_tokens"], 10)
        self.assertEqual(calls, [("", 1)])
        self.assertFalse(quality["enabled"])
        self.assertEqual(len(quality["attempts"]), 1)

    async def test_quality_guarded_generation_retries_with_feedback_when_live_judge_fails(self):
        calls: list[tuple[str, int]] = []

        async def generate_candidate(prompt_suffix: str, attempt: int):
            calls.append((prompt_suffix, attempt))
            return {"attempt": attempt}, {"prompt_tokens": 10 * attempt, "completion_tokens": attempt}

        judge_results = [
            JudgeResult(
                family="story_outline",
                label="Story Outline",
                enabled=True,
                skipped=False,
                shadow_mode=False,
                passed=False,
                overall_score=2.5,
                summary="需要强化 beats 递进",
                feedback_instructions=["强化每集 beats 的升级与转折，避免重复复述"],
            ),
            JudgeResult(
                family="story_outline",
                label="Story Outline",
                enabled=True,
                skipped=False,
                shadow_mode=False,
                passed=True,
                overall_score=4.2,
                summary="通过",
            ),
        ]

        with (
            patch("app.services.quality.settings.quality_layer_enabled", True),
            patch("app.services.quality.settings.quality_outline_enabled", True),
            patch("app.services.quality.settings.quality_dspy_enabled", True),
            patch("app.services.quality.settings.quality_judge_enabled", True),
            patch("app.services.quality.settings.quality_judge_shadow_mode", False),
            patch("app.services.quality.settings.quality_feedback_loop_enabled", True),
            patch("app.services.quality.settings.quality_feedback_max_retries", 1),
            patch("app.services.quality.run_quality_judge", new=AsyncMock(side_effect=judge_results)),
        ):
            candidate, usage, quality = await run_quality_guarded_generation(
                family="story_outline",
                provider="claude",
                model="claude-sonnet-4-6",
                api_key="test-key",
                base_url="https://example.com",
                generate_candidate=generate_candidate,
            )

        self.assertEqual(candidate["attempt"], 2)
        self.assertEqual(usage["prompt_tokens"], 20)
        self.assertEqual(len(calls), 2)
        self.assertIn("DSPy 编译约束", calls[0][0])
        self.assertIn("强化每集 beats 的升级与转折", calls[1][0])
        self.assertTrue(quality["enabled"])
        self.assertTrue(quality["feedback_enabled"])
        self.assertEqual(len(quality["attempts"]), 2)
        self.assertTrue(quality["final_passed"])

    async def test_quality_guarded_generation_falls_back_to_previous_candidate_when_retry_generation_fails(self):
        async def generate_candidate(prompt_suffix: str, attempt: int):
            if attempt == 2:
                raise RuntimeError("retry failed")
            return {"attempt": attempt}, {"prompt_tokens": 10, "completion_tokens": 1}

        judge_result = JudgeResult(
            family="story_outline",
            label="Story Outline",
            enabled=True,
            skipped=False,
            shadow_mode=False,
            passed=False,
            overall_score=2.0,
            summary="需要修复",
            feedback_instructions=["补齐冲突与场景切分"],
        )

        with (
            patch("app.services.quality.settings.quality_layer_enabled", True),
            patch("app.services.quality.settings.quality_outline_enabled", True),
            patch("app.services.quality.settings.quality_dspy_enabled", True),
            patch("app.services.quality.settings.quality_judge_enabled", True),
            patch("app.services.quality.settings.quality_judge_shadow_mode", False),
            patch("app.services.quality.settings.quality_feedback_loop_enabled", True),
            patch("app.services.quality.settings.quality_feedback_max_retries", 1),
            patch("app.services.quality.run_quality_judge", new=AsyncMock(return_value=judge_result)),
        ):
            candidate, _, quality = await run_quality_guarded_generation(
                family="story_outline",
                provider="claude",
                model="claude-sonnet-4-6",
                api_key="test-key",
                base_url="https://example.com",
                generate_candidate=generate_candidate,
            )

        self.assertEqual(candidate["attempt"], 1)
        self.assertIn("retry failed", quality["warnings"][0])
        self.assertFalse(quality["final_passed"])

    async def test_runtime_generation_payload_retries_with_overlay_feedback(self):
        base_payload = {
            "shot_id": "scene1_shot1",
            "image_prompt": "Medium shot. Li Ming pauses at the doorway.",
            "final_video_prompt": "Medium shot. Static camera. Li Ming opens the wooden door.",
            "negative_prompt": "blur, low quality",
        }

        judge_results = [
            JudgeResult(
                family="generation_payload",
                label="Runtime Generation Payload",
                enabled=True,
                skipped=False,
                shadow_mode=False,
                passed=False,
                overall_score=2.6,
                summary="需要更强的首帧连续性约束",
                feedback_instructions=["Keep the opening frame fixed and make the motion shorter and smoother."],
            ),
            JudgeResult(
                family="generation_payload",
                label="Runtime Generation Payload",
                enabled=True,
                skipped=False,
                shadow_mode=False,
                passed=True,
                overall_score=4.1,
                summary="通过",
            ),
        ]

        with (
            patch("app.services.quality.settings.quality_layer_enabled", True),
            patch("app.services.quality.settings.quality_generation_payload_enabled", True),
            patch("app.services.quality.settings.quality_dspy_enabled", True),
            patch("app.services.quality.settings.quality_judge_enabled", True),
            patch("app.services.quality.settings.quality_judge_shadow_mode", False),
            patch("app.services.quality.settings.quality_feedback_loop_enabled", True),
            patch("app.services.quality.settings.quality_feedback_max_retries", 1),
            patch("app.services.quality.run_quality_judge", new=AsyncMock(side_effect=judge_results)),
        ):
            payload, quality = await run_quality_guarded_runtime_payload(
                provider="claude",
                model="claude-sonnet-4-6",
                api_key="test-key",
                base_url="https://example.com",
                base_payload_builder=lambda: dict(base_payload),
                telemetry_context={"shot_id": "scene1_shot1"},
            )

        self.assertIn(
            "Continuity lock:",
            quality["attempts"][0]["generation_usage"]["overlay_text"],
        )
        self.assertIn("Keep the opening frame fixed", payload["image_prompt"])
        self.assertIn("Keep the opening frame fixed", payload["final_video_prompt"])
        self.assertEqual(len(quality["attempts"]), 2)
        self.assertTrue(quality["final_passed"])

    async def test_prompt_payload_retries_with_overlay_feedback(self):
        base_payload = {
            "prompt": "Environment reference plate for a rainy courtyard.",
            "negative_prompt": "people, text, watermark",
        }

        judge_results = [
            JudgeResult(
                family="scene_reference_prompt",
                label="Scene Reference Prompt",
                enabled=True,
                skipped=False,
                shadow_mode=False,
                passed=False,
                overall_score=2.4,
                summary="需要更强的环境锁定",
                feedback_instructions=["Preserve the doorway layout and keep all people out of frame."],
            ),
            JudgeResult(
                family="scene_reference_prompt",
                label="Scene Reference Prompt",
                enabled=True,
                skipped=False,
                shadow_mode=False,
                passed=True,
                overall_score=4.3,
                summary="通过",
            ),
        ]

        with (
            patch("app.services.quality.settings.quality_layer_enabled", True),
            patch("app.services.quality.settings.quality_scene_reference_enabled", True),
            patch("app.services.quality.settings.quality_dspy_enabled", True),
            patch("app.services.quality.settings.quality_judge_enabled", True),
            patch("app.services.quality.settings.quality_judge_shadow_mode", False),
            patch("app.services.quality.settings.quality_feedback_loop_enabled", True),
            patch("app.services.quality.settings.quality_feedback_max_retries", 1),
            patch("app.services.quality.run_quality_judge", new=AsyncMock(side_effect=judge_results)),
        ):
            payload, quality = await run_quality_guarded_prompt_payload(
                family="scene_reference_prompt",
                provider="claude",
                model="claude-sonnet-4-6",
                api_key="test-key",
                base_url="https://example.com",
                base_payload_builder=lambda: dict(base_payload),
                telemetry_context={"environment_pack_key": "ep01_env01"},
            )

        self.assertIn("Environment lock:", quality["attempts"][0]["generation_usage"]["overlay_text"])
        self.assertIn("Preserve the doorway layout", payload["prompt"])
        self.assertEqual(payload["negative_prompt"], "people, text, watermark")
        self.assertEqual(len(quality["attempts"]), 2)
        self.assertTrue(quality["final_passed"])


class QualityIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_extract_character_appearance_can_return_quality_metadata(self):
        story = {
            "id": "story-quality-appearance",
            "characters": [
                {"id": "char_1", "name": "李明", "role": "主角", "description": "年轻男子，短黑发，深蓝长袍"}
            ],
        }
        candidate = {
            "characters": [
                {
                    "id": "char_1",
                    "body": "young man, short black hair, slim build",
                    "clothing": "dark blue robe",
                    "negative_prompt": "modern clothing",
                }
            ]
        }

        with (
            patch("app.services.story_context_service.get_llm_provider", return_value=object()),
            patch(
                "app.services.story_context_service.run_quality_guarded_generation",
                new=AsyncMock(
                    return_value=(
                        candidate,
                        {"prompt_tokens": 9, "completion_tokens": 3},
                        {"enabled": True, "family": "character_appearance_extract"},
                    )
                ),
            ),
        ):
            output, quality = await extract_character_appearance(
                story,
                provider="claude",
                api_key="test-key",
                include_quality=True,
            )

        self.assertEqual(output["char_1"]["body"], "young man, short black hair, slim build")
        self.assertEqual(output["char_1"]["clothing"], "dark blue robe")
        self.assertEqual(quality["family"], "character_appearance_extract")

    async def test_extract_scene_style_cache_can_return_quality_metadata(self):
        story = {
            "id": "story-quality-scene-style",
            "genre": "古风悬疑",
            "selected_setting": "江南雨夜茶馆，木构建筑，纸灯笼，湿石阶。",
        }
        candidate = {
            "styles": [
                {
                    "keywords": ["teahouse", "jiangnan"],
                    "image_extra": "jiangnan teahouse, rain mist, paper lanterns",
                    "video_extra": "jiangnan teahouse, damp stone steps, lantern glow",
                    "negative_prompt": "cars, neon signs",
                }
            ]
        }

        with (
            patch("app.services.story_context_service.get_llm_provider", return_value=object()),
            patch(
                "app.services.story_context_service.run_quality_guarded_generation",
                new=AsyncMock(
                    return_value=(
                        candidate,
                        {"prompt_tokens": 8, "completion_tokens": 4},
                        {"enabled": True, "family": "scene_style_extract"},
                    )
                ),
            ),
        ):
            output, quality = await extract_scene_style_cache(
                story,
                provider="claude",
                api_key="test-key",
                include_quality=True,
            )

        self.assertEqual(output[0]["image_extra"], "jiangnan teahouse, rain mist, paper lanterns")
        self.assertEqual(output[0]["negative_prompt"], "cars, neon signs")
        self.assertEqual(quality["family"], "scene_style_extract")

    async def test_prepare_story_context_persists_quality_runs_from_extractors(self):
        fake_db = object()
        story = {
            "id": "story-quality-context",
            "genre": "古风悬疑",
            "selected_setting": "江南雨夜茶馆，木构建筑，纸灯笼，湿石阶。",
            "meta": {
                "quality_runs": {
                    "story_outline": {"enabled": True, "family": "story_outline"},
                }
            },
            "characters": [
                {"id": "char_1", "name": "李明", "role": "主角", "description": "年轻男子，短黑发，深蓝长袍"}
            ],
            "character_images": {},
        }
        meta_updates: list[tuple[str, object]] = []

        async def fake_upsert_story_meta_cache(_db, _story_id, key, value):
            meta_updates.append((key, value))

        with (
            patch("app.services.story_context_service.repo.get_story", new=AsyncMock(return_value=story)),
            patch("app.services.story_context_service.repo.upsert_story_meta_cache", new=AsyncMock(side_effect=fake_upsert_story_meta_cache)),
            patch("app.services.story_context_service.repo.upsert_character_images", new=AsyncMock()),
            patch(
                "app.services.story_context_service.extract_character_appearance",
                new=AsyncMock(
                    return_value=(
                        {"char_1": {"body": "young man, short black hair", "clothing": "dark blue robe"}},
                        {"enabled": True, "family": "character_appearance_extract"},
                    )
                ),
            ),
            patch(
                "app.services.story_context_service.extract_scene_style_cache",
                new=AsyncMock(
                    return_value=(
                        [{"keywords": ["teahouse"], "image_extra": "jiangnan teahouse", "video_extra": "rain mist"}],
                        {"enabled": True, "family": "scene_style_extract"},
                    )
                ),
            ),
            patch("app.services.story_context_service.build_story_context", return_value=None),
        ):
            updated_story, ctx = await prepare_story_context(
                fake_db,
                "story-quality-context",
                provider="claude",
                api_key="test-key",
            )

        self.assertEqual(updated_story["id"], "story-quality-context")
        self.assertIsNone(ctx)
        quality_runs_payload = next(value for key, value in meta_updates if key == "quality_runs")
        self.assertEqual(quality_runs_payload["story_outline"]["family"], "story_outline")
        self.assertEqual(
            quality_runs_payload["character_appearance_extract"]["family"],
            "character_appearance_extract",
        )
        self.assertEqual(
            quality_runs_payload["scene_style_extract"]["family"],
            "scene_style_extract",
        )

    async def test_parse_script_to_storyboard_merges_quality_into_usage(self):
        shot = {
            "shot_id": "scene1_shot1",
            "estimated_duration": 4,
            "scene_intensity": "low",
            "storyboard_description": "李明停在门口。",
            "camera_setup": {"shot_size": "MS", "camera_angle": "Eye-level", "movement": "Static"},
            "visual_elements": {
                "subject_and_clothing": "李明，深色长衫",
                "action_and_expression": "停在门口，神情警觉",
                "environment_and_props": "茶馆门口，纸灯笼，湿石阶",
                "lighting_and_color": "雨夜冷光与暖灯",
            },
            "image_prompt": "李明停在门口。",
            "final_video_prompt": "李明停在门口，轻微呼吸。",
        }

        with (
            patch("app.services.storyboard.get_llm_provider", return_value=object()),
            patch(
                "app.services.storyboard.run_quality_guarded_generation",
                new=AsyncMock(return_value=([shot], {"prompt_tokens": 11, "completion_tokens": 7}, {"enabled": True})),
            ),
        ):
            shots, usage = await parse_script_to_storyboard(
                "# 第1集\n## 场景1\n【环境】茶馆门口\n【画面】李明停在门口。",
                provider="claude",
                api_key="test-key",
            )

        self.assertEqual(len(shots), 1)
        self.assertEqual(usage["prompt_tokens"], 11)
        self.assertEqual(usage["quality"], {"enabled": True})

    async def test_generate_outline_persists_quality_run_into_story_meta(self):
        fake_db = object()
        validated_outline = {
            "meta": {"title": "标题", "genre": "类型", "episodes": 6},
            "characters": [{"id": "char_1", "name": "李明", "role": "主角", "description": "青年"}],
            "relationships": [],
            "outline": [
                {
                    "episode": 1,
                    "title": "第一集",
                    "summary": "摘要",
                    "beats": ["冲突建立"],
                    "scene_list": ["夜 外 茶馆门口"],
                }
            ],
        }
        saved_payloads: list[dict] = []

        async def fake_save_story(_db, _story_id, data):
            saved_payloads.append(dict(data))

        with (
            patch("app.services.story_llm._make_client", return_value=object()),
            patch("app.services.story_llm.repo.get_story", new=AsyncMock(return_value={"meta": {"theme": "旧主题"}})),
            patch("app.services.story_llm.repo.save_story", new=AsyncMock(side_effect=fake_save_story)),
            patch("app.services.story_llm.repo.invalidate_story_consistency_cache", new=AsyncMock()),
            patch(
                "app.services.story_llm.run_quality_guarded_generation",
                new=AsyncMock(
                    return_value=(
                        validated_outline,
                        {"prompt_tokens": 12, "completion_tokens": 3},
                        {"enabled": True, "family": "story_outline"},
                    )
                ),
            ),
        ):
            result = await generate_outline(
                "story-quality",
                "世界观设定",
                db=fake_db,
                api_key="test-key",
                provider="claude",
                model="claude-sonnet-4-6",
            )

        self.assertEqual(result["quality"]["family"], "story_outline")
        self.assertEqual(saved_payloads[-1]["meta"]["quality_runs"]["story_outline"]["enabled"], True)
