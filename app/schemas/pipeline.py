from pydantic import BaseModel
from typing import Optional, List
from enum import Enum


class GenerationStrategy(str, Enum):
    """视频生成策略"""
    SEPARATED = "separated"  # 分离式：TTS → 图片 → 图生视频 → FFmpeg 合成
    INTEGRATED = "integrated"  # 一体式：图片 → 视频语音一体生成


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
    status: PipelineStatus
    progress: int
    current_step: str
    error: Optional[str] = None
    progress_detail: Optional[PipelineProgress] = None
    generated_files: Optional[dict] = None


class StoryboardRequest(BaseModel):
    script: str
    provider: Optional[str] = None
    model: Optional[str] = None


class AutoGenerateRequest(BaseModel):
    """一键生成请求"""
    script: str
    strategy: GenerationStrategy = GenerationStrategy.SEPARATED
    provider: str = "claude"
    model: Optional[str] = None

    # API Keys (从前端传入)
    llm_api_key: Optional[str] = ""
    llm_base_url: Optional[str] = ""
    image_api_key: Optional[str] = ""
    video_api_key: Optional[str] = ""

    # TTS 配置
    voice: str = "zh-CN-XiaoxiaoNeural"

    # 图片生成配置
    image_model: str = "black-forest-labs/FLUX.1-schnell"

    # 视频生成配置
    video_model: str = "wan2.6-i2v-flash"

    # 服务地址（用于拼接本地文件 URL）
    base_url: str = "http://localhost:8000"


class ShotResult(BaseModel):
    """单个镜头的生成结果"""
    shot_id: str
    audio_url: Optional[str] = None
    audio_duration: Optional[float] = None
    image_url: Optional[str] = None
    video_url: Optional[str] = None


class AutoGenerateResponse(BaseModel):
    """一键生成响应"""
    project_id: str
    message: str
    strategy: GenerationStrategy
