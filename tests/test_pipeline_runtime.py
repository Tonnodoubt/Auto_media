# ruff: noqa: RUF001

import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.core.api_keys import get_art_style
from app.paths import MEDIA_DIR
from app.core.story_script import serialize_story_to_script
from app.core.story_context import build_generation_payload, build_story_context
from app.core.pipeline_runtime import (
    INTEGRATED_FALLBACK_NOTE,
    INTEGRATED_FALLBACK_RUNTIME,
    build_runtime_strategy_metadata,
    resolve_tracking_story_id,
)
from app.main import app
from app.prompts.character import build_character_section
from app.routers.image import generate_images as generate_single_images, ImageRequest
from app.routers.pipeline import (
    _resolve_public_base_url,
    _persist_manual_pipeline_state,
    _trim_words,
    concat_videos,
    generate_assets,
    generate_storyboard,
    generate_transition,
    get_status,
    render_video,
)
from app.routers.video import generate_videos as generate_single_videos, VideoRequest
from app.schemas.pipeline import ConcatRequest, GenerationStrategy, PipelineStatus, StoryboardRequest, TransitionGenerateRequest
from app.schemas.storyboard import CameraSetup, Shot, VisualElements
from app.services.pipeline_executor import PipelineExecutor
from app.services import story_repository as repo


class PipelineRuntimeHelperTests(unittest.TestCase):
    def _make_request(self, host: str = "testserver") -> Request:
        return Request(
            {
                "type": "http",
                "headers": [],
                "scheme": "http",
                "server": (host, 80),
                "root_path": "",
                "path": "/",
            }
        )

    def test_executor_generation_payload_includes_scene_reference_assets(self):
        executor = PipelineExecutor("project-1", "pipeline-1", None)
        executor.art_style = "cinematic watercolor"
        executor.story_context = None
        executor.story = {
            "characters": [
                {
                    "id": "char_li_ming",
                    "name": "Li Ming",
                    "description": "young man, short black hair, wearing a dark blue robe.",
                }
            ],
            "character_images": {
                "char_li_ming": {
                    "image_url": "/media/characters/li_ming.png",
                    "image_path": "media/characters/li_ming.png",
                }
            },
            "meta": {
                "scene_reference_assets": {
                    "ep01_scene01": {
                        "summary_environment": "office lobby",
                        "summary_visuals": ["glass doors", "reception desk"],
                        "variants": {
                            "scene": {
                                "image_url": "/media/episodes/office.png",
                                "image_path": "media/episodes/office.png",
                            }
                        },
                    }
                }
            },
        }

        payload = executor._build_generation_payload(
            Shot(
                shot_id="scene1_shot1",
                source_scene_key="ep01_scene01",
                storyboard_description="李明停在门口。",
                camera_setup=CameraSetup(shot_size="MS", camera_angle="Eye-level", movement="Static"),
                visual_elements=VisualElements(
                    subject_and_clothing="李明穿深蓝长袍",
                    action_and_expression="停在门口",
                    environment_and_props="办公室大厅玻璃门与前台",
                    lighting_and_color="柔和晨光",
                ),
                image_prompt="Medium shot. Li Ming pauses at the doorway.",
                final_video_prompt="Medium shot. Static camera. Li Ming steps forward.",
            )
        )

        self.assertEqual(payload["source_scene_key"], "ep01_scene01")
        self.assertEqual(len(payload["reference_images"]), 2)

    def test_executor_generation_payload_story_only_fallback_keeps_character_anchor(self):
        executor = PipelineExecutor("project-1", "pipeline-1", None)
        executor.art_style = "cinematic watercolor"
        executor.story_context = None
        executor.story = {
            "characters": [
                {
                    "id": "char_li_ming",
                    "name": "Li Ming",
                    "description": "young man, short black hair, wearing a dark blue robe.",
                }
            ],
            "character_images": {
                "char_li_ming": {
                    "design_prompt": (
                        "Standard three-view character turnaround sheet for Li Ming, protagonist, determined expression, "
                        "character description: young man, short black hair, wearing a dark blue robe."
                    )
                }
            },
            "meta": {
                "scene_reference_assets": {
                    "ep01_scene01": {
                        "summary_environment": "office lobby",
                        "summary_visuals": ["glass doors", "reception desk"],
                        "variants": {
                            "scene": {
                                "image_url": "/media/episodes/office.png",
                                "image_path": "media/episodes/office.png",
                            }
                        },
                    }
                }
            },
        }

        payload = executor._build_generation_payload(
            Shot(
                shot_id="scene1_shot1",
                source_scene_key="ep01_scene01",
                storyboard_description="Li Ming pauses at the doorway.",
                camera_setup=CameraSetup(shot_size="MS", camera_angle="Eye-level", movement="Static"),
                visual_elements=VisualElements(
                    subject_and_clothing="Li Ming in a dark robe",
                    action_and_expression="pauses before entering",
                    environment_and_props="office lobby doorway",
                    lighting_and_color="soft overcast light",
                ),
                image_prompt="Medium shot. Li Ming pauses at the doorway.",
                final_video_prompt="Medium shot. Static camera. Li Ming steps forward.",
            )
        )

        self.assertIn("[Character Li Ming:", payload["image_prompt"])
        self.assertIn("office lobby", payload["image_prompt"])
        self.assertEqual(payload["source_scene_key"], "ep01_scene01")
        self.assertTrue(payload["reference_images"])

    def test_generated_files_snapshot_includes_generation_payload_quality(self):
        executor = PipelineExecutor("project-1", "pipeline-1", None)
        executor.generation_payload_quality = {
            "scene1_shot1": {
                "quality": {"enabled": True, "family": "generation_payload"}
            }
        }

        snapshot = executor._build_generated_files_snapshot()

        self.assertEqual(
            snapshot["generation_payloads"]["scene1_shot1"]["quality"]["family"],
            "generation_payload",
        )

    def test_trim_words_limits_cjk_without_whitespace(self):
        trimmed = _trim_words("保持同一人物与服装，动作从门口延续到进入房间。", 6)

        self.assertEqual(trimmed, "保持同一人物与服装")

    def test_resolve_tracking_story_id_prefers_story_id(self):
        self.assertEqual(resolve_tracking_story_id("project-1", "story-1"), "story-1")
        self.assertEqual(resolve_tracking_story_id("project-1", ""), "project-1")

    def test_integrated_strategy_metadata_declares_fallback(self):
        metadata = build_runtime_strategy_metadata(GenerationStrategy.INTEGRATED)
        self.assertEqual(metadata["requested_strategy"], "integrated")
        self.assertEqual(metadata["runtime_strategy"], INTEGRATED_FALLBACK_RUNTIME)
        self.assertEqual(metadata["note"], INTEGRATED_FALLBACK_NOTE)
        self.assertFalse(metadata["audio_integrated"])

    def test_resolve_public_base_url_rejects_loopback_fallback_when_not_configured(self):
        request = self._make_request("127.0.0.1")

        with patch("app.routers.pipeline.logger.warning") as warning_mock:
            with self.assertRaises(HTTPException) as ctx:
                _resolve_public_base_url(request, "")

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("base_url", ctx.exception.detail)
        warning_mock.assert_called_once()

    def test_resolve_public_base_url_allows_non_loopback_request_fallback(self):
        request = self._make_request("media.example.com")

        self.assertEqual(
            _resolve_public_base_url(request, ""),
            "http://media.example.com",
        )

    def test_app_no_longer_mounts_legacy_projects_router(self):
        paths = {route.path for route in app.router.routes}
        self.assertFalse(any(path.startswith("/api/v1/projects") for path in paths))

    def test_app_no_longer_mounts_placeholder_stitch_route(self):
        paths = {route.path for route in app.router.routes}
        self.assertNotIn("/api/v1/pipeline/{project_id}/stitch", paths)

    def test_legacy_character_prompt_enhancement_uses_clean_anchor(self):
        prompt = PipelineExecutor._enhance_prompt_with_character(
            "Medium shot. Li Ming pauses at the doorway.",
            {
                "characters": [
                    {
                        "name": "Li Ming",
                        "description": "young man, short black hair, wearing a dark blue robe.",
                    }
                ],
                "character_images": {
                    "Li Ming": {
                        "design_prompt": (
                            "Standard three-view character turnaround sheet for Li Ming, protagonist, determined expression, heroic bearing, "
                            "character description: young man, short black hair, wearing a dark blue robe, "
                            "show front view, side profile, and back view of the same character on one sheet, "
                            "full body in all three views, neutral standing pose, clear silhouette, "
                            "consistent facial features and costume details across views, clean neutral backdrop, "
                            "production-ready character turnaround sheet, costume construction details, fabric texture, "
                            "accessories, highly detailed, photorealistic"
                        )
                    }
                },
            },
        )

        self.assertIn("[Character Li Ming: young man, short black hair, wearing a dark blue robe]", prompt)
        self.assertNotIn("front view", prompt)
        self.assertNotIn("turnaround sheet", prompt)

    def test_legacy_character_prompt_enhancement_adds_view_hint_when_shot_mentions_profile(self):
        prompt = PipelineExecutor._enhance_prompt_with_character(
            "Medium shot. Side view of Li Ming pausing at the doorway.",
            {
                "characters": [
                    {
                        "name": "Li Ming",
                        "description": "young man, short black hair, wearing a dark blue robe.",
                    }
                ],
                "character_images": {
                    "Li Ming": {
                        "design_prompt": (
                            "Standard three-view character turnaround sheet for Li Ming, protagonist, determined expression, heroic bearing, "
                            "character description: young man, short black hair, wearing a dark blue robe, "
                            "show front view, side profile, and back view of the same character on one sheet, "
                            "full body in all three views, neutral standing pose, clear silhouette, "
                            "consistent facial features and costume details across views, clean neutral backdrop, "
                            "production-ready character turnaround sheet, costume construction details, fabric texture, "
                            "accessories, highly detailed, photorealistic"
                        )
                    }
                },
            },
        )

        self.assertIn("match the shot's side profile", prompt)
        self.assertNotIn("front view", prompt)
        self.assertNotIn("back view of the same character", prompt)

    def test_legacy_character_prompt_enhancement_ignores_other_character_view_hint(self):
        prompt = PipelineExecutor._enhance_prompt_with_character(
            "Medium shot. Li Ming pauses at the doorway while Boss Zhao stands behind him.",
            {
                "characters": [
                    {
                        "name": "Li Ming",
                        "description": "young man, short black hair, wearing a dark blue robe.",
                    }
                ],
                "character_images": {
                    "Li Ming": {
                        "design_prompt": (
                            "Standard three-view character turnaround sheet for Li Ming, protagonist, determined expression, heroic bearing, "
                            "character description: young man, short black hair, wearing a dark blue robe, "
                            "show front view, side profile, and back view of the same character on one sheet, "
                            "full body in all three views, neutral standing pose, clear silhouette, "
                            "consistent facial features and costume details across views, clean neutral backdrop, "
                            "production-ready character turnaround sheet, costume construction details, fabric texture, "
                            "accessories, highly detailed, photorealistic"
                        )
                    }
                },
            },
            {
                "storyboard_description": "Li Ming pauses at the doorway while Boss Zhao watches from the back.",
                "image_prompt": "Medium shot. Li Ming pauses at the doorway.",
                "final_video_prompt": "Medium shot. Static camera. Li Ming looks toward the room.",
                "visual_elements": {
                    "action_and_expression": "Boss Zhao is seen from behind in the background.",
                },
            },
        )

        self.assertNotIn("match the shot's back view", prompt)

    def test_legacy_character_prompt_enhancement_uses_structured_single_character_view_hint(self):
        prompt = PipelineExecutor._enhance_prompt_with_character(
            "Medium shot. Li Ming pauses at the doorway.",
            {
                "characters": [
                    {
                        "name": "Li Ming",
                        "description": "young man, short black hair, wearing a dark blue robe.",
                    }
                ],
                "character_images": {
                    "Li Ming": {
                        "design_prompt": (
                            "Standard three-view character turnaround sheet for Li Ming, protagonist, determined expression, heroic bearing, "
                            "character description: young man, short black hair, wearing a dark blue robe, "
                            "show front view, side profile, and back view of the same character on one sheet, "
                            "full body in all three views, neutral standing pose, clear silhouette, "
                            "consistent facial features and costume details across views, clean neutral backdrop, "
                            "production-ready character turnaround sheet, costume construction details, fabric texture, "
                            "accessories, highly detailed, photorealistic"
                        )
                    }
                },
            },
            {
                "characters": [{"name": "Li Ming"}],
                "storyboard_description": "A solitary figure pauses at the doorway.",
                "visual_elements": {
                    "subject_and_clothing": "young man in a dark blue robe at the doorway",
                    "action_and_expression": "背影站立，微微侧头",
                },
            },
        )

        self.assertIn("match the shot's back view", prompt)
        self.assertNotIn("front view", prompt)

    def test_legacy_character_prompt_enhancement_builds_richer_fallback_shot_when_shot_missing(self):
        visual_prompt = "Side profile of Li Ming turning toward the doorway."
        captured_shot = {}

        def fake_infer_shot_view_hint(name, shot):
            captured_shot.update(shot)
            return ""

        with (
            patch("app.services.pipeline_executor.build_character_reference_anchor", return_value="young man, short black hair"),
            patch("app.services.pipeline_executor.infer_shot_view_hint", side_effect=fake_infer_shot_view_hint),
        ):
            prompt = PipelineExecutor._enhance_prompt_with_character(
                visual_prompt,
                {
                    "characters": [
                        {
                            "name": "Li Ming",
                            "description": "young man, short black hair, wearing a dark blue robe.",
                        }
                    ],
                    "character_images": {
                        "Li Ming": {
                            "design_prompt": "Character turnaround prompt for Li Ming",
                        }
                    },
                },
            )

        self.assertIn("[Character Li Ming: young man, short black hair]", prompt)
        self.assertEqual(captured_shot["storyboard_description"], visual_prompt)
        self.assertEqual(captured_shot["image_prompt"], visual_prompt)
        self.assertEqual(captured_shot["final_video_prompt"], visual_prompt)
        self.assertEqual(captured_shot["visual_elements"]["subject_and_clothing"], visual_prompt)
        self.assertEqual(captured_shot["visual_elements"]["action_and_expression"], visual_prompt)

    def test_legacy_character_prompt_enhancement_still_uses_description_without_character_assets(self):
        prompt = PipelineExecutor._enhance_prompt_with_character(
            "Medium shot. Li Ming pauses at the doorway.",
            {
                "characters": [
                    {
                        "id": "char_li_ming",
                        "name": "Li Ming",
                        "description": "young man, short black hair, wearing a dark blue robe.",
                    }
                ],
                "character_images": {},
            },
        )

        self.assertIn("[Character Li Ming:", prompt)
        self.assertIn("young man", prompt)
        self.assertIn("short black hair", prompt)
        self.assertIn("dark blue robe", prompt)


class PipelineExecutorPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_snapshot_persistence_rolls_back_failed_session(self):
        db = AsyncMock()
        executor = PipelineExecutor("project-1", "pipeline-1", db, story_id="story-1")

        with (
            patch("app.services.pipeline_executor.repo.get_story", new=AsyncMock(return_value={"id": "story-1"})),
            patch(
                "app.services.pipeline_executor.persist_storyboard_generation_state",
                new=AsyncMock(side_effect=RuntimeError("boom")),
            ),
            patch("app.services.pipeline_executor.logger.exception") as logger_exception,
        ):
            await executor._persist_storyboard_generation_snapshot({"meta": {}})

        db.rollback.assert_awaited_once()
        logger_exception.assert_called_once()


class PipelineExecutorStateResetTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_full_pipeline_resets_previous_shots_and_results(self):
        executor = PipelineExecutor("project-1", "pipeline-1", None, story_id="story-1")
        executor.shots = [object()]
        executor.results = [{"shot_id": "stale"}]

        with (
            patch("app.services.pipeline_executor.prepare_story_context", new=AsyncMock(return_value=({}, None))),
            patch("app.services.pipeline_executor.parse_script_to_storyboard", new=AsyncMock(side_effect=RuntimeError("parse failed"))),
            patch.object(executor, "_update_state", new=AsyncMock()),
        ):
            with self.assertRaisesRegex(RuntimeError, "parse failed"):
                await executor.run_full_pipeline(
                    script="test",
                    strategy=GenerationStrategy.SEPARATED,
                    provider="openai",
                    model="gpt-test",
                    voice="voice",
                    image_model="image-model",
                    video_model="video-model",
                    base_url="http://testserver",
                    story_id="story-1",
                )

        self.assertEqual(executor.shots, [])
        self.assertEqual(executor.results, [])


class AutoPipelinePersistenceTests(unittest.IsolatedAsyncioTestCase):
    def _make_shot(self) -> Shot:
        return Shot(
            shot_id="scene1_shot1",
            storyboard_description="Li Ming pauses at the doorway.",
            camera_setup=CameraSetup(shot_size="MS", camera_angle="Eye-level", movement="Static"),
            visual_elements=VisualElements(
                subject_and_clothing="Li Ming in a dark robe",
                action_and_expression="pauses before entering",
                environment_and_props="wooden doorway",
                lighting_and_color="soft overcast light",
            ),
            image_prompt="Medium shot. Li Ming pauses at the doorway.",
            final_video_prompt="Medium shot. Static camera. Li Ming opens the door.",
        )

    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_auto_pipeline_persists_runtime_assets_to_pipeline_and_storyboard_generation(self):
        project_id = "auto-project"
        pipeline_id = "auto-pipe-1"
        story_id = "story-auto-persist"
        shot = self._make_shot()
        story = {
            "id": story_id,
            "idea": "idea",
            "genre": "genre",
            "tone": "tone",
            "meta": {
                "storyboard_generation": {
                    "shots": [{"shot_id": "stale-shot", "video_url": "/media/videos/stale.mp4"}],
                    "generated_files": {
                        "videos": {
                            "stale-shot": {
                                "shot_id": "stale-shot",
                                "video_url": "/media/videos/stale.mp4",
                            }
                        },
                        "final_video_url": "/media/videos/final-old.mp4",
                    },
                    "final_video_url": "/media/videos/final-old.mp4",
                }
            },
        }

        async with self.session_factory() as session:
            await repo.save_story(session, story_id, story)

            executor = PipelineExecutor(project_id, pipeline_id, session, story_id=story_id)
            with (
                patch("app.services.pipeline_executor.prepare_story_context", new=AsyncMock(return_value=(story, None))),
                patch(
                    "app.services.pipeline_executor.parse_script_to_storyboard",
                    new=AsyncMock(return_value=([shot], {"prompt_tokens": 1, "completion_tokens": 1})),
                ),
                patch(
                    "app.services.pipeline_executor.tts.generate_tts_batch",
                    new=AsyncMock(
                        return_value=[
                            {
                                "shot_id": shot.shot_id,
                                "audio_url": "/media/audio/scene1_shot1.mp3",
                                "duration_seconds": 1.5,
                            }
                        ]
                    ),
                ),
                patch(
                    "app.services.pipeline_executor.image.generate_images_batch",
                    new=AsyncMock(
                        return_value=[
                            {
                                "shot_id": shot.shot_id,
                                "image_url": "/media/images/scene1_shot1.png",
                                "image_path": "media/images/scene1_shot1.png",
                            }
                        ]
                    ),
                ),
                patch(
                    "app.services.pipeline_executor.video.generate_videos_batch",
                    new=AsyncMock(
                        return_value=[
                            {
                                "shot_id": shot.shot_id,
                                "video_url": "/media/videos/scene1_shot1.mp4",
                                "video_path": "media/videos/scene1_shot1.mp4",
                            }
                        ]
                    ),
                ),
                patch(
                    "app.services.pipeline_executor.ffmpeg.stitch_batch",
                    new=AsyncMock(
                        return_value=[
                            {
                                "shot_id": shot.shot_id,
                                "audio_url": "/media/audio/scene1_shot1.mp3",
                                "audio_duration": 1.5,
                                "image_url": "/media/images/scene1_shot1.png",
                                "video_url": "/media/videos/scene1_shot1.mp4",
                                "video_path": "media/videos/scene1_shot1.mp4",
                                "final_video_url": "http://testserver/media/videos/scene1_shot1_final.mp4",
                            }
                        ]
                    ),
                ),
            ):
                await executor.run_full_pipeline(
                    script="scene script",
                    strategy=GenerationStrategy.SEPARATED,
                    provider="openai",
                    model="gpt-test",
                    voice="zh-CN-XiaoxiaoNeural",
                    image_model="flux",
                    video_model="wan",
                    base_url="http://testserver",
                    llm_api_key="test-key",
                    story_id=story_id,
                )

            pipeline = await repo.get_pipeline(session, pipeline_id)
            persisted_story = await repo.get_story(session, story_id)

        self.assertEqual(pipeline["status"], PipelineStatus.COMPLETE)
        self.assertIn("storyboard", pipeline["generated_files"])
        self.assertIn("tts", pipeline["generated_files"])
        self.assertIn("images", pipeline["generated_files"])
        self.assertIn("videos", pipeline["generated_files"])
        self.assertEqual(
            pipeline["generated_files"]["videos"][shot.shot_id]["video_url"],
            "http://testserver/media/videos/scene1_shot1_final.mp4",
        )
        self.assertEqual(
            pipeline["generated_files"]["storyboard"]["shots"][0]["shot_id"],
            shot.shot_id,
        )
        self.assertEqual(
            pipeline["generated_files"]["meta"]["runtime_strategy"],
            GenerationStrategy.SEPARATED.value,
        )

        state = persisted_story["meta"]["storyboard_generation"]
        self.assertEqual(state["pipeline_id"], pipeline_id)
        self.assertEqual(state["project_id"], project_id)
        self.assertEqual(state["story_id"], story_id)
        self.assertEqual(state["shots"][0]["shot_id"], shot.shot_id)
        self.assertEqual(state["shots"][0]["audio_url"], "/media/audio/scene1_shot1.mp3")
        self.assertEqual(state["shots"][0]["image_url"], "/media/images/scene1_shot1.png")
        self.assertEqual(
            state["shots"][0]["video_url"],
            "http://testserver/media/videos/scene1_shot1_final.mp4",
        )
        self.assertEqual(
            state["generated_files"]["videos"][shot.shot_id]["video_url"],
            "http://testserver/media/videos/scene1_shot1_final.mp4",
        )
        self.assertEqual(state["final_video_url"], "")
        self.assertNotIn("final_video_url", state["generated_files"])

    async def test_auto_pipeline_failure_keeps_storyboard_snapshot_for_restore(self):
        project_id = "auto-project"
        pipeline_id = "auto-pipe-2"
        story_id = "story-auto-failure"
        shot = self._make_shot()
        story = {
            "id": story_id,
            "idea": "idea",
            "genre": "genre",
            "tone": "tone",
            "meta": {
                "storyboard_generation": {
                    "shots": [{"shot_id": "stale-shot", "video_url": "/media/videos/stale.mp4"}],
                    "generated_files": {
                        "videos": {
                            "stale-shot": {
                                "shot_id": "stale-shot",
                                "video_url": "/media/videos/stale.mp4",
                            }
                        }
                    },
                    "final_video_url": "/media/videos/final-old.mp4",
                }
            },
        }

        async with self.session_factory() as session:
            await repo.save_story(session, story_id, story)

            executor = PipelineExecutor(project_id, pipeline_id, session, story_id=story_id)
            with (
                patch("app.services.pipeline_executor.prepare_story_context", new=AsyncMock(return_value=(story, None))),
                patch(
                    "app.services.pipeline_executor.parse_script_to_storyboard",
                    new=AsyncMock(return_value=([shot], {"prompt_tokens": 1, "completion_tokens": 1})),
                ),
                patch(
                    "app.services.pipeline_executor.tts.generate_tts_batch",
                    new=AsyncMock(side_effect=RuntimeError("tts failed")),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "tts failed"):
                    await executor.run_full_pipeline(
                        script="scene script",
                        strategy=GenerationStrategy.SEPARATED,
                        provider="openai",
                        model="gpt-test",
                        voice="zh-CN-XiaoxiaoNeural",
                        image_model="flux",
                        video_model="wan",
                        base_url="http://testserver",
                        llm_api_key="test-key",
                        story_id=story_id,
                    )

            pipeline = await repo.get_pipeline(session, pipeline_id)
            persisted_story = await repo.get_story(session, story_id)

        self.assertEqual(pipeline["status"], PipelineStatus.FAILED)
        self.assertIn("storyboard", pipeline["generated_files"])
        self.assertNotIn("tts", pipeline["generated_files"])
        self.assertEqual(
            pipeline["generated_files"]["storyboard"]["shots"][0]["shot_id"],
            shot.shot_id,
        )

        state = persisted_story["meta"]["storyboard_generation"]
        self.assertEqual(state["shots"][0]["shot_id"], shot.shot_id)
        self.assertIn("storyboard", state["generated_files"])
        self.assertNotIn("tts", state["generated_files"])
        self.assertEqual(state["final_video_url"], "")


class PipelineStatusLookupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_status_prefers_story_lookup_when_story_id_is_provided(self):
        async with self.session_factory() as session:
            await repo.save_pipeline(
                session,
                "pipe-db-1",
                "story-123",
                {
                    "status": PipelineStatus.COMPLETE,
                    "progress": 100,
                    "current_step": "done",
                    "generated_files": {"meta": {"note": INTEGRATED_FALLBACK_NOTE}},
                },
            )

            status = await get_status("legacy-project", story_id="story-123", db=session)

        self.assertEqual(status.pipeline_id, "pipe-db-1")
        self.assertEqual(status.story_id, "story-123")
        self.assertEqual(status.status, PipelineStatus.COMPLETE)
        self.assertEqual(status.note, INTEGRATED_FALLBACK_NOTE)

    async def test_status_returns_default_pending_when_no_pipeline_is_persisted(self):
        async with self.session_factory() as session:
            status = await get_status("manual-project", db=session)

        self.assertIsNone(status.pipeline_id)
        self.assertEqual(status.story_id, "manual-project")
        self.assertEqual(status.status, PipelineStatus.PENDING)
        self.assertEqual(status.current_step, "Waiting to start")


class PipelineStoryContextFallbackTests(unittest.IsolatedAsyncioTestCase):
    def _make_shot(self) -> Shot:
        return Shot(
            shot_id="scene1_shot1",
            storyboard_description="Li Ming pauses at the doorway.",
            camera_setup=CameraSetup(shot_size="MS", camera_angle="Eye-level", movement="Static"),
            visual_elements=VisualElements(
                subject_and_clothing="Li Ming in a dark robe",
                action_and_expression="pauses before entering",
                environment_and_props="wooden doorway",
                lighting_and_color="soft overcast light",
            ),
            image_prompt="Medium shot. Li Ming pauses at the doorway.",
            final_video_prompt="Medium shot. Static camera. Li Ming opens the door.",
        )

    async def test_pipeline_executor_uses_constructor_story_id_when_call_arg_missing(self):
        executor = PipelineExecutor("legacy-project", "pipe-ctx-1", db=None, story_id="story-from-constructor")

        with (
            patch("app.services.pipeline_executor.prepare_story_context", new=AsyncMock(return_value=({}, None))) as prepare_mock,
            patch("app.services.pipeline_executor.parse_script_to_storyboard", new=AsyncMock(return_value=([self._make_shot()], {}))),
            patch.object(PipelineExecutor, "_run_separated_strategy", new=AsyncMock(return_value=None)),
            patch.object(PipelineExecutor, "_stitch_videos", new=AsyncMock(return_value=None)),
            patch("app.services.pipeline_executor.repo.save_pipeline", new=AsyncMock()),
        ):
            await executor.run_full_pipeline(
                script="scene script",
                strategy=GenerationStrategy.SEPARATED,
                provider="openai",
                model="gpt-test",
                voice="zh-CN-XiaoxiaoNeural",
                image_model="flux",
                video_model="wan",
                base_url="http://localhost:8000",
                llm_api_key="test-key",
                story_id=None,
            )

        self.assertEqual(prepare_mock.await_args.args[1], "story-from-constructor")

    async def test_pipeline_executor_updates_story_id_when_call_arg_provided(self):
        executor = PipelineExecutor("legacy-project", "pipe-ctx-2", db=None, story_id="story-from-constructor")

        with (
            patch("app.services.pipeline_executor.prepare_story_context", new=AsyncMock(return_value=({}, None))) as prepare_mock,
            patch("app.services.pipeline_executor.parse_script_to_storyboard", new=AsyncMock(return_value=([self._make_shot()], {}))),
            patch.object(PipelineExecutor, "_run_separated_strategy", new=AsyncMock(return_value=None)),
            patch.object(PipelineExecutor, "_stitch_videos", new=AsyncMock(return_value=None)),
            patch("app.services.pipeline_executor.repo.save_pipeline", new=AsyncMock()),
        ):
            await executor.run_full_pipeline(
                script="scene script",
                strategy=GenerationStrategy.SEPARATED,
                provider="openai",
                model="gpt-test",
                voice="zh-CN-XiaoxiaoNeural",
                image_model="flux",
                video_model="wan",
                base_url="http://localhost:8000",
                llm_api_key="test-key",
                story_id="story-from-call",
            )

        self.assertEqual(prepare_mock.await_args.args[1], "story-from-call")
        self.assertEqual(executor.story_id, "story-from-call")

    async def test_pipeline_executor_marks_failed_when_prepare_story_context_raises(self):
        executor = PipelineExecutor("legacy-project", "pipe-ctx-3", db=None, story_id="story-ctx-error")

        with (
            patch(
                "app.services.pipeline_executor.prepare_story_context",
                new=AsyncMock(side_effect=RuntimeError("context failed")),
            ),
            patch.object(executor, "_update_state", new=AsyncMock()) as update_state,
        ):
            with self.assertRaisesRegex(RuntimeError, "context failed"):
                await executor.run_full_pipeline(
                    script="scene script",
                    strategy=GenerationStrategy.SEPARATED,
                    provider="openai",
                    model="gpt-test",
                    voice="zh-CN-XiaoxiaoNeural",
                    image_model="flux",
                    video_model="wan",
                    base_url="http://localhost:8000",
                    llm_api_key="test-key",
                    story_id="story-ctx-error",
                )

        update_state.assert_awaited_once()
        self.assertEqual(update_state.await_args.args[0], PipelineStatus.FAILED)
        self.assertEqual(update_state.await_args.kwargs["error"], "context failed")

    async def test_generate_storyboard_loads_context_from_tracking_story_id(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        request = Request({"type": "http", "headers": []})
        req = StoryboardRequest(script="scene script", provider="openai", model="gpt-test")

        try:
            async with session_factory() as session:
                with (
                    patch("app.routers.pipeline._load_story_context", new=AsyncMock(return_value=({}, None))) as load_mock,
                    patch(
                        "app.routers.pipeline.parse_script_to_storyboard",
                        new=AsyncMock(return_value=([self._make_shot()], {"prompt_tokens": 1, "completion_tokens": 1})),
                    ),
                ):
                    result = await generate_storyboard(
                        "story-from-route",
                        request,
                        req,
                        llm={"provider": "openai", "model": "gpt-test", "api_key": "test-key", "base_url": "https://example.com/v1"},
                        db=session,
                    )
        finally:
            await engine.dispose()

        self.assertEqual(load_mock.await_args.args[1], "story-from-route")
        self.assertEqual(len(result.shots), 1)

    async def test_generate_storyboard_returns_success_when_storyboard_persist_fails(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        request = Request({"type": "http", "headers": []})
        req = StoryboardRequest(script="scene script", provider="openai", model="gpt-test", story_id="story-best-effort")

        try:
            async with session_factory() as session:
                with (
                    patch(
                        "app.routers.pipeline._load_story_context",
                        new=AsyncMock(return_value=({"id": "story-best-effort", "meta": {}}, None)),
                    ),
                    patch(
                        "app.routers.pipeline.parse_script_to_storyboard",
                        new=AsyncMock(return_value=([self._make_shot()], {"prompt_tokens": 1, "completion_tokens": 1})),
                    ),
                    patch(
                        "app.routers.pipeline.persist_storyboard_generation_state",
                        new=AsyncMock(side_effect=RuntimeError("persist failed")),
                    ),
                ):
                    result = await generate_storyboard(
                        "story-best-effort",
                        request,
                        req,
                        llm={"provider": "openai", "model": "gpt-test", "api_key": "test-key", "base_url": "https://example.com/v1"},
                        db=session,
                    )
                    pipeline = await repo.get_pipeline(session, result.pipeline_id)
        finally:
            await engine.dispose()

        self.assertEqual(result.story_id, "story-best-effort")
        self.assertEqual(len(result.shots), 1)
        self.assertEqual(pipeline["progress"], 30)

    async def test_generate_storyboard_replaces_stale_storyboard_generation_assets(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        request = Request({"type": "http", "headers": []})
        story_id = "story-refresh-state"
        req = StoryboardRequest(script="scene script", provider="openai", model="gpt-test", story_id=story_id)
        story = {
            "id": story_id,
            "idea": "idea",
            "genre": "genre",
            "tone": "tone",
            "meta": {
                "storyboard_generation": {
                    "shots": [{"shot_id": "stale-shot", "video_url": "/media/videos/stale.mp4"}],
                    "generated_files": {
                        "videos": {
                            "stale-shot": {
                                "shot_id": "stale-shot",
                                "video_url": "/media/videos/stale.mp4",
                            }
                        },
                        "final_video_url": "/media/videos/final-old.mp4",
                    },
                    "final_video_url": "/media/videos/final-old.mp4",
                }
            },
            "characters": [],
            "relationships": [],
            "outline": [],
            "scenes": [],
        }

        try:
            async with session_factory() as session:
                await repo.save_story(session, story_id, story)
                with (
                    patch(
                        "app.routers.pipeline._load_story_context",
                        new=AsyncMock(return_value=(story, None)),
                    ),
                    patch(
                        "app.routers.pipeline.parse_script_to_storyboard",
                        new=AsyncMock(return_value=([self._make_shot()], {"prompt_tokens": 1, "completion_tokens": 1})),
                    ),
                ):
                    result = await generate_storyboard(
                        story_id,
                        request,
                        req,
                        llm={"provider": "openai", "model": "gpt-test", "api_key": "test-key", "base_url": "https://example.com/v1"},
                        db=session,
                    )
                    persisted_story = await repo.get_story(session, story_id)
        finally:
            await engine.dispose()

        state = persisted_story["meta"]["storyboard_generation"]
        self.assertEqual(result.story_id, story_id)
        self.assertEqual(list(state["generated_files"].keys()), ["storyboard"])
        self.assertEqual(state["final_video_url"], "")
        self.assertEqual(state["shots"][0]["shot_id"], "scene1_shot1")

    async def test_generate_storyboard_logs_stage_timings(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        request = Request({"type": "http", "headers": []})
        req = StoryboardRequest(script="scene script", provider="openai", model="gpt-test")

        try:
            async with session_factory() as session:
                with (
                    patch("app.routers.pipeline._load_story_context", new=AsyncMock(return_value=({}, None))),
                    patch(
                        "app.routers.pipeline.parse_script_to_storyboard",
                        new=AsyncMock(return_value=([self._make_shot()], {"prompt_tokens": 1, "completion_tokens": 1})),
                    ),
                    patch("app.routers.pipeline.logger.info") as info_mock,
                ):
                    await generate_storyboard(
                        "story-log-timings",
                        request,
                        req,
                        llm={"provider": "openai", "model": "gpt-test", "api_key": "test-key", "base_url": "https://example.com/v1"},
                        db=session,
                    )
        finally:
            await engine.dispose()

        self.assertTrue(
            any(call.args and "STORYBOARD_TIMING" in str(call.args[0]) for call in info_mock.call_args_list)
        )

    async def test_generate_storyboard_returns_cache_metrics_in_usage(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        request = Request({"type": "http", "headers": []})
        req = StoryboardRequest(script="scene script", provider="openai", model="gpt-test")

        try:
            async with session_factory() as session:
                with (
                    patch("app.routers.pipeline._load_story_context", new=AsyncMock(return_value=({}, None))),
                    patch(
                        "app.routers.pipeline.parse_script_to_storyboard",
                        new=AsyncMock(
                            return_value=(
                                [self._make_shot()],
                                {
                                    "prompt_tokens": 1000,
                                    "completion_tokens": 50,
                                    "cache_enabled": True,
                                    "cached_tokens": 800,
                                },
                            )
                        ),
                    ),
                ):
                    result = await generate_storyboard(
                        "story-cache-usage",
                        request,
                        req,
                        llm={"provider": "openai", "model": "gpt-test", "api_key": "test-key", "base_url": "https://example.com/v1"},
                        db=session,
                    )
        finally:
            await engine.dispose()

        self.assertEqual(result.usage.prompt_tokens, 1000)
        self.assertEqual(result.usage.cached_tokens, 800)
        self.assertEqual(result.usage.uncached_prompt_tokens, 200)
        self.assertEqual(result.usage.cache_hit_ratio, 0.8)
        self.assertTrue(result.usage.cache_enabled)

    async def test_generate_storyboard_reuses_short_character_section_filtering_for_script_mentions(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        request = Request({"type": "http", "headers": []})
        story = {
            "id": "story-filtered-characters",
            "idea": "idea",
            "genre": "genre",
            "tone": "tone",
            "characters": [
                {"id": "char_li_ming", "name": "Li Ming", "role": "lead", "description": "young man, short black hair"},
                {"id": "char_a_yue", "name": "A Yue", "role": "support", "description": "young woman, long hair"},
            ],
            "character_images": {},
            "meta": {},
        }
        story_context = build_story_context(story)
        req = StoryboardRequest(script="Li Ming stands at the doorway.", provider="openai", model="gpt-test", story_id=story["id"])

        try:
            async with session_factory() as session:
                with (
                    patch(
                        "app.routers.pipeline._load_story_context",
                        new=AsyncMock(return_value=(story, story_context)),
                    ),
                    patch(
                        "app.routers.pipeline.parse_script_to_storyboard",
                        new=AsyncMock(return_value=([self._make_shot()], {"prompt_tokens": 1, "completion_tokens": 1})),
                    ) as parse_mock,
                ):
                    await generate_storyboard(
                        "story-filtered-characters",
                        request,
                        req,
                        llm={"provider": "openai", "model": "gpt-test", "api_key": "test-key", "base_url": "https://example.com/v1"},
                        db=session,
                    )
        finally:
            await engine.dispose()

        self.assertNotIn("character_section_override", parse_mock.await_args.kwargs)
        character_section = build_character_section(
            parse_mock.await_args.kwargs["character_info"],
            script=req.script,
        )
        self.assertIn("Li Ming", character_section)
        self.assertNotIn("A Yue", character_section)

    async def test_generate_storyboard_filters_using_serialized_script_body_not_character_header(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        request = Request({"type": "http", "headers": []})
        story = {
            "id": "story-filtered-serialized-script",
            "idea": "idea",
            "genre": "genre",
            "tone": "tone",
            "characters": [
                {"id": "char_li_ming", "name": "Li Ming", "role": "lead", "description": "young man, short black hair"},
                {"id": "char_a_yue", "name": "A Yue", "role": "support", "description": "young woman, long hair"},
            ],
            "character_images": {},
            "meta": {},
            "scenes": [
                {
                    "episode": 1,
                    "title": "Rainy Night",
                    "scenes": [
                        {
                            "scene_number": 1,
                            "environment": "doorway",
                            "visual": "Li Ming stands at the doorway and looks into the room.",
                            "audio": [],
                        }
                    ],
                }
            ],
        }
        story_context = build_story_context(story)
        req = StoryboardRequest(
            script=serialize_story_to_script(story),
            provider="openai",
            model="gpt-test",
            story_id=story["id"],
        )

        try:
            async with session_factory() as session:
                with (
                    patch(
                        "app.routers.pipeline._load_story_context",
                        new=AsyncMock(return_value=(story, story_context)),
                    ),
                    patch(
                        "app.routers.pipeline.parse_script_to_storyboard",
                        new=AsyncMock(return_value=([self._make_shot()], {"prompt_tokens": 1, "completion_tokens": 1})),
                    ) as parse_mock,
                ):
                    await generate_storyboard(
                        "story-filtered-serialized-script",
                        request,
                        req,
                        llm={"provider": "openai", "model": "gpt-test", "api_key": "test-key", "base_url": "https://example.com/v1"},
                        db=session,
                    )
        finally:
            await engine.dispose()

        self.assertNotIn("character_section_override", parse_mock.await_args.kwargs)
        character_section = build_character_section(
            parse_mock.await_args.kwargs["character_info"],
            script=req.script,
        )
        self.assertIn("Li Ming", character_section)
        self.assertNotIn("A Yue", character_section)

    async def test_generate_storyboard_filters_using_character_aliases(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        request = Request({"type": "http", "headers": []})
        story = {
            "id": "story-filtered-character-aliases",
            "idea": "idea",
            "genre": "genre",
            "tone": "tone",
            "characters": [
                {
                    "id": "char_boss_zhao",
                    "name": "Boss Zhao",
                    "role": "support",
                    "description": "middle-aged man, moustache",
                    "aliases": ["赵掌柜"],
                },
                {
                    "id": "char_a_yue",
                    "name": "A Yue",
                    "role": "support",
                    "description": "young woman, long hair",
                },
            ],
            "character_images": {},
            "meta": {},
            "scenes": [
                {
                    "episode": 1,
                    "title": "Rainy Night",
                    "scenes": [
                        {
                            "scene_number": 1,
                            "environment": "counter",
                            "visual": "赵掌柜站在柜台后抬眼看向门口。",
                            "audio": [],
                        }
                    ],
                }
            ],
        }
        story_context = build_story_context(story)
        req = StoryboardRequest(
            script=serialize_story_to_script(story),
            provider="openai",
            model="gpt-test",
            story_id=story["id"],
        )

        try:
            async with session_factory() as session:
                with (
                    patch(
                        "app.routers.pipeline._load_story_context",
                        new=AsyncMock(return_value=(story, story_context)),
                    ),
                    patch(
                        "app.routers.pipeline.parse_script_to_storyboard",
                        new=AsyncMock(return_value=([self._make_shot()], {"prompt_tokens": 1, "completion_tokens": 1})),
                    ) as parse_mock,
                ):
                    await generate_storyboard(
                        "story-filtered-character-aliases",
                        request,
                        req,
                        llm={"provider": "openai", "model": "gpt-test", "api_key": "test-key", "base_url": "https://example.com/v1"},
                        db=session,
                    )
        finally:
            await engine.dispose()

        self.assertNotIn("character_section_override", parse_mock.await_args.kwargs)
        character_section = build_character_section(
            parse_mock.await_args.kwargs["character_info"],
            script=req.script,
        )
        self.assertIn("Boss Zhao / 赵掌柜", character_section)
        self.assertNotIn("A Yue", character_section)


class ManualPipelineMainlineTests(unittest.IsolatedAsyncioTestCase):
    def _make_request(self) -> Request:
        return Request(
            {
                "type": "http",
                "headers": [],
                "scheme": "http",
                "server": ("testserver", 80),
                "root_path": "",
                "path": "/",
            }
        )

    def _make_shot(self) -> Shot:
        return Shot(
            shot_id="scene1_shot1",
            storyboard_description="Li Ming pauses at the doorway.",
            camera_setup=CameraSetup(shot_size="MS", camera_angle="Eye-level", movement="Static"),
            visual_elements=VisualElements(
                subject_and_clothing="Li Ming in a dark robe",
                action_and_expression="pauses before entering",
                environment_and_props="wooden doorway",
                lighting_and_color="soft overcast light",
            ),
            image_prompt="Medium shot. Li Ming pauses at the doorway.",
            final_video_prompt="Medium shot. Static camera. Li Ming opens the door.",
        )

    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_manual_pipeline_mainline_reuses_pipeline_and_accumulates_outputs(self):
        project_id = "manual-project"
        story_id = "story-mainline"
        request = self._make_request()
        shot = self._make_shot()

        async with self.session_factory() as session:
            with (
                patch("app.routers.pipeline._load_story_context", new=AsyncMock(return_value=({}, None))),
                patch(
                    "app.routers.pipeline.parse_script_to_storyboard",
                    new=AsyncMock(return_value=([shot], {"prompt_tokens": 1, "completion_tokens": 1})),
                ),
                patch(
                    "app.services.tts.generate_tts_batch",
                    new=AsyncMock(
                        return_value=[
                            {
                                "shot_id": shot.shot_id,
                                "audio_url": "/media/audio/scene1_shot1.mp3",
                                "duration_seconds": 1.5,
                            }
                        ]
                    ),
                ),
                patch(
                    "app.services.image.generate_images_batch",
                    new=AsyncMock(
                        return_value=[
                            {
                                "shot_id": shot.shot_id,
                                "image_url": "/media/images/scene1_shot1.png",
                            }
                        ]
                    ),
                ),
                patch(
                    "app.services.video.generate_videos_batch",
                    new=AsyncMock(
                        return_value=[
                            {
                                "shot_id": shot.shot_id,
                                "video_url": "/media/videos/scene1_shot1.mp4",
                            }
                        ]
                    ),
                ),
                patch("app.services.ffmpeg.concat_videos", new=AsyncMock(return_value="media/videos/episode_manual-project.mp4")),
            ):
                storyboard = await generate_storyboard(
                    project_id,
                    request,
                    StoryboardRequest(
                        script="scene script",
                        provider="openai",
                        model="gpt-test",
                        story_id=story_id,
                    ),
                    llm={
                        "provider": "openai",
                        "model": "gpt-test",
                        "api_key": "test-key",
                        "base_url": "https://example.com/v1",
                    },
                    db=session,
                )

                self.assertEqual(storyboard.story_id, story_id)
                self.assertIsNotNone(storyboard.pipeline_id)

                tts_response = await generate_assets(
                    project_id=project_id,
                    request=request,
                    storyboard=storyboard,
                    image_config={"image_api_key": "image-key", "image_base_url": "https://image.example/v1"},
                    llm={
                        "provider": "openai",
                        "model": "gpt-test",
                        "api_key": "test-key",
                        "base_url": "https://example.com/v1",
                    },
                    pipeline_id=storyboard.pipeline_id,
                    generate_tts=True,
                    generate_images=False,
                    voice="zh-CN-XiaoxiaoNeural",
                    image_model="flux-test",
                    story_id=storyboard.story_id,
                    background_tasks=None,
                    db=session,
                )
                self.assertEqual(tts_response.pipeline_id, storyboard.pipeline_id)

                status_after_tts = await get_status(
                    project_id,
                    pipeline_id=storyboard.pipeline_id,
                    story_id=storyboard.story_id,
                    db=session,
                )
                self.assertIn("tts", status_after_tts.generated_files)
                self.assertNotIn("images", status_after_tts.generated_files)

                images_response = await generate_assets(
                    project_id=project_id,
                    request=request,
                    storyboard=storyboard,
                    image_config={"image_api_key": "image-key", "image_base_url": "https://image.example/v1"},
                    llm={
                        "provider": "openai",
                        "model": "gpt-test",
                        "api_key": "test-key",
                        "base_url": "https://example.com/v1",
                    },
                    pipeline_id=storyboard.pipeline_id,
                    generate_tts=False,
                    generate_images=True,
                    voice="zh-CN-XiaoxiaoNeural",
                    image_model="flux-test",
                    story_id=storyboard.story_id,
                    background_tasks=None,
                    db=session,
                )
                self.assertEqual(images_response.pipeline_id, storyboard.pipeline_id)

                status_after_images = await get_status(
                    project_id,
                    pipeline_id=storyboard.pipeline_id,
                    story_id=storyboard.story_id,
                    db=session,
                )
                self.assertIn("tts", status_after_images.generated_files)
                self.assertIn("images", status_after_images.generated_files)

                image_url = status_after_images.generated_files["images"][shot.shot_id]["image_url"]
                video_response = await render_video(
                    project_id=project_id,
                    request=request,
                    shots_data=[{**storyboard.shots[0].model_dump(), "image_url": image_url}],
                    video_config={
                        "video_api_key": "video-key",
                        "video_base_url": "https://video.example/v1",
                        "video_provider": "dashscope",
                    },
                    llm={
                        "provider": "openai",
                        "model": "gpt-test",
                        "api_key": "test-key",
                        "base_url": "https://example.com/v1",
                    },
                    base_url="http://testserver",
                    video_model="wan-test",
                    pipeline_id=storyboard.pipeline_id,
                    story_id=storyboard.story_id,
                    background_tasks=None,
                    db=session,
                )
                self.assertEqual(video_response.pipeline_id, storyboard.pipeline_id)

                status_after_video = await get_status(
                    project_id,
                    pipeline_id=storyboard.pipeline_id,
                    story_id=storyboard.story_id,
                    db=session,
                )
                self.assertIn("tts", status_after_video.generated_files)
                self.assertIn("images", status_after_video.generated_files)
                self.assertIn("videos", status_after_video.generated_files)

                concat_response = await concat_videos(
                    project_id=project_id,
                    req=ConcatRequest(
                        video_urls=[status_after_video.generated_files["videos"][shot.shot_id]["video_url"]]
                    ),
                    request=request,
                    pipeline_id=storyboard.pipeline_id,
                    story_id=storyboard.story_id,
                    db=session,
                )

                final_status = await get_status(
                    project_id,
                    pipeline_id=storyboard.pipeline_id,
                    story_id=storyboard.story_id,
                    db=session,
                )

        self.assertEqual(concat_response.pipeline_id, storyboard.pipeline_id)
        self.assertEqual(concat_response.video_url, f"/media/videos/episode_{project_id}.mp4")
        self.assertEqual(final_status.status, PipelineStatus.COMPLETE)
        self.assertIn("tts", final_status.generated_files)
        self.assertIn("images", final_status.generated_files)
        self.assertIn("videos", final_status.generated_files)
        self.assertEqual(final_status.generated_files["final_video_url"], concat_response.video_url)

    async def test_end_to_end_simulation_from_scene_to_storyboard_image_video_transition_is_consistent(self):
        project_id = "manual-e2e"
        story_id = "story-e2e"
        request = self._make_request()
        story = {
            "idea": "雨夜茶馆重逢",
            "genre": "古风",
            "tone": "克制",
            "art_style": "cinematic watercolor",
            "characters": [
                {
                    "id": "char_li_ming",
                    "name": "Li Ming",
                    "role": "lead",
                    "description": "young man, short black hair, wearing a dark blue robe.",
                },
                {
                    "id": "char_boss_zhao",
                    "name": "Boss Zhao",
                    "role": "support",
                    "description": "middle-aged man, moustache, wearing a brown robe.",
                },
            ],
            "character_images": {
                "char_li_ming": {
                    "image_url": "/media/characters/li_ming.png",
                    "image_path": "media/characters/li_ming.png",
                    "visual_dna": "young man, short black hair, dark blue robe",
                    "character_id": "char_li_ming",
                    "character_name": "Li Ming",
                },
                "char_boss_zhao": {
                    "image_url": "/media/characters/boss_zhao.png",
                    "image_path": "media/characters/boss_zhao.png",
                    "visual_dna": "middle-aged man, moustache, brown robe",
                    "character_id": "char_boss_zhao",
                    "character_name": "Boss Zhao",
                },
            },
            "meta": {
                "scene_reference_assets": {
                    "ep01_scene01": {
                        "summary_environment": "jiangnan teahouse doorway and counter",
                        "summary_visuals": ["wooden door frame", "warm lantern glow", "rain-wet threshold", "abacus on counter"],
                        "summary_lighting": "soft rainy daylight with warm lantern fill",
                        "variants": {
                            "scene": {
                                "image_url": "/media/episodes/ep01_scene01.png",
                                "image_path": "media/episodes/ep01_scene01.png",
                            }
                        },
                    }
                }
            },
            "scenes": [
                {
                    "episode": 1,
                    "title": "雨夜来客",
                    "scenes": [
                        {
                            "scene_number": 1,
                            "scene_heading": "夜 外 茶馆门口/内堂",
                            "environment_anchor": "江南茶馆门口与柜台",
                            "environment": "雨夜江南茶馆门口，木门半开，内堂柜台与算盘隐约可见。",
                            "lighting": "雨夜冷天光与暖色灯笼补光并存",
                            "mood": "restrained tension",
                            "emotion_tags": [{"target": "Li Ming", "emotion": "hesitant", "intensity": 0.6}],
                            "key_props": ["木门", "灯笼", "算盘"],
                            "key_actions": ["李明右手扶门停住", "李明推门入内后看向柜台", "赵掌柜在柜台后抬眼回应"],
                            "visual": "李明停在门口，随后推门进入内堂，赵掌柜在柜台后与他对视。",
                            "transition_from_previous": "同一人物、同一服装，动作从门口停顿延续到推门进入内堂。",
                            "audio": [{"character": "李明", "line": "打扰了。"}],
                        }
                    ],
                }
            ],
        }
        storyboard_script = serialize_story_to_script(story)
        story_context = build_story_context(story)
        shot_one = Shot(
            shot_id="scene1_shot1",
            source_scene_key="ep01_scene01",
            characters=["Li Ming"],
            scene_position="establishing",
            storyboard_description="Li Ming pauses at the half-open wooden door, one hand still braced on the edge while rain glints on the threshold.",
            camera_setup=CameraSetup(shot_size="MS", camera_angle="Eye-level", movement="Static"),
            visual_elements=VisualElements(
                subject_and_clothing="Li Ming in a dark blue robe at the doorway",
                action_and_expression="one hand braces on the door before he steps inside",
                environment_and_props="wooden door, wet threshold, lantern glow",
                lighting_and_color="soft rainy daylight with warm lantern fill",
            ),
            image_prompt="Close portrait. Li Ming's face in rain mist at the doorway.",
            final_video_prompt="Medium shot. Static camera. Li Ming pushes the wooden door open with one hand and steps inside.",
        )
        shot_two = Shot(
            shot_id="scene1_shot2",
            source_scene_key="ep01_scene01",
            characters=["Li Ming", "Boss Zhao"],
            scene_position="development",
            storyboard_description="Li Ming steps through the doorway toward the counter while Boss Zhao raises his eyes behind the abacus.",
            camera_setup=CameraSetup(shot_size="MS", camera_angle="Eye-level", movement="Slow Dolly in"),
            visual_elements=VisualElements(
                subject_and_clothing="Li Ming in a dark blue robe facing Boss Zhao behind the counter",
                action_and_expression="Li Ming finishes entering and answers while Boss Zhao watches without moving",
                environment_and_props="teahouse counter, abacus, lanterns, half-open wooden door behind Li Ming",
                lighting_and_color="warm lantern fill over rainy daylight",
            ),
            image_prompt="Tight portrait. Li Ming looks toward Boss Zhao inside the teahouse.",
            final_video_prompt="Medium shot. Slow Dolly in. Li Ming answers at the counter while Boss Zhao watches from behind the abacus.",
            transition_from_previous="保持同一人物与服装，动作从门口停顿延续到进入内堂，右手仍扶着门边再放下。",
        )

        async def _fake_generate_images_batch(*, shots, **kwargs):
            return [
                {
                    "shot_id": shot["shot_id"],
                    "image_path": f"media/images/{shot['shot_id']}.png",
                    "image_url": f"/media/images/{shot['shot_id']}.png",
                }
                for shot in shots
            ]

        async def _fake_generate_videos_batch(*, shots, **kwargs):
            return [
                {
                    "shot_id": shot["shot_id"],
                    "video_path": f"media/videos/{shot['shot_id']}.mp4",
                    "video_url": f"/media/videos/{shot['shot_id']}.mp4",
                }
                for shot in shots
            ]

        async with self.session_factory() as session:
            await repo.save_story(session, story_id, story)

            with (
                patch("app.routers.pipeline._load_story_context", new=AsyncMock(return_value=(story, story_context))),
                patch(
                    "app.routers.pipeline.parse_script_to_storyboard",
                    new=AsyncMock(return_value=([shot_one, shot_two], {"prompt_tokens": 12, "completion_tokens": 34})),
                ) as parse_storyboard_mock,
                patch("app.services.image.generate_images_batch", new=AsyncMock(side_effect=_fake_generate_images_batch)) as generate_images_batch_mock,
                patch("app.services.video.generate_videos_batch", new=AsyncMock(side_effect=_fake_generate_videos_batch)) as generate_videos_batch_mock,
                patch(
                    "app.services.ffmpeg.extract_last_frame",
                    new=AsyncMock(return_value="media/images/transition_scene1_shot1__scene1_shot2_from_last.png"),
                ),
                patch(
                    "app.services.ffmpeg.extract_first_frame",
                    new=AsyncMock(return_value="media/images/transition_scene1_shot1__scene1_shot2_to_first.png"),
                ),
                patch(
                    "app.services.video.generate_transition_video",
                    new=AsyncMock(
                        return_value={
                            "shot_id": "transition_scene1_shot1__scene1_shot2",
                            "video_url": "/media/videos/transition_scene1_shot1__scene1_shot2.mp4",
                        }
                    ),
                ) as generate_transition_mock,
                patch("app.services.ffmpeg.concat_videos", new=AsyncMock(return_value="media/videos/episode_manual-e2e.mp4")) as concat_mock,
            ):
                storyboard = await generate_storyboard(
                    project_id,
                    request,
                    StoryboardRequest(
                        script=storyboard_script,
                        provider="openai",
                        model="gpt-test",
                        story_id=story_id,
                    ),
                    llm={
                        "provider": "openai",
                        "model": "gpt-test",
                        "api_key": "test-key",
                        "base_url": "https://example.com/v1",
                    },
                    db=session,
                )

                self.assertEqual(parse_storyboard_mock.await_args.args[0], storyboard_script)

                image_action = await generate_assets(
                    project_id=project_id,
                    request=request,
                    storyboard=storyboard,
                    image_config={"image_api_key": "image-key", "image_base_url": "https://image.example/v1"},
                    llm={
                        "provider": "openai",
                        "model": "gpt-test",
                        "api_key": "test-key",
                        "base_url": "https://example.com/v1",
                    },
                    pipeline_id=storyboard.pipeline_id,
                    generate_tts=False,
                    generate_images=True,
                    voice="zh-CN-XiaoxiaoNeural",
                    image_model="flux-test",
                    story_id=story_id,
                    background_tasks=None,
                    db=session,
                )

                status_after_images = await get_status(
                    project_id,
                    pipeline_id=storyboard.pipeline_id,
                    story_id=story_id,
                    db=session,
                )
                shots_with_images = []
                for shot in storyboard.shots:
                    serialized = shot.model_dump(mode="json")
                    serialized["image_url"] = status_after_images.generated_files["images"][shot.shot_id]["image_url"]
                    shots_with_images.append(serialized)

                video_action = await render_video(
                    project_id=project_id,
                    request=request,
                    shots_data=shots_with_images,
                    video_config={
                        "video_api_key": "video-key",
                        "video_base_url": "https://video.example/v1",
                        "video_provider": "dashscope",
                    },
                    llm={
                        "provider": "openai",
                        "model": "gpt-test",
                        "api_key": "test-key",
                        "base_url": "https://example.com/v1",
                    },
                    base_url="http://testserver",
                    video_model="wan-test",
                    pipeline_id=storyboard.pipeline_id,
                    story_id=story_id,
                    background_tasks=None,
                    db=session,
                )

                transition = await generate_transition(
                    project_id=project_id,
                    request=request,
                    req=TransitionGenerateRequest(
                        pipeline_id=storyboard.pipeline_id,
                        story_id=story_id,
                        from_shot_id=shot_one.shot_id,
                        to_shot_id=shot_two.shot_id,
                        transition_prompt="镜头衔接保持克制，不要跳出当前剧情。",
                        duration_seconds=2,
                    ),
                    video_config={
                        "video_api_key": "video-key",
                        "video_base_url": "https://video.example/v1",
                        "video_provider": "doubao",
                    },
                    llm={
                        "provider": "openai",
                        "model": "gpt-test",
                        "api_key": "test-key",
                        "base_url": "https://example.com/v1",
                    },
                    db=session,
                )

                concat_response = await concat_videos(
                    project_id=project_id,
                    req=ConcatRequest(video_urls=[]),
                    request=request,
                    pipeline_id=storyboard.pipeline_id,
                    story_id=story_id,
                    db=session,
                )
                final_status = await get_status(
                    project_id,
                    pipeline_id=storyboard.pipeline_id,
                    story_id=story_id,
                    db=session,
                )
                persisted_story = await repo.get_story(session, story_id)

        self.assertEqual(image_action.pipeline_id, storyboard.pipeline_id)
        self.assertEqual(video_action.pipeline_id, storyboard.pipeline_id)
        self.assertEqual(transition.transition_id, "transition_scene1_shot1__scene1_shot2")
        self.assertEqual(concat_response.video_url, f"/media/videos/episode_{project_id}.mp4")
        self.assertEqual(final_status.generated_files["final_video_url"], concat_response.video_url)
        self.assertEqual(
            final_status.generated_files["timeline"],
            [
                {"item_type": "shot", "item_id": shot_one.shot_id},
                {"item_type": "transition", "item_id": transition.transition_id},
                {"item_type": "shot", "item_id": shot_two.shot_id},
            ],
        )

        generate_images_batch_mock.assert_awaited_once()
        image_batch_payload = generate_images_batch_mock.await_args.kwargs["shots"]
        image_calls_by_shot = {shot["shot_id"]: shot for shot in image_batch_payload}
        first_image_call = image_calls_by_shot[shot_one.shot_id]
        second_image_call = image_calls_by_shot[shot_two.shot_id]
        self.assertTrue(first_image_call["image_prompt"].startswith("Medium shot."))
        self.assertIn("video opening frame", first_image_call["image_prompt"])
        self.assertIn("face-only portrait crop", first_image_call["image_prompt"])
        self.assertTrue(any(item["kind"] == "scene" for item in first_image_call["reference_images"]))
        self.assertTrue(any(item["kind"] == "character" for item in first_image_call["reference_images"]))
        self.assertTrue(second_image_call["image_prompt"].startswith("Medium shot."))
        self.assertIn("continuing beat inside the same scene", second_image_call["image_prompt"])
        self.assertTrue(any(item["kind"] == "previous_shot_image" for item in second_image_call["reference_images"]))

        generate_videos_batch_mock.assert_awaited_once()
        video_batch_payload = generate_videos_batch_mock.await_args.kwargs["shots"]
        video_calls_by_shot = {shot["shot_id"]: shot for shot in video_batch_payload}
        first_video_call = video_calls_by_shot[shot_one.shot_id]
        second_video_call = video_calls_by_shot[shot_two.shot_id]
        self.assertIn("Start from this exact opening frame:", first_video_call["final_video_prompt"])
        self.assertIn("Do not suddenly reveal missing hands, props", first_video_call["final_video_prompt"])
        self.assertIn("continuous beat in the same scene timeline", second_video_call["final_video_prompt"])
        self.assertEqual(first_video_call["image_url"], "/media/images/scene1_shot1.png")
        self.assertEqual(second_video_call["image_url"], "/media/images/scene1_shot2.png")

        transition_prompt = generate_transition_mock.await_args.kwargs["prompt"]
        self.assertIn("Action bridge:", transition_prompt)
        self.assertIn("Camera continuity:", transition_prompt)
        self.assertIn("Environment continuity:", transition_prompt)
        self.assertIn("Subject continuity:", transition_prompt)
        self.assertIn("doorway", transition_prompt)
        self.assertIn("counter", transition_prompt)

        concat_sequence = concat_mock.await_args.args[0]
        self.assertEqual(len(concat_sequence), 3)
        self.assertTrue(str(concat_sequence[0]).endswith("scene1_shot1.mp4"))
        self.assertTrue(str(concat_sequence[1]).endswith("transition_scene1_shot1__scene1_shot2.mp4"))
        self.assertTrue(str(concat_sequence[2]).endswith("scene1_shot2.mp4"))
        self.assertEqual(
            persisted_story["meta"]["storyboard_generation"]["generated_files"]["timeline"],
            final_status.generated_files["timeline"],
        )
        self.assertEqual(
            persisted_story["meta"]["storyboard_generation"]["final_video_url"],
            concat_response.video_url,
        )

    async def test_concat_videos_rejects_untrusted_video_urls(self):
        request = self._make_request()

        async with self.session_factory() as session:
            for video_url in (
                "http://evil.example/media/videos/scene1.mp4",
                "http://testserver/media/videos/../../outside.mp4",
            ):
                with self.subTest(video_url=video_url):
                    with self.assertRaises(HTTPException) as ctx:
                        await concat_videos(
                            project_id="manual-project",
                            req=ConcatRequest(video_urls=[video_url]),
                            request=request,
                            pipeline_id=None,
                            story_id=None,
                            db=session,
                        )

                    self.assertEqual(ctx.exception.status_code, 400)

    async def test_concat_videos_with_pipeline_id_requires_all_transitions_even_if_request_urls_exist(self):
        project_id = "manual-project"
        story_id = "story-concat-guard"
        pipeline_id = "pipe-concat-guard"
        request = self._make_request()
        shot_one = self._make_shot()
        shot_two = Shot(
            shot_id="scene1_shot2",
            storyboard_description="Li Ming enters the room and looks toward the desk.",
            camera_setup=CameraSetup(shot_size="MS", camera_angle="Eye-level", movement="Slow Dolly in"),
            visual_elements=VisualElements(
                subject_and_clothing="Li Ming in a dark robe",
                action_and_expression="steps into the room and raises his gaze",
                environment_and_props="wooden room with a desk",
                lighting_and_color="soft overcast light",
            ),
            image_prompt="Medium shot. Li Ming enters the room and looks toward the desk.",
            final_video_prompt="Medium shot. Slow Dolly in. Li Ming steps toward the desk.",
        )

        async with self.session_factory() as session:
            await repo.save_pipeline(
                session,
                pipeline_id,
                story_id,
                {
                    "status": PipelineStatus.RENDERING_VIDEO,
                    "progress": 85,
                    "current_step": "Videos ready",
                    "generated_files": {
                        "storyboard": {
                            "shots": [shot_one.model_dump(mode="json"), shot_two.model_dump(mode="json")],
                        },
                        "videos": {
                            shot_one.shot_id: {
                                "shot_id": shot_one.shot_id,
                                "video_url": "/media/videos/scene1_shot1.mp4",
                            },
                            shot_two.shot_id: {
                                "shot_id": shot_two.shot_id,
                                "video_url": "/media/videos/scene1_shot2.mp4",
                            },
                        },
                    },
                },
            )

            with self.assertRaises(HTTPException) as ctx:
                await concat_videos(
                    project_id=project_id,
                    req=ConcatRequest(video_urls=["/media/videos/scene1_shot1.mp4"]),
                    request=request,
                    pipeline_id=pipeline_id,
                    story_id=story_id,
                    db=session,
                )

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("缺少过渡视频", ctx.exception.detail)

    async def test_generate_transition_uses_adjacent_videos_and_persists_timeline(self):
        project_id = "manual-project"
        story_id = "story-mainline"
        pipeline_id = "pipe-transition-1"
        request = self._make_request()
        shot_one = self._make_shot()
        shot_two = Shot(
            shot_id="scene1_shot2",
            storyboard_description="Li Ming enters the room and looks toward the desk.",
            camera_setup=CameraSetup(shot_size="MS", camera_angle="Eye-level", movement="Slow Dolly in"),
            visual_elements=VisualElements(
                subject_and_clothing="Li Ming in a dark robe",
                action_and_expression="steps into the room and raises his gaze",
                environment_and_props="wooden room with a desk",
                lighting_and_color="soft overcast light",
            ),
            image_prompt="Medium shot. Li Ming enters the room and looks toward the desk.",
            final_video_prompt="Medium shot. Slow Dolly in. Li Ming steps toward the desk.",
            transition_from_previous="保持同一人物与服装，动作从门口延续到进入房间。",
        )

        async with self.session_factory() as session:
            await repo.save_pipeline(
                session,
                pipeline_id,
                story_id,
                {
                    "status": PipelineStatus.RENDERING_VIDEO,
                    "progress": 85,
                    "current_step": "Videos ready",
                    "generated_files": {
                        "storyboard": {
                            "shots": [shot_one.model_dump(mode="json"), shot_two.model_dump(mode="json")],
                        },
                        "videos": {
                            shot_one.shot_id: {
                                "shot_id": shot_one.shot_id,
                                "video_url": "/media/videos/scene1_shot1.mp4",
                            },
                            shot_two.shot_id: {
                                "shot_id": shot_two.shot_id,
                                "video_url": "/media/videos/scene1_shot2.mp4",
                            },
                        },
                    },
                },
            )

            with (
                patch("app.routers.pipeline._load_story_context", new=AsyncMock(return_value=({}, None))),
                patch(
                    "app.services.ffmpeg.extract_last_frame",
                    new=AsyncMock(return_value="media/images/transition_scene1_shot1__scene1_shot2_from_last.png"),
                ) as extract_last_mock,
                patch(
                    "app.services.ffmpeg.extract_first_frame",
                    new=AsyncMock(return_value="media/images/transition_scene1_shot1__scene1_shot2_to_first.png"),
                ) as extract_first_mock,
                patch(
                    "app.services.video.generate_transition_video",
                    new=AsyncMock(
                        return_value={
                            "shot_id": "transition_scene1_shot1__scene1_shot2",
                            "video_url": "/media/videos/transition_scene1_shot1__scene1_shot2.mp4",
                        }
                    ),
                ) as generate_transition_mock,
            ):
                result = await generate_transition(
                    project_id=project_id,
                    request=request,
                    req=TransitionGenerateRequest(
                        pipeline_id=pipeline_id,
                        story_id=story_id,
                        from_shot_id=shot_one.shot_id,
                        to_shot_id=shot_two.shot_id,
                        transition_prompt="镜头衔接保持克制，不要跳出当前剧情。",
                        duration_seconds=3,
                    ),
                    video_config={
                        "video_api_key": "video-key",
                        "video_base_url": "https://video.example/v1",
                        "video_provider": "doubao",
                    },
                    llm={
                        "provider": "openai",
                        "model": "gpt-test",
                        "api_key": "test-key",
                        "base_url": "https://example.com/v1",
                    },
                    db=session,
                )

                status = await get_status(
                    project_id,
                    pipeline_id=pipeline_id,
                    story_id=story_id,
                    db=session,
                )

        self.assertEqual(result.transition_id, "transition_scene1_shot1__scene1_shot2")
        self.assertEqual(result.duration_seconds, 3)
        self.assertEqual(result.first_frame_source.extracted_image_url, "/media/images/transition_scene1_shot1__scene1_shot2_from_last.png")
        self.assertEqual(result.last_frame_source.extracted_image_url, "/media/images/transition_scene1_shot1__scene1_shot2_to_first.png")
        self.assertEqual(result.first_frame_source.source_type, "video_frame")
        self.assertEqual(result.last_frame_source.source_type, "video_frame")
        self.assertIn("前后锚点都来自相邻主镜头视频抽帧", result.diagnostic_summary)
        self.assertEqual(extract_last_mock.await_args.kwargs["output_name"], "transition_scene1_shot1__scene1_shot2_from_last.png")
        self.assertEqual(extract_first_mock.await_args.kwargs["output_name"], "transition_scene1_shot1__scene1_shot2_to_first.png")
        expected_first_frame_path = str((MEDIA_DIR / "images" / "transition_scene1_shot1__scene1_shot2_from_last.png").resolve(strict=False))
        expected_last_frame_path = str((MEDIA_DIR / "images" / "transition_scene1_shot1__scene1_shot2_to_first.png").resolve(strict=False))
        self.assertEqual(
            generate_transition_mock.await_args.kwargs["first_frame_url"],
            expected_first_frame_path,
        )
        self.assertEqual(
            generate_transition_mock.await_args.kwargs["last_frame_url"],
            expected_last_frame_path,
        )
        self.assertEqual(generate_transition_mock.await_args.kwargs["duration_seconds"], 3)
        transition_prompt = generate_transition_mock.await_args.kwargs["prompt"]
        transition_negative_prompt = generate_transition_mock.await_args.kwargs["negative_prompt"]
        self.assertIn("extracted last frame", transition_prompt)
        self.assertIn("extracted first frame", transition_prompt)
        self.assertIn("smooth and natural", transition_prompt)
        self.assertIn("middle frames must interpolate", transition_prompt)
        self.assertIn("Action bridge:", transition_prompt)
        self.assertIn("Camera continuity:", transition_prompt)
        self.assertIn("Environment continuity:", transition_prompt)
        self.assertIn("Lighting continuity:", transition_prompt)
        self.assertIn("Subject continuity:", transition_prompt)
        self.assertIn("camera motion", transition_prompt)
        self.assertIn("identity drift", transition_prompt)
        self.assertIn("pauses before entering", transition_prompt)
        self.assertIn("steps into the room and raises his gaze", transition_prompt)
        self.assertIn("wooden doorway", transition_prompt)
        self.assertIn("wooden room with a desk", transition_prompt)
        self.assertIn("camera jitter", transition_negative_prompt)
        self.assertIn("background morphing", transition_negative_prompt)
        self.assertIn("transitions", status.generated_files)
        self.assertIn(result.transition_id, status.generated_files["transitions"])
        self.assertEqual(
            status.generated_files["transitions"][result.transition_id]["first_frame_source"]["source_type"],
            "video_frame",
        )
        self.assertEqual(status.generated_files["timeline"][1]["item_type"], "transition")

    async def test_generate_transition_records_storyboard_fallback_diagnostics_when_frame_extraction_fails(self):
        project_id = "manual-project"
        story_id = "story-transition-fallback"
        pipeline_id = "pipe-transition-fallback"
        request = self._make_request()
        shot_one = self._make_shot()
        shot_two = Shot(
            shot_id="scene1_shot2",
            storyboard_description="Li Ming enters the room and looks toward the desk.",
            camera_setup=CameraSetup(shot_size="MS", camera_angle="Eye-level", movement="Slow Dolly in"),
            visual_elements=VisualElements(
                subject_and_clothing="Li Ming in a dark robe",
                action_and_expression="steps into the room and raises his gaze",
                environment_and_props="wooden room with a desk",
                lighting_and_color="soft overcast light",
            ),
            image_prompt="Medium shot. Li Ming enters the room and looks toward the desk.",
            final_video_prompt="Medium shot. Slow Dolly in. Li Ming steps toward the desk.",
            transition_from_previous="保持同一人物与服装，动作从门口延续到进入房间。",
        )

        async with self.session_factory() as session:
            await repo.save_story(
                session,
                story_id,
                {
                    "idea": "idea",
                    "genre": "genre",
                    "tone": "tone",
                    "meta": {
                        "storyboard_generation": {
                            "pipeline_id": pipeline_id,
                            "project_id": project_id,
                            "story_id": story_id,
                            "shots": [shot_one.model_dump(mode="json"), shot_two.model_dump(mode="json")],
                        }
                    },
                },
            )
            await repo.save_pipeline(
                session,
                pipeline_id,
                story_id,
                {
                    "status": PipelineStatus.RENDERING_VIDEO,
                    "progress": 85,
                    "current_step": "Videos ready",
                    "generated_files": {
                        "storyboard": {
                            "shots": [shot_one.model_dump(mode="json"), shot_two.model_dump(mode="json")],
                        },
                        "images": {
                            shot_one.shot_id: {
                                "shot_id": shot_one.shot_id,
                                "image_url": "/media/images/scene1_shot1.png",
                            },
                            shot_two.shot_id: {
                                "shot_id": shot_two.shot_id,
                                "image_url": "/media/images/scene1_shot2.png",
                            },
                        },
                        "videos": {
                            shot_one.shot_id: {
                                "shot_id": shot_one.shot_id,
                                "video_url": "/media/videos/scene1_shot1.mp4",
                            },
                            shot_two.shot_id: {
                                "shot_id": shot_two.shot_id,
                                "video_url": "/media/videos/scene1_shot2.mp4",
                            },
                        },
                    },
                },
            )

            with (
                patch("app.routers.pipeline._load_story_context", new=AsyncMock(return_value=({}, None))),
                patch(
                    "app.services.ffmpeg.extract_last_frame",
                    new=AsyncMock(side_effect=RuntimeError("ffmpeg last frame failed")),
                ),
                patch(
                    "app.services.ffmpeg.extract_first_frame",
                    new=AsyncMock(return_value="media/images/transition_scene1_shot1__scene1_shot2_to_first.png"),
                ),
                patch(
                    "app.services.video.generate_transition_video",
                    new=AsyncMock(
                        return_value={
                            "shot_id": "transition_scene1_shot1__scene1_shot2",
                            "video_url": "/media/videos/transition_scene1_shot1__scene1_shot2.mp4",
                        }
                    ),
                ) as generate_transition_mock,
                patch("app.routers.pipeline.persist_storyboard_generation_state", new=AsyncMock()),
            ):
                result = await generate_transition(
                    project_id=project_id,
                    request=request,
                    req=TransitionGenerateRequest(
                        pipeline_id=pipeline_id,
                        story_id=story_id,
                        from_shot_id=shot_one.shot_id,
                        to_shot_id=shot_two.shot_id,
                        transition_prompt="镜头衔接保持克制，不要跳出当前剧情。",
                        duration_seconds=2,
                    ),
                    video_config={
                        "video_api_key": "video-key",
                        "video_base_url": "https://video.example/v1",
                        "video_provider": "doubao",
                    },
                    llm={
                        "provider": "openai",
                        "model": "gpt-test",
                        "api_key": "test-key",
                        "base_url": "https://example.com/v1",
                    },
                    db=session,
                )

        self.assertEqual(result.first_frame_source.source_type, "storyboard_image_fallback")
        self.assertEqual(result.first_frame_source.extracted_image_url, "/media/images/scene1_shot1.png")
        self.assertIn("ffmpeg last frame failed", result.first_frame_source.extraction_error)
        self.assertEqual(result.last_frame_source.source_type, "video_frame")
        self.assertIn("前镜锚点当前回退到了分镜图", result.diagnostic_summary)
        expected_storyboard_frame_path = str((MEDIA_DIR / "images" / "scene1_shot1.png").resolve(strict=False))
        self.assertEqual(
            generate_transition_mock.await_args.kwargs["first_frame_url"],
            expected_storyboard_frame_path,
        )

    async def test_generate_transition_does_not_trust_request_video_urls(self):
        project_id = "manual-project"
        story_id = "story-transition-strict"
        pipeline_id = "pipe-transition-strict"
        request = self._make_request()
        shot_one = self._make_shot()
        shot_two = Shot(
            shot_id="scene1_shot2",
            storyboard_description="李明已经进入房间。",
            camera_setup=CameraSetup(shot_size="MS", camera_angle="Eye-level", movement="Slow Dolly in"),
            visual_elements=VisualElements(
                subject_and_clothing="Li Ming in a dark robe",
                action_and_expression="has entered the room and looks toward the desk",
                environment_and_props="interior desk area",
                lighting_and_color="soft overcast light",
            ),
            image_prompt="Medium shot. Li Ming enters the room and looks toward the desk.",
            final_video_prompt="Medium shot. Slow Dolly in. Li Ming steps toward the desk.",
            transition_from_previous="保持同一人物与服装，动作从门口延续到进入房间。",
        )

        async with self.session_factory() as session:
            await repo.save_story(
                session,
                story_id,
                {
                    "idea": "idea",
                    "genre": "genre",
                    "tone": "tone",
                    "meta": {
                        "storyboard_generation": {
                            "pipeline_id": pipeline_id,
                            "project_id": project_id,
                            "story_id": story_id,
                            "shots": [shot_one.model_dump(mode="json"), shot_two.model_dump(mode="json")],
                        }
                    },
                },
            )
            await repo.save_pipeline(
                session,
                pipeline_id,
                story_id,
                {
                    "status": PipelineStatus.RENDERING_VIDEO,
                    "progress": 85,
                    "current_step": "Videos missing in pipeline",
                    "generated_files": {
                        "storyboard": {
                            "shots": [shot_one.model_dump(mode="json"), shot_two.model_dump(mode="json")],
                        },
                    },
                },
            )

            with self.assertRaises(HTTPException) as exc_info:
                await generate_transition(
                    project_id=project_id,
                    request=request,
                    req=TransitionGenerateRequest.model_validate(
                        {
                            "pipeline_id": pipeline_id,
                            "story_id": story_id,
                            "from_shot_id": shot_one.shot_id,
                            "to_shot_id": shot_two.shot_id,
                            "from_video_url": "/media/videos/scene1_shot1_external.mp4",
                            "to_video_url": "/media/videos/scene1_shot2_external.mp4",
                        }
                    ),
                    video_config={
                        "video_api_key": "video-key",
                        "video_base_url": "https://video.example/v1",
                        "video_provider": "doubao",
                    },
                    llm={
                        "provider": "openai",
                        "model": "gpt-test",
                        "api_key": "test-key",
                        "base_url": "https://example.com/v1",
                    },
                    db=session,
                )

        self.assertEqual(exc_info.exception.status_code, 400)
        self.assertEqual(
            exc_info.exception.detail,
            "Transition requires both adjacent shot videos to be generated first. Missing video for: scene1_shot1, scene1_shot2",
        )

    async def test_generate_transition_prefers_pipeline_story_and_persisted_shot_order(self):
        project_id = "manual-project"
        story_id = "story-transition-canonical"
        stale_story_id = "story-transition-stale"
        pipeline_id = "pipe-transition-canonical"
        request = self._make_request()
        shot_one = self._make_shot()
        shot_two = Shot(
            shot_id="scene1_shot2",
            storyboard_description="Li Ming enters the room and looks toward the desk.",
            camera_setup=CameraSetup(shot_size="MS", camera_angle="Eye-level", movement="Slow Dolly in"),
            visual_elements=VisualElements(
                subject_and_clothing="Li Ming in a dark robe",
                action_and_expression="steps into the room and raises his gaze",
                environment_and_props="wooden room with a desk",
                lighting_and_color="soft overcast light",
            ),
            image_prompt="Medium shot. Li Ming enters the room and looks toward the desk.",
            final_video_prompt="Medium shot. Slow Dolly in. Li Ming steps toward the desk.",
            transition_from_previous="保持同一人物与服装，动作从门口延续到进入房间。",
        )

        async with self.session_factory() as session:
            await repo.save_story(
                session,
                story_id,
                {
                    "idea": "idea",
                    "genre": "genre",
                    "tone": "tone",
                    "meta": {
                        "storyboard_generation": {
                            "pipeline_id": pipeline_id,
                            "project_id": project_id,
                            "story_id": story_id,
                            "shots": [shot_two.model_dump(mode="json"), shot_one.model_dump(mode="json")],
                        }
                    },
                },
            )
            await repo.save_pipeline(
                session,
                pipeline_id,
                story_id,
                {
                    "status": PipelineStatus.RENDERING_VIDEO,
                    "progress": 85,
                    "current_step": "Videos ready",
                    "generated_files": {
                        "storyboard": {
                            "shots": [shot_one.model_dump(mode="json"), shot_two.model_dump(mode="json")],
                        },
                        "videos": {
                            shot_one.shot_id: {
                                "shot_id": shot_one.shot_id,
                                "video_url": "/media/videos/scene1_shot1.mp4",
                            },
                            shot_two.shot_id: {
                                "shot_id": shot_two.shot_id,
                                "video_url": "/media/videos/scene1_shot2.mp4",
                            },
                        },
                    },
                },
            )

            with (
                patch("app.routers.pipeline._load_story_context", new=AsyncMock(return_value=({}, None))) as load_mock,
                patch(
                    "app.services.ffmpeg.extract_last_frame",
                    new=AsyncMock(return_value="media/images/transition_scene1_shot2__scene1_shot1_from_last.png"),
                ),
                patch(
                    "app.services.ffmpeg.extract_first_frame",
                    new=AsyncMock(return_value="media/images/transition_scene1_shot2__scene1_shot1_to_first.png"),
                ),
                patch(
                    "app.services.video.generate_transition_video",
                    new=AsyncMock(
                        return_value={
                            "shot_id": "transition_scene1_shot2__scene1_shot1",
                            "video_url": "/media/videos/transition_scene1_shot2__scene1_shot1.mp4",
                        }
                    ),
                ),
                patch("app.routers.pipeline.persist_storyboard_generation_state", new=AsyncMock()),
            ):
                result = await generate_transition(
                    project_id=project_id,
                    request=request,
                    req=TransitionGenerateRequest(
                        pipeline_id=pipeline_id,
                        story_id=stale_story_id,
                        from_shot_id=shot_two.shot_id,
                        to_shot_id=shot_one.shot_id,
                        transition_prompt="镜头衔接保持克制，不要跳出当前剧情。",
                        duration_seconds=3,
                    ),
                    video_config={
                        "video_api_key": "video-key",
                        "video_base_url": "https://video.example/v1",
                        "video_provider": "doubao",
                    },
                    llm={
                        "provider": "openai",
                        "model": "gpt-test",
                        "api_key": "test-key",
                        "base_url": "https://example.com/v1",
                    },
                    db=session,
                )

        self.assertEqual(result.transition_id, "transition_scene1_shot2__scene1_shot1")
        self.assertEqual(load_mock.await_args.args[1], story_id)

    async def test_single_image_and_video_routes_persist_into_existing_pipeline(self):
        project_id = "story-mainline"
        story_id = "story-mainline"
        pipeline_id = "pipe-single-api-1"
        request = self._make_request()
        shot = self._make_shot()

        async with self.session_factory() as session:
            await repo.save_story(
                session,
                story_id,
                {
                    "idea": "idea",
                    "genre": "genre",
                    "tone": "tone",
                    "meta": {
                        "storyboard_generation": {
                            "pipeline_id": pipeline_id,
                            "project_id": project_id,
                            "story_id": story_id,
                            "shots": [shot.model_dump(mode="json")],
                        }
                    },
                },
            )
            await repo.save_pipeline(
                session,
                pipeline_id,
                story_id,
                {
                    "status": PipelineStatus.STORYBOARD,
                    "progress": 30,
                    "current_step": "Storyboard ready",
                    "generated_files": {
                        "storyboard": {
                            "shots": [shot.model_dump(mode="json")],
                        }
                    },
                },
            )

            with (
                patch(
                    "app.routers.image.prepare_story_context",
                    new=AsyncMock(
                        return_value=(
                            {
                                "meta": {
                                    "storyboard_generation": {
                                        "pipeline_id": pipeline_id,
                                        "project_id": project_id,
                                        "story_id": story_id,
                                        "shots": [shot.model_dump(mode="json")],
                                    }
                                }
                            },
                            None,
                        )
                    ),
                ),
                patch(
                    "app.routers.image.generate_images_batch",
                    new=AsyncMock(return_value=[{"shot_id": shot.shot_id, "image_url": "/media/images/scene1_shot1.png"}]),
                ),
            ):
                await generate_single_images(
                    project_id=project_id,
                    request=request,
                    body=ImageRequest(
                        shots=[shot.model_dump(mode="json")],
                        story_id=story_id,
                        pipeline_id=pipeline_id,
                    ),
                    image_config={"image_api_key": "image-key", "image_base_url": "https://image.example/v1"},
                    llm={
                        "provider": "openai",
                        "model": "gpt-test",
                        "api_key": "test-key",
                        "base_url": "https://example.com/v1",
                    },
                    db=session,
                )

            status_after_image = await get_status(
                project_id,
                pipeline_id=pipeline_id,
                story_id=story_id,
                db=session,
            )
            self.assertIn("images", status_after_image.generated_files)
            self.assertEqual(
                status_after_image.generated_files["images"][shot.shot_id]["image_url"],
                "/media/images/scene1_shot1.png",
            )
            persisted_story = await repo.get_story(session, story_id)
            self.assertEqual(
                persisted_story["meta"]["storyboard_generation"]["generated_files"]["images"][shot.shot_id]["image_url"],
                "/media/images/scene1_shot1.png",
            )

            with (
                patch(
                    "app.routers.video.prepare_story_context",
                    new=AsyncMock(
                        return_value=(
                            {
                                "meta": {
                                    "storyboard_generation": {
                                        "pipeline_id": pipeline_id,
                                        "project_id": project_id,
                                        "story_id": story_id,
                                        "shots": [shot.model_dump(mode="json")],
                                    }
                                }
                            },
                            None,
                        )
                    ),
                ),
                patch(
                    "app.routers.video.generate_videos_batch",
                    new=AsyncMock(return_value=[{"shot_id": shot.shot_id, "video_url": "/media/videos/scene1_shot1.mp4"}]),
                ),
            ):
                await generate_single_videos(
                    project_id=project_id,
                    request=request,
                    body=VideoRequest(
                        shots=[{**shot.model_dump(mode="json"), "image_url": "/media/images/scene1_shot1.png"}],
                        story_id=story_id,
                        pipeline_id=pipeline_id,
                    ),
                    video_config={
                        "video_api_key": "video-key",
                        "video_base_url": "https://video.example/v1",
                        "video_provider": "dashscope",
                    },
                    llm={
                        "provider": "openai",
                        "model": "gpt-test",
                        "api_key": "test-key",
                        "base_url": "https://example.com/v1",
                    },
                    db=session,
                )

            status_after_video = await get_status(
                project_id,
                pipeline_id=pipeline_id,
                story_id=story_id,
                db=session,
            )
            persisted_story = await repo.get_story(session, story_id)
            persisted_video_url = (
                persisted_story["meta"]["storyboard_generation"]["generated_files"]["videos"][shot.shot_id]["video_url"]
            )

        self.assertIn("videos", status_after_video.generated_files)
        self.assertEqual(
            status_after_video.generated_files["videos"][shot.shot_id]["video_url"],
            "/media/videos/scene1_shot1.mp4",
        )
        self.assertEqual(persisted_video_url, "/media/videos/scene1_shot1.mp4")

    async def test_single_image_generation_invalidates_dependent_transition_and_final_video(self):
        project_id = "story-mainline"
        story_id = "story-single-image-invalidates"
        pipeline_id = "pipe-single-image-invalidates"
        request = self._make_request()
        shot_one = self._make_shot()
        shot_two = Shot(
            shot_id="scene1_shot2",
            storyboard_description="Li Ming enters the room and looks toward the desk.",
            camera_setup=CameraSetup(shot_size="MS", camera_angle="Eye-level", movement="Slow Dolly in"),
            visual_elements=VisualElements(
                subject_and_clothing="Li Ming in a dark robe",
                action_and_expression="steps into the room and raises his gaze",
                environment_and_props="wooden room with a desk",
                lighting_and_color="soft overcast light",
            ),
            image_prompt="Medium shot. Li Ming enters the room and looks toward the desk.",
            final_video_prompt="Medium shot. Slow Dolly in. Li Ming steps toward the desk.",
        )

        storyboard_generation = {
            "pipeline_id": pipeline_id,
            "project_id": project_id,
            "story_id": story_id,
            "shots": [shot_one.model_dump(mode="json"), shot_two.model_dump(mode="json")],
            "generated_files": {
                "images": {
                    shot_one.shot_id: {"shot_id": shot_one.shot_id, "image_url": "/media/images/scene1_shot1_old.png"},
                    shot_two.shot_id: {"shot_id": shot_two.shot_id, "image_url": "/media/images/scene1_shot2.png"},
                },
                "videos": {
                    shot_one.shot_id: {"shot_id": shot_one.shot_id, "video_url": "/media/videos/scene1_shot1.mp4"},
                    shot_two.shot_id: {"shot_id": shot_two.shot_id, "video_url": "/media/videos/scene1_shot2.mp4"},
                },
                "transitions": {
                    f"transition_{shot_one.shot_id}__{shot_two.shot_id}": {
                        "transition_id": f"transition_{shot_one.shot_id}__{shot_two.shot_id}",
                        "from_shot_id": shot_one.shot_id,
                        "to_shot_id": shot_two.shot_id,
                        "video_url": "/media/videos/transition_scene1_shot1__scene1_shot2.mp4",
                    }
                },
                "timeline": [
                    {"item_type": "shot", "item_id": shot_one.shot_id},
                    {"item_type": "transition", "item_id": f"transition_{shot_one.shot_id}__{shot_two.shot_id}"},
                    {"item_type": "shot", "item_id": shot_two.shot_id},
                ],
            },
            "final_video_url": "/media/videos/final-old.mp4",
        }

        async with self.session_factory() as session:
            await repo.save_story(
                session,
                story_id,
                {
                    "idea": "idea",
                    "genre": "genre",
                    "tone": "tone",
                    "meta": {
                        "storyboard_generation": storyboard_generation,
                    },
                },
            )
            await repo.save_pipeline(
                session,
                pipeline_id,
                story_id,
                {
                    "status": PipelineStatus.RENDERING_VIDEO,
                    "progress": 85,
                    "current_step": "Videos ready",
                    "generated_files": {
                        "storyboard": {
                            "shots": [shot_one.model_dump(mode="json"), shot_two.model_dump(mode="json")],
                        },
                        **storyboard_generation["generated_files"],
                        "final_video_url": "/media/videos/final-old.mp4",
                    },
                },
            )

            with (
                patch(
                    "app.routers.image.prepare_story_context",
                    new=AsyncMock(
                        return_value=(
                            {"meta": {"storyboard_generation": storyboard_generation}},
                            None,
                        )
                    ),
                ),
                patch(
                    "app.routers.image.generate_images_batch",
                    new=AsyncMock(return_value=[{"shot_id": shot_one.shot_id, "image_url": "/media/images/scene1_shot1_new.png"}]),
                ),
            ):
                await generate_single_images(
                    project_id=project_id,
                    request=request,
                    body=ImageRequest(
                        shots=[shot_one.model_dump(mode="json")],
                        story_id=story_id,
                        pipeline_id=pipeline_id,
                    ),
                    image_config={"image_api_key": "image-key", "image_base_url": "https://image.example/v1"},
                    llm={
                        "provider": "openai",
                        "model": "gpt-test",
                        "api_key": "test-key",
                        "base_url": "https://example.com/v1",
                    },
                    db=session,
                )

            status_after_image = await get_status(
                project_id,
                pipeline_id=pipeline_id,
                story_id=story_id,
                db=session,
            )
            persisted_story = await repo.get_story(session, story_id)

        self.assertEqual(
            status_after_image.generated_files["images"][shot_one.shot_id]["image_url"],
            "/media/images/scene1_shot1_new.png",
        )
        self.assertEqual(
            status_after_image.generated_files["videos"],
            {shot_two.shot_id: {"shot_id": shot_two.shot_id, "video_url": "/media/videos/scene1_shot2.mp4"}},
        )
        self.assertEqual(status_after_image.generated_files["transitions"], {})
        self.assertNotIn("final_video_url", status_after_image.generated_files)
        self.assertEqual(persisted_story["meta"]["storyboard_generation"]["final_video_url"], "")

    async def test_manual_pipeline_state_preserves_existing_story_id(self):
        project_id = "manual-project"
        story_id = "story-preserved"
        pipeline_id = "pipe-preserved"

        async with self.session_factory() as session:
            await repo.save_pipeline(
                session,
                pipeline_id,
                story_id,
                {
                    "status": PipelineStatus.STORYBOARD,
                    "progress": 30,
                    "current_step": "Storyboard ready",
                    "generated_files": {"storyboard": {"shots": []}},
                },
            )

            pipeline = await _persist_manual_pipeline_state(
                session,
                project_id=project_id,
                pipeline_id=pipeline_id,
                story_id=project_id,
                updates={"progress": 60, "current_step": "Updated in place"},
                merge_generated_files=True,
            )
            persisted = await repo.get_pipeline(session, pipeline_id)

        self.assertEqual(pipeline["story_id"], story_id)
        self.assertEqual(persisted["story_id"], story_id)


class SingleAssetPersistenceIsolationTests(unittest.IsolatedAsyncioTestCase):
    def _make_request(self) -> Request:
        return Request({"type": "http", "headers": []})

    async def test_single_image_and_video_routes_share_story_context_prompt_contract(self):
        request = self._make_request()
        story = {
            "genre": "历史",
            "characters": [
                {
                    "id": "char_li_ming",
                    "name": "Li Ming",
                    "description": "young man, short black hair, wearing a dark blue robe.",
                }
            ],
            "character_images": {
                "char_li_ming": {
                    "image_url": "/media/characters/li_ming.png",
                    "character_id": "char_li_ming",
                    "character_name": "Li Ming",
                    "visual_dna": "young man, short black hair",
                }
            },
            "meta": {
                "character_appearance_cache": {
                    "char_li_ming": {
                        "body": "young man, short black hair",
                        "clothing": "dark blue robe",
                        "negative_prompt": "modern clothing",
                    }
                },
                "scene_style_cache": [
                    {
                        "keywords": ["teahouse"],
                        "image_extra": "jiangnan teahouse doorway, rain mist",
                        "video_extra": "jiangnan teahouse doorway, rain mist",
                        "negative_prompt": "cars",
                    }
                ],
                "scene_reference_assets": {
                    "ep01_scene01": {
                        "summary_environment": "jiangnan teahouse doorway",
                        "summary_visuals": ["wooden door frame", "warm lantern glow"],
                        "summary_lighting": "soft rainy daylight with lantern fill",
                        "variants": {
                            "scene": {
                                "image_url": "/media/episodes/ep01_scene01.png",
                                "image_path": "media/episodes/ep01_scene01.png",
                            }
                        },
                    }
                },
            },
        }
        shot = {
            "shot_id": "scene1_shot1",
            "source_scene_key": "ep01_scene01",
            "storyboard_description": "Li Ming pauses at the teahouse doorway.",
            "image_prompt": "Medium shot. Li Ming pauses at the teahouse doorway.",
            "final_video_prompt": "Medium shot. Static camera. Li Ming pushes the wooden door inward.",
            "image_url": "/media/images/scene1_shot1.png",
        }
        story_context = build_story_context(story)
        expected_payload = build_generation_payload(
            shot,
            story_context,
            art_style=get_art_style(request),
            story=story,
        )
        image_results = [{"shot_id": shot["shot_id"], "image_url": "/media/images/scene1_shot1.png"}]
        video_results = [{"shot_id": shot["shot_id"], "video_url": "/media/videos/scene1_shot1.mp4"}]

        with (
            patch("app.routers.image.prepare_story_context", new=AsyncMock(return_value=(story, story_context))),
            patch("app.routers.video.prepare_story_context", new=AsyncMock(return_value=(story, story_context))),
            patch("app.routers.image.generate_images_batch", new=AsyncMock(return_value=image_results)) as generate_images_batch,
            patch("app.routers.video.generate_videos_batch", new=AsyncMock(return_value=video_results)) as generate_videos_batch,
            patch("app.routers.image.persist_storyboard_generation_state", new=AsyncMock()),
            patch("app.routers.image.persist_generated_files_to_pipeline", new=AsyncMock()),
            patch("app.routers.video.persist_storyboard_generation_state", new=AsyncMock()),
            patch("app.routers.video.persist_generated_files_to_pipeline", new=AsyncMock()),
        ):
            image_response = await generate_single_images(
                project_id="project-1",
                request=request,
                body=ImageRequest(
                    shots=[{k: v for k, v in shot.items() if k != "image_url"}],
                    story_id="story-1",
                ),
                image_config={"image_api_key": "", "image_base_url": ""},
                llm={"provider": "openai", "model": "gpt-test", "api_key": "test-key", "base_url": ""},
                db=None,
            )
            video_response = await generate_single_videos(
                project_id="project-1",
                request=request,
                body=VideoRequest(
                    shots=[shot],
                    story_id="story-1",
                ),
                video_config={
                    "video_api_key": "video-key",
                    "video_base_url": "https://video.example/v1",
                    "video_provider": "dashscope",
                },
                llm={"provider": "openai", "model": "gpt-test", "api_key": "test-key", "base_url": ""},
                db=None,
            )

        self.assertEqual(image_response, image_results)
        self.assertEqual(video_response, video_results)

        image_payload = generate_images_batch.await_args.args[0][0]
        video_payload = generate_videos_batch.await_args.args[0][0]
        self.assertEqual(image_payload["image_prompt"], expected_payload["image_prompt"])
        self.assertEqual(image_payload["negative_prompt"], expected_payload["negative_prompt"])
        self.assertEqual(image_payload["reference_images"], expected_payload["reference_images"])
        self.assertEqual(video_payload["final_video_prompt"], expected_payload["final_video_prompt"])
        self.assertEqual(video_payload["negative_prompt"], expected_payload["negative_prompt"])
        self.assertEqual(video_payload["reference_images"], expected_payload["reference_images"])

    async def test_single_image_generation_returns_success_when_persistence_fails(self):
        results = [
            {
                "shot_id": "scene1_shot1",
                "image_path": "media/images/scene1_shot1.png",
                "image_url": "/media/images/scene1_shot1.png",
            }
        ]

        with (
            patch(
                "app.routers.image.prepare_story_context",
                new=AsyncMock(return_value=({"meta": {"storyboard_generation": {"pipeline_id": "pipe-1"}}}, None)),
            ),
            patch("app.routers.image.generate_images_batch", new=AsyncMock(return_value=results)) as generate_batch,
            patch(
                "app.routers.image.persist_storyboard_generation_state",
                new=AsyncMock(side_effect=RuntimeError("persist failed")),
            ),
            patch("app.routers.image.persist_generated_files_to_pipeline", new=AsyncMock()) as persist_pipeline,
        ):
            response = await generate_single_images(
                project_id="project-1",
                request=self._make_request(),
                body=ImageRequest(
                    shots=[{"shot_id": "scene1_shot1", "image_prompt": "Medium shot. Hero at doorway."}],
                    story_id="story-1",
                ),
                image_config={"image_api_key": "", "image_base_url": ""},
                llm={"provider": "openai", "model": "gpt-test", "api_key": "test-key", "base_url": ""},
                db=None,
            )

        self.assertEqual(response, results)
        self.assertEqual(generate_batch.await_count, 1)
        persist_pipeline.assert_awaited_once()
        self.assertEqual(persist_pipeline.await_args.kwargs["story_id"], "story-1")

    async def test_single_image_generation_fallback_keeps_explicit_pipeline_id(self):
        results = [
            {
                "shot_id": "scene1_shot1",
                "image_path": "media/images/scene1_shot1.png",
                "image_url": "/media/images/scene1_shot1.png",
            }
        ]

        with (
            patch(
                "app.routers.image.prepare_story_context",
                new=AsyncMock(side_effect=[({"meta": {}}, None), ({}, None)]),
            ),
            patch(
                "app.routers.image.build_generation_payload",
                side_effect=RuntimeError("payload build failed"),
            ),
            patch("app.routers.image.generate_images_batch", new=AsyncMock(return_value=results)),
            patch("app.routers.image.persist_storyboard_generation_state", new=AsyncMock()),
            patch("app.routers.image.persist_generated_files_to_pipeline", new=AsyncMock()) as persist_pipeline,
        ):
            response = await generate_single_images(
                project_id="project-1",
                request=self._make_request(),
                body=ImageRequest(
                    shots=[{"shot_id": "scene1_shot1", "image_prompt": "Medium shot. Hero at doorway."}],
                    story_id="story-1",
                    pipeline_id="pipe-explicit",
                ),
                image_config={"image_api_key": "", "image_base_url": ""},
                llm={"provider": "openai", "model": "gpt-test", "api_key": "test-key", "base_url": ""},
                db=None,
            )

        self.assertEqual(response, results)
        persist_pipeline.assert_awaited_once()
        self.assertEqual(persist_pipeline.await_args.kwargs["pipeline_id"], "pipe-explicit")

    async def test_single_image_generation_persists_to_pipeline_without_story_context(self):
        results = [
            {
                "shot_id": "scene1_shot1",
                "image_path": "media/images/scene1_shot1.png",
                "image_url": "/media/images/scene1_shot1.png",
            }
        ]

        with (
            patch("app.routers.image.generate_images_batch", new=AsyncMock(return_value=results)) as generate_batch,
            patch("app.routers.image.persist_storyboard_generation_state", new=AsyncMock()) as persist_storyboard,
            patch("app.routers.image.persist_generated_files_to_pipeline", new=AsyncMock()) as persist_pipeline,
            patch("app.routers.image.repo.get_pipeline", new=AsyncMock(return_value={"story_id": "story-from-pipeline"})),
        ):
            response = await generate_single_images(
                project_id="project-1",
                request=self._make_request(),
                body=ImageRequest(
                    shots=[{"shot_id": "scene1_shot1", "image_prompt": "Medium shot. Hero at doorway."}],
                    pipeline_id="pipe-1",
                ),
                image_config={"image_api_key": "", "image_base_url": ""},
                llm={"provider": "openai", "model": "gpt-test", "api_key": "test-key", "base_url": ""},
                db=None,
            )

        self.assertEqual(response, results)
        self.assertEqual(generate_batch.await_count, 1)
        persist_storyboard.assert_not_awaited()
        persist_pipeline.assert_awaited_once()
        self.assertEqual(persist_pipeline.await_args.kwargs["story_id"], "story-from-pipeline")

    async def test_single_tts_generation_returns_success_when_persistence_fails(self):
        results = [
            {
                "shot_id": "scene1_shot1",
                "audio_url": "/media/audio/scene1_shot1.mp3",
                "duration_seconds": 1.2,
            }
        ]

        with (
            patch("app.routers.tts.repo.get_story", new=AsyncMock(return_value={"meta": {"storyboard_generation": {"pipeline_id": "pipe-1"}}})),
            patch("app.routers.tts.generate_tts_batch", new=AsyncMock(return_value=results)) as generate_batch,
            patch(
                "app.routers.tts.persist_storyboard_generation_state",
                new=AsyncMock(side_effect=RuntimeError("persist failed")),
            ),
            patch("app.routers.tts.persist_generated_files_to_pipeline", new=AsyncMock()) as persist_pipeline,
        ):
            from app.routers.tts import TTSRequest, generate_audio

            response = await generate_audio(
                project_id="project-1",
                body=TTSRequest(
                    shots=[{"shot_id": "scene1_shot1", "dialogue": "你好"}],
                    story_id="story-1",
                ),
                db=None,
            )

        self.assertEqual(response, results)
        self.assertEqual(generate_batch.await_count, 1)
        persist_pipeline.assert_not_awaited()

    async def test_single_video_generation_persists_to_pipeline_without_story_context(self):
        results = [
            {
                "shot_id": "scene1_shot1",
                "video_url": "/media/videos/scene1_shot1.mp4",
            }
        ]

        with (
            patch("app.routers.video.generate_videos_batch", new=AsyncMock(return_value=results)) as generate_batch,
            patch("app.routers.video.persist_storyboard_generation_state", new=AsyncMock()) as persist_storyboard,
            patch("app.routers.video.persist_generated_files_to_pipeline", new=AsyncMock()) as persist_pipeline,
            patch("app.routers.video.repo.get_pipeline", new=AsyncMock(return_value={"story_id": "story-from-pipeline"})),
        ):
            response = await generate_single_videos(
                project_id="project-1",
                request=self._make_request(),
                body=VideoRequest(
                    shots=[{"shot_id": "scene1_shot1", "image_url": "/media/images/scene1_shot1.png", "final_video_prompt": "test"}],
                    pipeline_id="pipe-1",
                ),
                video_config={
                    "video_api_key": "video-key",
                    "video_base_url": "https://video.example/v1",
                    "video_provider": "dashscope",
                },
                llm={"provider": "openai", "model": "gpt-test", "api_key": "test-key", "base_url": ""},
                db=None,
            )

        self.assertEqual(response, results)
        self.assertEqual(generate_batch.await_count, 1)
        persist_storyboard.assert_not_awaited()
        persist_pipeline.assert_awaited_once()
        self.assertEqual(persist_pipeline.await_args.kwargs["story_id"], "story-from-pipeline")

    async def test_single_video_generation_uses_story_scene_reference_in_prompt(self):
        results = [
            {
                "shot_id": "scene1_shot1",
                "video_url": "/media/videos/scene1_shot1.mp4",
            }
        ]
        story = {
            "meta": {
                "scene_reference_assets": {
                    "ep01_scene01": {
                        "summary_environment": "office lobby with glass doors and reception desk",
                        "summary_visuals": ["glass doors", "reception desk"],
                        "summary_lighting": "soft office ceiling light",
                        "variants": {
                            "scene": {"image_url": "/media/episodes/office.png"}
                        },
                    }
                }
            }
        }

        with (
            patch("app.routers.video.prepare_story_context", new=AsyncMock(return_value=(story, None))),
            patch("app.routers.video.generate_videos_batch", new=AsyncMock(return_value=results)) as generate_batch,
            patch("app.routers.video.persist_storyboard_generation_state", new=AsyncMock()),
            patch("app.routers.video.persist_generated_files_to_pipeline", new=AsyncMock()),
        ):
            response = await generate_single_videos(
                project_id="project-1",
                request=self._make_request(),
                body=VideoRequest(
                    shots=[
                        {
                            "shot_id": "scene1_shot1",
                            "source_scene_key": "ep01_scene01",
                            "image_url": "/media/images/scene1_shot1.png",
                            "final_video_prompt": "Medium shot. Static camera. Li Ming steps forward.",
                        }
                    ],
                    story_id="story-1",
                ),
                video_config={
                    "video_api_key": "video-key",
                    "video_base_url": "https://video.example/v1",
                    "video_provider": "dashscope",
                },
                llm={"provider": "openai", "model": "gpt-test", "api_key": "test-key", "base_url": ""},
                db=None,
            )

        prepared_shot = generate_batch.await_args.args[0][0]
        self.assertEqual(response, results)
        self.assertIn("office lobby with glass doors and reception desk", prepared_shot["final_video_prompt"])

    async def test_single_video_generation_returns_success_when_persistence_fails(self):
        results = [
            {
                "shot_id": "scene1_shot1",
                "video_url": "/media/videos/scene1_shot1.mp4",
            }
        ]

        with (
            patch(
                "app.routers.video.prepare_story_context",
                new=AsyncMock(return_value=({"meta": {"storyboard_generation": {"pipeline_id": "pipe-1"}}}, None)),
            ),
            patch("app.routers.video.generate_videos_batch", new=AsyncMock(return_value=results)) as generate_batch,
            patch(
                "app.routers.video.persist_storyboard_generation_state",
                new=AsyncMock(side_effect=RuntimeError("story persist failed")),
            ) as persist_storyboard,
            patch(
                "app.routers.video.persist_generated_files_to_pipeline",
                new=AsyncMock(side_effect=RuntimeError("pipeline persist failed")),
            ) as persist_pipeline,
        ):
            response = await generate_single_videos(
                project_id="project-1",
                request=self._make_request(),
                body=VideoRequest(
                    shots=[{"shot_id": "scene1_shot1", "image_url": "/media/images/scene1_shot1.png", "final_video_prompt": "test"}],
                    story_id="story-1",
                ),
                video_config={
                    "video_api_key": "video-key",
                    "video_base_url": "https://video.example/v1",
                    "video_provider": "dashscope",
                },
                llm={"provider": "openai", "model": "gpt-test", "api_key": "test-key", "base_url": ""},
                db=None,
            )

        self.assertEqual(response, results)
        self.assertEqual(generate_batch.await_count, 1)
        persist_storyboard.assert_awaited_once()
        persist_pipeline.assert_awaited_once()
