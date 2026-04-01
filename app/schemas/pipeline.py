from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from enum import Enum


class GenerationStrategy(str, Enum):
    """视频生成策略"""
    SEPARATED = "separated"  # 分离式：TTS → 图片 → 图生视频 → FFmpeg 合成
    INTEGRATED = "integrated"  # 一体式：图片 → 视频语音一体生成
    CHAINED = "chained"  # 链式：分离式 + 场景内链式帧传递，提升镜头间视觉一致性


class PipelineStatus(str, Enum):
    PENDING = "pending"
    STORYBOARD = "storyboard"
    GENERATING_ASSETS = "generating_assets"
    RENDERING_VIDEO = "rendering_video"
    STITCHING = "stitching"
    COMPLETE = "complete"
    FAILED = "failed"


class PipelineProgress(BaseModel):
    """详细的进度信息"""
    step: str
    current: int
    total: int
    message: str


class PipelineStatusResponse(BaseModel):
    project_id: str
    pipeline_id: Optional[str] = None
    story_id: Optional[str] = None
    status: PipelineStatus
    progress: int
    current_step: str
    error: Optional[str] = None
    progress_detail: Optional[PipelineProgress] = None
    generated_files: Optional[dict] = None
    note: Optional[str] = None


class PipelineActionResponse(BaseModel):
    project_id: str
    pipeline_id: str
    story_id: Optional[str] = None
    message: str
    state: Optional[PipelineStatusResponse] = None


class StoryboardRequest(BaseModel):
    script: str
    provider: Optional[str] = None
    model: Optional[str] = None
    story_id: Optional[str] = None


class AutoGenerateRequest(BaseModel):
    """一键生成请求"""
    script: str
    strategy: GenerationStrategy = GenerationStrategy.SEPARATED
    provider: str = "claude"
    model: Optional[str] = None
    story_id: Optional[str] = None

    # API Keys (从前端传入)
    llm_api_key: Optional[str] = ""
    llm_base_url: Optional[str] = ""
    image_api_key: Optional[str] = ""
    video_api_key: Optional[str] = ""

    # TTS 配置
    voice: str = "zh-CN-XiaoxiaoNeural"

    # 图片生成配置
    image_model: Optional[str] = None

    # 视频生成配置
    video_model: Optional[str] = None

    # 服务地址（用于拼接本地文件 URL）
    base_url: str = ""

    # 画风提示词(统一应用于图片/视频生成)
    art_style: str = ""


class ShotResult(BaseModel):
    """单个镜头的生成结果"""
    shot_id: str
    audio_url: Optional[str] = None
    audio_duration: Optional[float] = None
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    final_video_url: Optional[str] = None


class AutoGenerateResponse(BaseModel):
    """一键生成响应"""
    project_id: str
    pipeline_id: str
    story_id: Optional[str] = None
    message: str
    strategy: GenerationStrategy
    note: Optional[str] = None


class TransitionGenerateRequest(BaseModel):
    pipeline_id: str
    story_id: Optional[str] = None
    from_shot_id: str
    to_shot_id: str
    transition_prompt: Optional[str] = None
    duration_seconds: int = Field(default=2, gt=0)
    model: Optional[str] = None


class TransitionFrameSource(BaseModel):
    shot_id: str
    video_url: str
    frame_role: Literal["from_last", "to_first"]
    extracted_image_url: str
    source_type: Literal["video_frame", "storyboard_image_fallback"] = "video_frame"
    diagnostic_note: Optional[str] = None
    extraction_error: Optional[str] = None


class TransitionResult(BaseModel):
    transition_id: str
    from_shot_id: str
    to_shot_id: str
    prompt: Optional[str] = None
    duration_seconds: int = Field(default=2, gt=0)
    video_url: str
    first_frame_source: TransitionFrameSource
    last_frame_source: TransitionFrameSource
    diagnostic_summary: Optional[str] = None


class TimelineItem(BaseModel):
    item_type: Literal["shot", "transition"]
    item_id: str


class ConcatRequest(BaseModel):
    """视频拼接请求 — 按顺序排列的视频 URL"""
    video_urls: list[str]


class ConcatResponse(BaseModel):
    """视频拼接响应"""
    video_url: str
    pipeline_id: Optional[str] = None
    story_id: Optional[str] = None
