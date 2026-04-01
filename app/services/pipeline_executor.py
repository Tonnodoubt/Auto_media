"""
自动化流水线执行器 - 支持多种生成策略
"""
import asyncio
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.storyboard import Shot
from app.schemas.pipeline import GenerationStrategy, PipelineStatus
from app.services import tts, image, video, ffmpeg
from app.services.storyboard import parse_script_to_storyboard
from app.services import story_repository as repo
from app.core.story_context import StoryContext, build_character_reference_anchor, build_generation_payload, infer_shot_view_hint
from app.core.api_keys import inject_art_style
from app.core.pipeline_runtime import (
    build_runtime_strategy_metadata,
    get_runtime_strategy_note,
)
from app.services.storyboard_state import (
    persist_storyboard_generation_state,
    serialize_shot_for_storage,
)
from app.services.story_context_service import prepare_story_context

logger = logging.getLogger(__name__)


class PipelineExecutor:
    """流水线执行器 - 处理完整的视频生成流程"""

    def __init__(
        self,
        project_id: str,
        pipeline_id: str,
        db: AsyncSession,
        *,
        story_id: Optional[str] = None,
    ):
        self.project_id = project_id
        self.story_id = story_id or project_id
        self.pipeline_id = pipeline_id
        self.db = db
        self.shots: List[Shot] = []
        self.results: List[dict] = []
        self.base_url: str = ""
        self.character_info: Optional[dict] = None
        self.art_style: str = ""
        self.story_context: Optional[StoryContext] = None
        self.story: Optional[dict] = None
        self.strategy: GenerationStrategy = GenerationStrategy.SEPARATED
        self.runtime_strategy_metadata: dict[str, object] = {}
        self.tts_results: dict[str, dict[str, Any]] = {}
        self.image_results: dict[str, dict[str, Any]] = {}
        self.video_results: dict[str, dict[str, Any]] = {}
        self._latest_generated_files: dict[str, Any] | None = None

    def _serialize_storyboard_shots(self) -> list[dict[str, Any]]:
        return [serialize_shot_for_storage(shot) for shot in self.shots]

    def _build_generated_files_snapshot(self) -> dict[str, Any]:
        snapshot: dict[str, Any] = {
            "meta": dict(self.runtime_strategy_metadata),
        }
        storyboard_shots = self._serialize_storyboard_shots()
        if storyboard_shots:
            snapshot["storyboard"] = {"shots": storyboard_shots}
        if self.tts_results:
            snapshot["tts"] = deepcopy(self.tts_results)
        if self.image_results:
            snapshot["images"] = deepcopy(self.image_results)
        if self.video_results:
            snapshot["videos"] = deepcopy(self.video_results)
        if self.results:
            snapshot["shots"] = [deepcopy(result) for result in self.results]
        return snapshot

    def _refresh_video_results_from_stitched_outputs(self) -> None:
        for result in self.results:
            shot_id = str(result.get("shot_id", "")).strip()
            if not shot_id:
                continue
            entry = deepcopy(dict(self.video_results.get(shot_id) or {}))
            video_url = str(result.get("final_video_url") or result.get("video_url") or "").strip()
            if video_url:
                entry["shot_id"] = shot_id
                entry["video_url"] = video_url
            video_path = str(result.get("video_path") or entry.get("video_path") or "").strip()
            if video_path:
                entry["video_path"] = video_path
            if entry:
                self.video_results[shot_id] = entry

    async def _persist_storyboard_generation_snapshot(self, generated_files: dict[str, Any]) -> None:
        if self.db is None or not self.story_id:
            return
        try:
            story = await repo.get_story(self.db, self.story_id)
            if not story:
                return
            await persist_storyboard_generation_state(
                self.db,
                story_id=self.story_id,
                story=story,
                shots=self._serialize_storyboard_shots(),
                partial_shots=False,
                generated_files=generated_files,
                pipeline_id=self.pipeline_id,
                project_id=self.project_id,
                replace_generated_files=True,
                prune_generated_files_to_shots=True,
                clear_final_video=True,
            )
        except Exception:
            try:
                await self.db.rollback()
            except Exception:
                logger.exception(
                    "Auto pipeline storyboard persistence rollback failed project=%s pipeline_id=%s story_id=%s",
                    self.project_id,
                    self.pipeline_id,
                    self.story_id,
                )
            logger.exception(
                "Auto pipeline storyboard persistence failed project=%s pipeline_id=%s story_id=%s",
                self.project_id,
                self.pipeline_id,
                self.story_id,
            )

    async def run_full_pipeline(
        self,
        script: str,
        strategy: GenerationStrategy,
        provider: str,
        model: Optional[str],
        voice: str,
        image_model: str,
        video_model: str,
        base_url: str,
        llm_api_key: str = "",
        llm_base_url: str = "",
        image_api_key: str = "",
        image_base_url: str = "",
        video_api_key: str = "",
        video_base_url: str = "",
        video_provider: str = "dashscope",
        character_info: Optional[dict] = None,
        art_style: str = "",
        story_id: Optional[str] = None,
    ):
        """执行完整的生成流水线"""
        self.base_url = base_url
        self.character_info = character_info
        self.art_style = art_style
        self.strategy = strategy
        self.runtime_strategy_metadata = build_runtime_strategy_metadata(strategy)
        self.shots = []
        self.results = []
        self.story_context = None
        self.story = None
        self.tts_results = {}
        self.image_results = {}
        self.video_results = {}
        effective_story_id = (story_id or self.story_id or "").strip()
        if effective_story_id:
            self.story_id = effective_story_id
            self.story, self.story_context = await self._prepare_story_context(
                effective_story_id,
                provider=provider,
                model=model or "",
                api_key=llm_api_key,
                base_url=llm_base_url,
            )
        self._latest_generated_files = {
            "meta": dict(self.runtime_strategy_metadata),
        }
        try:
            # Step 1: 分镜解析
            await self._update_state(
                PipelineStatus.STORYBOARD,
                5,
                "解析分镜中",
                {"step": "storyboard", "current": 0, "total": 100, "message": "正在解析剧本..."},
            )
            self.shots, _ = await parse_script_to_storyboard(
                script, provider, model, api_key=llm_api_key, base_url=llm_base_url,
                character_info=character_info,
                character_section_override=self.story_context.clean_character_section if self.story_context else None,
            )

            if not self.shots:
                raise ValueError("分镜解析失败：没有生成任何镜头")

            await self._update_state(
                PipelineStatus.STORYBOARD,
                15,
                f"分镜解析完成，共 {len(self.shots)} 个镜头",
                {"step": "storyboard", "current": len(self.shots), "total": len(self.shots), "message": "分镜解析完成"},
                generated_files=self._build_generated_files_snapshot(),
            )

            await asyncio.sleep(0.5)

            # 根据策略执行
            if strategy == GenerationStrategy.SEPARATED:
                await self._run_separated_strategy(
                    voice, image_model, video_model, base_url, image_api_key, image_base_url, video_api_key, video_base_url, video_provider
                )
            elif strategy == GenerationStrategy.CHAINED:
                await self._run_chained_strategy(
                    voice, image_model, video_model, base_url, image_api_key, image_base_url, video_api_key, video_base_url, video_provider
                )
            else:
                await self._run_integrated_strategy(
                    image_model, video_model, base_url, image_api_key, image_base_url, video_api_key, video_base_url, video_provider
                )
            # Step 5: FFmpeg 合成（分离式和链式策略需要）
            if strategy in (GenerationStrategy.SEPARATED, GenerationStrategy.CHAINED):
                await self._stitch_videos()

            # 完成
            await self._update_state(
                PipelineStatus.COMPLETE,
                100,
                "视频生成完成",
                generated_files=self._build_generated_files_snapshot(),
            )

        except Exception as e:
            await self._update_state(PipelineStatus.FAILED, 0, "生成失败", error=str(e))
            raise

    async def _prepare_story_context(
        self,
        effective_story_id: str,
        *,
        provider: str,
        model: str,
        api_key: str,
        base_url: str,
    ):
        try:
            return await prepare_story_context(
                self.db,
                effective_story_id,
                provider=provider,
                model=model,
                api_key=api_key,
                base_url=base_url,
            )
        except Exception as exc:
            await self._update_state(PipelineStatus.FAILED, 0, "Story context failed", error=str(exc))
            raise

    async def _run_separated_strategy(
        self,
        voice: str,
        image_model: str,
        video_model: str,
        base_url: str,
        image_api_key: str = "",
        image_base_url: str = "",
        video_api_key: str = "",
        video_base_url: str = "",
        video_provider: str = "dashscope",
    ):
        """
        策略 A: 分离式
        TTS → 图片 → 图生视频
        最后通过 FFmpeg 合成音视频
        """
        total = len(self.shots)

        # Step 2: TTS 生成
        await self._update_state(
            PipelineStatus.GENERATING_ASSETS,
            20,
            "生成语音中",
            {"step": "tts", "current": 0, "total": total, "message": "正在生成语音..."},
        )

        tts_results = await tts.generate_tts_batch(
            shots=[{
                "shot_id": s.shot_id,
                "dialogue": s.audio_reference.content if s.audio_reference and s.audio_reference.type in ("dialogue", "narration") else None,
            } for s in self.shots],
            voice=voice,
        )
        tts_map = {r["shot_id"]: r for r in tts_results}
        self.tts_results = {
            shot_id: deepcopy(result)
            for shot_id, result in tts_map.items()
            if shot_id
        }

        await self._update_state(
            PipelineStatus.GENERATING_ASSETS,
            40,
            f"语音生成完成 {len(tts_results)} 个",
            {"step": "tts", "current": total, "total": total, "message": "语音生成完成"},
            generated_files=self._build_generated_files_snapshot(),
        )

        await asyncio.sleep(0.3)

        # Step 3: 图片生成
        await self._update_state(
            PipelineStatus.GENERATING_ASSETS,
            45,
            "生成图片中",
            {"step": "image", "current": 0, "total": total, "message": "正在生成图片..."},
        )

        image_results = await image.generate_images_batch(
            shots=[self._build_generation_payload(s) for s in self.shots],
            model=image_model,
            image_api_key=image_api_key,
            image_base_url=image_base_url,
            art_style=self.art_style,
        )
        image_map = {r["shot_id"]: r for r in image_results}
        self.image_results = {
            shot_id: deepcopy(result)
            for shot_id, result in image_map.items()
            if shot_id
        }

        await self._update_state(
            PipelineStatus.GENERATING_ASSETS,
            65,
            f"图片生成完成 {len(image_results)} 个",
            {"step": "image", "current": total, "total": total, "message": "图片生成完成"},
            generated_files=self._build_generated_files_snapshot(),
        )

        await asyncio.sleep(0.3)

        # Step 4: 图生视频
        await self._update_state(
            PipelineStatus.RENDERING_VIDEO,
            70,
            "生成视频中",
            {"step": "video", "current": 0, "total": total, "message": "正在生成视频..."},
        )

        video_shots = []
        for shot in self.shots:
            if shot.shot_id not in image_map:
                continue
            payload = self._build_generation_payload(shot)
            video_shots.append(
                {
                    "shot_id": shot.shot_id,
                    "image_url": image_map[shot.shot_id]["image_url"],
                    "final_video_prompt": payload["final_video_prompt"],
                    "negative_prompt": payload.get("negative_prompt", ""),
                    "reference_images": payload.get("reference_images", []),
                }
            )

        video_results = await video.generate_videos_batch(
            shots=video_shots,
            base_url=base_url,
            model=video_model,
            video_api_key=video_api_key,
            video_base_url=video_base_url,
            video_provider=video_provider,
            art_style=self.art_style,
        )
        video_map = {r["shot_id"]: r for r in video_results}
        self.video_results = {
            shot_id: deepcopy(result)
            for shot_id, result in video_map.items()
            if shot_id
        }

        # 组装结果
        for shot in self.shots:
            result = {
                "shot_id": shot.shot_id,
                "audio_url": tts_map.get(shot.shot_id, {}).get("audio_url"),
                "audio_duration": tts_map.get(shot.shot_id, {}).get("duration_seconds"),
                "image_url": image_map.get(shot.shot_id, {}).get("image_url"),
                "video_url": video_map.get(shot.shot_id, {}).get("video_url"),
            }
            self.results.append(result)

        await self._update_state(
            PipelineStatus.RENDERING_VIDEO,
            85,
            f"视频生成完成 {len(video_results)} 个",
            {"step": "video", "current": total, "total": total, "message": "视频生成完成"},
            generated_files=self._build_generated_files_snapshot(),
        )

    @staticmethod
    def _enhance_prompt_with_character(visual_prompt: str, character_info: Optional[dict], shot: Optional[dict | Shot] = None) -> str:
        """
        角色 prompt 增强：检查 visual_prompt 中是否提及角色名，
        如果匹配到，将提炼后的角色外貌锚点与轻量视角提示拼接到 visual_prompt 尾部。

        Args:
            visual_prompt: 原始视觉提示词
            character_info: 角色信息 dict，包含 characters 和 character_images

        Returns:
            增强后的 visual_prompt
        """
        if not character_info:
            return visual_prompt

        characters = character_info.get("characters", [])
        character_images = character_info.get("character_images", {})

        if not characters:
            return visual_prompt

        additions = []
        for char in characters:
            char_id = char.get("id", "")
            char_name = char.get("name", "")
            if not char_name:
                continue
            # 检查角色名是否出现在 visual_prompt 中（不区分大小写）
            if char_name.lower() not in visual_prompt.lower():
                continue
            reference_anchor = build_character_reference_anchor(
                character_images,
                char_name,
                character_id=char_id,
                description=str(char.get("description", "")),
            )
            if reference_anchor:
                effective_shot = shot or {
                    "storyboard_description": visual_prompt,
                    "image_prompt": visual_prompt,
                    "final_video_prompt": visual_prompt,
                    "visual_elements": {
                        "subject_and_clothing": visual_prompt,
                        "action_and_expression": visual_prompt,
                    },
                }
                view_hint = infer_shot_view_hint(char_name, effective_shot)
                suffix = f"; {view_hint}" if view_hint else ""
                additions.append(f"[Character {char_name}: {reference_anchor}{suffix}]")

        if not additions:
            return visual_prompt
        return f"{visual_prompt} {' '.join(additions)}"

    @classmethod
    def _build_image_prompts(cls, shot: Shot, character_info: Optional[dict]) -> dict:
        """构建静态首帧提示词，并统一注入角色外观增强。"""
        prompts = {
            "shot_id": shot.shot_id,
            "image_prompt": cls._enhance_prompt_with_character(
                shot.image_prompt or shot.final_video_prompt,
                character_info,
                shot,
            ),
        }
        return prompts

    @classmethod
    def _build_video_prompt(cls, shot: Shot, character_info: Optional[dict]) -> str:
        """构建视频阶段 prompt, 保持与图片阶段一致的角色增强逻辑。"""
        return cls._enhance_prompt_with_character(
            shot.final_video_prompt,
            character_info,
            shot,
        )

    def _build_generation_payload(self, shot: Shot) -> dict:
        payload = build_generation_payload(
            shot,
            self.story_context,
            art_style=self.art_style,
            story=self.story,
        )
        if self.story_context:
            return payload
        if self.story:
            story_character_info = self.character_info
            if not story_character_info and isinstance(self.story, dict):
                characters = self.story.get("characters", [])
                character_images = self.story.get("character_images", {})
                if characters:
                    story_character_info = {
                        "characters": characters,
                        "character_images": character_images or {},
                        "meta": self.story.get("meta") or {},
                    }
            fallback_payload = {
                "shot_id": payload.get("shot_id", shot.shot_id),
                "image_prompt": self._enhance_prompt_with_character(
                    payload["image_prompt"],
                    story_character_info,
                    shot,
                ),
                "final_video_prompt": self._enhance_prompt_with_character(
                    payload["final_video_prompt"],
                    story_character_info,
                    shot,
                ),
            }
            negative_prompt = payload.get("negative_prompt")
            if negative_prompt:
                fallback_payload["negative_prompt"] = negative_prompt
            reference_images = payload.get("reference_images")
            if reference_images:
                fallback_payload["reference_images"] = reference_images
            source_scene_key = payload.get("source_scene_key")
            if source_scene_key:
                fallback_payload["source_scene_key"] = source_scene_key
            return fallback_payload

        # Fallback for legacy no-story-id flows. Keep the old enhancement path available
        # until all entry points consistently pass through StoryContext.
        legacy_payload = self._build_image_prompts(shot, self.character_info)
        legacy_payload["image_prompt"] = inject_art_style(legacy_payload["image_prompt"], self.art_style)
        legacy_payload["final_video_prompt"] = inject_art_style(
            self._build_video_prompt(shot, self.character_info),
            self.art_style,
        )
        return legacy_payload

    async def _run_chained_strategy(
        self,
        voice: str,
        image_model: str,
        video_model: str,
        base_url: str,
        image_api_key: str = "",
        image_base_url: str = "",
        video_api_key: str = "",
        video_base_url: str = "",
        video_provider: str = "dashscope",
    ):
        """
        策略 C: 按场景分组执行
        TTS -> 首帧生图 -> 单首帧 I2V
        保留场景维度的执行节奏，但不再做尾帧传递
        """
        total = len(self.shots)

        # Step 2: TTS 生成（与分离式相同）
        await self._update_state(
            PipelineStatus.GENERATING_ASSETS,
            20,
            "生成语音中",
            {"step": "tts", "current": 0, "total": total, "message": "正在生成语音..."},
        )

        tts_results = await tts.generate_tts_batch(
            shots=[{
                "shot_id": s.shot_id,
                "dialogue": s.audio_reference.content if s.audio_reference and s.audio_reference.type in ("dialogue", "narration") else None,
            } for s in self.shots],
            voice=voice,
        )
        tts_map = {r["shot_id"]: r for r in tts_results}
        self.tts_results = {
            shot_id: deepcopy(result)
            for shot_id, result in tts_map.items()
            if shot_id
        }

        await self._update_state(
            PipelineStatus.GENERATING_ASSETS,
            35,
            f"语音生成完成 {len(tts_results)} 个",
            {"step": "tts", "current": total, "total": total, "message": "语音生成完成"},
            generated_files=self._build_generated_files_snapshot(),
        )

        # Step 3+4: 链式图片+视频生成
        await self._update_state(
            PipelineStatus.RENDERING_VIDEO,
            40,
            "链式生成视频中",
            {"step": "video_chained", "current": 0, "total": total, "message": "正在链式生成视频..."},
        )

        # 构建 shots 数据并增强 prompt
        shots_data = []
        for s in self.shots:
            shots_data.append(self._build_generation_payload(s))

        scene_groups = video.group_shots_by_scene(shots_data)
        scene_names = list(scene_groups.keys())

        async def on_progress(scene_key: str, current_idx: int, scene_total: int, shot_id: str):
            scene_num = scene_names.index(scene_key) + 1 if scene_key in scene_names else 0
            completed = sum(
                len(scene_groups[sk]) for sk in scene_names[:scene_names.index(scene_key)]
            ) + current_idx if scene_key in scene_names else current_idx
            progress = 40 + int(45 * completed / total)
            await self._update_state(
                PipelineStatus.RENDERING_VIDEO,
                progress,
                f"场景{scene_num}: 正在生成第 {current_idx + 1}/{scene_total} 个镜头",
                {"step": "video_chained", "current": completed, "total": total,
                 "message": f"场景{scene_num}: 正在生成第 {current_idx + 1}/{scene_total} 个镜头"},
            )

        chained_results = await video.generate_videos_chained(
            shots=shots_data,
            base_url=base_url,
            model=video_model,
            video_api_key=video_api_key,
            video_base_url=video_base_url,
            video_provider=video_provider,
            image_model=image_model,
            image_api_key=image_api_key,
            image_base_url=image_base_url,
            on_progress=on_progress,
        )
        chained_map = {r["shot_id"]: r for r in chained_results}
        self.image_results = {
            str(result.get("shot_id", "")).strip(): {
                "shot_id": str(result.get("shot_id", "")).strip(),
                "image_url": result.get("image_url"),
                "image_path": result.get("image_path"),
            }
            for result in chained_results
            if str(result.get("shot_id", "")).strip()
        }
        self.video_results = {
            str(result.get("shot_id", "")).strip(): {
                "shot_id": str(result.get("shot_id", "")).strip(),
                "video_url": result.get("video_url"),
                "video_path": result.get("video_path"),
            }
            for result in chained_results
            if str(result.get("shot_id", "")).strip()
        }

        # 组装结果（格式与 separated 一致）
        for shot in self.shots:
            result = {
                "shot_id": shot.shot_id,
                "audio_url": tts_map.get(shot.shot_id, {}).get("audio_url"),
                "audio_duration": tts_map.get(shot.shot_id, {}).get("duration_seconds"),
                "image_url": chained_map.get(shot.shot_id, {}).get("image_url"),
                "video_url": chained_map.get(shot.shot_id, {}).get("video_url"),
            }
            self.results.append(result)

        await self._update_state(
            PipelineStatus.RENDERING_VIDEO,
            85,
            f"链式视频生成完成 {len(chained_results)} 个",
            {"step": "video_chained", "current": total, "total": total, "message": "链式视频生成完成"},
            generated_files=self._build_generated_files_snapshot(),
        )

    async def _run_integrated_strategy(
        self,
        image_model: str,
        video_model: str,
        base_url: str,
        image_api_key: str = "",
        image_base_url: str = "",
        video_api_key: str = "",
        video_base_url: str = "",
        video_provider: str = "dashscope",
    ):
        """
        策略 B: 一体式
        图片 → 视频语音一体生成
        不需要 TTS 和 FFmpeg 合成
        """
        total = len(self.shots)

        # Step 2: 图片生成
        await self._update_state(
            PipelineStatus.GENERATING_ASSETS,
            20,
            "生成图片中",
            {"step": "image", "current": 0, "total": total, "message": "正在生成图片..."},
        )

        image_results = await image.generate_images_batch(
            shots=[self._build_generation_payload(s) for s in self.shots],
            model=image_model,
            image_api_key=image_api_key,
            image_base_url=image_base_url,
            art_style=self.art_style,
        )
        image_map = {r["shot_id"]: r for r in image_results}
        self.image_results = {
            shot_id: deepcopy(result)
            for shot_id, result in image_map.items()
            if shot_id
        }

        await self._update_state(
            PipelineStatus.GENERATING_ASSETS,
            50,
            f"图片生成完成 {len(image_results)} 个",
            {"step": "image", "current": total, "total": total, "message": "图片生成完成"},
            generated_files=self._build_generated_files_snapshot(),
        )

        await asyncio.sleep(0.3)

        # Step 3: 视频语音一体生成
        await self._update_state(
            PipelineStatus.RENDERING_VIDEO,
            55,
            "integrated 策略已降级为图生视频 fallback",
            {
                "step": "video_integrated",
                "current": 0,
                "total": total,
                "message": "正在以图生视频 fallback 方式执行 integrated 策略，不包含语音一体化。",
            },
        )

        # TODO: 调用支持视频语音一体生成的 API
        # 目前先复用现有的图生视频接口
        video_shots = []
        for shot in self.shots:
            if shot.shot_id not in image_map:
                continue
            payload = self._build_generation_payload(shot)
            video_shots.append(
                {
                    "shot_id": shot.shot_id,
                    "image_url": image_map[shot.shot_id]["image_url"],
                    "final_video_prompt": payload["final_video_prompt"],
                    "negative_prompt": payload.get("negative_prompt", ""),
                    "reference_images": payload.get("reference_images", []),
                }
            )

        video_results = await video.generate_videos_batch(
            shots=video_shots,
            base_url=base_url,
            model=video_model,
            video_api_key=video_api_key,
            video_base_url=video_base_url,
            video_provider=video_provider,
            art_style=self.art_style,
        )
        video_map = {r["shot_id"]: r for r in video_results}
        self.video_results = {
            shot_id: deepcopy(result)
            for shot_id, result in video_map.items()
            if shot_id
        }

        # 组装结果
        for shot in self.shots:
            result = {
                "shot_id": shot.shot_id,
                "image_url": image_map.get(shot.shot_id, {}).get("image_url"),
                "video_url": video_map.get(shot.shot_id, {}).get("video_url"),
                # 一体式生成时，音频已嵌入视频
                "audio_url": None,
                "audio_duration": None,
            }
            self.results.append(result)

        await self._update_state(
            PipelineStatus.RENDERING_VIDEO,
            85,
            get_runtime_strategy_note(self.strategy) or "integrated fallback 执行完成",
            {
                "step": "video_integrated",
                "current": total,
                "total": total,
                "message": "integrated 策略 fallback 执行完成",
            },
            generated_files=self._build_generated_files_snapshot(),
        )

    async def _stitch_videos(self):
        """使用 FFmpeg 合成音视频（仅分离式策略需要）"""
        total = len(self.results)
        await self._update_state(
            PipelineStatus.STITCHING,
            90,
            "合成音视频中",
            {"step": "stitch", "current": 0, "total": total, "message": "正在合成..."},
        )

        self.results = await ffmpeg.stitch_batch(self.results, base_url=self.base_url)
        self._refresh_video_results_from_stitched_outputs()

        stitched = sum(1 for r in self.results if r.get("final_video_url"))
        await self._update_state(
            PipelineStatus.STITCHING,
            95,
            f"音视频合成完成（{stitched}/{total}）",
            {"step": "stitch", "current": total, "total": total, "message": "合成完成"},
            generated_files=self._build_generated_files_snapshot(),
        )

    async def _update_state(
        self,
        status: PipelineStatus,
        progress: int,
        current_step: str,
        progress_detail: Optional[dict] = None,
        error: Optional[str] = None,
        generated_files: Optional[dict] = None,
    ):
        """更新流水线状态到数据库"""
        effective_generated_files = deepcopy(generated_files) if generated_files is not None else deepcopy(self._latest_generated_files)
        if generated_files is not None:
            self._latest_generated_files = deepcopy(generated_files)
        await repo.save_pipeline(self.db, self.pipeline_id, self.story_id, {
            "status": status,
            "progress": progress,
            "current_step": current_step,
            "error": error,
            "progress_detail": progress_detail,
            "generated_files": effective_generated_files,
        })
        if generated_files is not None:
            await self._persist_storyboard_generation_snapshot(generated_files)
