from pydantic import BaseModel, model_validator
from typing import Any, Dict, List, Literal, Optional


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
    id: Optional[str] = None
    name: str
    role: str
    description: str


class OutlineScene(BaseModel):
    episode: int
    title: str
    summary: str
    beats: Optional[List[str]] = None
    scene_list: Optional[List[str]] = None


class Relationship(BaseModel):
    source: str
    target: str
    source_id: Optional[str] = None
    target_id: Optional[str] = None
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
    mode: Optional[Literal["generic", "character", "episode", "outline"]] = "generic"
    context: Optional[dict] = None


class GenerateScriptRequest(BaseModel):
    story_id: str


class StoryboardScriptRequest(BaseModel):
    selected_scenes: Optional[Dict[str, List[int]]] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_selected_scenes(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        raw_selected_scenes = data.get("selected_scenes")
        if not isinstance(raw_selected_scenes, dict):
            return data

        normalized: dict[str, list[int]] = {}
        for episode_key, scene_numbers in raw_selected_scenes.items():
            episode = str(episode_key).strip()
            if not episode:
                continue

            selected_scene_numbers: list[int] = []
            if isinstance(scene_numbers, dict):
                for scene_number, is_selected in scene_numbers.items():
                    if not is_selected:
                        continue
                    try:
                        selected_scene_numbers.append(int(scene_number))
                    except (TypeError, ValueError):
                        continue
            elif isinstance(scene_numbers, (list, tuple, set)):
                for scene_number in scene_numbers:
                    try:
                        selected_scene_numbers.append(int(scene_number))
                    except (TypeError, ValueError):
                        continue
            else:
                continue

            if selected_scene_numbers:
                normalized[episode] = selected_scene_numbers

        return {**data, "selected_scenes": normalized}


class ChatMessage(BaseModel):
    role: Literal["user", "ai"]
    text: str


class PatchStoryRequest(BaseModel):
    story_id: str
    characters: Optional[List[Character]] = None
    outline: Optional[List[OutlineScene]] = None
    art_style: Optional[str] = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "PatchStoryRequest":
        if self.characters is None and self.outline is None and self.art_style is None:
            raise ValueError("至少需要提供 characters、outline 或 art_style 之一")
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


class EmotionTag(BaseModel):
    target: str
    emotion: str
    intensity: float


class ScriptScene(BaseModel):
    scene_number: int
    environment: str
    visual: str
    audio: List[AudioLine]
    scene_heading: Optional[str] = None
    environment_anchor: Optional[str] = None
    mood: Optional[str] = None
    lighting: Optional[str] = None
    emotion_tags: Optional[List[EmotionTag]] = None
    key_props: Optional[List[str]] = None
    key_actions: Optional[List[str]] = None
    shot_suggestions: Optional[List[str]] = None
    transition_from_previous: Optional[str] = None


class SceneScript(BaseModel):
    episode: int
    title: str
    scenes: List[ScriptScene]
