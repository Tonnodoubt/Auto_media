from pydantic import BaseModel, Field
from typing import List, Optional, Literal


class CameraSetup(BaseModel):
    """摄影机参数，前端可通过下拉框独立编辑。"""
    shot_size: Literal["EWS", "WS", "MWS", "MS", "MCU", "CU", "ECU", "OTS"] = Field(description="景别")
    camera_angle: Literal["Eye-level", "Low angle", "High angle", "Dutch angle", "Bird's eye", "Worm's eye"] = Field(default="Eye-level", description="摄像机角度")
    movement: Literal["Static", "Slow Dolly in", "Dolly out", "Pan left", "Pan right", "Tilt up", "Tilt down", "Tracking shot", "Handheld subtle shake", "Crane up", "Crane down"] = Field(description="摄像机运动")


class VisualElements(BaseModel):
    """结构化视觉元素，强制 LLM 逐项填写，防止遗漏（Chain-of-Thought 变形）。"""
    subject_and_clothing: str = Field(description="主体完整物理描述：年龄/性别/发型颜色/服装材质颜色质感/体型/特征标记")
    action_and_expression: str = Field(description="1-2 个原子物理动作 + 微表情，禁止心理描写")
    environment_and_props: str = Field(description="环境细节/道具/前后景分离/景深描述")
    lighting_and_color: str = Field(description="光源方向/类型/色温/阴影特征/整体色彩倾向")


class AudioReference(BaseModel):
    """音频关联，支持台词/旁白/音效三种类型，便于 TTS 支路分发。"""
    type: Optional[Literal["dialogue", "narration", "sfx"]] = Field(default=None, description="dialogue/narration/sfx；null 时整体置 None")
    content: Optional[str] = Field(default=None, description="原文台词或音效描述")


class Shot(BaseModel):
    shot_id: str = Field(description="scene{N}_shot{M}")
    estimated_duration: int = Field(default=4, description="时长（秒），3-5")
    scene_intensity: Literal["low", "high"] = Field(default="low", description="low=日常过场 / high=高潮核心")
    storyboard_description: str = Field(description="中文画面简述，供前端展示（2-4句具体描述）")
    camera_setup: CameraSetup = Field(description="摄影机参数")
    visual_elements: VisualElements = Field(description="结构化视觉元素")
    final_video_prompt: str = Field(description="完整英文物理级 Prompt，直接送入视频生成 API")
    audio_reference: Optional[AudioReference] = Field(default=None, description="音频关联")
    mood: Optional[str] = Field(default=None, description="情绪基调英文短语")
    scene_position: Optional[Literal["establishing", "development", "climax", "resolution"]] = Field(default=None, description="镜头在场景中的位置")
    transition_from_previous: Optional[str] = Field(default=None, description="与前一个镜头的视觉/叙事过渡关系描述（如何平滑衔接、状态变化、摄像机运动等）")


class Usage(BaseModel):
    prompt_tokens: int = Field(default=0, description="Number of prompt tokens used")
    completion_tokens: int = Field(default=0, description="Number of completion tokens used")


class Storyboard(BaseModel):
    shots: List[Shot]
    usage: Optional[Usage] = Field(default=None, description="Token usage information")
