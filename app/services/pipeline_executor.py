"""
自动化流水线执行器 - 支持多种生成策略
"""
import asyncio
from pathlib import Path
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.storyboard import Shot
from app.schemas.pipeline import GenerationStrategy, PipelineStatus
from app.services import tts, image, video, ffmpeg
from app.services.storyboard import parse_script_to_storyboard
from app.services import story_repository as repo


class PipelineExecutor:
    """流水线执行器 - 处理完整的视频生成流程"""

    def __init__(self, project_id: str, pipeline_id: str, db: AsyncSession):
        self.project_id = project_id
        self.pipeline_id = pipeline_id
        self.db = db
        self.shots: List[Shot] = []
        self.results: List[dict] = []
        self.base_url: str = ""
        self.character_info: Optional[dict] = None

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
    ):
        """执行完整的生成流水线"""
        self.base_url = base_url
        self.character_info = character_info
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
            )

            if not self.shots:
                raise ValueError("分镜解析失败：没有生成任何镜头")

            await self._update_state(
                PipelineStatus.STORYBOARD,
                15,
                f"分镜解析完成，共 {len(self.shots)} 个镜头",
                {"step": "storyboard", "current": len(self.shots), "total": len(self.shots), "message": "分镜解析完成"},
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
                generated_files={"shots": self.results},
            )

        except Exception as e:
            await self._update_state(PipelineStatus.FAILED, 0, "生成失败", error=str(e))
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

        await self._update_state(
            PipelineStatus.GENERATING_ASSETS,
            40,
            f"语音生成完成 {len(tts_results)} 个",
            {"step": "tts", "current": total, "total": total, "message": "语音生成完成"},
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
            shots=[
                {
                    "shot_id": s.shot_id,
                    "visual_prompt": self._enhance_prompt_with_character(s.final_video_prompt, self.character_info),
                }
                for s in self.shots
            ],
            model=image_model,
            image_api_key=image_api_key,
            image_base_url=image_base_url,
        )
        image_map = {r["shot_id"]: r for r in image_results}

        await self._update_state(
            PipelineStatus.GENERATING_ASSETS,
            65,
            f"图片生成完成 {len(image_results)} 个",
            {"step": "image", "current": total, "total": total, "message": "图片生成完成"},
        )

        await asyncio.sleep(0.3)

        # Step 4: 图生视频
        await self._update_state(
            PipelineStatus.RENDERING_VIDEO,
            70,
            "生成视频中",
            {"step": "video", "current": 0, "total": total, "message": "正在生成视频..."},
        )

        video_results = await video.generate_videos_batch(
            shots=[
                {
                    "shot_id": s.shot_id,
                    "image_url": image_map[s.shot_id]["image_url"],
                    "final_video_prompt": s.final_video_prompt,
                }
                for s in self.shots
                if s.shot_id in image_map
            ],
            base_url=base_url,
            model=video_model,
            video_api_key=video_api_key,
            video_base_url=video_base_url,
            video_provider=video_provider,
        )
        video_map = {r["shot_id"]: r for r in video_results}

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
        )

    @staticmethod
    def _enhance_prompt_with_character(visual_prompt: str, character_info: Optional[dict]) -> str:
        """
        角色 prompt 增强：检查 visual_prompt 中是否提及角色名，
        如果匹配到，将角色人设图的 portrait prompt 拼接到 visual_prompt 尾部。

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

        if not characters or not character_images:
            return visual_prompt

        additions = []
        for char in characters:
            char_name = char.get("name", "")
            if not char_name:
                continue
            # 检查角色名是否出现在 visual_prompt 中（不区分大小写）
            if char_name.lower() not in visual_prompt.lower():
                continue
            # 从 character_images 中查找该角色的 prompt
            char_img = character_images.get(char_name, {})
            portrait_prompt = char_img.get("prompt", "")
            if portrait_prompt:
                additions.append(f"[Character {char_name}: {portrait_prompt}]")

        if not additions:
            return visual_prompt
        return f"{visual_prompt} {' '.join(additions)}"

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
        策略 C: 链式
        TTS → 场景内链式帧传递（首帧独立生图 → 图到视频 → 提取最后一帧 → 下一帧）
        不同场景之间并行，同一场景内串行
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

        await self._update_state(
            PipelineStatus.GENERATING_ASSETS,
            35,
            f"语音生成完成 {len(tts_results)} 个",
            {"step": "tts", "current": total, "total": total, "message": "语音生成完成"},
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
            enhanced_prompt = self._enhance_prompt_with_character(s.final_video_prompt, self.character_info)
            shots_data.append({
                "shot_id": s.shot_id,
                "final_video_prompt": enhanced_prompt,
            })

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
            shots=[{"shot_id": s.shot_id, "visual_prompt": s.final_video_prompt} for s in self.shots],
            model=image_model,
            image_api_key=image_api_key,
            image_base_url=image_base_url,
        )
        image_map = {r["shot_id"]: r for r in image_results}

        await self._update_state(
            PipelineStatus.GENERATING_ASSETS,
            50,
            f"图片生成完成 {len(image_results)} 个",
            {"step": "image", "current": total, "total": total, "message": "图片生成完成"},
        )

        await asyncio.sleep(0.3)

        # Step 3: 视频语音一体生成
        await self._update_state(
            PipelineStatus.RENDERING_VIDEO,
            55,
            "生成视频和语音中",
            {"step": "video_integrated", "current": 0, "total": total, "message": "正在生成视频和语音..."},
        )

        # TODO: 调用支持视频语音一体生成的 API
        # 目前先复用现有的图生视频接口
        video_results = await video.generate_videos_batch(
            shots=[
                {
                    "shot_id": s.shot_id,
                    "image_url": image_map[s.shot_id]["image_url"],
                    "final_video_prompt": s.final_video_prompt,
                }
                for s in self.shots
                if s.shot_id in image_map
            ],
            base_url=base_url,
            model=video_model,
            video_api_key=video_api_key,
            video_base_url=video_base_url,
            video_provider=video_provider,
        )
        video_map = {r["shot_id"]: r for r in video_results}

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

        stitched = sum(1 for r in self.results if r.get("final_video_url"))
        await self._update_state(
            PipelineStatus.STITCHING,
            95,
            f"音视频合成完成（{stitched}/{total}）",
            {"step": "stitch", "current": total, "total": total, "message": "合成完成"},
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
        await repo.save_pipeline(self.db, self.pipeline_id, self.project_id, {
            "status": status,
            "progress": progress,
            "current_step": current_step,
            "error": error,
            "progress_detail": progress_detail,
            "generated_files": generated_files,
        })
