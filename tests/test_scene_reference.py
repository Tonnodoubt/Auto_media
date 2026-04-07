# ruff: noqa: RUF001

import unittest
from typing import Optional
from unittest.mock import AsyncMock, patch

from fastapi import Request
from fastapi import HTTPException
import httpx

from app.routers.story import SceneReferenceGenerateRequest, generate_scene_reference
from app.services.scene_reference import (
    SCENE_REFERENCE_IMAGE_TIMEOUT_SECONDS,
    build_episode_environment_prompts,
    generate_episode_scene_reference,
    group_episode_scenes_by_environment,
)


def _make_request(headers: Optional[list[tuple[bytes, bytes]]] = None) -> Request:
    return Request({"type": "http", "headers": headers or []})


class SceneReferencePromptTests(unittest.TestCase):
    def test_group_episode_scenes_by_environment_splits_different_locations(self):
        groups = group_episode_scenes_by_environment(
            1,
            [
                {"scene_number": 1, "environment": "古代王府回廊", "visual": "回廊地面反光，朱红立柱与灯笼形成主视觉"},
                {"scene_number": 2, "environment": "古代王府回廊", "visual": "回廊尽头可见庭院入口与湿润青石地面"},
                {"scene_number": 3, "environment": "地牢刑房", "visual": "潮湿石墙与铁链，只有顶部冷光照下"},
            ],
        )

        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0]["scene_numbers"], [1, 2])
        self.assertEqual(groups[1]["scene_numbers"], [3])

    def test_group_episode_scenes_by_environment_ignores_abstract_scene_noise(self):
        groups = group_episode_scenes_by_environment(
            1,
            [
                {
                    "scene_number": 1,
                    "environment": "王府回廊，雨后地面反光，气氛压抑",
                    "visual": "沈砚快步前行，神色紧绷，朱红立柱与灯笼在后方",
                },
                {
                    "scene_number": 2,
                    "environment": "王府回廊尽头，灯笼摇晃，宿命感逼近",
                    "visual": "宁微停下脚步回头看，湿润青石地面延伸到入口",
                },
                {
                    "scene_number": 3,
                    "environment": "地牢刑房，潮湿石墙与铁链，压迫感更强",
                    "visual": "人物被迫停住，顶部冷光照在牢门上",
                },
            ],
        )

        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0]["scene_numbers"], [1, 2])
        self.assertEqual(groups[1]["scene_numbers"], [3])

    def test_build_episode_environment_prompts_stays_environment_focused(self):
        prompts = build_episode_environment_prompts(
            [
                {
                    "scene_number": 1,
                    "environment": "古代王府回廊",
                    "visual": "男主站在回廊里，雨后的地面反光，朱红立柱与灯笼形成主视觉",
                    "lighting": "冷色天光混合暖色灯笼侧光",
                    "mood": "压抑克制",
                },
                {
                    "scene_number": 2,
                    "environment": "古代王府回廊",
                    "visual": "女主从回廊尽头回头，庭院入口与湿润青石地面清晰可见",
                    "lighting": "冷色天光混合暖色灯笼侧光",
                    "mood": "压抑克制",
                },
            ],
            story_context=None,
            art_style="电影级写实",
        )

        self.assertEqual(set(prompts.keys()), {"scene"})
        self.assertIn("Environment only", prompts["scene"]["prompt"])
        self.assertIn("One clean master environment reference image", prompts["scene"]["prompt"])
        self.assertIn("电影级写实", prompts["scene"]["prompt"])
        self.assertIn("No characters", prompts["scene"]["prompt"])
        self.assertNotIn("男主", prompts["scene"]["prompt"])
        self.assertNotIn("女主", prompts["scene"]["prompt"])
        self.assertIn("foreground hero", prompts["scene"]["negative_prompt"])
        self.assertIn("person", prompts["scene"]["negative_prompt"])
        self.assertIn("costume", prompts["scene"]["negative_prompt"])
        self.assertIn("split composition", prompts["scene"]["negative_prompt"])

    def test_build_episode_environment_prompts_preserves_specific_environment_description(self):
        prompts = build_episode_environment_prompts(
            [
                {
                    "scene_number": 1,
                    "environment": "夜晚，孤儿院宿舍内。房间简陋但整洁，一张木床靠墙放置，窗外月光洒入。",
                    "visual": "林浩从床上惊醒，视线扫过木床、旧书桌和窗边。",
                    "lighting": "冷白色月光从窗户左侧照射进来，室内角落部分被阴影覆盖。",
                    "mood": "平静转为惊讶",
                }
            ],
            story_context=None,
            art_style="写实摄影风格",
        )

        self.assertIn("一张木床靠墙放置", prompts["scene"]["prompt"])
        self.assertIn("Do not replace this with a generic room", prompts["scene"]["prompt"])


class SceneReferenceRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_episode_scene_reference_uses_extended_timeout(self):
        story = {
            "id": "story-scene-ref-timeout-window",
            "meta": {},
            "scenes": [
                {
                    "episode": 1,
                    "title": "第一集",
                    "scenes": [
                        {"scene_number": 1, "environment": "庭院", "visual": "雨夜庭院"},
                    ],
                }
            ],
        }

        with patch(
            "app.services.scene_reference.generate_image",
            new=AsyncMock(
                return_value={
                    "shot_id": "ep01_env01_scene",
                    "image_url": "/media/episodes/scene-1.png",
                    "image_path": "media/episodes/scene-1.png",
                }
            ),
        ) as generate_mock:
            await generate_episode_scene_reference(
                story,
                story_context=None,
                episode=1,
            )

        self.assertEqual(generate_mock.await_args.kwargs["timeout_seconds"], SCENE_REFERENCE_IMAGE_TIMEOUT_SECONDS)

    async def test_generate_episode_scene_reference_converts_timeout_to_gateway_timeout(self):
        story = {
            "id": "story-scene-ref-timeout",
            "meta": {},
            "scenes": [
                {
                    "episode": 1,
                    "title": "第一集",
                    "scenes": [
                        {"scene_number": 1, "environment": "庭院", "visual": "雨夜庭院"},
                    ],
                }
            ],
        }

        with patch(
            "app.services.scene_reference.generate_image",
            new=AsyncMock(side_effect=httpx.ReadTimeout("timed out")),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await generate_episode_scene_reference(
                    story,
                    story_context=None,
                    episode=1,
                )

        self.assertEqual(ctx.exception.status_code, 504)
        self.assertIn("环境图生成超时", ctx.exception.detail)

    async def test_generate_episode_scene_reference_converts_wrapped_timeout_to_gateway_timeout(self):
        story = {
            "id": "story-scene-ref-timeout-wrapped",
            "meta": {},
            "scenes": [
                {
                    "episode": 1,
                    "title": "Episode 1",
                    "scenes": [
                        {"scene_number": 1, "environment": "courtyard", "visual": "rainy courtyard at night"},
                    ],
                }
            ],
        }

        async def _raise_wrapped_timeout(*args, **kwargs):
            try:
                raise httpx.ReadTimeout("timed out")
            except httpx.TimeoutException as exc:
                raise RuntimeError("wrapped image timeout") from exc

        with patch(
            "app.services.scene_reference.generate_image",
            new=AsyncMock(side_effect=_raise_wrapped_timeout),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await generate_episode_scene_reference(
                    story,
                    story_context=None,
                    episode=1,
                )

        self.assertEqual(ctx.exception.status_code, 504)
        self.assertIn("环境图生成超时", ctx.exception.detail)

    async def test_generate_episode_scene_reference_reuses_existing_asset_for_minor_scene_tweaks(self):
        story = {
            "id": "story-scene-ref-reuse",
            "meta": {},
            "scenes": [
                {
                    "episode": 1,
                    "title": "第一集",
                    "scenes": [
                        {
                            "scene_number": 1,
                            "environment": "王府回廊，雨后地面反光，气氛压抑",
                            "visual": "沈砚快步前行，朱红立柱与灯笼在背景里",
                        },
                        {
                            "scene_number": 2,
                            "environment": "王府回廊尽头，灯笼摇晃，宿命感逼近",
                            "visual": "宁微停下脚步回头看，湿润青石地面延伸到入口",
                        },
                    ],
                }
            ],
        }
        existing_assets = [
            {
                "status": "ready",
                "variants": {
                    "scene": {"prompt": "scene-old", "image_url": "/media/episodes/scene-old.png", "image_path": "media/episodes/scene-old.png"},
                },
                "summary_environment": "王府回廊",
                "summary_visuals": ["朱红立柱", "灯笼", "青石地面"],
                "affected_scene_keys": ["ep01_scene01", "ep01_scene02"],
            }
        ]

        with patch("app.services.scene_reference.generate_image", new=AsyncMock()) as generate_mock:
            result = await generate_episode_scene_reference(
                story,
                story_context=None,
                episode=1,
                existing_assets=existing_assets,
            )

        self.assertEqual(len(result["groups"]), 1)
        asset = result["groups"][0]["asset"]
        self.assertEqual(asset["variants"]["scene"]["image_url"], "/media/episodes/scene-old.png")
        self.assertEqual(asset["affected_scene_numbers"], [1, 2])
        generate_mock.assert_not_awaited()

    async def test_generate_episode_scene_reference_persists_prompt_quality(self):
        story = {
            "id": "story-scene-ref-quality",
            "meta": {},
            "scenes": [
                {
                    "episode": 1,
                    "title": "第一集",
                    "scenes": [
                        {"scene_number": 1, "environment": "庭院", "visual": "雨夜庭院"},
                    ],
                }
            ],
        }
        quality_payload = {
            "enabled": True,
            "family": "scene_reference_prompt",
            "final_passed": True,
        }

        with (
            patch(
                "app.services.scene_reference.resolve_default_quality_llm_config",
                return_value=("claude", "demo-model", "quality-key", "https://llm.example.com"),
            ),
            patch(
                "app.services.scene_reference.run_quality_guarded_prompt_payload",
                new=AsyncMock(
                    return_value=(
                        {
                            "prompt": "guarded scene reference prompt",
                            "negative_prompt": "guarded scene negative",
                        },
                        quality_payload,
                    )
                ),
            ),
            patch(
                "app.services.scene_reference.generate_image",
                new=AsyncMock(
                    return_value={
                        "shot_id": "ep01_env01_scene",
                        "image_url": "/media/episodes/scene-quality.png",
                        "image_path": "media/episodes/scene-quality.png",
                    }
                ),
            ) as generate_mock,
        ):
            result = await generate_episode_scene_reference(
                story,
                story_context=None,
                episode=1,
            )

        variant = result["groups"][0]["asset"]["variants"]["scene"]
        self.assertEqual(variant["prompt"], "guarded scene reference prompt")
        self.assertEqual(variant["quality"], quality_payload)
        self.assertEqual(generate_mock.await_args.args[0], "guarded scene reference prompt")
        self.assertEqual(generate_mock.await_args.kwargs["negative_prompt"], "guarded scene negative")

    async def test_generate_episode_scene_reference_binds_group_context_for_prompt_builders(self):
        story = {
            "id": "story-scene-ref-builder-binding",
            "meta": {},
            "scenes": [
                {
                    "episode": 1,
                    "title": "第一集",
                    "scenes": [
                        {"scene_number": 1, "environment": "庭院", "visual": "雨夜庭院，青石地面与廊灯"},
                        {"scene_number": 2, "environment": "书房", "visual": "烛火书房，书架与木桌"},
                    ],
                }
            ],
        }
        captured_builders = []

        async def fake_run_quality_guarded_prompt_payload(*, base_payload_builder, **_kwargs):
            captured_builders.append(base_payload_builder)
            return (
                {
                    "prompt": "guarded scene reference prompt",
                    "negative_prompt": "guarded scene negative",
                },
                {"enabled": True, "family": "scene_reference_prompt"},
            )

        with (
            patch(
                "app.services.scene_reference.resolve_default_quality_llm_config",
                return_value=("claude", "demo-model", "quality-key", "https://llm.example.com"),
            ),
            patch(
                "app.services.scene_reference.run_quality_guarded_prompt_payload",
                new=AsyncMock(side_effect=fake_run_quality_guarded_prompt_payload),
            ),
            patch(
                "app.services.scene_reference.generate_image",
                new=AsyncMock(
                    return_value={
                        "shot_id": "ep01_env_scene",
                        "image_url": "/media/episodes/scene-quality.png",
                        "image_path": "media/episodes/scene-quality.png",
                    }
                ),
            ),
        ):
            await generate_episode_scene_reference(
                story,
                story_context=None,
                episode=1,
            )

        self.assertEqual(len(captured_builders), 2)
        built_payloads = [builder() for builder in captured_builders]
        self.assertEqual(built_payloads[0]["environment_pack_key"], "ep01_env01")
        self.assertEqual(built_payloads[1]["environment_pack_key"], "ep01_env02")
        self.assertEqual(built_payloads[0]["group_label"], "环境组 1")
        self.assertEqual(built_payloads[1]["group_label"], "环境组 2")
        self.assertEqual(built_payloads[0]["summary_environment"], "庭院")
        self.assertEqual(built_payloads[1]["summary_environment"], "书房")

    async def test_generate_scene_reference_persists_episode_and_scene_assets(self):
        story = {
            "id": "story-scene-ref",
            "meta": {},
            "scenes": [
                {
                    "episode": 1,
                    "title": "第一集",
                    "scenes": [
                        {"scene_number": 1, "environment": "庭院", "visual": "雨夜庭院"},
                        {"scene_number": 2, "environment": "书房", "visual": "烛火书房"},
                    ],
                }
            ],
        }
        result_payload = {
            "episode": 1,
            "groups": [
                {
                    "environment_pack_key": "ep01_env01",
                    "affected_scene_keys": ["ep01_scene01"],
                    "asset": {
                        "status": "ready",
                        "variants": {
                            "scene": {"prompt": "scene-1", "image_url": "/media/episodes/scene-1.png", "image_path": "media/episodes/scene-1.png"},
                        },
                        "environment_pack_key": "ep01_env01",
                        "group_index": 1,
                        "group_label": "环境组 1",
                        "affected_scene_keys": ["ep01_scene01"],
                        "affected_scene_numbers": [1],
                        "updated_at": "2026-03-27T12:00:00+00:00",
                        "error": "",
                    },
                },
                {
                    "environment_pack_key": "ep01_env02",
                    "affected_scene_keys": ["ep01_scene02"],
                    "asset": {
                        "status": "ready",
                        "variants": {
                            "scene": {"prompt": "scene-2", "image_url": "/media/episodes/scene-2.png", "image_path": "media/episodes/scene-2.png"},
                        },
                        "environment_pack_key": "ep01_env02",
                        "group_index": 2,
                        "group_label": "环境组 2",
                        "affected_scene_keys": ["ep01_scene02"],
                        "affected_scene_numbers": [2],
                        "updated_at": "2026-03-27T12:00:00+00:00",
                        "error": "",
                    },
                },
            ],
        }

        save_story = AsyncMock()
        with (
            patch("app.routers.story.prepare_story_context", new=AsyncMock(return_value=(story, None))),
            patch("app.routers.story.generate_episode_scene_reference", new=AsyncMock(return_value=result_payload)),
            patch("app.routers.story.repo.get_story", new=AsyncMock(return_value=story)),
            patch("app.routers.story.repo.save_story", new=save_story),
        ):
            response = await generate_scene_reference(
                "story-scene-ref",
                SceneReferenceGenerateRequest(episode=1),
                _make_request(),
                llm={"provider": "claude", "model": "demo", "api_key": "key", "base_url": ""},
                image_config={"image_api_key": "img-key", "image_base_url": "https://example.com"},
                db=None,
            )

        self.assertEqual(response, result_payload)
        save_story.assert_awaited_once()
        saved_meta = save_story.await_args.args[2]["meta"]
        self.assertIn("episode_reference_assets", saved_meta)
        self.assertIn("scene_reference_assets", saved_meta)
        self.assertIn("ep01_env01", saved_meta["episode_reference_assets"])
        self.assertIn("ep01_env02", saved_meta["episode_reference_assets"])
        self.assertIn("ep01_scene01", saved_meta["scene_reference_assets"])
        self.assertIn("ep01_scene02", saved_meta["scene_reference_assets"])

    async def test_generate_scene_reference_reuses_existing_asset_without_regeneration(self):
        story = {
            "id": "story-existing-scene-ref",
            "meta": {
                "episode_reference_assets": {
                    "ep01_env01": {
                        "status": "ready",
                        "affected_scene_keys": ["ep01_scene01"],
                        "variants": {
                            "scene": {"image_url": "/media/episodes/scene-existing.png"},
                        },
                    }
                }
            },
            "scenes": [
                {
                    "episode": 1,
                    "title": "第一集",
                    "scenes": [{"scene_number": 1, "environment": "庭院", "visual": "雨夜庭院"}],
                }
            ],
        }
        result_payload = {
            "episode": 1,
            "groups": [
                {
                    "environment_pack_key": "ep01_env01",
                    "affected_scene_keys": ["ep01_scene01"],
                    "asset": {
                        "status": "ready",
                        "variants": {
                            "scene": {"image_url": "/media/episodes/scene-existing.png"},
                        },
                        "environment_pack_key": "ep01_env01",
                        "affected_scene_keys": ["ep01_scene01"],
                        "affected_scene_numbers": [1],
                        "error": "",
                    },
                }
            ],
        }

        with (
            patch("app.routers.story.prepare_story_context", new=AsyncMock(return_value=(story, None))),
            patch("app.routers.story.generate_episode_scene_reference", new=AsyncMock(return_value=result_payload)) as generate_mock,
            patch("app.routers.story.repo.get_story", new=AsyncMock(return_value=story)),
            patch("app.routers.story.repo.save_story", new=AsyncMock()) as save_story,
        ):
            response = await generate_scene_reference(
                "story-existing-scene-ref",
                SceneReferenceGenerateRequest(episode=1),
                _make_request(),
                llm={"provider": "claude", "model": "demo", "api_key": "key", "base_url": ""},
                image_config={"image_api_key": "img-key", "image_base_url": "https://example.com"},
                db=None,
            )

        self.assertEqual(len(response["groups"]), 1)
        self.assertEqual(response["groups"][0]["environment_pack_key"], "ep01_env01")
        self.assertEqual(response["groups"][0]["asset"]["status"], "ready")
        generate_mock.assert_awaited_once()
        self.assertEqual(generate_mock.await_args.kwargs["existing_assets"][0]["affected_scene_keys"], ["ep01_scene01"])
        save_story.assert_awaited_once()
