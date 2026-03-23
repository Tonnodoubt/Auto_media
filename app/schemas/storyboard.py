from pydantic import BaseModel, Field
from typing import List, Optional


class Shot(BaseModel):
    shot_id: str = Field(description="Unique ID, e.g. scene1_shot1")
    visual_description_zh: str = Field(description="简短的中文画面描述，供团队审阅用。")
    visual_prompt: str = Field(description="Highly detailed English prompt for image generation, includes character, environment, lighting, camera angle, and style tags.")
    camera_motion: str = Field(description="Simple English instruction for video generation, e.g. 'Pan right', 'Zoom in slowly', 'Static'.")
    dialogue: Optional[str] = Field(default=None, description="Exact Chinese text for TTS. None if no dialogue.")
    estimated_duration: int = Field(default=4, description="Estimated duration in seconds (3-5).")
    shot_size: str = Field(default="Medium", description="Shot size: EWS/WS/MWS/MS/MCU/CU/ECU/OTS")
    mood: Optional[str] = Field(default=None, description="Emotional tone of the shot, e.g. 'tense', 'warm'")
    scene_position: Optional[str] = Field(default=None, description="Narrative position: establishing/development/climax/resolution")


class Usage(BaseModel):
    prompt_tokens: int = Field(default=0, description="Number of prompt tokens used")
    completion_tokens: int = Field(default=0, description="Number of completion tokens used")


class Storyboard(BaseModel):
    shots: List[Shot]
    usage: Optional[Usage] = Field(default=None, description="Token usage information")
