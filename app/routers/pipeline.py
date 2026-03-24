from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Body, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db, AsyncSessionLocal
from app.core.config import settings as _cfg
from app.core.api_keys import extract_api_keys, resolve_image_key, image_config_dep, video_config_dep, llm_config_dep, validate_user_base_url, resolve_llm_config
from app.schemas.pipeline import (
    PipelineStatusResponse,
    PipelineStatus,
    AutoGenerateRequest,
    AutoGenerateResponse,
    GenerationStrategy,
    StoryboardRequest,
    ConcatRequest,
    ConcatResponse,
)
from app.schemas.storyboard import Storyboard
from app.services.storyboard import parse_script_to_storyboard
from app.services.pipeline_executor import PipelineExecutor
from app.services import story_repository as repo
from uuid import uuid4

router = APIRouter(prefix="/api/v1/pipeline", tags=["pipeline"])

# 手动步进模式使用的内存状态（每个 project 一个）
_pipeline_states: dict[str, dict] = {}


def _get_or_create(project_id: str) -> dict:
    """获取或初始化手动步进模式的内存状态。"""
    if project_id not in _pipeline_states:
        _pipeline_states[project_id] = {
            "status": PipelineStatus.PENDING,
            "progress": 0,
            "current_step": "等待开始",
            "error": None,
            "progress_detail": None,
            "generated_files": None,
        }
    return _pipeline_states[project_id]


@router.post("/{project_id}/auto-generate", response_model=AutoGenerateResponse)
async def auto_generate(
    project_id: str,
    req: AutoGenerateRequest,
    background_tasks: BackgroundTasks,
    request: Request,
):
    """
    一键生成完整视频 - 自动执行全流程

    支持三种策略：
    - separated: TTS → 图片 → 图生视频 → FFmpeg 合成
    - integrated: 图片 → 视频语音一体生成
    - chained: 分离式 + 场景内链式帧传递，同一场景内串行生成以保持镜头间视觉一致性
    """
    # 创建新的 pipeline 记录
    pipeline_id = str(uuid4())

    # 在请求上下文中提取 API Key（header 优先，回退到请求体字段）
    keys = extract_api_keys(request)
    llm_api_key  = keys.llm_api_key  or req.llm_api_key  or ""
    llm_base_url = keys.llm_base_url or req.llm_base_url or ""
    image_api_key = resolve_image_key(keys.image_api_key or req.image_api_key or "")
    validated_image_base_url = validate_user_base_url(keys.image_base_url)
    if validated_image_base_url and not keys.image_api_key:
        raise HTTPException(status_code=400, detail="使用自定义 X-Image-Base-URL 时必须同时提供 X-Image-API-Key")
    image_base_url = validated_image_base_url or _cfg.siliconflow_base_url

    video_cfg = video_config_dep(request)
    video_api_key = video_cfg["video_api_key"]
    video_base_url = video_cfg["video_base_url"]
    video_provider = video_cfg["video_provider"]

    async def _run_pipeline():
        """后台执行流水线"""
        # 创建新的数据库会话用于后台任务
        async with AsyncSessionLocal() as db_session:
            # 初始化 pipeline 状态
            await repo.save_pipeline(db_session, pipeline_id, project_id, {
                "status": PipelineStatus.PENDING,
                "progress": 0,
                "current_step": "准备开始",
                "error": None,
                "progress_detail": None,
                "generated_files": None,
            })

            # 获取角色信息（如果提供了 story_id）
            character_info = None
            if req.story_id:
                try:
                    story = await repo.get_story(db_session, req.story_id)
                    if story:
                        characters = story.get("characters", [])
                        character_images = story.get("character_images", {})
                        if characters:
                            character_info = {
                                "characters": characters,
                                "character_images": character_images or {},
                            }
                except Exception:
                    pass  # 降级：无角色信息但不报错

            executor = PipelineExecutor(project_id, pipeline_id, db_session)
            await executor.run_full_pipeline(
                script=req.script,
                strategy=req.strategy,
                provider=req.provider,
                model=req.model,
                voice=req.voice,
                image_model=req.image_model,
                video_model=req.video_model,
                base_url=req.base_url,
                llm_api_key=llm_api_key,
                llm_base_url=llm_base_url,
                image_api_key=image_api_key,
                image_base_url=image_base_url,
                video_api_key=video_api_key,
                video_base_url=video_base_url,
                video_provider=video_provider,
                character_info=character_info,
            )

    background_tasks.add_task(_run_pipeline)

    return AutoGenerateResponse(
        project_id=project_id,
        message=f"自动化流水线已启动（策略：{req.strategy.value}）",
        strategy=req.strategy,
    )


@router.post("/{project_id}/storyboard", response_model=Storyboard)
async def generate_storyboard(
    project_id: str,
    request: Request,
    req: StoryboardRequest = Body(...),
    llm: dict = Depends(llm_config_dep),
    db: AsyncSession = Depends(get_db),
):
    """手动触发：分镜解析"""
    pipeline_id = str(uuid4())

    # 读取分镜专用配置（X-Script-* headers）
    s_provider = request.headers.get("X-Script-Provider", "")
    s_api_key  = request.headers.get("X-Script-API-Key",  "")
    s_base_url = request.headers.get("X-Script-Base-URL", "")
    s_model    = request.headers.get("X-Script-Model",    "")

    if s_provider or s_api_key or s_base_url or s_model:
        script_llm = resolve_llm_config(s_api_key, s_base_url, s_provider, s_model)
    else:
        script_llm = llm

    provider = script_llm["provider"] or req.provider or "claude"

    await repo.save_pipeline(db, pipeline_id, project_id, {
        "status": PipelineStatus.STORYBOARD,
        "progress": 10,
        "current_step": "解析分镜中",
    })

    try:
        # 获取角色信息（如果提供了 story_id）
        character_info = None
        if req.story_id:
            try:
                story = await repo.get_story(db, req.story_id)
                if story:
                    characters = story.get("characters", [])
                    character_images = story.get("character_images", {})
                    if characters:
                        character_info = {
                            "characters": characters,
                            "character_images": character_images or {},
                        }
            except Exception:
                pass  # 降级：无角色信息但不报错

        shots, usage = await parse_script_to_storyboard(
            req.script,
            provider=provider,
            model=script_llm["model"] or req.model,
            api_key=script_llm["api_key"],
            base_url=script_llm["base_url"],
            character_info=character_info,
        )
    except Exception as e:
        await repo.save_pipeline(db, pipeline_id, project_id, {
            "status": PipelineStatus.FAILED,
            "error": str(e),
        })
        raise HTTPException(status_code=500, detail=f"分镜解析失败: {e}") from e

    await repo.save_pipeline(db, pipeline_id, project_id, {
        "progress": 30,
        "current_step": "分镜解析完成",
    })

    return Storyboard(
        shots=shots,
        usage={
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
        }
    )


@router.post("/{project_id}/generate-assets")
async def generate_assets(
    project_id: str,
    storyboard: Storyboard,
    image_config: dict = Depends(image_config_dep),
    voice: str = Query("zh-CN-XiaoxiaoNeural", description="TTS 语音"),
    image_model: str = Query("black-forest-labs/FLUX.1-schnell", description="图片生成模型"),
    background_tasks: BackgroundTasks = None,
):
    """
    手动触发：生成 TTS 和图片资产

    参数：
    - storyboard: 分镜数据（从 storyboard 接口获取）
    - voice: TTS 语音（默认：晓晓）
    - image_model: 图片生成模型（默认：FLUX.1-schnell）
    """
    from app.services import tts, image

    state = _get_or_create(project_id)
    state.update(
        status=PipelineStatus.GENERATING_ASSETS,
        progress=30,
        current_step="生成 TTS 和图片中",
    )

    shots = storyboard.shots
    total = len(shots)

    async def _generate():
        """后台生成任务"""
        try:
            # TTS
            state["progress_detail"] = {"step": "tts", "current": 0, "total": total, "message": "生成语音..."}
            tts_results = await tts.generate_tts_batch(
                shots=[{
                    "shot_id": s.shot_id,
                    "dialogue": s.audio_reference.content if s.audio_reference and s.audio_reference.type in ("dialogue", "narration") else None,
                } for s in shots],
                voice=voice,
            )

            # 图片
            state["progress_detail"] = {"step": "image", "current": 0, "total": total, "message": "生成图片..."}
            image_results = await image.generate_images_batch(
                shots=[{"shot_id": s.shot_id, "final_video_prompt": s.final_video_prompt} for s in shots],
                model=image_model,
                **image_config,
            )

            # 保存结果
            state.update(
                progress=60,
                current_step=f"资产生成完成（TTS: {len(tts_results)}, 图片: {len(image_results)}）",
                generated_files={
                    "tts": {r["shot_id"]: r for r in tts_results},
                    "images": {r["shot_id"]: r for r in image_results},
                },
            )
        except Exception as e:
            state.update(status=PipelineStatus.FAILED, error=str(e))

    if background_tasks:
        background_tasks.add_task(_generate)
        return {"project_id": project_id, "message": "资产生成任务已启动"}
    else:
        await _generate()
        return {"project_id": project_id, "message": "资产生成完成", "state": state}


@router.post("/{project_id}/render-video")
async def render_video(
    project_id: str,
    shots_data: list[dict],
    video_config: dict = Depends(video_config_dep),
    base_url: str = Query("http://localhost:8000", description="服务器地址"),
    video_model: str = Query("wan2.6-i2v-flash", description="视频生成模型"),
    background_tasks: BackgroundTasks = None,
):
    """
    手动触发：图生视频

    参数：
    - shots_data: 镜头数据列表，每个包含 shot_id, image_url, visual_prompt, camera_motion
    - base_url: 服务器地址（用于拼接本地图片 URL）
    - video_model: 视频生成模型（默认：wan2.6-i2v-flash）
    """
    from app.services import video

    state = _get_or_create(project_id)
    state.update(
        status=PipelineStatus.RENDERING_VIDEO,
        progress=65,
        current_step="图生视频中",
    )

    async def _render():
        """后台渲染任务"""
        try:
            total = len(shots_data)
            state["progress_detail"] = {"step": "video", "current": 0, "total": total, "message": "生成视频..."}

            video_results = await video.generate_videos_batch(
                shots=shots_data,
                base_url=base_url,
                model=video_model,
                **video_config,
            )

            state.update(
                progress=85,
                current_step=f"视频渲染完成（{len(video_results)} 个）",
                generated_files={"videos": {r["shot_id"]: r for r in video_results}},
            )
        except Exception as e:
            state.update(status=PipelineStatus.FAILED, error=str(e))

    if background_tasks:
        background_tasks.add_task(_render)
        return {"project_id": project_id, "message": "视频渲染任务已启动"}
    else:
        await _render()
        return {"project_id": project_id, "message": "视频渲染完成", "state": state}


@router.get("/{project_id}/status", response_model=PipelineStatusResponse)
async def get_status(project_id: str, pipeline_id: str = None, db: AsyncSession = Depends(get_db)):
    """
    获取流水线状态

    参数：
    - project_id: 项目 ID
    - pipeline_id: 流水线 ID（可选，如果不提供则返回最新的）

    优先级：
    1. 手动步进的内存状态（_pipeline_states）
    2. 指定 pipeline_id 的数据库记录
    3. 最新的数据库记录
    4. 默认待机状态
    """
    # 手动步进模式：内存状态优先（仅在未指定 pipeline_id 时）
    if not pipeline_id and project_id in _pipeline_states:
        pipeline = _pipeline_states[project_id]
    elif pipeline_id:
        pipeline = await repo.get_pipeline(db, pipeline_id)
        if not pipeline:
            raise HTTPException(status_code=404, detail="Pipeline not found")
    else:
        pipeline = await repo.get_pipeline_by_story(db, project_id)
        if not pipeline:
            pipeline = {
                "status": PipelineStatus.PENDING,
                "progress": 0,
                "current_step": "等待开始",
                "error": None,
                "progress_detail": None,
                "generated_files": None,
            }

    return PipelineStatusResponse(
        project_id=project_id,
        status=pipeline.get("status", PipelineStatus.PENDING),
        progress=pipeline.get("progress", 0),
        current_step=pipeline.get("current_step", "等待开始"),
        error=pipeline.get("error"),
        progress_detail=pipeline.get("progress_detail"),
        generated_files=pipeline.get("generated_files"),
    )


@router.post("/{project_id}/concat", response_model=ConcatResponse)
async def concat_videos(
    project_id: str,
    req: ConcatRequest,
    request: Request,
):
    """
    将多个镜头视频按顺序拼接为一个完整 MP4。

    使用 ffmpeg concat + stream copy，不重编码，速度极快。
    """
    from app.services.ffmpeg import concat_videos as do_concat, _url_to_local_path, VIDEO_DIR

    if not req.video_urls:
        raise HTTPException(status_code=400, detail="视频列表为空")

    base_url = str(request.base_url).rstrip("/")

    # URL → 本地路径
    local_paths = [_url_to_local_path(url, base_url) for url in req.video_urls]

    output_path = str(VIDEO_DIR / f"episode_{project_id}.mp4")

    try:
        await do_concat(local_paths, output_path)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    video_url = f"/{output_path}"
    return ConcatResponse(video_url=video_url)


@router.post("/{project_id}/stitch")
async def stitch_video(
    project_id: str,
    shots_data: list[dict],
    background_tasks: BackgroundTasks = None,
):
    """
    手动触发：FFmpeg 合成音视频

    参数：
    - shots_data: 镜头数据列表，每个包含 shot_id, video_url, audio_url（可选）
    """
    state = _get_or_create(project_id)
    state.update(status=PipelineStatus.STITCHING, progress=90, current_step="FFmpeg 合成中")

    async def _stitch():
        """后台合成任务"""
        try:
            # TODO: 实现真实的 FFmpeg 合成逻辑
            # 目前先模拟
            import asyncio
            await asyncio.sleep(2)

            state.update(
                status=PipelineStatus.COMPLETE,
                progress=100,
                current_step="视频合成完成",
            )
        except Exception as e:
            state.update(status=PipelineStatus.FAILED, error=str(e))

    if background_tasks:
        background_tasks.add_task(_stitch)
        return {"project_id": project_id, "message": "视频合成任务已启动"}
    else:
        await _stitch()
        return {"project_id": project_id, "message": "视频合成完成", "state": state}
