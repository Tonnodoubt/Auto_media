from pydantic import BaseModel, model_validator
from typing import List, Literal, Optional


class AnalyzeIdeaRequest(BaseModel):
    idea: str
    genre: str
    tone: str


class SuggestionGroup(BaseModel):
    label: str
    options: List[str]


class AnalyzeIdeaResponse(BaseModel):
    story_id: str
    analysis: str
    suggestions: List[SuggestionGroup]
    placeholder: str


class GenerateOutlineRequest(BaseModel):
    story_id: str
    selected_setting: str


class Character(BaseModel):
    name: str
    role: str
    description: str


class OutlineScene(BaseModel):
    episode: int
    title: str
    summary: str


class Relationship(BaseModel):
    source: str
    target: str
    label: str


class GenerateOutlineResponse(BaseModel):
    story_id: str
    meta: dict
    characters: List[Character]
    relationships: List[Relationship]
    outline: List[OutlineScene]


class ChatRequest(BaseModel):
    story_id: str
    message: str


class GenerateScriptRequest(BaseModel):
    story_id: str


class ChatMessage(BaseModel):
    role: Literal["user", "ai"]
    text: str


class PatchStoryRequest(BaseModel):
    story_id: str
    characters: Optional[List[Character]] = None
    outline: Optional[List[OutlineScene]] = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "PatchStoryRequest":
        if self.characters is None and self.outline is None:
            raise ValueError("至少需要提供 characters 或 outline 之一")
        return self


class ApplyChatRequest(BaseModel):
    story_id: str
    change_type: Literal["character", "episode"]
    chat_history: List[ChatMessage]
    current_item: dict        # character 或 episode 对象（类型依 change_type 而定）


class RefineRequest(BaseModel):
    story_id: str
    change_type: Literal["character", "episode"]
    change_summary: str


class RefineResponse(BaseModel):
    relationships: Optional[List[Relationship]]
    outline: Optional[List[OutlineScene]]
    meta_theme: Optional[str]


class WorldBuildingStartRequest(BaseModel):
    idea: str


class WorldBuildingTurnRequest(BaseModel):
    story_id: str
    answer: str


class WorldBuildingQuestion(BaseModel):
    type: str          # "options" | "open"
    text: str
    options: Optional[List[str]]
    dimension: str


class WorldBuildingTurnResponse(BaseModel):
    story_id: str
    status: str        # "questioning" | "complete"
    turn: int
    question: Optional[WorldBuildingQuestion]
    world_summary: Optional[str]
    usage: Optional[dict]


class AudioLine(BaseModel):
    character: str
    line: str


class ScriptScene(BaseModel):
    scene_number: int
    environment: str
    visual: str
    audio: List[AudioLine]
    mood: Optional[str] = None
    lighting: Optional[str] = None
    key_actions: Optional[List[str]] = None
    shot_suggestions: Optional[List[str]] = None
    transition_from_previous: Optional[str] = None


class SceneScript(BaseModel):
    episode: int
    title: str
    scenes: List[ScriptScene]
