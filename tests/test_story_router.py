import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.routers.story import (
    SceneReferenceGenerateRequest,
    api_generate_script,
    api_patch,
    generate_scene_reference,
    router,
)
from app.schemas.story import Character, GenerateScriptRequest, OutlineScene, PatchStoryRequest


async def _collect_stream(response) -> str:
    chunks: list[str] = []
    async for chunk in response.body_iterator:
        if isinstance(chunk, bytes):
            chunks.append(chunk.decode("utf-8"))
        else:
            chunks.append(str(chunk))
    return "".join(chunks)


class StoryRouterStreamTests(unittest.IsolatedAsyncioTestCase):
    def _make_request(self) -> Request:
        return Request({"type": "http", "headers": []})

    async def test_generate_script_saves_and_emits_done_only_on_success(self):
        async def fake_generate_script(*args, **kwargs):
            yield {"episode": 1, "title": "Ep1", "scenes": [{"scene_number": 1}]}
            yield {"__usage__": {"prompt_tokens": 10, "completion_tokens": 4}}

        save_story = AsyncMock()
        with (
            patch("app.routers.story.generate_script", new=fake_generate_script),
            patch("app.routers.story.repo.get_story", new=AsyncMock(return_value={"outline": [{"episode": 1, "title": "Ep1", "summary": "摘要"}]})),
            patch("app.routers.story.repo.save_story", new=save_story),
        ):
            response = await api_generate_script(
                GenerateScriptRequest(story_id="story-success"),
                self._make_request(),
                llm={"provider": "openai", "model": "gpt-test", "api_key": "test-key", "base_url": ""},
                db=None,
            )
            payload = await _collect_stream(response)

        save_story.assert_awaited_once_with(None, "story-success", {"scenes": [{"episode": 1, "title": "Ep1", "scenes": [{"scene_number": 1}]}]})
        self.assertIn("data: [DONE]", payload)
        self.assertNotIn("data: [ERROR]", payload)

    async def test_generate_script_does_not_save_partial_scenes_on_failure(self):
        async def fake_generate_script(*args, **kwargs):
            yield {"episode": 1, "title": "Ep1", "scenes": [{"scene_number": 1}]}
            raise RuntimeError("boom")

        save_story = AsyncMock()
        with (
            patch("app.routers.story.generate_script", new=fake_generate_script),
            patch("app.routers.story.repo.get_story", new=AsyncMock(return_value={"outline": [{"episode": 1, "title": "Ep1", "summary": "摘要"}]})),
            patch("app.routers.story.repo.save_story", new=save_story),
        ):
            response = await api_generate_script(
                GenerateScriptRequest(story_id="story-failure"),
                self._make_request(),
                llm={"provider": "openai", "model": "gpt-test", "api_key": "test-key", "base_url": ""},
                db=None,
            )
            payload = await _collect_stream(response)

        save_story.assert_not_awaited()
        self.assertIn("data: [ERROR] boom", payload)
        self.assertNotIn("data: [DONE]", payload)


class StoryRouterPatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_patch_persists_outline_and_invalidates_scene_style_cache(self):
        save_story = AsyncMock()
        invalidate_cache = AsyncMock()

        with (
            patch("app.routers.story.repo.save_story", new=save_story),
            patch("app.routers.story.repo.invalidate_story_consistency_cache", new=invalidate_cache),
        ):
            result = await api_patch(
                PatchStoryRequest(
                    story_id="story-patch-test",
                    outline=[{"episode": 1, "title": "新标题", "summary": "新摘要"}],
                ),
                db=None,
            )

        self.assertEqual(result, {"ok": True})
        save_story.assert_awaited_once_with(
            None,
            "story-patch-test",
            {
                "outline": [OutlineScene(episode=1, title="新标题", summary="新摘要")],
                "scenes": [],
            },
        )
        invalidate_cache.assert_awaited_once_with(
            None,
            "story-patch-test",
            appearance=False,
            scene_style=True,
        )

    async def test_patch_persists_characters_and_invalidates_appearance_cache(self):
        save_story = AsyncMock()
        invalidate_cache = AsyncMock()

        with (
            patch("app.routers.story.repo.save_story", new=save_story),
            patch("app.routers.story.repo.invalidate_story_consistency_cache", new=invalidate_cache),
        ):
            result = await api_patch(
                PatchStoryRequest(
                    story_id="story-patch-character-test",
                    characters=[{"id": "char_hero", "name": "林晓雨", "role": "女主角", "description": "新描述"}],
                ),
                db=None,
            )

        self.assertEqual(result, {"ok": True})
        save_story.assert_awaited_once_with(
            None,
            "story-patch-character-test",
            {
                "characters": [Character(id="char_hero", name="林晓雨", role="女主角", description="新描述")],
                "scenes": [],
            },
        )
        invalidate_cache.assert_awaited_once_with(
            None,
            "story-patch-character-test",
            appearance=True,
            scene_style=False,
        )


class StoryRouterStoryboardScriptTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(router)

        async def fake_db():
            yield None

        self.app.dependency_overrides[get_db] = fake_db
        self.client = TestClient(self.app)

        self.story = {
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

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def test_storyboard_script_route_accepts_boolean_selection_map(self):
        with patch("app.routers.story.repo.get_story", new=AsyncMock(return_value=self.story)):
            response = self.client.post(
                "/api/v1/story/story-1/storyboard-script",
                json={"selected_scenes": {"1": {"1": False, "2": True}}},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["story_id"], "story-1")
        self.assertIn("场景二环境", payload["script"])
        self.assertNotIn("场景一环境", payload["script"])

    def test_storyboard_script_route_accepts_list_selection_map(self):
        with patch("app.routers.story.repo.get_story", new=AsyncMock(return_value=self.story)):
            response = self.client.post(
                "/api/v1/story/story-2/storyboard-script",
                json={"selected_scenes": {"1": [2]}},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["story_id"], "story-2")
        self.assertIn("场景二环境", payload["script"])
        self.assertNotIn("场景一环境", payload["script"])

    def test_storyboard_script_route_does_not_422_for_unexpected_selected_scenes_shape(self):
        with patch("app.routers.story.repo.get_story", new=AsyncMock(return_value=self.story)):
            response = self.client.post(
                "/api/v1/story/story-3/storyboard-script",
                json={"selected_scenes": "invalid-shape"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["story_id"], "story-3")
        self.assertIn("场景一环境", payload["script"])
        self.assertIn("场景二环境", payload["script"])


class StoryRouterSceneReferenceTests(unittest.IsolatedAsyncioTestCase):
    def _make_request(self) -> Request:
        return Request({"type": "http", "headers": []})

    async def test_generate_scene_reference_force_regenerate_skips_reuse_assets(self):
        story = {
            "meta": {
                "episode_reference_assets": {
                    "ep01_env01": {
                        "status": "ready",
                        "affected_scene_keys": ["ep01_scene01"],
                        "reuse_signature": "sig-1",
                    }
                }
            }
        }
        save_story = AsyncMock()
        generate_reference = AsyncMock(return_value={"episode": 1, "groups": []})

        with (
            patch("app.routers.story.prepare_story_context", new=AsyncMock(return_value=(story, None))),
            patch("app.routers.story.get_art_style", return_value=""),
            patch("app.routers.story.generate_episode_scene_reference", new=generate_reference),
            patch("app.routers.story.repo.get_story", new=AsyncMock(return_value=story)),
            patch("app.routers.story.repo.save_story", new=save_story),
        ):
            result = await generate_scene_reference(
                "story-force",
                SceneReferenceGenerateRequest(episode=1, force_regenerate=True),
                self._make_request(),
                llm={"provider": "openai", "model": "gpt-test", "api_key": "test-key", "base_url": ""},
                image_config={},
                db=None,
            )

        self.assertEqual(result, {"episode": 1, "groups": []})
        self.assertEqual(generate_reference.await_args.kwargs["existing_assets"], [])
        save_story.assert_awaited_once()
        self.assertEqual(save_story.await_args.args[0], None)
        self.assertEqual(save_story.await_args.args[1], "story-force")
        payload = save_story.await_args.args[2]
        self.assertEqual(payload["meta"]["episode_reference_assets"], {})
        self.assertEqual(payload["meta"]["scene_reference_assets"], {})
