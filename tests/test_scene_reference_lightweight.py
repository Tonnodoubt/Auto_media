import sys
import types
import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import patch


def _load_scene_reference_module():
    module_path = Path(__file__).resolve().parents[1] / "app" / "services" / "scene_reference.py"
    spec = spec_from_file_location("scene_reference_lightweight_module", module_path)
    assert spec and spec.loader

    api_keys_module = types.ModuleType("app.core.api_keys")
    api_keys_module.inject_art_style = lambda prompt, art_style: prompt

    story_context_module = types.ModuleType("app.core.story_context")

    class StoryContext:  # pragma: no cover - stub for import only
        pass

    story_context_module.StoryContext = StoryContext

    image_module = types.ModuleType("app.services.image")
    image_module.DEFAULT_MODEL = "test-image-model"
    image_module.EPISODE_DIR = "episodes"

    async def generate_image(*args, **kwargs):  # pragma: no cover - should not be called here
        raise AssertionError("generate_image should not be called in lightweight scene reference tests")

    image_module.generate_image = generate_image

    with patch.dict(
        sys.modules,
        {
            "app.core.api_keys": api_keys_module,
            "app.core.story_context": story_context_module,
            "app.services.image": image_module,
        },
    ):
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


_scene_reference_module = _load_scene_reference_module()
group_episode_scenes_by_environment = _scene_reference_module.group_episode_scenes_by_environment


class SceneReferenceLightweightTests(unittest.TestCase):
    def test_environment_anchor_groups_variant_environment_copy_together(self):
        groups = group_episode_scenes_by_environment(
            1,
            [
                {
                    "scene_number": 1,
                    "scene_heading": "[夜] [室内] [王府回廊]",
                    "environment_anchor": "王府回廊",
                    "environment": "夜晚的王府回廊，朱红立柱、青石地面和灯笼沿线展开。",
                    "visual": "沈砚沿着回廊快步向前。",
                },
                {
                    "scene_number": 2,
                    "scene_heading": "[夜] [室内] [王府回廊尽头]",
                    "environment_anchor": "王府回廊",
                    "environment": "回廊尽头靠近庭院入口，湿润青石地面反光，灯笼轻晃。",
                    "visual": "宁微在入口附近停下回头。",
                },
            ],
        )

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["scene_numbers"], [1, 2])
        self.assertEqual(groups[0]["summary_environment"], "王府回廊")


if __name__ == "__main__":
    unittest.main()
