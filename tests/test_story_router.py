import unittest
from unittest.mock import AsyncMock, patch

from fastapi import Request

from app.routers.story import api_generate_script, api_patch
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
