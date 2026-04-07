import json
import logging
import re
from collections.abc import Mapping
from typing import Any, List, Optional

from pydantic import ValidationError
from app.services.llm.factory import get_llm_provider
from app.services.quality import run_quality_guarded_generation
from app.schemas.storyboard import Shot
from app.prompts.storyboard import SYSTEM_PROMPT, USER_TEMPLATE
from app.prompts.character import build_character_section


logger = logging.getLogger(__name__)

_CONTINUITY_PATTERNS = (
    r"\bcontinuing\b",
    r"\bmaintaining\b",
    r"\bseamlessly transitioning\b",
    r"\bfrom the previous (?:shot|frame)\b",
    r"\bsame location\b",
    r"\bcamera pulls?\b",
)
_VIDEO_VERBOSE_PATTERNS = (
    r"\bcontinuing from the previous[^.,;]*",
    r"\bmaintaining the same[^.,;]*",
    r"\bsame [^.,;]*(?:background|lighting|location|room|office)[^.,;]*",
)
_STYLE_PATTERNS = (
    r"--ar\s+\S+",
    r"\b(?:Cinematic|Masterpiece|photorealistic|ultra-detailed|highly detailed|4k|8k|ARRI Alexa 65|macro lens|cinema lighting|professional color grading)\b",
)
_CAMERA_MOVEMENT_PATTERNS = (
    r"\bStatic camera\b",
    r"\bStatic\b",
    r"\bSlow Dolly in\b",
    r"\bDolly out\b",
    r"\bPan left\b",
    r"\bPan right\b",
    r"\bTilt up\b",
    r"\bTilt down\b",
    r"\bTracking shot\b",
    r"\bHandheld subtle shake\b",
    r"\bCrane up\b",
    r"\bCrane down\b",
)
_MOTION_PATTERNS = (
    r"\bwalk(?:s|ing)?\b",
    r"\bstand(?:s|ing)?\b",
    r"\bsit(?:s|ting)?\b",
    r"\bturn(?:s|ing)?\b",
    r"\braise(?:s|ing)?\b",
    r"\blower(?:s|ing)?\b",
    r"\bblink(?:s|ing)?\b",
    r"\bglance(?:s|ing)?\b",
    r"\bspeak(?:s|ing)?\b",
    r"\bbreath(?:e|es|ing)\b",
    r"站",
    r"坐",
    r"走",
    r"转",
    r"抬",
    r"眨",
    r"呼吸",
    r"说",
)
_DYNAMIC_MOTION_PATTERNS = (
    r"\bwalk(?:s|ing)?\b",
    r"\bturn(?:s|ing)?\b",
    r"\braise(?:s|ing)?\b",
    r"\blower(?:s|ing)?\b",
    r"\bblink(?:s|ing)?\b",
    r"\bglance(?:s|ing)?\b",
    r"\bspeak(?:s|ing)?\b",
    r"\bbreath(?:e|es|ing)\b",
    r"\bshift(?:s|ing)?\b",
    r"\bsway(?:s|ing)?\b",
    r"\btrembl(?:e|es|ing)\b",
    r"走",
    r"转",
    r"抬",
    r"眨",
    r"呼吸",
    r"说",
    r"移动",
    r"晃",
)
_SHOT_LABELS = {
    "EWS": "Extreme wide shot",
    "WS": "Wide shot",
    "MWS": "Medium wide shot",
    "MS": "Medium shot",
    "MCU": "Medium close-up",
    "CU": "Close-up",
    "ECU": "Extreme close-up",
    "OTS": "Over-the-shoulder shot",
}
_SHOT_LABELS_ZH = {
    "EWS": "极远景",
    "WS": "远景",
    "MWS": "中远景",
    "MS": "中景",
    "MCU": "中近景",
    "CU": "近景",
    "ECU": "特写",
    "OTS": "越肩镜头",
}
_ANGLE_LABELS_ZH = {
    "Eye-level": "平视",
    "Low angle": "低角度",
    "High angle": "高角度",
    "Dutch angle": "倾斜角度",
    "Bird's eye": "俯视",
    "Worm's eye": "仰视",
}
_MOVEMENT_LABELS_ZH = {
    "Static": "固定机位",
    "Slow Dolly in": "缓慢推近",
    "Dolly out": "拉远",
    "Pan left": "左摇",
    "Pan right": "右摇",
    "Tilt up": "上摇",
    "Tilt down": "下摇",
    "Tracking shot": "跟拍",
    "Handheld subtle shake": "轻微手持晃动",
    "Crane up": "升降上移",
    "Crane down": "升降下移",
}
_CANONICAL_CAMERA_ANGLES = (
    "Eye-level",
    "Low angle",
    "High angle",
    "Dutch angle",
    "Bird's eye",
    "Worm's eye",
)
_CANONICAL_SHOT_SIZES = (
    "EWS",
    "WS",
    "MWS",
    "MS",
    "MCU",
    "CU",
    "ECU",
    "OTS",
)
_CANONICAL_SCENE_POSITIONS = (
    "establishing",
    "development",
    "climax",
    "resolution",
)
_CANONICAL_CAMERA_MOVEMENTS = (
    "Static",
    "Slow Dolly in",
    "Dolly out",
    "Pan left",
    "Pan right",
    "Tilt up",
    "Tilt down",
    "Tracking shot",
    "Handheld subtle shake",
    "Crane up",
    "Crane down",
)
_GENERIC_CHARACTER_LABELS = {
    "crowd",
    "extras",
    "extra",
    "bystander",
    "bystanders",
    "passerby",
    "passersby",
    "pedestrian",
    "pedestrians",
    "stranger",
    "strangers",
    "background crowd",
    "background extra",
    "unnamed extra",
    "路人",
    "路人甲",
    "路人乙",
    "群众",
    "行人",
    "人群",
    "背景人群",
    "围观者",
    "陌生人",
    "无名角色",
    "临时路人",
}
_GENERIC_SPEAKER_LABELS = {
    "he",
    "she",
    "they",
    "him",
    "her",
    "them",
    "the man",
    "the woman",
    "the boy",
    "the girl",
    "that man",
    "that woman",
    "person",
    "someone",
    "某人",
    "有人",
    "他",
    "她",
    "他们",
    "她们",
    "那人",
    "那个人",
    "那个男人",
    "那个女人",
    "男人",
    "女人",
    "男孩",
    "女孩",
}
_NARRATOR_SPEAKER_LABELS = {
    "旁白",
    "画外音",
    "解说",
    "narrator",
    "narration",
    "voiceover",
    "voice over",
    "voice-over",
}
_SCRIPT_SFX_LABELS = {
    "音效",
    "声效",
    "sfx",
    "fx",
    "sound effect",
    "sound effects",
}
_SCRIPT_METADATA_LABELS = {
    "场景标题",
    "环境锚点",
    "环境",
    "光线",
    "氛围",
    "情感标尺",
    "关键道具",
    "画面",
    "内容覆盖清单",
    "动作拆解",
    "镜头建议",
    "过渡",
}


def _strip_terminal_punctuation(text: str) -> str:
    return (text or "").strip(" ,.;:!?，。；：！？、")


def _serialize_storyboard_candidate_shot(shot: Shot | Mapping[str, Any]) -> dict[str, Any]:
    if hasattr(shot, "model_dump"):
        return shot.model_dump(mode="json")
    if hasattr(shot, "dict"):
        return shot.dict()
    return dict(shot)


def _collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _trim_words(text: str, limit: int) -> str:
    cleaned = _collapse_spaces(text)
    if not cleaned:
        return ""

    words = cleaned.split()
    if len(words) <= limit:
        if _contains_cjk(cleaned) and len(words) <= 1:
            char_limit = max(limit * 3, 1)
            if len(cleaned) > char_limit:
                return _strip_terminal_punctuation(cleaned[:char_limit].rstrip())
        return _strip_terminal_punctuation(cleaned)
    return _strip_terminal_punctuation(" ".join(words[:limit]))


def _normalize_camera_movement(value: str) -> str:
    text = _collapse_spaces(value)
    if not text:
        return "Static"

    for movement in _CANONICAL_CAMERA_MOVEMENTS:
        if text.lower() == movement.lower():
            return movement

    normalized = re.sub(r"[_/|]", " ", text.lower())
    normalized = re.sub(r"\s*\+\s*", " ", normalized)
    normalized = re.sub(r"[(),.;:]+", " ", normalized)
    normalized = _collapse_spaces(normalized)

    alias_groups = (
        ("Slow Dolly in", ("dolly in", "push in", "push-in", "zoom in", "camera in", "缓慢推近", "推近", "推进", "拉近", "镜头推进")),
        ("Dolly out", ("dolly out", "pull out", "pull back", "zoom out", "camera out", "拉远", "后拉", "镜头拉远", "拉出")),
        ("Pan left", ("pan left", "left pan", "pan to the left", "左摇", "向左摇", "往左摇", "镜头左摇")),
        ("Pan right", ("pan right", "right pan", "pan to the right", "右摇", "向右摇", "往右摇", "镜头右摇")),
        ("Tilt up", ("tilt up", "tilt upward", "tilt upwards", "上摇", "上仰", "镜头上摇", "向上倾斜")),
        ("Tilt down", ("tilt down", "tilt downward", "tilt downwards", "下摇", "下俯", "镜头下摇", "向下倾斜")),
        ("Tracking shot", ("tracking shot", "track shot", "tracking", "follow shot", "follow camera", "跟拍", "跟随", "跟镜", "跟随镜头")),
        ("Handheld subtle shake", ("handheld", "hand held", "subtle shake", "slight shake", "camera shake", "手持", "手持晃动", "轻微手持晃动", "轻微晃动")),
        ("Crane up", ("crane up", "boom up", "jib up", "升降上移", "吊臂上移", "摇臂上移", "上升摇臂")),
        ("Crane down", ("crane down", "boom down", "jib down", "升降下移", "吊臂下移", "摇臂下移", "下降摇臂")),
        ("Static", ("static", "locked off", "lock off", "still camera", "fixed camera", "no camera movement", "固定机位", "定机位", "静止机位", "静态镜头", "固定镜头")),
    )

    weighted_matches: list[tuple[int, str]] = []
    for index, (canonical, aliases) in enumerate(alias_groups):
        for alias in aliases:
            if alias in normalized:
                score = 2 if any(speed in normalized for speed in ("fast", "slow", "slight", "subtle", "快速", "缓慢", "轻微")) else 1
                weighted_matches.append((score * 100 - index, canonical))
                break

    if weighted_matches:
        return max(weighted_matches)[1]

    if normalized in {"pan", "摇镜", "摇摄"} or normalized.startswith("pan ") or normalized.startswith("摇"):
        return "Pan left" if ("left" in normalized or "左" in normalized) else "Pan right"
    if normalized in {"tilt", "俯仰"} or normalized.startswith("tilt ") or normalized.startswith("上摇") or normalized.startswith("下摇") or normalized.startswith("上仰") or normalized.startswith("下俯"):
        return "Tilt down" if ("down" in normalized or "下" in normalized or "俯" in normalized) else "Tilt up"
    if normalized in {"crane", "boom", "jib", "升降", "摇臂", "吊臂"} or normalized.startswith("crane ") or normalized.startswith("boom ") or normalized.startswith("jib ") or normalized.startswith("升降") or normalized.startswith("摇臂") or normalized.startswith("吊臂"):
        return "Crane down" if ("down" in normalized or "下" in normalized) else "Crane up"

    return "Static"


def _normalize_camera_angle(value: str) -> str:
    text = _collapse_spaces(value)
    if not text:
        return "Eye-level"

    for angle in _CANONICAL_CAMERA_ANGLES:
        if text.lower() == angle.lower():
            return angle

    normalized = re.sub(r"[_/|]", " ", text.lower())
    normalized = re.sub(r"\s*\+\s*", " ", normalized)
    normalized = re.sub(r"[(),.;:]+", " ", normalized)
    normalized = _collapse_spaces(normalized)

    alias_groups = (
        ("Bird's eye", ("birds eye", "bird eye", "bird s eye", "bird's eye", "overhead", "top down", "top-down", "aerial view", "俯视", "鸟瞰", "上帝视角")),
        ("Worm's eye", ("worms eye", "worm eye", "worm s eye", "worm's eye", "extreme low angle", "ground level up", "ground-level up", "仰视", "虫视角")),
        ("Dutch angle", ("dutch angle", "canted angle", "tilted angle", "slanted angle", "倾斜角度", "斜角", "倾斜镜头")),
        ("High angle", ("high angle", "slightly high angle", "mild high angle", "subtle high angle", "downward angle", "slight downward angle", "高角度", "高机位", "高视角", "俯角")),
        ("Low angle", ("low angle", "slightly low angle", "mild low angle", "subtle low angle", "upward angle", "slight upward angle", "低角度", "低机位", "低视角", "仰角")),
        ("Eye-level", ("eye level", "eye-level", "neutral angle", "straight on", "straight-on", "level angle", "平视", "视平", "正视")),
    )

    for canonical, aliases in alias_groups:
        if any(alias in normalized for alias in aliases):
            return canonical

    if "overhead" in normalized or "top down" in normalized or "top-down" in normalized:
        return "Bird's eye"
    if "high" in normalized or "俯" in normalized:
        return "High angle"
    if "low" in normalized or "仰" in normalized:
        return "Low angle"
    if "tilt" in normalized or "canted" in normalized or "斜" in normalized:
        return "Dutch angle"

    return "Eye-level"


def _normalize_shot_size(value: str) -> str:
    text = _collapse_spaces(value)
    if not text:
        return "MS"

    for shot_size in _CANONICAL_SHOT_SIZES:
        if text.upper() == shot_size:
            return shot_size

    normalized = re.sub(r"[_/|]", " ", text.lower())
    normalized = re.sub(r"[(),.;:]+", " ", normalized)
    normalized = _collapse_spaces(normalized)

    alias_groups = (
        ("EWS", ("extreme wide shot", "extreme wide", "超远景", "极远景", "大全景")),
        ("ECU", ("extreme close up", "extreme close-up", "特特写", "极近特写")),
        ("MCU", ("medium close up", "medium close-up", "中近景", "近中景")),
        ("MWS", ("medium wide shot", "medium wide", "中远景")),
        ("OTS", ("over the shoulder", "over-the-shoulder", "越肩", "肩后")),
        ("WS", ("wide shot", "wide", "远景", "全景")),
        ("CU", ("close up", "close-up", "close shot", "近景", "特写")),
        ("MS", ("medium shot", "medium", "中景")),
    )

    for canonical, aliases in alias_groups:
        if any(alias in normalized for alias in aliases):
            return canonical

    return "MS"


def _normalize_scene_intensity(value: str) -> str:
    normalized = _collapse_spaces(value).lower()
    if normalized in {"high", "高潮", "高", "intense", "climax", "peak"}:
        return "high"
    return "low"


def _normalize_scene_position(value: str) -> str | None:
    normalized = _collapse_spaces(value).lower()
    if not normalized:
        return None

    for position in _CANONICAL_SCENE_POSITIONS:
        if normalized == position:
            return position

    alias_groups = (
        ("establishing", ("opening", "opener", "establishing", "intro", "start", "开场", "建立")),
        ("development", ("development", "middle", "buildup", "progression", "发展", "中段")),
        ("climax", ("climax", "peak", "turning point", "高潮", "爆发")),
        ("resolution", ("resolution", "ending", "closing", "outro", "结尾", "收束")),
    )
    for canonical, aliases in alias_groups:
        if any(alias in normalized for alias in aliases):
            return canonical
    return None


def _stringify_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _normalize_audio_content_key(value: Any) -> str:
    cleaned = re.sub(r"^[（(【\[][^）)】\]]{0,12}[）)】\]]\s*", "", _stringify_text(value))
    return _strip_terminal_punctuation(_collapse_spaces(cleaned)).casefold()


def _coerce_estimated_duration(value: Any) -> int:
    try:
        duration = int(value)
    except (TypeError, ValueError):
        return 4
    return max(1, min(duration, 10))


def _normalize_audio_reference(value: Any, legacy_dialogue: Any = None) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        content = _stringify_text(value.get("content"))
        raw_type = _collapse_spaces(value.get("type")).lower()
        raw_speaker = _stringify_text(value.get("speaker") or value.get("character") or value.get("voice"))
        speaker_lower = raw_speaker.casefold()
        is_narrator = speaker_lower in _NARRATOR_SPEAKER_LABELS
        speaker = "旁白" if is_narrator else (raw_speaker or None)
        if raw_type in {"dialogue", "dialog", "speech", "spoken"}:
            ref_type = "dialogue"
        elif raw_type in {"narration", "voiceover", "voice over", "voice-over", "narrator"}:
            ref_type = "narration"
        elif raw_type in {"sfx", "sound effect", "sound-effect", "fx"}:
            ref_type = "sfx"
        elif is_narrator and content:
            ref_type = "narration"
        elif speaker and content:
            ref_type = "dialogue"
        else:
            ref_type = "dialogue" if content and legacy_dialogue else None
        if ref_type == "dialogue" and is_narrator:
            ref_type = "narration"
        if ref_type == "sfx":
            speaker = None
        return {"type": ref_type, "speaker": speaker, "content": content or None} if (ref_type or speaker or content) else None

    dialogue = _stringify_text(legacy_dialogue)
    if dialogue:
        return {"type": "dialogue", "speaker": None, "content": dialogue}
    return None


def _finalize_audio_reference(
    audio_reference: dict[str, Any] | None,
    *,
    characters: list[str] | None = None,
) -> dict[str, Any] | None:
    if not audio_reference:
        return None

    normalized = dict(audio_reference)
    ref_type = _stringify_text(normalized.get("type")).lower() or None
    speaker = _stringify_text(normalized.get("speaker")) or None
    content = _stringify_text(normalized.get("content")) or None

    if speaker and speaker.casefold() in _GENERIC_SPEAKER_LABELS:
        speaker = None

    if ref_type == "narration":
        speaker = "旁白"
    elif ref_type == "sfx":
        speaker = None
    elif ref_type == "dialogue" and not speaker and characters and len(characters) == 1:
        speaker = characters[0]

    return {"type": ref_type, "speaker": speaker, "content": content} if (ref_type or speaker or content) else None


def _normalize_character_mentions(value: Any) -> list[str] | None:
    if value is None:
        return None

    if isinstance(value, str):
        raw_items = re.split(r"[,，/、\n]+", value)
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        return None

    names: list[str] = []
    for item in raw_items:
        candidate = item.get("name") if isinstance(item, Mapping) else item
        normalized = _stringify_text(candidate)
        if not normalized:
            continue
        if normalized.lower() in _GENERIC_CHARACTER_LABELS:
            continue
        if normalized not in names:
            names.append(normalized)

    return names or None


def _fallback_storyboard_description(item: Mapping[str, Any], shot_number: int) -> str:
    for candidate in (
        item.get("storyboard_description"),
        item.get("image_prompt"),
        item.get("final_video_prompt"),
        item.get("visual_description_zh"),
        ((item.get("visual_elements") or {}) if isinstance(item.get("visual_elements"), Mapping) else {}).get("action_and_expression"),
        ((item.get("visual_elements") or {}) if isinstance(item.get("visual_elements"), Mapping) else {}).get("environment_and_props"),
    ):
        text = _stringify_text(candidate)
        if text:
            return text
    return f"镜头{shot_number}画面。"


def _build_shot_id(raw_shot_id: Any, shot_number: int) -> str:
    shot_id = _stringify_text(raw_shot_id)
    return shot_id or f"scene{shot_number}_shot1"


def _normalize_shot_item(
    raw_item: Any,
    *,
    shot_number: int,
    scene_mapping: Optional[dict[int, str]] = None,
) -> dict[str, Any]:
    item = dict(raw_item) if isinstance(raw_item, Mapping) else {"storyboard_description": _stringify_text(raw_item)}

    if "visual_prompt" in item and "final_video_prompt" not in item:
        item["final_video_prompt"] = item.get("visual_prompt")
    if "visual_description_zh" in item and "storyboard_description" not in item:
        item["storyboard_description"] = item.get("visual_description_zh")

    camera_setup_raw = item.get("camera_setup") if isinstance(item.get("camera_setup"), Mapping) else {}
    legacy_movement = item.get("camera_motion")
    shot_size = _normalize_shot_size(camera_setup_raw.get("shot_size") or item.get("shot_size"))
    camera_angle = _normalize_camera_angle(camera_setup_raw.get("camera_angle") or "Eye-level")
    movement = _normalize_camera_movement(camera_setup_raw.get("movement") or legacy_movement or "Static")

    visual_elements_raw = item.get("visual_elements") if isinstance(item.get("visual_elements"), Mapping) else {}
    visual_elements = {
        "subject_and_clothing": _stringify_text(visual_elements_raw.get("subject_and_clothing")),
        "action_and_expression": _stringify_text(visual_elements_raw.get("action_and_expression")),
        "environment_and_props": _stringify_text(visual_elements_raw.get("environment_and_props")),
        "lighting_and_color": _stringify_text(visual_elements_raw.get("lighting_and_color")),
    }

    storyboard_description = _stringify_text(item.get("storyboard_description")) or _fallback_storyboard_description(item, shot_number)
    image_prompt = _stringify_text(item.get("image_prompt"))
    final_video_prompt = _stringify_text(item.get("final_video_prompt"))
    if not image_prompt and not final_video_prompt and not any(visual_elements.values()):
        image_prompt = storyboard_description
        final_video_prompt = storyboard_description

    shot_id = _build_shot_id(item.get("shot_id"), shot_number)
    shot_scene_index = _extract_scene_index_from_shot_id(shot_id)
    source_scene_key = _stringify_text(item.get("source_scene_key"))
    if shot_scene_index is not None:
        mapped_scene_key = (scene_mapping or {}).get(shot_scene_index)
        source_scene_key = mapped_scene_key or source_scene_key or f"scene{shot_scene_index}"

    characters = (
        _normalize_character_mentions(item.get("characters"))
        or _normalize_character_mentions(item.get("character_names"))
        or _normalize_character_mentions(item.get("mentioned_characters"))
        or _normalize_character_mentions(item.get("cast"))
        or _normalize_character_mentions(item.get("participants"))
    )
    audio_reference = _finalize_audio_reference(
        _normalize_audio_reference(item.get("audio_reference"), legacy_dialogue=item.get("dialogue")),
        characters=characters,
    )

    normalized = {
        "shot_id": shot_id,
        "source_scene_key": source_scene_key or None,
        "characters": characters,
        "estimated_duration": _coerce_estimated_duration(item.get("estimated_duration", 4)),
        "scene_intensity": _normalize_scene_intensity(item.get("scene_intensity", "low")),
        "storyboard_description": storyboard_description,
        "camera_setup": {
            "shot_size": shot_size,
            "camera_angle": camera_angle,
            "movement": movement,
        },
        "visual_elements": visual_elements,
        "image_prompt": image_prompt or None,
        "final_video_prompt": final_video_prompt,
        "last_frame_prompt": None,
        "audio_reference": audio_reference,
        "mood": _stringify_text(item.get("mood")) or None,
        "scene_position": _normalize_scene_position(item.get("scene_position")),
        "transition_from_previous": _stringify_text(item.get("transition_from_previous")) or None,
        "last_frame_url": None,
    }
    return normalized


def _build_minimal_valid_shot_item(
    item: Mapping[str, Any],
    *,
    shot_number: int,
    scene_mapping: Optional[dict[int, str]] = None,
) -> dict[str, Any]:
    fallback_description = _fallback_storyboard_description(item, shot_number)
    shot_id = _build_shot_id(item.get("shot_id"), shot_number)
    shot_scene_index = _extract_scene_index_from_shot_id(shot_id)
    mapped_scene_key = (scene_mapping or {}).get(shot_scene_index) if shot_scene_index is not None else None

    return {
        "shot_id": shot_id,
        "source_scene_key": mapped_scene_key or _stringify_text(item.get("source_scene_key")) or None,
        "characters": (
            _normalize_character_mentions(item.get("characters"))
            or _normalize_character_mentions(item.get("character_names"))
            or _normalize_character_mentions(item.get("mentioned_characters"))
            or _normalize_character_mentions(item.get("cast"))
            or _normalize_character_mentions(item.get("participants"))
        ),
        "estimated_duration": 4,
        "scene_intensity": "low",
        "storyboard_description": fallback_description,
        "camera_setup": {
            "shot_size": "MS",
            "camera_angle": "Eye-level",
            "movement": "Static",
        },
        "visual_elements": {
            "subject_and_clothing": "",
            "action_and_expression": "",
            "environment_and_props": "",
            "lighting_and_color": "",
        },
        "image_prompt": _stringify_text(item.get("image_prompt")) or fallback_description,
        "final_video_prompt": _stringify_text(item.get("final_video_prompt")) or _stringify_text(item.get("image_prompt")) or fallback_description,
        "last_frame_prompt": None,
        "audio_reference": _finalize_audio_reference(
            _normalize_audio_reference(item.get("audio_reference"), legacy_dialogue=item.get("dialogue")),
            characters=(
                _normalize_character_mentions(item.get("characters"))
                or _normalize_character_mentions(item.get("character_names"))
                or _normalize_character_mentions(item.get("mentioned_characters"))
                or _normalize_character_mentions(item.get("cast"))
                or _normalize_character_mentions(item.get("participants"))
            ),
        ),
        "mood": _stringify_text(item.get("mood")) or None,
        "scene_position": None,
        "transition_from_previous": _stringify_text(item.get("transition_from_previous")) or None,
        "last_frame_url": None,
    }


def _load_storyboard_items(raw: str) -> list[Any]:
    cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
    candidates = [cleaned]

    array_start, array_end = cleaned.find("["), cleaned.rfind("]")
    if array_start != -1 and array_end > array_start:
        candidates.append(cleaned[array_start:array_end + 1])

    object_start, object_end = cleaned.find("{"), cleaned.rfind("}")
    if object_start != -1 and object_end > object_start:
        candidates.append(cleaned[object_start:object_end + 1])

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
            if isinstance(payload, list):
                return payload
            if isinstance(payload, Mapping):
                shots = payload.get("shots")
                if isinstance(shots, list):
                    return shots
                if any(
                    key in payload
                    for key in (
                        "shot_id",
                        "storyboard_description",
                        "camera_setup",
                        "visual_elements",
                        "image_prompt",
                        "final_video_prompt",
                    )
                ):
                    return [payload]
                raise ValueError("Storyboard response object does not contain shot fields")
        except Exception as exc:  # noqa: BLE001
            last_error = exc

    if last_error:
        raise last_error
    raise ValueError("Storyboard response is not a valid JSON array or object")


def _extract_script_scene_number(line: str) -> int | None:
    scene_match = re.search(r"(?:【\s*场景\s*(\d+)\s*】|^##\s*场景\s*(\d+)\s*$)", line)
    if not scene_match:
        return None
    return int(scene_match.group(1) or scene_match.group(2))


def _build_script_audio_lookup(
    script: str,
    *,
    scene_mapping: Optional[dict[int, str]] = None,
) -> dict[str, dict[tuple[str, str, str | None], dict[str, Any]]]:
    allowed_audio: dict[str, dict[tuple[str, str, str | None], dict[str, Any]]] = {}
    current_scene_key = "scene1"
    scene_index = 0

    def _register(scene_key: str, ref_type: str, speaker: str | None, content: str) -> None:
        content_key = _normalize_audio_content_key(content)
        if not content_key:
            return
        normalized_type = _stringify_text(ref_type).lower()
        normalized_speaker = _stringify_text(speaker) or None
        bucket_key = (content_key, normalized_type, normalized_speaker)
        bucket = allowed_audio.setdefault(scene_key, {})
        bucket[bucket_key] = {
            "type": normalized_type,
            "speaker": normalized_speaker,
            "content": _stringify_text(content),
        }

    for raw_line in (script or "").splitlines():
        line = _collapse_spaces(raw_line)
        if not line:
            continue

        if _extract_script_scene_number(line) is not None:
            scene_index += 1
            current_scene_key = (scene_mapping or {}).get(scene_index) or f"scene{scene_index}"
            continue

        bracket_match = re.match(r"^【([^】]+)】\s*(.*)$", line)
        if bracket_match:
            label = _stringify_text(bracket_match.group(1))
            content = _stringify_text(bracket_match.group(2))
            if not content or label in _SCRIPT_METADATA_LABELS:
                continue

            label_key = label.casefold()
            if label_key in _NARRATOR_SPEAKER_LABELS:
                _register(current_scene_key, "narration", "旁白", content)
            elif label_key in _SCRIPT_SFX_LABELS:
                _register(current_scene_key, "sfx", None, content)
            else:
                _register(current_scene_key, "dialogue", label, content)
            continue

        coverage_match = re.match(r"^-+\s*台词/旁白[:：]\s*([^：:]+)\s*[:：]\s*(.+)$", line)
        if not coverage_match:
            continue

        speaker = _stringify_text(coverage_match.group(1))
        content = _stringify_text(coverage_match.group(2))
        if not speaker or not content:
            continue
        speaker_key = speaker.casefold()
        if speaker_key in _NARRATOR_SPEAKER_LABELS:
            _register(current_scene_key, "narration", "旁白", content)
        elif speaker_key in _SCRIPT_SFX_LABELS:
            _register(current_scene_key, "sfx", None, content)
        else:
            _register(current_scene_key, "dialogue", speaker, content)

    return allowed_audio


def _filter_audio_reference_to_script(
    audio_reference: dict[str, Any] | None,
    *,
    shot_id: str,
    source_scene_key: str | None,
    characters: list[str] | None = None,
    allowed_audio_lookup: Optional[dict[str, dict[tuple[str, str, str | None], dict[str, Any]]]] = None,
) -> dict[str, Any] | None:
    normalized = _finalize_audio_reference(audio_reference, characters=characters)
    if not normalized:
        return None

    scene_key = _stringify_text(source_scene_key)
    if not scene_key:
        shot_match = re.match(r"scene(\d+)_shot", _collapse_spaces(shot_id), flags=re.IGNORECASE)
        scene_key = f"scene{shot_match.group(1)}" if shot_match else "scene1"

    content_key = _normalize_audio_content_key(normalized.get("content"))
    if not content_key:
        return None

    normalized_type = _stringify_text(normalized.get("type")).lower()
    normalized_speaker = _stringify_text(normalized.get("speaker")) or None
    scene_bucket = (allowed_audio_lookup or {}).get(scene_key, {})
    scene_entries = list(reversed(list(scene_bucket.items())))
    content_matches = [
        entry
        for (candidate_content_key, candidate_type, candidate_speaker), entry in scene_entries
        if candidate_content_key == content_key
        and (not normalized_type or candidate_type == normalized_type)
    ]
    if not content_matches:
        return None

    matched_audio = next(
        (
            entry
            for (candidate_content_key, candidate_type, candidate_speaker), entry in scene_entries
            if candidate_content_key == content_key
            and (not normalized_type or candidate_type == normalized_type)
            and candidate_speaker == normalized_speaker
        ),
        None,
    )
    if not matched_audio and normalized_speaker is None and len(content_matches) == 1:
        matched_audio = content_matches[0]
    if not matched_audio:
        return None

    return _finalize_audio_reference(dict(matched_audio), characters=characters)


def _strip_patterns(text: str, patterns: tuple[str, ...]) -> str:
    cleaned = text or ""
    for pattern in patterns:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    return _collapse_spaces(cleaned)


def _sentence(text: str, prefix: str = "") -> str:
    cleaned = _strip_terminal_punctuation(_collapse_spaces(text))
    if not cleaned:
        return ""
    if prefix:
        cleaned = f"{prefix}{cleaned}"
    return f"{cleaned}."


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def _preferred_language(shot: Shot) -> str:
    prompt_or_structured_fields = " ".join(
        [
            shot.image_prompt or "",
            shot.final_video_prompt or "",
            shot.last_frame_prompt or "",
            shot.visual_elements.subject_and_clothing or "",
            shot.visual_elements.action_and_expression or "",
            shot.visual_elements.environment_and_props or "",
            shot.visual_elements.lighting_and_color or "",
            shot.mood or "",
        ]
    )
    if _collapse_spaces(prompt_or_structured_fields):
        return "zh" if _contains_cjk(prompt_or_structured_fields) else "en"
    return "zh" if _contains_cjk(shot.storyboard_description or "") else "en"


def _sentence_localized(text: str, lang: str, prefix: str = "") -> str:
    cleaned = _strip_terminal_punctuation(_collapse_spaces(text))
    if not cleaned:
        return ""
    if prefix:
        cleaned = f"{prefix}{cleaned}"
    return f"{cleaned}。" if lang == "zh" else f"{cleaned}."


def _join_prompt_parts(parts: list[str], lang: str) -> str:
    filtered = [part for part in parts if part]
    if not filtered:
        return ""
    return "".join(filtered) if lang == "zh" else " ".join(filtered)


def _shot_phrase(shot: Shot, lang: str) -> str:
    if lang == "zh":
        shot_size = _SHOT_LABELS_ZH.get(shot.camera_setup.shot_size, shot.camera_setup.shot_size)
        angle = _ANGLE_LABELS_ZH.get(shot.camera_setup.camera_angle, shot.camera_setup.camera_angle)
        return _sentence_localized(f"{shot_size}，{angle}", lang)
    shot_size = _SHOT_LABELS.get(shot.camera_setup.shot_size, shot.camera_setup.shot_size)
    angle = shot.camera_setup.camera_angle
    return _sentence_localized(f"{shot_size}, {angle}", lang)


def _has_motion(text: str) -> bool:
    return any(re.search(pattern, text or "", flags=re.IGNORECASE) for pattern in _MOTION_PATTERNS)


def _has_dynamic_motion(text: str) -> bool:
    return any(re.search(pattern, text or "", flags=re.IGNORECASE) for pattern in _DYNAMIC_MOTION_PATTERNS)


def _motion_action_phrase(text: str) -> str:
    action = _collapse_spaces(text)
    if not action:
        return ""

    replacements = (
        (r"\bspeaking dialogue with natural lip movements\b", "speaks with clear lip movement"),
        (r"\bspeaks? with visible lip movement\b", "speaks with clear lip movement"),
        (r"\bspeaking\b", "speaks"),
        (r"\bwalking forward steadily at normal pace\b", "walks forward steadily"),
        (r"\bwalking forward\b", "walks forward"),
        (r"\bwalking\b", "walks"),
        (r"\beyes shifting toward the boss direction\b", "gaze shifting toward the boss"),
        (r"\beyes shifting toward\b", "gaze shifting toward"),
        (r"\beyes shifting\b", "gaze shifting"),
        (r"\bstanding in formation\b", "stands in formation"),
        (r"\bholding coffee cup at waist level\b", "holding the coffee cup at waist level"),
        (r"快速移动", "快速穿行"),
        (r"寻找最佳射击位置", "搜索更好的射击位置"),
        (r"寻找", "搜索"),
        (r"说话", "开口说话"),
        (r"开口", "开口说话"),
        (r"抬头", "抬起头部"),
        (r"站立", "站定"),
    )
    for pattern, replacement in replacements:
        action = re.sub(pattern, replacement, action, flags=re.IGNORECASE)

    action = re.sub(r"\s*,\s*", ", ", action)
    action = re.sub(r"(?:,\s*){2,}", ", ", action)
    action = action.strip(" ,.;")
    return _trim_words(action, 24)


def _minimal_motion_clause(shot: Shot) -> str:
    lang = _preferred_language(shot)
    action = _motion_action_phrase(shot.visual_elements.action_and_expression)
    if shot.audio_reference and shot.audio_reference.type == "dialogue":
        if action:
            if re.search(r"\bspeak", action, flags=re.IGNORECASE):
                return _sentence_localized(f"{action}, with natural blinking", lang)
            if lang == "zh":
                return _sentence_localized(f"{action}，伴随清晰口型和自然眨眼", lang)
            return _sentence_localized(f"Speaks with clear lip movement while {action}, with natural blinking", lang)
        if lang == "zh":
            return _sentence_localized("说话时口型清晰，伴随轻微呼吸和自然眨眼", lang)
        return _sentence_localized("Speaks with clear lip movement, slight breathing, and natural blinking", lang)

    if shot.audio_reference and shot.audio_reference.type == "narration":
        if action:
            if _has_dynamic_motion(action):
                if lang == "zh":
                    return _sentence_localized(f"{action}，伴随自然眨眼", lang)
                return _sentence_localized(f"{action}, with natural blinking", lang)
            if lang == "zh":
                return _sentence_localized(f"{action}，伴随轻微呼吸和自然眨眼", lang)
            return _sentence_localized(f"{action}, with slight breathing and natural blinking", lang)
        if shot.camera_setup.shot_size in ("MCU", "CU", "ECU"):
            if lang == "zh":
                return _sentence_localized("维持当前姿态，伴随轻微呼吸、自然眨眼和细微面部紧张感", lang)
            return _sentence_localized("Holds the pose with slight breathing, a natural blink, and subtle facial tension", lang)
        if lang == "zh":
            return _sentence_localized("维持当前姿态，伴随轻微呼吸和自然眨眼", lang)
        return _sentence_localized("Maintains the pose with slight breathing and natural blinking", lang)

    if _has_dynamic_motion(action):
        return _sentence_localized(action, lang)

    subject_text = f"{shot.visual_elements.subject_and_clothing} {shot.visual_elements.action_and_expression}"
    if re.search(r"\bsit|坐", subject_text, flags=re.IGNORECASE):
        if lang == "zh":
            return _sentence_localized("坐姿保持稳定，伴随轻微呼吸、细小重心调整和自然眨眼", lang)
        return _sentence_localized("Sits steady with slight breathing, a small posture shift, and a natural blink", lang)
    if re.search(r"\bstand|站", subject_text, flags=re.IGNORECASE):
        if lang == "zh":
            return _sentence_localized("站定不动，伴随轻微呼吸、自然眨眼和细微衣料摆动", lang)
        return _sentence_localized("Stands in place with slight breathing, a natural blink, and a subtle fabric movement", lang)
    if shot.camera_setup.shot_size in ("MCU", "CU", "ECU"):
        if lang == "zh":
            return _sentence_localized("轻微呼吸，自然眨眼，并带出细微面部变化", lang)
        return _sentence_localized("Breathes lightly, blinking once with subtle facial movement", lang)
    if lang == "zh":
        return _sentence_localized("保持当前姿态，伴随轻微呼吸和自然眨眼", lang)
    return _sentence_localized("Holds position with slight breathing and a natural blink", lang)


def _normalize_image_prompt(text: str) -> str:
    cleaned = _strip_patterns(text, _CONTINUITY_PATTERNS + _STYLE_PATTERNS)
    cleaned = _strip_patterns(cleaned, _CAMERA_MOVEMENT_PATTERNS)
    return _trim_words(cleaned, 78)


def _normalize_video_prompt(text: str) -> str:
    cleaned = _strip_patterns(text, _STYLE_PATTERNS + _VIDEO_VERBOSE_PATTERNS)
    cleaned = re.sub(r"[\"'][^\"']+[\"']", " speaking", cleaned)
    cleaned = re.sub(r"\s*,\s*", ", ", cleaned)
    cleaned = re.sub(r"(?:,\s*){2,}", ", ", cleaned)
    cleaned = re.sub(r"(^|[.])\s*,\s*", r"\1 ", cleaned)
    return _trim_words(cleaned, 64)


def _freeze_action_phrase(text: str) -> str:
    frozen = _collapse_spaces(text)
    if not frozen:
        return ""

    replacements = (
        (r"\bspeaking dialogue with natural lip movements\b", "lips slightly parted"),
        (r"\bspeaks? with visible lip movement\b", "lips slightly parted"),
        (r"\bspeaking\b", "lips slightly parted"),
        (r"\beyes shifting toward the boss direction\b", "gaze angled toward the boss"),
        (r"\beyes shifting toward\b", "gaze angled toward"),
        (r"\beyes shifting\b", "gaze angled"),
        (r"\bwalking forward steadily at normal pace\b", "captured mid-step"),
        (r"\bwalking forward\b", "captured mid-step"),
        (r"\bwalks? forward\b", "captured mid-step"),
        (r"\bwalking\b", "captured mid-step"),
        (r"\bstanding in formation\b", "upright stance in formation"),
        (r"\bturning around\b", "body caught mid-turn"),
        (r"\bturning\b", "body caught mid-turn"),
        (r"\bturns?\b", "body angled in a turn"),
        (r"\braising his head\b", "head slightly lifted"),
        (r"\braises? (?:his|her|the) head\b", "head slightly lifted"),
        (r"\blooks? up\b", "gaze lifted upward"),
        (r"\bglancing\b", "gaze angled"),
        (r"\bglances?\b", "gaze directed"),
        (r"\bbreathing\b", ""),
        (r"\bnatural blinking\b", ""),
        (r"\bblinking\b", ""),
        (r"\bslight body sway\b", ""),
        (r"\bsubtle shoulder motion\b", ""),
        (r"\bsubtle fabric movement\b", ""),
        (r"\bvisible lip movement\b", "lips slightly parted"),
        (r"\bholding coffee cup at waist level\b", "coffee cup held at waist level"),
        (r"快速移动", "身体压低，脚步前探"),
        (r"移动", "前探步态"),
        (r"寻找最佳射击位置", "目光搜索合适的射击位置"),
        (r"寻找", "目光搜索"),
        (r"说话", "嘴唇微张"),
        (r"开口说话", "嘴唇微张"),
        (r"开口", "嘴唇微张"),
        (r"站立", "站姿稳定"),
        (r"持枪", "双手持枪"),
    )
    for pattern, replacement in replacements:
        frozen = re.sub(pattern, replacement, frozen, flags=re.IGNORECASE)

    frozen = re.sub(r"\bcontinue(?:s|d|ing)?\b", " ", frozen, flags=re.IGNORECASE)
    frozen = re.sub(r"\bmove(?:s|d|ing)?\b", " ", frozen, flags=re.IGNORECASE)
    frozen = re.sub(r"\bslowly\b|\bsteadily\b|\brapidly\b|\bviolently\b", " ", frozen, flags=re.IGNORECASE)
    frozen = re.sub(r"\bwith natural lip movements\b", " ", frozen, flags=re.IGNORECASE)
    frozen = re.sub(r"\bwith visible lip movement\b", " ", frozen, flags=re.IGNORECASE)
    frozen = re.sub(r"\s*,\s*", ", ", frozen)
    frozen = re.sub(r"(?:,\s*){2,}", ", ", frozen)
    frozen = frozen.strip(" ,.;")
    return _trim_words(frozen, 22)


def _camera_movement_sentence(shot: Shot) -> str:
    lang = _preferred_language(shot)
    movement = shot.camera_setup.movement or "Static"
    if lang == "zh":
        movement_zh = _MOVEMENT_LABELS_ZH.get(movement, movement)
        if movement == "Static":
            return _sentence_localized(movement_zh, lang)
        return _sentence_localized(movement_zh, lang, "运镜：")
    if movement == "Static":
        return "Static camera."
    return _sentence_localized(movement, lang, "Camera movement: ")


def _compose_image_prompt(shot: Shot) -> str:
    lang = _preferred_language(shot)
    subject = _trim_words(shot.visual_elements.subject_and_clothing, 20)
    pose = _freeze_action_phrase(shot.visual_elements.action_and_expression)
    environment = _trim_words(shot.visual_elements.environment_and_props, 18)
    lighting = _trim_words(shot.visual_elements.lighting_and_color, 12)
    parts = [
        _shot_phrase(shot, lang),
        _sentence_localized(subject, lang),
        _sentence_localized(pose, lang, "定格：") if pose and lang == "zh" else _sentence_localized(pose, lang, "Frozen pose: ") if pose else "",
        _sentence_localized(environment, lang) if environment else "",
        _sentence_localized(lighting, lang) if lighting else "",
    ]
    return _trim_words(_join_prompt_parts(parts, lang), 88)


def _compose_video_prompt(shot: Shot) -> str:
    lang = _preferred_language(shot)
    movement = _camera_movement_sentence(shot)
    subject = _trim_words(shot.visual_elements.subject_and_clothing, 16)
    environment = _trim_words(shot.visual_elements.environment_and_props, 12)
    lighting = _trim_words(shot.visual_elements.lighting_and_color, 10)
    parts = [
        _shot_phrase(shot, lang),
        movement,
        _sentence_localized(subject, lang) if subject else "",
        _minimal_motion_clause(shot),
        _sentence_localized(environment, lang) if environment else "",
        _sentence_localized(lighting, lang) if lighting else "",
    ]
    return _trim_words(_join_prompt_parts(parts, lang), 68)


def _postprocess_shot(shot: Shot) -> Shot:
    raw_image_prompt = shot.image_prompt or ""
    raw_video_prompt = shot.final_video_prompt or ""
    has_composable_visuals = bool(
        shot.visual_elements.subject_and_clothing
        or shot.visual_elements.environment_and_props
        or shot.visual_elements.action_and_expression
        or shot.visual_elements.lighting_and_color
    )

    description_units = _split_text_units(shot.storyboard_description)
    if description_units:
        shot.storyboard_description = _trim_words(_join_text_units(description_units[:3]), 48)

    shot.visual_elements.subject_and_clothing = _trim_words(shot.visual_elements.subject_and_clothing, 18)
    shot.visual_elements.action_and_expression = _trim_words(shot.visual_elements.action_and_expression, 18)
    shot.visual_elements.environment_and_props = _trim_words(shot.visual_elements.environment_and_props, 16)
    shot.visual_elements.lighting_and_color = _trim_words(shot.visual_elements.lighting_and_color, 10)

    if shot.mood:
        shot.mood = _trim_words(shot.mood, 6) or None

    if shot.transition_from_previous:
        transition_units = _split_text_units(shot.transition_from_previous)
        if transition_units:
            shot.transition_from_previous = _trim_words(_join_text_units(transition_units[:2]), 24) or None

    composed_image_prompt = _compose_image_prompt(shot) if has_composable_visuals else ""

    # Preserve prompt fields generated by the storyboard LLM whenever available.
    # Recent system-prompt updates intentionally shape image/video prompt wording,
    # length, and language. Rebuilding them here would silently override those changes.
    if raw_image_prompt:
        shot.image_prompt = _normalize_image_prompt(raw_image_prompt)
        normalized_image_prompt = _collapse_spaces(shot.image_prompt)
        if composed_image_prompt and normalized_image_prompt:
            prompt_words = normalized_image_prompt.split()
            is_sparse_image_prompt = (
                (_contains_cjk(normalized_image_prompt) and len(normalized_image_prompt) < 28)
                or (not _contains_cjk(normalized_image_prompt) and len(prompt_words) < 10)
            )
            if is_sparse_image_prompt:
                shot.image_prompt = _normalize_image_prompt(
                    _merge_text_units(composed_image_prompt, normalized_image_prompt, max_units=4) or composed_image_prompt
                )
    elif shot.visual_elements.subject_and_clothing or shot.visual_elements.environment_and_props:
        shot.image_prompt = composed_image_prompt
    elif raw_video_prompt:
        shot.image_prompt = _normalize_image_prompt(raw_video_prompt)

    if raw_video_prompt:
        shot.final_video_prompt = _normalize_video_prompt(raw_video_prompt)
    elif shot.visual_elements.action_and_expression or shot.visual_elements.subject_and_clothing:
        shot.final_video_prompt = _compose_video_prompt(shot)

    if not shot.image_prompt:
        if raw_video_prompt:
            shot.image_prompt = _normalize_image_prompt(raw_video_prompt)
        elif has_composable_visuals:
            shot.image_prompt = _compose_image_prompt(shot)
        else:
            raise ValueError(f"shot {shot.shot_id} has no image prompt available")

    # Phase 4: main storyboard shots now use single-frame I2V only.
    # Keep transition data out of the core shot payload to avoid dual-frame pollution.
    shot.last_frame_prompt = None
    shot.last_frame_url = None

    return shot


def _extract_scene_index_from_shot_id(shot_id: str) -> int | None:
    match = re.match(r"scene(\d+)_shot\d+$", _collapse_spaces(shot_id), flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def _build_scene_mapping(script: str) -> dict[int, str]:
    current_episode = 1
    scene_index = 0
    mapping: dict[int, str] = {}
    for raw_line in (script or "").splitlines():
        line = _collapse_spaces(raw_line)
        if not line:
            continue
        episode_match = re.search(r"第\s*(\d+)\s*集", line)
        if episode_match:
            current_episode = int(episode_match.group(1))
            continue
        scene_number = _extract_script_scene_number(line)
        if scene_number is None:
            continue
        scene_index += 1
        mapping[scene_index] = f"ep{current_episode:02d}_scene{scene_number:02d}"
    return mapping


def _build_scene_mapping_section(script: str) -> str:
    scene_mapping = _build_scene_mapping(script)
    if not scene_mapping:
        return (
            "SCENE SOURCE MAP:\n"
            "- If the script excerpt contains only one episode, infer `source_scene_key` as epXX_sceneYY.\n"
            "- If scene origin is ambiguous, keep `source_scene_key` consistent with the shot's best source scene.\n"
        )
    lines = [
        "SCENE SOURCE MAP:",
        "- Use the exact mapping below.",
        "- `shot_id` must use this map's scene order: scene1, scene2, scene3...",
        "- `source_scene_key` must copy the mapped key exactly for every shot.",
    ]
    for scene_index, source_scene_key in scene_mapping.items():
        lines.append(f"- scene{scene_index} -> {source_scene_key}")
    return "\n".join(lines)


def _core_transition_hint(previous_item: Mapping[str, Any], current_item: Mapping[str, Any]) -> str:
    current_text = " ".join(
        [
            _stringify_text(current_item.get("storyboard_description")),
            _stringify_text(current_item.get("image_prompt")),
            _stringify_text(current_item.get("final_video_prompt")),
        ]
    )
    lang = "zh" if re.search(r"[\u4e00-\u9fff]", current_text) else "en"
    prev_characters = _normalize_character_mentions(previous_item.get("characters")) or []
    current_characters = _normalize_character_mentions(current_item.get("characters")) or []
    shared_characters = [name for name in current_characters if name in prev_characters]

    if lang == "zh":
        if shared_characters:
            subject = "、".join(shared_characters)
            return f"承接上一镜头，保持{subject}外观与主衣物、场景布局和光线连续，衔接当前动作起点。"
        return "承接上一镜头，保持场景布局和光线连续，衔接当前动作起点。"

    if shared_characters:
        subject = ", ".join(shared_characters)
        return (
            f"Continue from the previous shot, keep {subject} on-model in the same primary outfit, "
            "and preserve the same layout and lighting before the next action."
        )
    return "Continue from the previous shot, preserving the same layout and lighting before the next action."


def _scene_core_middle_score(item: Mapping[str, Any], original_index: int, group_size: int) -> tuple[int, float]:
    scene_position = _stringify_text(item.get("scene_position")).lower()
    scene_intensity = _stringify_text(item.get("scene_intensity")).lower()
    audio_reference = item.get("audio_reference") if isinstance(item.get("audio_reference"), Mapping) else {}
    audio_type = _stringify_text(audio_reference.get("type")).lower()

    score = 0
    if scene_position == "climax":
        score += 60
    elif scene_position == "development":
        score += 45
    elif scene_position == "resolution":
        score += 35
    elif scene_position == "establishing":
        score += 10

    if scene_intensity == "high":
        score += 18
    if audio_type in {"dialogue", "narration"}:
        score += 10

    center = (group_size - 1) / 2
    distance_penalty = abs(original_index - center)
    return score, -distance_penalty


def _split_text_units(text: Any) -> list[str]:
    cleaned = _collapse_spaces(_stringify_text(text))
    if not cleaned:
        return []

    parts = re.split(r"(?:[。！？!?；;]+|\.\s+|\n+)", cleaned)
    units: list[str] = []
    for part in parts:
        normalized = _strip_terminal_punctuation(part)
        if not normalized:
            continue
        if re.fullmatch(r"(?:镜头|shot)\s*[一二三四五六七八九十百千万0-9]+", normalized, flags=re.IGNORECASE):
            continue
        lowered = normalized.casefold()
        if any(lowered in existing.casefold() or existing.casefold() in lowered for existing in units):
            continue
        units.append(normalized)
    return units


def _join_text_units(units: list[str]) -> str:
    if not units:
        return ""
    if _contains_cjk(" ".join(units)):
        return "。".join(units) + "。"
    return ". ".join(units) + "."


def _merge_text_units(base: Any, extra: Any, *, max_units: int | None = None) -> str:
    merged = list(_split_text_units(base))
    for unit in _split_text_units(extra):
        lowered = unit.casefold()
        if any(lowered in existing.casefold() or existing.casefold() in lowered for existing in merged):
            continue
        merged.append(unit)
    if max_units is not None and len(merged) > max_units:
        merged = merged[:max_units]
    return _join_text_units(merged)


def _merge_character_lists(base: Any, extra: Any) -> list[str] | None:
    merged: list[str] = []
    for candidate in (_normalize_character_mentions(base) or []) + (_normalize_character_mentions(extra) or []):
        if candidate not in merged:
            merged.append(candidate)
    return merged or None


def _audio_reference_story_note(audio_reference: Mapping[str, Any] | None) -> str:
    if not isinstance(audio_reference, Mapping):
        return ""

    content = _stringify_text(audio_reference.get("content"))
    if not content:
        return ""

    speaker = _stringify_text(audio_reference.get("speaker"))
    audio_type = _stringify_text(audio_reference.get("type")).lower()
    if audio_type == "narration" or speaker == "旁白":
        return f"同时旁白补充：{content}" if _contains_cjk(content) else f"Narration adds: {content}"
    if speaker:
        return f"同时{speaker}开口说：{content}" if _contains_cjk(content + speaker) else f"{speaker} speaks: {content}"
    return content


def _merge_audio_references(
    target_audio: Mapping[str, Any] | None,
    source_audio: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(source_audio, Mapping):
        return dict(target_audio) if isinstance(target_audio, Mapping) else None
    if not isinstance(target_audio, Mapping):
        return dict(source_audio)

    target_type = _stringify_text(target_audio.get("type")).lower()
    source_type = _stringify_text(source_audio.get("type")).lower()
    target_speaker = _stringify_text(target_audio.get("speaker"))
    source_speaker = _stringify_text(source_audio.get("speaker"))
    if target_type != source_type or target_speaker != source_speaker:
        return dict(target_audio)

    merged = dict(target_audio)
    merged["content"] = _merge_text_units(
        target_audio.get("content"),
        source_audio.get("content"),
        max_units=2,
    ) or _stringify_text(target_audio.get("content")) or _stringify_text(source_audio.get("content")) or None
    return merged


def _score_merge_target(
    *,
    source_index: int,
    source_item: Mapping[str, Any],
    target_index: int,
    target_item: Mapping[str, Any],
) -> tuple[int, int, int, int]:
    distance = abs(source_index - target_index)
    score = -distance * 10

    source_audio = source_item.get("audio_reference") if isinstance(source_item.get("audio_reference"), Mapping) else None
    target_audio = target_item.get("audio_reference") if isinstance(target_item.get("audio_reference"), Mapping) else None
    if source_audio:
        if not target_audio:
            score += 8
        elif (
            _stringify_text(source_audio.get("type")).lower() == _stringify_text(target_audio.get("type")).lower()
            and _stringify_text(source_audio.get("speaker")) == _stringify_text(target_audio.get("speaker"))
        ):
            score += 6
        else:
            score -= 6

    source_position = _stringify_text(source_item.get("scene_position")).lower()
    target_position = _stringify_text(target_item.get("scene_position")).lower()
    if source_position and source_position == target_position:
        score += 2
    if source_position in {"development", "climax", "resolution"} and target_position == "establishing":
        score -= 12
    if source_position in {"development", "climax"} and target_position in {"development", "climax"}:
        score += 4
    if source_position == "resolution" and target_position == "resolution":
        score += 4

    direction_bias = 1 if target_index >= source_index else 0
    return score, -distance, direction_bias, target_index


def _merge_core_shot_item(target_item: dict[str, Any], source_item: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(target_item)
    merged["characters"] = _merge_character_lists(merged.get("characters"), source_item.get("characters"))

    merged["storyboard_description"] = _merge_text_units(
        merged.get("storyboard_description"),
        source_item.get("storyboard_description"),
        max_units=4,
    ) or _stringify_text(merged.get("storyboard_description"))

    target_visuals = dict(merged.get("visual_elements") or {})
    source_visuals = dict(source_item.get("visual_elements") or {})
    for field_name, max_units in (
        ("subject_and_clothing", 3),
        ("action_and_expression", 3),
        ("environment_and_props", 3),
        ("lighting_and_color", 2),
    ):
        target_visuals[field_name] = _merge_text_units(
            target_visuals.get(field_name),
            source_visuals.get(field_name),
            max_units=max_units,
        ) or _stringify_text(target_visuals.get(field_name))
    merged["visual_elements"] = target_visuals

    merged["image_prompt"] = _merge_text_units(
        merged.get("image_prompt"),
        source_item.get("image_prompt"),
        max_units=4,
    ) or _stringify_text(merged.get("image_prompt")) or None
    merged["final_video_prompt"] = _merge_text_units(
        merged.get("final_video_prompt"),
        source_item.get("final_video_prompt"),
        max_units=4,
    ) or _stringify_text(merged.get("final_video_prompt"))

    original_target_audio = merged.get("audio_reference") if isinstance(merged.get("audio_reference"), Mapping) else None
    source_audio = source_item.get("audio_reference") if isinstance(source_item.get("audio_reference"), Mapping) else None
    merged_audio = _merge_audio_references(original_target_audio, source_audio)
    merged["audio_reference"] = merged_audio
    if source_audio and merged_audio == original_target_audio:
        merged["storyboard_description"] = _merge_text_units(
            merged.get("storyboard_description"),
            _audio_reference_story_note(source_audio),
            max_units=4,
        ) or _stringify_text(merged.get("storyboard_description"))

    if _normalize_scene_intensity(source_item.get("scene_intensity", "low")) == "high":
        merged["scene_intensity"] = "high"

    merged["estimated_duration"] = min(
        5,
        max(
            _coerce_estimated_duration(merged.get("estimated_duration")),
            _coerce_estimated_duration(source_item.get("estimated_duration")),
        ),
    )
    merged["mood"] = _merge_text_units(
        merged.get("mood"),
        source_item.get("mood"),
        max_units=2,
    ) or _stringify_text(merged.get("mood")) or _stringify_text(source_item.get("mood")) or None
    return merged


def _limit_core_shot_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped_items: list[tuple[str, list[tuple[int, dict[str, Any]]]]] = []
    group_lookup: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for original_index, item in enumerate(items):
        scene_key = _stringify_text(item.get("source_scene_key"))
        if not scene_key:
            shot_scene_index = _extract_scene_index_from_shot_id(_stringify_text(item.get("shot_id")))
            scene_key = f"scene{shot_scene_index}" if shot_scene_index is not None else f"scene_group_{original_index + 1}"
        bucket = group_lookup.get(scene_key)
        if bucket is None:
            bucket = []
            group_lookup[scene_key] = bucket
            grouped_items.append((scene_key, bucket))
        bucket.append((original_index, item))

    limited: list[dict[str, Any]] = []
    for group_order, (_, group) in enumerate(grouped_items, start=1):
        if len(group) <= 3:
            selected_items = [(original_index, dict(raw_item)) for original_index, raw_item in group]
        else:
            first_entry = group[0]
            last_entry = group[-1]
            middle_candidates = group[1:-1]
            middle_entry = max(
                middle_candidates,
                key=lambda entry: _scene_core_middle_score(entry[1], entry[0], len(group)),
            )
            selected = [first_entry, middle_entry, last_entry]
            selected.sort(key=lambda entry: entry[0])
            selected_items = [(original_index, dict(raw_item)) for original_index, raw_item in selected]
            selected_original_indices = {original_index for original_index, _ in selected}
            omitted_items = [
                (original_index, raw_item)
                for original_index, raw_item in group
                if original_index not in selected_original_indices
            ]
            for omitted_index, omitted_item in omitted_items:
                best_selected_position = max(
                    range(len(selected_items)),
                    key=lambda selected_position: _score_merge_target(
                        source_index=omitted_index,
                        source_item=omitted_item,
                        target_index=selected_items[selected_position][0],
                        target_item=selected_items[selected_position][1],
                    ),
                )
                target_index, target_item = selected_items[best_selected_position]
                selected_items[best_selected_position] = (
                    target_index,
                    _merge_core_shot_item(target_item, omitted_item),
                )

        original_scene_index = _extract_scene_index_from_shot_id(_stringify_text(group[0][1].get("shot_id")))
        scene_index = original_scene_index or group_order

        previous_selected_item: dict[str, Any] | None = None
        previous_original_index: int | None = None
        for new_position, (original_index, raw_item) in enumerate(selected_items, start=1):
            updated = dict(raw_item)
            updated["shot_id"] = f"scene{scene_index}_shot{new_position}"
            if new_position == 1:
                updated["transition_from_previous"] = None
            elif previous_selected_item is not None:
                if previous_original_index is not None and original_index == previous_original_index + 1:
                    existing_transition = _stringify_text(updated.get("transition_from_previous"))
                    updated["transition_from_previous"] = existing_transition or _core_transition_hint(previous_selected_item, updated)
                else:
                    updated["transition_from_previous"] = _core_transition_hint(previous_selected_item, updated)
            if not _stringify_text(updated.get("scene_position")):
                updated["scene_position"] = ("establishing", "development", "climax")[min(new_position - 1, 2)]
            limited.append(updated)
            previous_selected_item = updated
            previous_original_index = original_index

    return limited


def _parse_shots(
    raw: str,
    *,
    scene_mapping: Optional[dict[int, str]] = None,
    allowed_audio_lookup: Optional[dict[str, dict[tuple[str, str, str | None], dict[str, Any]]]] = None,
) -> List[Shot]:
    """解析 LLM 输出为 Shot 列表，兼容新旧两种 JSON 格式。"""
    data = [
        _normalize_shot_item(raw_item, shot_number=shot_number, scene_mapping=scene_mapping)
        for shot_number, raw_item in enumerate(_load_storyboard_items(raw), start=1)
    ]
    for item in data:
        item["audio_reference"] = _filter_audio_reference_to_script(
            item.get("audio_reference") if isinstance(item.get("audio_reference"), Mapping) else None,
            shot_id=_stringify_text(item.get("shot_id")),
            source_scene_key=_stringify_text(item.get("source_scene_key")) or None,
            characters=_normalize_character_mentions(item.get("characters")),
            allowed_audio_lookup=allowed_audio_lookup,
        )
    data = _limit_core_shot_items(data)
    scene_items: dict[str, list[dict[str, Any]]] = {}
    for item in data:
        scene_key = _stringify_text(item.get("source_scene_key"))
        if not scene_key:
            shot_match = re.match(r"scene(\d+)_shot", _collapse_spaces(_stringify_text(item.get("shot_id"))), flags=re.IGNORECASE)
            scene_key = f"scene{shot_match.group(1)}" if shot_match else "scene1"
        scene_items.setdefault(scene_key, []).append(item)

    shots = []
    for scene_key, items in scene_items.items():
        has_retained_audio = any(item.get("audio_reference") for item in items)
        allowed_audio_items = list((allowed_audio_lookup or {}).get(scene_key, {}).values())
        if not has_retained_audio and len(allowed_audio_items) == 1:
            candidate_audio = allowed_audio_items[0]
            if _stringify_text(candidate_audio.get("type")).lower() == "narration":
                first_item = items[0]
                first_item["audio_reference"] = _finalize_audio_reference(
                    dict(candidate_audio),
                    characters=_normalize_character_mentions(first_item.get("characters")),
                )

    for shot_number, item in enumerate(data, start=1):
        try:
            shots.append(_postprocess_shot(Shot(**item)))
            continue
        except (ValidationError, ValueError, TypeError) as exc:
            logger.warning(
                "Storyboard shot fallback triggered shot_number=%s shot_id=%s error=%s",
                shot_number,
                item.get("shot_id", ""),
                exc,
            )

        fallback_item = _build_minimal_valid_shot_item(item, shot_number=shot_number, scene_mapping=scene_mapping)
        try:
            shots.append(_postprocess_shot(Shot(**fallback_item)))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Storyboard shot dropped after fallback shot_number=%s shot_id=%s error=%s",
                shot_number,
                fallback_item.get("shot_id", ""),
                exc,
            )

    if not shots:
        raise ValueError("分镜解析失败：没有可用镜头")
    return shots


async def parse_script_to_storyboard(
    script: str,
    provider: str,
    model: str | None = None,
    api_key: str = "",
    base_url: str = "",
    character_info: Optional[dict] = None,
    character_section_override: Optional[str] = None,
    telemetry_context: Optional[dict[str, Any]] = None,
) -> tuple[list[Shot], dict]:
    """
    Parse script to storyboard shots.

    Args:
        script: The script text to parse
        provider: LLM provider name (claude, openai, qwen, zhipu, gemini, siliconflow)
        model: Model name (optional)
        api_key: API key for the provider (optional, will use settings if not provided)
        base_url: Base URL for the provider (optional, will use settings if not provided)
        character_info: Character data dict with 'characters' list and 'character_images' dict (optional)
        character_section_override: Override character reference block sent to storyboard LLM

    Returns:
        tuple: (list of Shot objects, usage dict with prompt_tokens and completion_tokens)
    """
    character_section = character_section_override or build_character_section(character_info, script=script)
    scene_mapping = _build_scene_mapping(script)
    scene_mapping_section = _build_scene_mapping_section(script)
    script_audio_lookup = _build_script_audio_lookup(script, scene_mapping=scene_mapping)
    llm = get_llm_provider(provider, model=model, api_key=api_key, base_url=base_url)
    async def _generate_storyboard_candidate(prompt_suffix: str, _attempt: int) -> tuple[list[Shot], dict[str, Any]]:
        request_messages = [
            {
                "role": "user",
                "content": USER_TEMPLATE.format(
                    character_section=character_section,
                    scene_mapping_section=scene_mapping_section,
                    script="[SCRIPT PROVIDED IN THE NEXT MESSAGE]",
                ),
                "cacheable": True,
            },
            {
                "role": "user",
                "content": f"Audio-Visual Script:\n---\n{script}\n---\n\nReturn a JSON array of shots only.",
            },
        ]
        if str(prompt_suffix or "").strip():
            request_messages.append(
                {
                    "role": "user",
                    "content": f"Additional quality constraints:\n{prompt_suffix.strip()}",
                }
            )

        try:
            raw, usage = await llm.complete_messages_with_usage(
                system=SYSTEM_PROMPT,
                messages=request_messages,
                temperature=0.2,
                enable_caching=True,
                telemetry_context={
                    **dict(telemetry_context or {}),
                    "operation": "storyboard.parse",
                },
            )
        except Exception as exc:
            resolved_base_url = base_url or "(default)"
            logger.exception(
                "Storyboard LLM request failed provider=%s model=%s base_url=%s script_chars=%s",
                provider,
                model or "(default)",
                resolved_base_url,
                len(script or ""),
            )
            raise RuntimeError(
                f"Storyboard LLM request failed (provider={provider}, model={model or '(default)'}, "
                f"base_url={resolved_base_url}): {exc}"
            ) from exc

        shots = _parse_shots(raw, scene_mapping=scene_mapping, allowed_audio_lookup=script_audio_lookup)
        return shots, usage

    shots, usage, quality_run = await run_quality_guarded_generation(
        family="storyboard_parse",
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        generate_candidate=_generate_storyboard_candidate,
        candidate_payload_builder=lambda candidate: [_serialize_storyboard_candidate_shot(shot) for shot in candidate],
        telemetry_context=telemetry_context,
    )
    merged_usage = dict(usage or {})
    merged_usage["quality"] = quality_run
    return shots, merged_usage
