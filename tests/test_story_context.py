import unittest
from unittest.mock import patch

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.core.story_assets import (
    build_character_asset_record,
    get_character_design_prompt,
    get_character_visual_dna,
    get_scene_reference_asset,
)
from app.core.story_context import _GENRE_STYLE_RULES, build_generation_payload, build_story_context, character_appears_in_shot, infer_shot_view_hint
from app.models.story import Story
from app.schemas.storyboard import AudioReference, CameraSetup, Shot, VisualElements
from app.services import story_context_service
from app.services import story_repository as repo
from app.routers.image import _build_basic_payload
from app.services.story_context_service import (
    APPEARANCE_CACHE_SCHEMA_VERSION,
    SCENE_STYLE_CACHE_SCHEMA_VERSION,
    _parse_json,
    prepare_story_context,
)
from app.services.storyboard import _build_scene_mapping, parse_script_to_storyboard


class StoryContextTests(unittest.TestCase):
    def test_scene_mapping_accepts_finalize_heading_format(self):
        mapping = _build_scene_mapping(
            "# 第1集 雨夜来客\n"
            "## 场景1\n"
            "【环境】江南茶馆门口\n"
            "## 场景2\n"
            "【环境】茶馆内堂\n"
        )

        self.assertEqual(
            mapping,
            {
                1: "ep01_scene01",
                2: "ep01_scene02",
            },
        )

    def test_build_generation_payload_injects_scene_reference_and_dual_images(self):
        story = {
            "art_style": "cinematic watercolor",
            "characters": [
                {
                    "id": "char_li_ming",
                    "name": "Li Ming",
                    "role": "lead",
                    "description": "young man, short black hair, wearing a dark blue robe.",
                }
            ],
            "character_images": {
                "char_li_ming": {
                    "image_url": "/media/characters/li_ming.png",
                    "image_path": "media/characters/li_ming.png",
                    "visual_dna": "young man, short black hair",
                    "character_id": "char_li_ming",
                    "character_name": "Li Ming",
                }
            },
            "meta": {
                "scene_reference_assets": {
                    "ep01_scene01": {
                        "summary_environment": "jiangnan teahouse doorway",
                        "summary_visuals": ["wet stone threshold", "wooden door frame", "warm lantern glow"],
                        "summary_lighting": "soft rainy daylight with warm lantern fill",
                        "variants": {
                            "scene": {
                                "image_url": "/media/episodes/ep01_env01_scene.png",
                                "image_path": "media/episodes/ep01_env01_scene.png",
                            }
                        },
                    }
                }
            },
        }
        shot = {
            "shot_id": "scene1_shot1",
            "source_scene_key": "ep01_scene01",
            "storyboard_description": "李明站在茶馆门口。",
            "image_prompt": "Medium shot. Li Ming pauses at the teahouse doorway.",
            "final_video_prompt": "Medium shot. Static camera. Li Ming pushes the door inward.",
        }

        payload = build_generation_payload(shot, build_story_context(story), story=story)

        self.assertEqual(payload["source_scene_key"], "ep01_scene01")
        self.assertIn("Treat the linked scene reference image as environment canon", payload["image_prompt"])
        self.assertIn("Match the linked environment layout", payload["image_prompt"])
        self.assertIn("jiangnan teahouse doorway", payload["image_prompt"])
        self.assertIn("Treat the linked scene reference image as environment canon", payload["final_video_prompt"])
        self.assertIn("Match the linked environment layout", payload["final_video_prompt"])
        self.assertIn("jiangnan teahouse doorway", payload["final_video_prompt"])
        self.assertIn("wrong location layout", payload["negative_prompt"])
        self.assertEqual(len(payload["reference_images"]), 2)
        self.assertEqual(payload["reference_images"][0]["kind"], "character")
        self.assertEqual(payload["reference_images"][1]["kind"], "scene")
        self.assertGreater(payload["reference_images"][1]["weight"], 0.4)

    def test_build_story_context_uses_character_design_prompt_to_lock_headwear(self):
        story = {
            "characters": [
                {
                    "id": "char_li_ming",
                    "name": "Li Ming",
                    "description": "young man with calm expression.",
                }
            ],
            "character_images": {
                "char_li_ming": {
                    "design_prompt": (
                        "Standard three-view character turnaround sheet for Li Ming, protagonist, determined expression, "
                        "character description: young man, short black hair, wearing a dark blue robe, black bamboo hat, leather belt, "
                        "show front view, side profile, and back view of the same character on one sheet"
                    )
                }
            },
        }
        shot = {
            "shot_id": "scene1_shot1",
            "storyboard_description": "Li Ming waits by the doorway.",
            "image_prompt": "Medium shot. Li Ming waits by the doorway.",
            "final_video_prompt": "Medium shot. Static camera. Li Ming looks toward the courtyard.",
        }

        ctx = build_story_context(story)
        payload = build_generation_payload(shot, ctx, story=story)

        self.assertIn("black bamboo hat", ctx.clean_character_section)
        self.assertIn("dark blue robe", payload["image_prompt"])
        self.assertIn("black bamboo hat", payload["image_prompt"])
        self.assertIn("signature accessories", payload["image_prompt"])

    def test_build_generation_payload_adds_video_execution_guidance_for_identity_and_motion(self):
        story = {
            "characters": [
                {
                    "id": "char_li_ming",
                    "name": "Li Ming",
                    "description": "young man, short black hair, wearing a dark blue robe.",
                }
            ]
        }
        shot = {
            "shot_id": "scene1_shot1",
            "characters": ["Li Ming"],
            "storyboard_description": "Li Ming pauses at the doorway, then steps into the room.",
            "camera_setup": {"shot_size": "MS", "camera_angle": "Eye-level", "movement": "Slow Dolly in"},
            "image_prompt": "Medium shot. Li Ming pauses at the doorway.",
            "final_video_prompt": "Medium shot. Slow Dolly in. Li Ming steps into the room.",
        }

        payload = build_generation_payload(shot, build_story_context(story), story=story)

        self.assertIn("Keep the same face, hairstyle, primary outfit silhouette", payload["final_video_prompt"])
        self.assertIn("Make the camera move clearly readable and smooth", payload["final_video_prompt"])

    def test_scene_reference_prompt_uses_chinese_anchor_for_cjk_shot(self):
        story = {
            "meta": {
                "scene_reference_assets": {
                    "ep01_scene01": {
                        "summary_environment": "江南茶馆门口",
                        "summary_visuals": ["木门", "灯笼", "青石门槛"],
                        "summary_lighting": "雨后天光混合暖色灯笼补光",
                        "variants": {
                            "scene": {
                                "image_url": "/media/episodes/ep01_env01_scene.png",
                                "image_path": "media/episodes/ep01_env01_scene.png",
                            }
                        },
                    }
                }
            }
        }
        shot = {
            "shot_id": "scene1_shot1",
            "source_scene_key": "ep01_scene01",
            "storyboard_description": "李明站在茶馆门口。",
            "image_prompt": "中景，李明停在茶馆门口。",
            "final_video_prompt": "中景固定镜头，李明推门进入茶馆。",
        }

        payload = build_generation_payload(shot, None, story=story)

        self.assertIn("把关联场景参考图当作当前镜头的环境基准", payload["image_prompt"])
        self.assertIn("保持命中的环境布局", payload["image_prompt"])

    def test_build_generation_payload_keeps_multiple_character_reference_images(self):
        story = {
            "characters": [
                {
                    "id": "char_li_ming",
                    "name": "Li Ming",
                    "description": "young man, short black hair, wearing a dark blue robe.",
                },
                {
                    "id": "char_boss_zhao",
                    "name": "Boss Zhao",
                    "description": "middle-aged man, moustache, wearing a brown brocade robe.",
                },
            ],
            "character_images": {
                "char_li_ming": {
                    "image_url": "/media/characters/li_ming.png",
                    "image_path": "media/characters/li_ming.png",
                },
                "char_boss_zhao": {
                    "image_url": "/media/characters/boss_zhao.png",
                    "image_path": "media/characters/boss_zhao.png",
                },
            },
            "meta": {
                "scene_reference_assets": {
                    "ep01_scene01": {
                        "status": "ready",
                        "variants": {
                            "scene": {
                                "image_url": "/media/episodes/teahouse.png",
                                "image_path": "media/episodes/teahouse.png",
                            }
                        },
                    }
                }
            },
        }
        shot = {
            "shot_id": "scene1_shot1",
            "source_scene_key": "ep01_scene01",
            "characters": [{"name": "Li Ming"}, {"name": "Boss Zhao"}],
            "image_prompt": "Medium shot. Li Ming faces Boss Zhao across the teahouse counter.",
            "final_video_prompt": "Medium shot. Static camera. Li Ming speaks while Boss Zhao listens across the counter.",
        }

        payload = build_generation_payload(shot, build_story_context(story), story=story)

        self.assertEqual(len(payload["reference_images"]), 3)
        self.assertEqual(payload["reference_images"][0]["kind"], "character")
        self.assertEqual(payload["reference_images"][1]["kind"], "character")
        self.assertEqual(payload["reference_images"][2]["kind"], "scene")

    def test_get_scene_reference_asset_fallback_respects_episode_token(self):
        story = {
            "meta": {
                "scene_reference_assets": {
                    "ep01_scene01": {
                        "status": "ready",
                        "variants": {"scene": {"image_url": "/media/episodes/ep01_scene01.png"}},
                    },
                    "ep02_scene01": {
                        "status": "ready",
                        "variants": {"scene": {"image_url": "/media/episodes/ep02_scene01.png"}},
                    },
                }
            }
        }

        asset = get_scene_reference_asset(
            story,
            "ep02_scene01_variant",
            shot_id="scene1_shot1",
        )

        self.assertEqual(asset["variants"]["scene"]["image_url"], "/media/episodes/ep02_scene01.png")

    def test_build_generation_payload_preserves_explicit_reference_images(self):
        story = {
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
                        "status": "ready",
                        "variants": {
                            "scene": {
                                "image_url": "/media/episodes/ep01_env01_scene.png",
                                "image_path": "media/episodes/ep01_env01_scene.png",
                            }
                        },
                    }
                }
            },
        }
        shot = {
            "shot_id": "scene1_shot1",
            "source_scene_key": "ep01_scene01",
            "image_prompt": "Medium shot. Li Ming pauses at the teahouse doorway.",
            "final_video_prompt": "Medium shot. Static camera. Li Ming pushes the door inward.",
            "reference_images": [
                {"kind": "custom", "image_url": "/media/images/custom.png"},
                {"kind": "scene", "image_url": "/media/episodes/ep01_env01_scene.png"},
            ],
        }

        payload = build_generation_payload(shot, build_story_context(story), story=story)

        self.assertEqual(len(payload["reference_images"]), 3)
        self.assertEqual(payload["reference_images"][0]["kind"], "custom")
        self.assertEqual(payload["reference_images"][1]["kind"], "scene")
        self.assertEqual(payload["reference_images"][2]["kind"], "character")

    def test_build_story_context_and_payload_preserve_split_prompts(self):
        story = {
            "art_style": "cinematic watercolor",
            "genre": "古风",
            "selected_setting": "江南水乡，临河茶馆，细雨薄雾，木窗与灯笼营造出潮湿古镇气息。",
            "characters": [
                {
                    "id": "char_li_ming",
                    "name": "李明",
                    "role": "主角",
                    "description": "25岁青年男子，黑色短发，身形清瘦，穿着深蓝长衫，神情沉稳。",
                }
            ],
            "character_images": {
                "char_li_ming": {
                    "prompt": "Character portrait of 李明, clean background, studio lighting, dramatic portrait",
                    "visual_dna": "25-year-old man, short black hair, slim build",
                    "character_id": "char_li_ming",
                    "character_name": "李明",
                }
            },
            "meta": {
                "scene_style_cache": [
                    {
                        "keywords": [],
                        "image_extra": "jiangnan river town, wet stone paths, warm lantern glow",
                        "video_extra": "jiangnan river town, warm lantern glow, wet stone paths",
                    }
                ]
            },
        }
        shot = Shot(
            shot_id="scene1_shot1",
            storyboard_description="李明站在茶馆门口，准备推门进入。",
            camera_setup=CameraSetup(shot_size="MS", camera_angle="Eye-level", movement="Static"),
            visual_elements=VisualElements(
                subject_and_clothing="李明穿着深蓝长衫，站在门口",
                action_and_expression="右手抬起准备推门，目光看向屋内",
                environment_and_props="临河茶馆木门、雨雾和灯笼",
                lighting_and_color="柔和阴天自然光，暖色灯笼补光",
            ),
            image_prompt="Medium shot. Li Ming in a dark blue robe pauses at the teahouse doorway, hand lifted toward the wooden door. River-town rain mist and lanterns frame the still composition.",
            final_video_prompt="Medium shot. Static camera. Li Ming pushes the wooden door inward and steps into the teahouse. Rain mist and lantern glow stay stable around the entrance.",
            last_frame_prompt="Medium shot. Li Ming has just entered the teahouse, one hand still on the opened wooden door, lantern glow behind him.",
            audio_reference=AudioReference(type="dialogue", content="到了。"),
        )

        ctx = build_story_context(story)
        payload = build_generation_payload(shot, ctx)

        self.assertIn("Visual DNA", ctx.clean_character_section)
        self.assertNotIn("studio lighting", ctx.clean_character_section.lower())
        self.assertIn("Maintain consistent appearance:", payload["image_prompt"])
        self.assertIn("Li Ming pushes the wooden door inward", payload["final_video_prompt"])
        self.assertIn("cinematic watercolor", payload["image_prompt"])
        self.assertIn("cinematic watercolor", payload["final_video_prompt"])
        self.assertIn("jiangnan river town", payload["image_prompt"])
        self.assertNotIn("江南水乡", payload["image_prompt"])
        self.assertNotIn("江南水乡", payload["final_video_prompt"])
        self.assertNotIn("last_frame_prompt", payload)
        self.assertNotEqual(payload["image_prompt"], payload["final_video_prompt"])
        self.assertNotIn("Character anchor:", payload["image_prompt"])

    def test_build_generation_payload_aligns_prompts_with_opening_frame_and_transition_state(self):
        story = {
            "art_style": "cinematic watercolor",
            "characters": [
                {
                    "id": "char_li_ming",
                    "name": "Li Ming",
                    "role": "lead",
                    "description": "young man, short black hair, wearing a dark blue robe.",
                }
            ],
        }
        shot = {
            "shot_id": "scene1_shot2",
            "storyboard_description": (
                "Li Ming pauses at the half-open wooden door, his right hand still braced on the door edge. "
                "Warm lantern light hangs behind him and rain glints on the stone threshold. "
                "Then he lifts his gaze into the room."
            ),
            "transition_from_previous": (
                "Camera cuts tighter from the exterior medium shot. "
                "Li Ming's right hand is still braced on the half-open door. "
                "Warm lantern light and rain sheen stay unchanged."
            ),
            "image_prompt": "Medium shot. Li Ming pauses at the half-open doorway.",
            "final_video_prompt": "Medium shot. Static camera. Li Ming lifts his gaze into the teahouse interior.",
        }

        payload = build_generation_payload(shot, build_story_context(story))

        self.assertIn("Match this exact opening frame:", payload["image_prompt"])
        self.assertIn("Li Ming pauses at the half-open wooden door", payload["image_prompt"])
        self.assertIn("Keep the carried-over pose, prop state, and spatial continuity:", payload["image_prompt"])
        self.assertIn("Li Ming's right hand is still braced on the half-open door", payload["image_prompt"])
        self.assertNotIn("Camera cuts tighter", payload["image_prompt"])
        self.assertIn("Start from this exact opening frame:", payload["final_video_prompt"])
        self.assertIn("Preserve the carried-over state before motion:", payload["final_video_prompt"])

    def test_build_generation_payload_keeps_image_framing_compatible_with_video_motion(self):
        shot = Shot(
            shot_id="scene1_shot1",
            storyboard_description="Li Ming braces one hand on the half-open wooden door before stepping inside.",
            camera_setup=CameraSetup(shot_size="MS", camera_angle="Eye-level", movement="Static"),
            visual_elements=VisualElements(
                subject_and_clothing="Li Ming in a dark blue robe at the doorway",
                action_and_expression="one hand braces on the door before he steps inside",
                environment_and_props="wooden door, wet threshold, warm lantern",
                lighting_and_color="soft overcast daylight with warm lantern fill",
            ),
            image_prompt="Close portrait. Li Ming's face in rain mist at the doorway.",
            final_video_prompt="Medium shot. Static camera. Li Ming pushes the wooden door open with one hand and steps inside.",
        )

        payload = build_generation_payload(
            shot,
            build_story_context(
                {
                    "characters": [
                        {
                            "id": "char_li_ming",
                            "name": "Li Ming",
                            "description": "young man, short black hair, wearing a dark blue robe.",
                        }
                    ]
                }
            ),
        )

        self.assertTrue(payload["image_prompt"].startswith("Medium shot."))
        self.assertIn("video opening frame", payload["image_prompt"])
        self.assertIn("face-only portrait crop", payload["image_prompt"])
        self.assertIn("acting hands, arms, and interacted prop", payload["image_prompt"])
        self.assertIn("Do not suddenly reveal missing hands, props", payload["final_video_prompt"])

    def test_build_generation_payload_marks_nonfirst_shot_as_same_scene_continuation(self):
        shot = {
            "shot_id": "scene1_shot2",
            "scene_position": "development",
            "storyboard_description": "Li Ming turns from the doorway toward Boss Zhao across the teahouse counter.",
            "camera_setup": {"shot_size": "MS", "camera_angle": "Eye-level", "movement": "Static"},
            "visual_elements": {
                "subject_and_clothing": "Li Ming in a dark blue robe, Boss Zhao behind the counter",
                "action_and_expression": "Li Ming turns and answers, Boss Zhao watches without moving",
                "environment_and_props": "teahouse counter, abacus, warm lanterns",
                "lighting_and_color": "warm lantern fill over rainy daylight",
            },
            "image_prompt": "Medium shot. Li Ming turns toward Boss Zhao.",
            "final_video_prompt": "Medium shot. Static camera. Li Ming answers while Boss Zhao watches from behind the counter.",
        }

        payload = build_generation_payload(shot, build_story_context({}))

        self.assertIn("continuing beat inside the same scene", payload["image_prompt"])
        self.assertIn("continuous beat in the same scene timeline", payload["final_video_prompt"])

    def test_sanitize_non_physical_character_cache_before_injection(self):
        story = {
            "characters": [
                {
                    "id": "char_aiwen",
                    "name": "艾文",
                    "role": "主角",
                    "description": "年轻男性，黑色短发，身形清瘦，穿着深蓝长袍。性格孤僻但内心善良，拥有解开时间循环秘密的能力。",
                }
            ],
            "meta": {
                "character_appearance_cache": {
                    "char_aiwen": {
                        "body": "年轻男性，天才魔法师，孤僻善良，解开时间循环秘密",
                        "clothing": "深蓝长袍",
                    }
                }
            },
        }
        shot = {
            "storyboard_description": "艾文站在走廊尽头。",
            "image_prompt": "Medium shot. Aiwen stands at the corridor end.",
            "final_video_prompt": "Medium shot. Static camera. Aiwen raises his head slowly.",
        }

        ctx = build_story_context(story)
        payload = build_generation_payload(shot, ctx)

        self.assertIn("深蓝长袍", ctx.clean_character_section)
        self.assertNotIn("天才魔法师", payload["image_prompt"])
        self.assertNotIn("解开时间循环秘密", payload["final_video_prompt"])

    def test_multi_character_anchor_uses_natural_phrase(self):
        story = {
            "characters": [
                {"id": "char_li_ming", "name": "Li Ming", "role": "lead", "description": "25-year-old man, short black hair, slim build, wearing a dark blue robe."},
                {"id": "char_boss_zhao", "name": "Boss Zhao", "role": "support", "description": "40-year-old heavyset man, moustache, wearing a brown brocade robe."},
            ]
        }
        shot = {
            "storyboard_description": "Li Ming stands at the counter while Boss Zhao sits behind the account desk.",
            "image_prompt": "Medium shot. Li Ming stands at the counter while Boss Zhao sits behind the desk.",
            "final_video_prompt": "Medium shot. Static camera. Li Ming lowers his gaze while Boss Zhao leans forward.",
        }

        payload = build_generation_payload(shot, build_story_context(story))

        self.assertIn("Maintain consistent appearance:", payload["image_prompt"])
        self.assertIn("alongside", payload["image_prompt"])
        self.assertNotIn("Character anchor:", payload["image_prompt"])

    def test_cache_metadata_fields_do_not_change_runtime_prompt_consumption(self):
        story = {
            "genre": "古风",
            "characters": [
                {
                    "id": "char_li_ming",
                    "name": "Li Ming",
                    "description": "young man, short black hair, wearing a dark blue robe.",
                }
            ],
            "meta": {
                "character_appearance_cache": {
                    "char_li_ming": {
                        "body": "young man, short black hair",
                        "clothing": "dark blue robe",
                        "negative_prompt": "modern clothing",
                        "schema_version": APPEARANCE_CACHE_SCHEMA_VERSION,
                        "source_provider": "openai",
                        "source_model": "gpt-4o-mini",
                        "updated_at": "2026-03-31T12:00:00+00:00",
                    }
                },
                "scene_style_cache": [
                    {
                        "keywords": ["teahouse"],
                        "image_extra": "jiangnan teahouse, rain mist",
                        "video_extra": "jiangnan teahouse, rain mist",
                        "negative_prompt": "cars, neon signs",
                        "schema_version": SCENE_STYLE_CACHE_SCHEMA_VERSION,
                        "source_provider": "openai",
                        "source_model": "gpt-4o-mini",
                        "updated_at": "2026-03-31T12:00:00+00:00",
                    }
                ],
            },
        }
        shot = {
            "storyboard_description": "Li Ming pauses at the teahouse doorway.",
            "image_prompt": "Medium shot. Li Ming pauses at the teahouse doorway.",
            "final_video_prompt": "Medium shot. Static camera. Li Ming pushes the wooden door inward.",
        }

        payload = build_generation_payload(shot, build_story_context(story))

        self.assertIn("dark blue robe", payload["image_prompt"])
        self.assertIn("jiangnan teahouse", payload["image_prompt"])
        self.assertIn("modern clothing", payload["negative_prompt"])
        self.assertIn("cars", payload["negative_prompt"])
        self.assertIn("neon signs", payload["negative_prompt"])

    def test_future_cache_schema_versions_are_ignored_by_runtime_payload(self):
        story = {
            "genre": "古风",
            "characters": [
                {
                    "id": "char_li_ming",
                    "name": "Li Ming",
                    "description": "young man, short black hair, wearing a dark blue robe.",
                }
            ],
            "character_images": {
                "char_li_ming": {
                    "visual_dna": "young man, short black hair",
                    "character_id": "char_li_ming",
                    "character_name": "Li Ming",
                }
            },
            "meta": {
                "character_appearance_cache": {
                    "char_li_ming": {
                        "body": "silver android with glowing eyes",
                        "clothing": "neon armored coat",
                        "negative_prompt": "rust",
                        "schema_version": APPEARANCE_CACHE_SCHEMA_VERSION + 1,
                    }
                },
                "scene_style_cache": [
                    {
                        "keywords": ["teahouse"],
                        "image_extra": "futuristic megamall, neon escalators",
                        "video_extra": "futuristic megamall, neon escalators",
                        "negative_prompt": "ancient wood",
                        "schema_version": SCENE_STYLE_CACHE_SCHEMA_VERSION + 1,
                    }
                ],
            },
        }
        shot = {
            "storyboard_description": "Li Ming pauses at the teahouse doorway.",
            "image_prompt": "Medium shot. Li Ming pauses at the teahouse doorway.",
            "final_video_prompt": "Medium shot. Static camera. Li Ming pushes the wooden door inward.",
        }

        payload = build_generation_payload(shot, build_story_context(story))

        expected_style = (_GENRE_STYLE_RULES.get(story["genre"]) or next(iter(_GENRE_STYLE_RULES.values())))[0]
        self.assertIn("short black hair", payload["image_prompt"])
        self.assertIn("dark blue robe", payload["image_prompt"])
        self.assertIn(expected_style, payload["image_prompt"])
        self.assertNotIn("silver android", payload["image_prompt"])
        self.assertNotIn("neon armored coat", payload["image_prompt"])
        self.assertNotIn("futuristic megamall", payload["image_prompt"])
        self.assertNotIn("rust", payload["negative_prompt"])

    def test_character_matching_avoids_substring_false_positive(self):
        story = {
            "characters": [
                {"id": "char_ann", "name": "Ann", "role": "support", "description": "short hair"},
                {"id": "char_anna", "name": "Anna", "role": "lead", "description": "long hair"},
            ],
            "meta": {
                "character_appearance_cache": {
                    "char_ann": {"negative_prompt": "ann-only"},
                    "char_anna": {"negative_prompt": "anna-only"},
                }
            },
        }
        shot = {
            "storyboard_description": "Anna opens the door and looks back.",
            "negative_prompt": "low quality, blur",
        }

        ctx = build_story_context(story)
        payload = build_generation_payload(shot, ctx)

        self.assertFalse(character_appears_in_shot("Ann", shot))
        self.assertTrue(character_appears_in_shot("Anna", shot))
        self.assertIn("low quality", payload["negative_prompt"])
        self.assertIn("blur", payload["negative_prompt"])
        self.assertIn("anna-only", payload["negative_prompt"])
        self.assertIn("wrong face", payload["negative_prompt"])
        self.assertIn("different primary outfit", payload["negative_prompt"])

    def test_character_matching_prefers_structured_names(self):
        shot = {
            "storyboard_description": "",
            "characters": [{"name": "Li Ming"}],
        }
        self.assertTrue(character_appears_in_shot("Li Ming", shot))
        self.assertFalse(character_appears_in_shot("Li", shot))

    def test_character_matching_uses_structured_names_when_text_only_has_pronoun(self):
        shot = {
            "storyboard_description": "他停在门口，回头看向屋内。",
            "image_prompt": "Medium shot. He pauses at the doorway.",
            "final_video_prompt": "Medium shot. Static camera. He turns his gaze into the room.",
            "characters": ["李明"],
        }

        self.assertTrue(character_appears_in_shot("李明", shot))
        self.assertFalse(character_appears_in_shot("顾北辰", shot))

    def test_character_matching_ignores_environment_only_name_mentions(self):
        shot = {
            "storyboard_description": "空镜头展示走廊尽头。",
            "image_prompt": "Wide shot. Empty corridor under cold light.",
            "final_video_prompt": "Wide shot. Static camera. Dust floats through the corridor.",
            "visual_elements": {
                "environment_and_props": "墙上挂着 Li Ming 的画像与旧徽章",
            },
        }

        self.assertFalse(character_appears_in_shot("Li Ming", shot))

    def test_infer_shot_view_hint_ignores_generic_profile_phrases(self):
        shot = {
            "storyboard_description": "Li Ming keeps a low profile while moving through the market.",
            "image_prompt": "Medium shot. Li Ming keeps a low profile in the crowd.",
        }

        self.assertEqual(infer_shot_view_hint("Li Ming", shot), "")

    def test_infer_shot_view_hint_uses_structured_single_character_fields_even_with_existing_contexts(self):
        shot = {
            "characters": [{"name": "Li Ming"}],
            "storyboard_description": "Li Ming pauses at the doorway.",
            "image_prompt": "Medium shot. Li Ming pauses at the doorway.",
            "visual_elements": {
                "subject_and_clothing": "young man in a dark blue robe",
                "action_and_expression": "seen from behind while turning toward the doorway",
            },
        }

        self.assertEqual(infer_shot_view_hint("Li Ming", shot), "match the shot's back view")

    def test_genre_fallback_style_still_applies_when_scene_cache_keywords_do_not_match(self):
        story = {
            "meta": {
                "scene_style_cache": [
                    {
                        "keywords": ["teahouse"],
                        "image_extra": "jiangnan teahouse interior",
                        "video_extra": "jiangnan teahouse interior",
                    }
                ]
            },
        }
        story["genre"] = next(iter(_GENRE_STYLE_RULES))
        shot = {
            "storyboard_description": "Moonlight falls across an empty stone bridge.",
            "image_prompt": "Wide shot. Moonlight washes over an ancient stone bridge.",
            "final_video_prompt": "Wide shot. Static camera. Mist drifts above the stone bridge.",
        }

        payload = build_generation_payload(shot, build_story_context(story))

        self.assertIn(next(iter(_GENRE_STYLE_RULES.values()))[0], payload["image_prompt"])
        self.assertNotIn("jiangnan teahouse interior", payload["image_prompt"])

    def test_clothing_change_hint_only_applies_to_segments_mentioning_same_character(self):
        story = {
            "characters": [
                {"id": "char_li_ming", "name": "Li Ming", "role": "lead", "description": "young man, short black hair. wearing a dark blue robe."},
                {"id": "char_boss_zhao", "name": "Boss Zhao", "role": "support", "description": "middle-aged man, moustache, wearing a brown robe."},
            ]
        }
        shot = {
            "storyboard_description": "Li Ming stands at the counter while Boss Zhao watches from the back room.",
            "image_prompt": "Medium shot. Li Ming waits at the counter.",
            "final_video_prompt": "Medium shot. Static camera. Li Ming looks toward the ledger desk.",
            "visual_elements": {
                "action_and_expression": "Boss Zhao changes outfit in the back room before returning.",
            },
        }

        payload = build_generation_payload(shot, build_story_context(story))

        self.assertIn("wearing a dark blue robe", payload["image_prompt"])

    def test_build_generation_payload_uses_structured_character_name_for_pronoun_only_shot(self):
        story = {
            "characters": [
                {
                    "id": "char_li_ming",
                    "name": "Li Ming",
                    "description": "young man, short black hair, wearing a dark blue robe.",
                },
                {
                    "id": "char_boss_zhao",
                    "name": "Boss Zhao",
                    "description": "middle-aged man, moustache, wearing a brown robe.",
                },
            ],
            "character_images": {
                "char_li_ming": {
                    "image_url": "/media/characters/li_ming.png",
                    "image_path": "media/characters/li_ming.png",
                },
                "char_boss_zhao": {
                    "image_url": "/media/characters/boss_zhao.png",
                    "image_path": "media/characters/boss_zhao.png",
                },
            },
        }
        shot = {
            "storyboard_description": "他停在门口，右手还扶着木门。",
            "image_prompt": "Medium shot. He pauses at the doorway.",
            "final_video_prompt": "Medium shot. Static camera. He looks into the room.",
            "characters": ["Li Ming"],
        }

        payload = build_generation_payload(shot, build_story_context(story), story=story)

        self.assertIn("Li Ming", payload["image_prompt"])
        self.assertIn("dark blue robe", payload["image_prompt"])
        self.assertEqual(len(payload["reference_images"]), 1)
        self.assertEqual(payload["reference_images"][0]["image_url"], "/media/characters/li_ming.png")


class ParseStoryboardOverrideTests(unittest.IsolatedAsyncioTestCase):
    async def test_parse_script_to_storyboard_uses_character_section_override(self):
        response = """
        [
          {
            "shot_id": "scene1_shot1",
            "storyboard_description": "李明推门进入茶馆。",
            "camera_setup": {"shot_size": "MS", "camera_angle": "Eye-level", "movement": "Static"},
            "visual_elements": {
              "subject_and_clothing": "李明，深蓝长衫",
              "action_and_expression": "推门进入",
              "environment_and_props": "茶馆木门与灯笼",
              "lighting_and_color": "暖色灯笼与阴天自然光"
            },
            "image_prompt": "Medium shot. Li Ming pauses at the wooden teahouse doorway.",
            "final_video_prompt": "Medium shot. Static camera. Li Ming pushes open the wooden door and enters the teahouse."
          }
        ]
        """.strip()

        class FakeProvider:
            def __init__(self):
                self.messages = []

            async def complete_messages_with_usage(self, messages, system: str = "", temperature: float = 0.3, **kwargs):
                self.messages = messages
                return response, {"prompt_tokens": 10, "completion_tokens": 5}

        fake = FakeProvider()
        with patch("app.services.storyboard.get_llm_provider", return_value=fake):
            shots, usage = await parse_script_to_storyboard(
                "【环境】茶馆门口\n【画面】李明推门进入。",
                provider="openai",
                character_info={
                    "characters": [{"id": "char_li_ming", "name": "李明", "role": "主角", "description": "青年男子"}],
                    "character_images": {"char_li_ming": {"prompt": "Character portrait, studio lighting", "character_id": "char_li_ming", "character_name": "李明"}},
                },
                character_section_override="## Character Reference\n- 李明：Visual DNA only",
            )

        self.assertEqual(len(shots), 1)
        self.assertEqual(usage["prompt_tokens"], 10)
        flattened = "\n".join(message.get("content", "") for message in fake.messages)
        self.assertIn("Visual DNA only", flattened)
        self.assertNotIn("studio lighting", flattened.lower())

    async def test_parse_script_to_storyboard_rewrites_wrong_source_scene_key_from_scene_map(self):
        response = """
        [
          {
            "shot_id": "scene2_shot1",
            "source_scene_key": "ep99_scene99",
            "storyboard_description": "镜头切到书房内景。",
            "camera_setup": {"shot_size": "MS", "camera_angle": "Eye-level", "movement": "Static"},
            "visual_elements": {
              "subject_and_clothing": "书桌前的男子背影",
              "action_and_expression": "停在桌前",
              "environment_and_props": "书房书桌、烛台与窗棂",
              "lighting_and_color": "烛火暖光与窗外冷光"
            },
            "image_prompt": "Medium shot. A man pauses at the writing desk in the study.",
            "final_video_prompt": "Medium shot. Static camera. He lowers his gaze toward the desk."
          }
        ]
        """.strip()

        class FakeProvider:
            async def complete_messages_with_usage(self, messages, system: str = "", temperature: float = 0.3, **kwargs):
                return response, {"prompt_tokens": 10, "completion_tokens": 5}

        with patch("app.services.storyboard.get_llm_provider", return_value=FakeProvider()):
            shots, _ = await parse_script_to_storyboard(
                "第 1 集：测试\n\n【场景 3】\n环境：回廊\n画面：空镜头。\n\n【场景 7】\n环境：书房\n画面：男子停在桌前。",
                provider="openai",
            )

        self.assertEqual(len(shots), 1)
        self.assertEqual(shots[0].source_scene_key, "ep01_scene07")

    async def test_parse_script_to_storyboard_normalizes_camera_angle_variants(self):
        response = """
        [
          {
            "shot_id": "scene1_shot1",
            "storyboard_description": "李明站在楼梯上方向下看。",
            "camera_setup": {"shot_size": "MS", "camera_angle": "Slightly high angle", "movement": "Static"},
            "visual_elements": {
              "subject_and_clothing": "李明，深色外套",
              "action_and_expression": "停下脚步，低头看向楼下",
              "environment_and_props": "木质楼梯与走廊扶手",
              "lighting_and_color": "室内暖光与走廊阴影"
            },
            "image_prompt": "Medium shot. Li Ming pauses on the staircase and looks downward.",
            "final_video_prompt": "Medium shot. Static camera. Li Ming pauses on the staircase and looks down the hallway."
          }
        ]
        """.strip()

        class FakeProvider:
            async def complete_messages_with_usage(self, messages, system: str = "", temperature: float = 0.3, **kwargs):
                return response, {"prompt_tokens": 10, "completion_tokens": 5}

        with patch("app.services.storyboard.get_llm_provider", return_value=FakeProvider()):
            shots, _ = await parse_script_to_storyboard(
                "【环境】走廊楼梯\n【画面】李明停在楼梯上方向下看。",
                provider="openai",
            )

        self.assertEqual(len(shots), 1)
        self.assertEqual(shots[0].camera_setup.camera_angle, "High angle")

    async def test_parse_script_to_storyboard_preserves_structured_characters_for_pronoun_shot(self):
        response = """
        [
          {
            "shot_id": "scene1_shot1",
            "characters": ["李明", "路人"],
            "storyboard_description": "他停在茶馆门口，右手还扶着木门。",
            "camera_setup": {"shot_size": "MS", "camera_angle": "Eye-level", "movement": "Static"},
            "visual_elements": {
              "subject_and_clothing": "青年男子，深蓝长衫",
              "action_and_expression": "停在门口，抬眼看向屋内",
              "environment_and_props": "茶馆木门与灯笼",
              "lighting_and_color": "暖色灯笼与阴天自然光"
            },
            "image_prompt": "Medium shot. He pauses at the wooden doorway.",
            "final_video_prompt": "Medium shot. Static camera. He lifts his gaze into the teahouse."
          }
        ]
        """.strip()

        class FakeProvider:
            async def complete_messages_with_usage(self, messages, system: str = "", temperature: float = 0.3, **kwargs):
                return response, {"prompt_tokens": 10, "completion_tokens": 5}

        with patch("app.services.storyboard.get_llm_provider", return_value=FakeProvider()):
            shots, _ = await parse_script_to_storyboard(
                "【环境】茶馆门口\n【画面】李明停在门口，随后他看向屋内。",
                provider="openai",
            )

        self.assertEqual(len(shots), 1)
        self.assertEqual(shots[0].characters, ["李明"])
        self.assertTrue(character_appears_in_shot("李明", shots[0]))

    async def test_parse_script_to_storyboard_normalizes_audio_speaker_for_narration(self):
        response = """
        [
          {
            "shot_id": "scene1_shot1",
            "characters": ["李明"],
            "storyboard_description": "他停在门口，旁白落下。",
            "camera_setup": {"shot_size": "MS", "camera_angle": "Eye-level", "movement": "Static"},
            "visual_elements": {
              "subject_and_clothing": "青年男子，深蓝长衫",
              "action_and_expression": "停在门口，抬眼看向屋内",
              "environment_and_props": "茶馆木门与灯笼",
              "lighting_and_color": "暖色灯笼与阴天自然光"
            },
            "image_prompt": "Medium shot. He pauses at the doorway.",
            "final_video_prompt": "Medium shot. Static camera. He looks into the teahouse.",
            "audio_reference": {
              "type": "voiceover",
              "speaker": "Narrator",
              "content": "他知道，门后的一切都会改变。"
            }
          }
        ]
        """.strip()

        class FakeProvider:
            async def complete_messages_with_usage(self, messages, system: str = "", temperature: float = 0.3, **kwargs):
                return response, {"prompt_tokens": 10, "completion_tokens": 5}

        with patch("app.services.storyboard.get_llm_provider", return_value=FakeProvider()):
            shots, _ = await parse_script_to_storyboard(
                "【环境】茶馆门口\n【画面】李明停在门口。\n【旁白】他知道，门后的一切都会改变。",
                provider="openai",
            )

        self.assertEqual(len(shots), 1)
        self.assertEqual(shots[0].audio_reference.type, "narration")
        self.assertEqual(shots[0].audio_reference.speaker, "旁白")
        self.assertEqual(shots[0].audio_reference.content, "他知道，门后的一切都会改变。")

    async def test_parse_script_to_storyboard_preserves_dialogue_speaker_name(self):
        response = """
        [
          {
            "shot_id": "scene1_shot1",
            "characters": ["李明"],
            "storyboard_description": "他停在门口，说出一句提醒。",
            "camera_setup": {"shot_size": "MS", "camera_angle": "Eye-level", "movement": "Static"},
            "visual_elements": {
              "subject_and_clothing": "青年男子，深蓝长衫",
              "action_and_expression": "停在门口，开口说话",
              "environment_and_props": "茶馆木门与灯笼",
              "lighting_and_color": "暖色灯笼与阴天自然光"
            },
            "image_prompt": "Medium shot. He pauses at the doorway.",
            "final_video_prompt": "Medium shot. Static camera. He speaks while holding the door.",
            "audio_reference": {
              "speaker": "李明",
              "content": "别进去。"
            }
          }
        ]
        """.strip()

        class FakeProvider:
            async def complete_messages_with_usage(self, messages, system: str = "", temperature: float = 0.3, **kwargs):
                return response, {"prompt_tokens": 10, "completion_tokens": 5}

        with patch("app.services.storyboard.get_llm_provider", return_value=FakeProvider()):
            shots, _ = await parse_script_to_storyboard(
                "【环境】茶馆门口\n【画面】李明停在门口。\n【李明】别进去。",
                provider="openai",
            )

        self.assertEqual(len(shots), 1)
        self.assertEqual(shots[0].audio_reference.type, "dialogue")
        self.assertEqual(shots[0].audio_reference.speaker, "李明")
        self.assertEqual(shots[0].audio_reference.content, "别进去。")

    async def test_parse_script_to_storyboard_tolerates_minor_schema_drift(self):
        response = """
        {
          "shots": [
            {
              "shot_id": "scene1_shot1",
              "storyboard_description": "李明在走廊尽头停住，抬头观察二楼窗户。",
              "scene_intensity": "medium",
              "scene_position": "opening",
              "camera_setup": {
                "shot_size": "Medium shot",
                "camera_angle": "Slightly high angle",
                "movement": "Push in"
              },
              "visual_elements": {
                "subject_and_clothing": "李明，深色外套",
                "action_and_expression": "停步抬头观察",
                "environment_and_props": "老旧走廊、木栏杆、二楼窗户",
                "lighting_and_color": "昏黄顶灯与窗边冷光"
              },
              "audio_reference": {
                "type": "voiceover",
                "content": "他意识到有人在楼上看着自己。"
              },
              "final_video_prompt": ""
            }
          ]
        }
        """.strip()

        class FakeProvider:
            async def complete_messages_with_usage(self, messages, system: str = "", temperature: float = 0.3, **kwargs):
                return response, {"prompt_tokens": 10, "completion_tokens": 5}

        with patch("app.services.storyboard.get_llm_provider", return_value=FakeProvider()):
            shots, _ = await parse_script_to_storyboard(
                "【环境】旧楼走廊\n【画面】李明在走廊尽头停下，抬头看向二楼。",
                provider="openai",
            )

        self.assertEqual(len(shots), 1)
        self.assertEqual(shots[0].camera_setup.shot_size, "MS")
        self.assertEqual(shots[0].camera_setup.camera_angle, "High angle")
        self.assertEqual(shots[0].camera_setup.movement, "Slow Dolly in")
        self.assertEqual(shots[0].scene_intensity, "low")
        self.assertEqual(shots[0].scene_position, "establishing")
        self.assertEqual(shots[0].audio_reference.type, "narration")
        self.assertTrue(shots[0].image_prompt)
        self.assertTrue(shots[0].final_video_prompt)

    async def test_parse_script_to_storyboard_rejects_non_shot_wrapper_object(self):
        response = """
        {
          "message": "temporary failure",
          "request_id": "req_123"
        }
        """.strip()

        class FakeProvider:
            async def complete_messages_with_usage(self, messages, system: str = "", temperature: float = 0.3, **kwargs):
                return response, {"prompt_tokens": 10, "completion_tokens": 5}

        with patch("app.services.storyboard.get_llm_provider", return_value=FakeProvider()):
            with self.assertRaises(ValueError):
                await parse_script_to_storyboard(
                    "【环境】旧楼走廊\n【画面】李明在走廊尽头停下。",
                    provider="openai",
                )


class StoryContextPreparationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_prepare_story_context_extracts_and_persists_caches(self):
        async with self.session_factory() as session:
            await repo.save_story(
                session,
                "story-ctx-prepare",
                {
                    "idea": "test",
                    "genre": "历史",
                    "tone": "沉稳",
                    "selected_setting": "江南古镇，临河茶馆，木窗灯笼，细雨薄雾。",
                    "characters": [
                        {
                            "id": "char_li_ming",
                            "name": "李明",
                            "role": "主角",
                            "description": "25岁青年男子，黑色短发，身形清瘦，穿着深蓝长衫。",
                        }
                    ],
                    "meta": {},
                },
            )

            class FakeProvider:
                async def complete_messages_with_usage(self, messages, system: str = "", temperature: float = 0.3, **kwargs):
                    if "stable visual anchors" in system:
                        return (
                            """
                            {
                              "characters": [
                                {
                                  "id": "char_li_ming",
                                  "body": "young man, short black hair, slim build",
                                  "clothing": "dark blue robe",
                                  "negative_prompt": "modern clothing"
                                }
                              ]
                            }
                            """.strip(),
                            {"prompt_tokens": 120, "completion_tokens": 40},
                        )
                    return (
                        """
                        {
                          "styles": [
                            {
                              "keywords": ["teahouse", "river town"],
                              "image_extra": "jiangnan river town, wooden teahouse, rain mist, warm lantern glow",
                              "video_extra": "jiangnan river town, rain mist, warm lantern glow",
                              "negative_prompt": "cars, neon signs"
                            }
                          ]
                        }
                        """.strip(),
                        {"prompt_tokens": 80, "completion_tokens": 30},
                    )

            with patch("app.services.story_context_service.get_llm_provider", return_value=FakeProvider()):
                story, ctx = await prepare_story_context(
                    session,
                    "story-ctx-prepare",
                    provider="openai",
                    model="gpt-4o-mini",
                    api_key="test-key",
                    base_url="https://example.com/v1",
                )

            self.assertIsNotNone(ctx)
            self.assertEqual(
                story["meta"]["character_appearance_cache"][story["characters"][0]["id"]]["body"],
                "young man, short black hair, slim build",
            )
            self.assertEqual(
                story["meta"]["character_appearance_cache"][story["characters"][0]["id"]]["schema_version"],
                APPEARANCE_CACHE_SCHEMA_VERSION,
            )
            self.assertEqual(
                story["meta"]["character_appearance_cache"][story["characters"][0]["id"]]["source_provider"],
                "openai",
            )
            self.assertEqual(
                story["meta"]["character_appearance_cache"][story["characters"][0]["id"]]["source_model"],
                "gpt-4o-mini",
            )
            self.assertTrue(
                story["meta"]["character_appearance_cache"][story["characters"][0]["id"]]["updated_at"],
            )
            self.assertEqual(story.get("character_images", {}), {})
            self.assertEqual(
                story["meta"]["scene_style_cache"][0]["video_extra"],
                "jiangnan river town, rain mist, warm lantern glow",
            )
            self.assertEqual(
                story["meta"]["scene_style_cache"][0]["schema_version"],
                SCENE_STYLE_CACHE_SCHEMA_VERSION,
            )
            self.assertEqual(
                story["meta"]["scene_style_cache"][0]["source_provider"],
                "openai",
            )
            self.assertEqual(
                story["meta"]["scene_style_cache"][0]["source_model"],
                "gpt-4o-mini",
            )
            self.assertTrue(story["meta"]["scene_style_cache"][0]["updated_at"])
            shot = {
                "shot_id": "scene1_shot1",
                "storyboard_description": "李明在茶馆门口停下。",
                "image_prompt": "Medium shot. Li Ming pauses at the teahouse doorway.",
                "final_video_prompt": "Medium shot. Static camera. Li Ming pushes the wooden door inward.",
            }
            payload = build_generation_payload(shot, ctx)
            self.assertIn("jiangnan river town", payload["image_prompt"])
            self.assertIn("modern clothing", payload["negative_prompt"])

    async def test_prepare_story_context_projects_visual_dna_only_when_asset_exists(self):
        async with self.session_factory() as session:
            await repo.save_story(
                session,
                "story-ctx-project-dna",
                {
                    "idea": "test",
                    "genre": "历史",
                    "tone": "沉稳",
                    "selected_setting": "江南古镇，临河茶馆。",
                    "characters": [
                        {
                            "id": "char_li_ming",
                            "name": "李明",
                            "role": "主角",
                            "description": "25岁青年男子，黑色短发，身形清瘦，穿着深蓝长衫。",
                        }
                    ],
                    "character_images": {
                        "char_li_ming": build_character_asset_record(
                            image_url="/media/characters/li_ming.png",
                            image_path="media/characters/li_ming.png",
                            prompt="Standard three-view character turnaround sheet for 李明",
                            character_id="char_li_ming",
                            character_name="李明",
                        )
                    },
                    "meta": {},
                },
            )

            class FakeProvider:
                async def complete_messages_with_usage(self, messages, system: str = "", temperature: float = 0.3, **kwargs):
                    if "stable visual anchors" in system:
                        return (
                            '{"characters":[{"id":"char_li_ming","body":"young man, short black hair, slim build","clothing":"dark blue robe"}]}',
                            {"prompt_tokens": 12, "completion_tokens": 5},
                        )
                    return (
                        '{"styles":[{"keywords":["teahouse"],"image_extra":"jiangnan teahouse","video_extra":"jiangnan teahouse"}]}',
                        {"prompt_tokens": 8, "completion_tokens": 4},
                    )

            with patch("app.services.story_context_service.get_llm_provider", return_value=FakeProvider()):
                story, _ = await prepare_story_context(
                    session,
                    "story-ctx-project-dna",
                    provider="openai",
                    model="gpt-4o-mini",
                    api_key="test-key",
                    base_url="https://example.com/v1",
                )

            self.assertEqual(
                story["character_images"]["char_li_ming"]["visual_dna"],
                "young man, short black hair, slim build",
            )

    async def test_prepare_story_context_only_merges_missing_appearance_cache_entries(self):
        async with self.session_factory() as session:
            await repo.save_story(
                session,
                "story-ctx-missing-appearance-only",
                {
                    "idea": "test",
                    "genre": "历史",
                    "tone": "沉稳",
                    "selected_setting": "江南古镇，临河茶馆。",
                    "characters": [
                        {
                            "id": "char_li_ming",
                            "name": "李明",
                            "role": "主角",
                            "description": "25岁青年男子，黑色短发，身形清瘦，穿着深蓝长衫。",
                        },
                        {
                            "id": "char_a_yue",
                            "name": "阿月",
                            "role": "配角",
                            "description": "20岁年轻女子，长发，穿着浅青色襦裙。",
                        },
                    ],
                    "character_images": {
                        "char_li_ming": build_character_asset_record(
                            image_url="/media/characters/li_ming.png",
                            image_path="media/characters/li_ming.png",
                            prompt="Standard three-view character turnaround sheet for 李明",
                            existing={"visual_dna": "young man, short black hair, slim build"},
                            character_id="char_li_ming",
                            character_name="李明",
                        ),
                        "char_a_yue": build_character_asset_record(
                            image_url="/media/characters/a_yue.png",
                            image_path="media/characters/a_yue.png",
                            prompt="Standard three-view character turnaround sheet for 阿月",
                            character_id="char_a_yue",
                            character_name="阿月",
                        ),
                    },
                    "meta": {
                        "character_appearance_cache": {
                            "char_li_ming": {
                                "body": "young man, short black hair, slim build",
                                "clothing": "dark blue robe",
                                "negative_prompt": "modern clothing",
                            }
                        }
                    },
                },
            )

            class FakeProvider:
                async def complete_messages_with_usage(self, messages, system: str = "", temperature: float = 0.3, **kwargs):
                    if "stable visual anchors" in system:
                        return (
                            """
                            {
                              "characters": [
                                {
                                  "id": "char_li_ming",
                                  "body": "tall young man, loose black hair",
                                  "clothing": "light robe",
                                  "negative_prompt": "armor"
                                },
                                {
                                  "id": "char_a_yue",
                                  "body": "young woman, long black hair, slim build",
                                  "clothing": "light cyan ruqun"
                                }
                              ]
                            }
                            """.strip(),
                            {"prompt_tokens": 20, "completion_tokens": 8},
                        )
                    return (
                        '{"styles":[{"keywords":["teahouse"],"image_extra":"jiangnan teahouse","video_extra":"jiangnan teahouse"}]}',
                        {"prompt_tokens": 8, "completion_tokens": 4},
                    )

            with patch("app.services.story_context_service.get_llm_provider", return_value=FakeProvider()):
                story, _ = await prepare_story_context(
                    session,
                    "story-ctx-missing-appearance-only",
                    provider="openai",
                    model="gpt-4o-mini",
                    api_key="test-key",
                    base_url="https://example.com/v1",
                )

            self.assertEqual(
                story["meta"]["character_appearance_cache"]["char_li_ming"]["body"],
                "young man, short black hair, slim build",
            )
            self.assertEqual(
                story["meta"]["character_appearance_cache"]["char_li_ming"]["clothing"],
                "dark blue robe",
            )
            self.assertEqual(
                story["meta"]["character_appearance_cache"]["char_a_yue"]["body"],
                "young woman, long black hair, slim build",
            )
            self.assertEqual(
                story["character_images"]["char_li_ming"]["visual_dna"],
                "young man, short black hair, slim build",
            )
            self.assertEqual(
                story["character_images"]["char_a_yue"]["visual_dna"],
                "young woman, long black hair, slim build",
            )

    async def test_prepare_story_context_refreshes_future_schema_cache_versions(self):
        async with self.session_factory() as session:
            await repo.save_story(
                session,
                "story-ctx-refresh-future-schema",
                {
                    "idea": "test",
                    "genre": "历史",
                    "tone": "沉稳",
                    "selected_setting": "江南古镇，临河茶馆，细雨薄雾。",
                    "characters": [
                        {
                            "id": "char_li_ming",
                            "name": "李明",
                            "role": "主角",
                            "description": "25岁青年男子，黑色短发，身形清瘦，穿着深蓝长衫。",
                        }
                    ],
                    "meta": {
                        "character_appearance_cache": {
                            "char_li_ming": {
                                "body": "silver android",
                                "clothing": "neon armor",
                                "negative_prompt": "rust",
                                "schema_version": APPEARANCE_CACHE_SCHEMA_VERSION + 1,
                            }
                        },
                        "scene_style_cache": [
                            {
                                "keywords": ["teahouse"],
                                "image_extra": "futuristic megamall",
                                "video_extra": "futuristic megamall",
                                "negative_prompt": "ancient wood",
                                "schema_version": SCENE_STYLE_CACHE_SCHEMA_VERSION + 1,
                            }
                        ],
                    },
                },
            )

            class FakeProvider:
                async def complete_messages_with_usage(self, messages, system: str = "", temperature: float = 0.3, **kwargs):
                    if "stable visual anchors" in system:
                        return (
                            '{"characters":[{"id":"char_li_ming","body":"young man, short black hair, slim build","clothing":"dark blue robe","negative_prompt":"modern clothing"}]}',
                            {"prompt_tokens": 20, "completion_tokens": 8},
                        )
                    return (
                        '{"styles":[{"keywords":["teahouse"],"image_extra":"jiangnan teahouse, rain mist","video_extra":"jiangnan teahouse, rain mist","negative_prompt":"cars"}]}',
                        {"prompt_tokens": 8, "completion_tokens": 4},
                    )

            with patch("app.services.story_context_service.get_llm_provider", return_value=FakeProvider()):
                story, ctx = await prepare_story_context(
                    session,
                    "story-ctx-refresh-future-schema",
                    provider="openai",
                    model="gpt-4o-mini",
                    api_key="test-key",
                    base_url="https://example.com/v1",
                )

            self.assertIsNotNone(ctx)
            self.assertEqual(
                story["meta"]["character_appearance_cache"]["char_li_ming"]["body"],
                "young man, short black hair, slim build",
            )
            self.assertEqual(
                story["meta"]["character_appearance_cache"]["char_li_ming"]["schema_version"],
                APPEARANCE_CACHE_SCHEMA_VERSION,
            )
            self.assertEqual(
                story["meta"]["scene_style_cache"][0]["image_extra"],
                "jiangnan teahouse, rain mist",
            )
            self.assertEqual(
                story["meta"]["scene_style_cache"][0]["schema_version"],
                SCENE_STYLE_CACHE_SCHEMA_VERSION,
            )

    async def test_prepare_story_context_does_not_pollute_existing_cache_when_appearance_refresh_fails(self):
        async with self.session_factory() as session:
            await repo.save_story(
                session,
                "story-ctx-appearance-refresh-failure",
                {
                    "idea": "test",
                    "genre": "历史",
                    "tone": "沉稳",
                    "selected_setting": "江南古镇，石桥，细雨。",
                    "characters": [
                        {
                            "id": "char_li_ming",
                            "name": "李明",
                            "role": "主角",
                            "description": "25岁青年男子，黑色短发，穿着深蓝长衫。",
                        },
                        {
                            "id": "char_a_yue",
                            "name": "阿月",
                            "role": "配角",
                            "description": "20岁年轻女子，长发，穿着浅青色襦裙。",
                        },
                    ],
                    "meta": {
                        "character_appearance_cache": {
                            "char_li_ming": {
                                "body": "young man, short black hair",
                                "clothing": "dark blue robe",
                                "negative_prompt": "modern clothing",
                                "schema_version": APPEARANCE_CACHE_SCHEMA_VERSION,
                            }
                        }
                    },
                },
            )

            class FakeProvider:
                async def complete_messages_with_usage(self, messages, system: str = "", temperature: float = 0.3, **kwargs):
                    if "stable visual anchors" in system:
                        raise RuntimeError("appearance extraction failed")
                    return (
                        '{"styles":[{"keywords":["bridge"],"image_extra":"ancient bridge, rain mist","video_extra":"ancient bridge, rain mist"}]}',
                        {"prompt_tokens": 8, "completion_tokens": 4},
                    )

            with patch("app.services.story_context_service.get_llm_provider", return_value=FakeProvider()):
                story, _ = await prepare_story_context(
                    session,
                    "story-ctx-appearance-refresh-failure",
                    provider="openai",
                    model="gpt-4o-mini",
                    api_key="test-key",
                    base_url="https://example.com/v1",
                )

            self.assertEqual(
                story["meta"]["character_appearance_cache"]["char_li_ming"]["body"],
                "young man, short black hair",
            )
            self.assertNotIn("char_a_yue", story["meta"]["character_appearance_cache"])
            self.assertEqual(
                story["meta"]["scene_style_cache"][0]["image_extra"],
                "ancient bridge, rain mist",
            )

    async def test_prepare_story_context_uses_env_backfill_credentials(self):
        async with self.session_factory() as session:
            await repo.save_story(
                session,
                "story-ctx-env-fallback",
                {
                    "idea": "test",
                    "genre": "历史",
                    "tone": "沉稳",
                    "selected_setting": "江南古镇，石桥，细雨。",
                    "characters": [
                        {
                            "id": "char_li_ming",
                            "name": "李明",
                            "role": "主角",
                            "description": "25岁青年男子，黑色短发，穿着深蓝长衫。",
                        }
                    ],
                    "meta": {},
                },
            )

            class FakeProvider:
                async def complete_messages_with_usage(self, messages, system: str = "", temperature: float = 0.3, **kwargs):
                    if "stable visual anchors" in system:
                        return (
                            '{"characters":[{"id":"char_li_ming","body":"young man, short black hair","clothing":"dark blue robe"}]}',
                            {"prompt_tokens": 10, "completion_tokens": 5},
                        )
                    return (
                        '{"styles":[{"keywords":["bridge"],"image_extra":"ancient bridge, rain mist","video_extra":"ancient bridge, rain mist"}]}',
                        {"prompt_tokens": 8, "completion_tokens": 4},
                    )

            with patch("app.services.story_context_service.get_llm_provider", return_value=FakeProvider()):
                with patch("app.services.story_context_service.settings.anthropic_api_key", "env-key"):
                    story, _ = await prepare_story_context(
                        session,
                        "story-ctx-env-fallback",
                        provider="claude",
                        model="claude-sonnet-4-6",
                        api_key="",
                        base_url="",
                    )

            self.assertIn("character_appearance_cache", story["meta"])
            self.assertIn("scene_style_cache", story["meta"])


class StoryContextServiceParsingTests(unittest.TestCase):
    def tearDown(self):
        story_context_service._story_context_locks.clear()

    def test_parse_json_extracts_first_fenced_block(self):
        content = """
        Intro text
        ```json
        {"characters": {"Li Ming": {"body": "short black hair"}}}
        ```
        ```json
        {"ignored": true}
        ```
        """.strip()

        parsed = _parse_json(content)

        self.assertEqual(parsed["characters"]["Li Ming"]["body"], "short black hair")

    def test_get_story_context_lock_prunes_stale_entries(self):
        with patch("app.services.story_context_service._STORY_CONTEXT_LOCK_TTL_SECONDS", 1.0):
            with patch("app.services.story_context_service.monotonic", side_effect=[0.0, 2.0]):
                first_lock = story_context_service._get_story_context_lock("story-1")
                second_lock = story_context_service._get_story_context_lock("story-2")

        self.assertIsNot(first_lock, second_lock)
        self.assertNotIn("story-1", story_context_service._story_context_locks)
        self.assertIn("story-2", story_context_service._story_context_locks)


class StoryAssetHelperTests(unittest.TestCase):
    def test_character_asset_record_preserves_compatibility_fields(self):
        record = build_character_asset_record(
            image_url="/media/characters/li_ming.png",
            image_path="media/characters/li_ming.png",
            prompt="Standard three-view character turnaround sheet for Li Ming",
            existing={"visual_dna": "young man, short black hair"},
        )

        self.assertEqual(record["prompt"], "Standard three-view character turnaround sheet for Li Ming")
        self.assertEqual(record["design_prompt"], "Standard three-view character turnaround sheet for Li Ming")
        self.assertEqual(record["asset_kind"], "character_sheet")
        self.assertEqual(record["framing"], "three_view")
        self.assertEqual(record["visual_dna"], "young man, short black hair")

    def test_character_asset_record_ignores_whitespace_visual_dna_updates(self):
        record = build_character_asset_record(
            image_url="/media/characters/li_ming.png",
            image_path="media/characters/li_ming.png",
            prompt="Standard three-view character turnaround sheet for Li Ming",
            existing={"visual_dna": "young man, short black hair"},
            visual_dna="   ",
        )

        self.assertEqual(record["visual_dna"], "young man, short black hair")

    def test_character_asset_getters_prefer_new_fields_and_keep_visual_dna(self):
        character_images = {
            "Li Ming": {
                "prompt": "legacy prompt",
                "design_prompt": "new design prompt",
                "visual_dna": "young man, short black hair",
            }
        }

        self.assertEqual(get_character_design_prompt(character_images, "Li Ming"), "new design prompt")
        self.assertEqual(get_character_visual_dna(character_images, "Li Ming"), "young man, short black hair")

    def test_character_asset_getters_accept_legacy_name_key_when_loading_by_id(self):
        character_images = {
            "Li Ming": {
                "prompt": "legacy prompt",
                "design_prompt": "legacy design prompt",
                "visual_dna": "young man, short black hair",
                "character_name": "Li Ming",
            }
        }

        self.assertEqual(
            get_character_design_prompt(character_images, "char_li_ming", name="Li Ming"),
            "legacy design prompt",
        )
        self.assertEqual(
            get_character_visual_dna(character_images, "char_li_ming", name="Li Ming"),
            "young man, short black hair",
        )


class StoryRepositoryHelperTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_meta_cache_helpers_preserve_other_meta_keys(self):
        async with self.session_factory() as session:
            await repo.save_story(
                session,
                "story-cache-test",
                {"idea": "test", "genre": "古风", "tone": "沉稳", "meta": {"theme": "雨夜古镇"}},
            )
            await repo.upsert_story_meta_cache(
                session,
                "story-cache-test",
                "character_appearance_cache",
                {"李明": {"body": "short black hair", "clothing": "dark blue robe"}},
            )

            story = await repo.get_story(session, "story-cache-test")
            self.assertEqual(story["meta"]["theme"], "雨夜古镇")
            self.assertIn("character_appearance_cache", story["meta"])

            await repo.invalidate_story_consistency_cache(session, "story-cache-test", appearance=True)
            updated_story = await repo.get_story(session, "story-cache-test")
            self.assertEqual(updated_story["meta"]["theme"], "雨夜古镇")
            self.assertNotIn("character_appearance_cache", updated_story["meta"])


class ImageRouterFallbackTests(unittest.TestCase):
    def test_basic_payload_keeps_negative_prompt_separate_from_art_style(self):
        payload = _build_basic_payload(
            {
                "shot_id": "scene1_shot1",
                "image_prompt": "Medium shot. A hero stands in the rain.",
                "negative_prompt": "blur, low quality",
            },
            "cinematic watercolor",
        )

        self.assertEqual(payload["negative_prompt"], "blur, low quality")
        self.assertIn("cinematic watercolor", payload["image_prompt"])

    def test_basic_payload_preserves_reference_images(self):
        payload = _build_basic_payload(
            {
                "shot_id": "scene1_shot1",
                "image_prompt": "Medium shot. A hero stands in the rain.",
                "reference_images": [
                    {"kind": "character", "image_url": "/media/characters/hero.png"},
                    {"kind": "scene", "image_url": "/media/episodes/env.png"},
                ],
            },
            "cinematic watercolor",
        )

        self.assertEqual(len(payload["reference_images"]), 2)


if __name__ == "__main__":
    unittest.main()
