"""
自动化流水线执行器 - 支持多种生成策略
"""
import asyncio
from pathlib import Path
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.storyboard import Shot
from app.schemas.pipeline import GenerationStrategy, PipelineStatus
from app.services import tts, image, video
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
    ):
        """执行完整的生成流水线"""
        try:
            # Step 1: 分镜解析
            await self._update_state(
                PipelineStatus.STORYBOARD,
                5,
                "解析分镜中",
                {"step": "storyboard", "current": 0, "total": 100, "message": "正在解析剧本..."},
            )
            self.shots = await parse_script_to_storyboard(script, provider, model)

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
                    voice, image_model, video_model, base_url
                )
            else:
                await self._run_integrated_strategy(
                    image_model, video_model, base_url
                )

            # Step 5: FFmpeg 合成（仅分离策略需要）
            if strategy == GenerationStrategy.SEPARATED:
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
            shots=[{"shot_id": s.shot_id, "dialogue": s.dialogue} for s in self.shots],
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
            shots=[{"shot_id": s.shot_id, "visual_prompt": s.visual_prompt} for s in self.shots],
            model=image_model,
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
                    "visual_prompt": s.visual_prompt,
                    "camera_motion": s.camera_motion,
                }
                for s in self.shots
                if s.shot_id in image_map
            ],
            base_url=base_url,
            model=video_model,
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

    async def _run_integrated_strategy(
        self,
        image_model: str,
        video_model: str,
        base_url: str,
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
            shots=[{"shot_id": s.shot_id, "visual_prompt": s.visual_prompt} for s in self.shots],
            model=image_model,
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
                    "visual_prompt": f"{s.visual_prompt} {s.camera_motion}",
                    "camera_motion": s.camera_motion,
                }
                for s in self.shots
                if s.shot_id in image_map
            ],
            base_url=base_url,
            model=video_model,
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

        await self._update_state(
            PipelineStatus.COMPLETE,
            100,
            f"视频生成完成 {len(video_results)} 个（含音频）",
            {"step": "video_integrated", "current": total, "total": total, "message": "视频生成完成"},
        )

    async def _stitch_videos(self):
        """使用 FFmpeg 合成音视频（仅分离式策略需要）"""
        await self._update_state(
            PipelineStatus.STITCHING,
            90,
            "合成音视频中",
            {"step": "stitch", "current": 0, "total": len(self.results), "message": "正在合成..."},
        )

        # TODO: 实现 FFmpeg 合成逻辑
        # 目前先跳过，直接返回分离的视频和音频文件
        await asyncio.sleep(1)

        await self._update_state(
            PipelineStatus.STITCHING,
            95,
            "音视频合成完成",
            {"step": "stitch", "current": len(self.results), "total": len(self.results), "message": "合成完成"},
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
