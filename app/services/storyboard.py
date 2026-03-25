import json
import re
from typing import List, Optional

from app.services.llm.factory import get_llm_provider
from app.schemas.storyboard import Shot
from app.prompts.storyboard import SYSTEM_PROMPT, USER_TEMPLATE
from app.prompts.character import build_character_section

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


def _strip_terminal_punctuation(text: str) -> str:
    return (text or "").strip(" ,.;:!?，。；：！？、")


def _collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _trim_words(text: str, limit: int) -> str:
    words = _collapse_spaces(text).split()
    if len(words) <= limit:
        return _strip_terminal_punctuation(_collapse_spaces(text))
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
    return _trim_words(cleaned, 110)


def _normalize_video_prompt(text: str) -> str:
    cleaned = _strip_patterns(text, _STYLE_PATTERNS + _VIDEO_VERBOSE_PATTERNS)
    cleaned = re.sub(r"[\"'][^\"']+[\"']", " speaking", cleaned)
    cleaned = re.sub(r"\s*,\s*", ", ", cleaned)
    cleaned = re.sub(r"(?:,\s*){2,}", ", ", cleaned)
    cleaned = re.sub(r"(^|[.])\s*,\s*", r"\1 ", cleaned)
    return _trim_words(cleaned, 85)


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
    subject = _trim_words(shot.visual_elements.subject_and_clothing, 28)
    pose = _freeze_action_phrase(shot.visual_elements.action_and_expression)
    environment = _trim_words(shot.visual_elements.environment_and_props, 24)
    lighting = _trim_words(shot.visual_elements.lighting_and_color, 18)
    parts = [
        _shot_phrase(shot, lang),
        _sentence_localized(subject, lang),
        _sentence_localized(pose, lang, "定格：") if pose and lang == "zh" else _sentence_localized(pose, lang, "Frozen pose: ") if pose else "",
        _sentence_localized(environment, lang) if environment else "",
        _sentence_localized(lighting, lang) if lighting else "",
    ]
    return _trim_words(_join_prompt_parts(parts, lang), 120)


def _compose_video_prompt(shot: Shot) -> str:
    lang = _preferred_language(shot)
    movement = _camera_movement_sentence(shot)
    subject = _trim_words(shot.visual_elements.subject_and_clothing, 20)
    environment = _trim_words(shot.visual_elements.environment_and_props, 14)
    lighting = _trim_words(shot.visual_elements.lighting_and_color, 12)
    parts = [
        _shot_phrase(shot, lang),
        movement,
        _sentence_localized(subject, lang) if subject else "",
        _minimal_motion_clause(shot),
        _sentence_localized(environment, lang) if environment else "",
        _sentence_localized(lighting, lang) if lighting else "",
    ]
    return _trim_words(_join_prompt_parts(parts, lang), 85)


def _postprocess_shot(shot: Shot) -> Shot:
    raw_image_prompt = shot.image_prompt or ""
    raw_video_prompt = shot.final_video_prompt or ""
    has_composable_visuals = bool(
        shot.visual_elements.subject_and_clothing
        or shot.visual_elements.environment_and_props
        or shot.visual_elements.action_and_expression
        or shot.visual_elements.lighting_and_color
    )

    # Preserve prompt fields generated by the storyboard LLM whenever available.
    # Recent system-prompt updates intentionally shape image/video prompt wording,
    # length, and language. Rebuilding them here would silently override those changes.
    if raw_image_prompt:
        shot.image_prompt = _normalize_image_prompt(raw_image_prompt)
    elif shot.visual_elements.subject_and_clothing or shot.visual_elements.environment_and_props:
        shot.image_prompt = _compose_image_prompt(shot)
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

    if shot.last_frame_prompt:
        shot.last_frame_prompt = _normalize_image_prompt(shot.last_frame_prompt)

    return shot


def _parse_shots(raw: str) -> List[Shot]:
    """解析 LLM 输出为 Shot 列表，兼容新旧两种 JSON 格式。"""
    cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
    data = json.loads(cleaned)
    shots = []
    for item in data:
        # 旧格式兼容：将扁平字段映射到新嵌套结构
        if "visual_prompt" in item and "final_video_prompt" not in item:
            item["final_video_prompt"] = item.pop("visual_prompt")
        if "visual_description_zh" in item and "storyboard_description" not in item:
            item["storyboard_description"] = item.pop("visual_description_zh")
        if "camera_motion" in item and "camera_setup" not in item:
            item["camera_setup"] = {
                "shot_size": item.pop("shot_size", "MS"),
                "camera_angle": "Eye-level",
                "movement": item.pop("camera_motion"),
            }
        elif "camera_setup" not in item:
            item["camera_setup"] = {
                "shot_size": item.pop("shot_size", "MS"),
                "camera_angle": "Eye-level",
                "movement": "Static",
            }
        else:
            # Partial nested dict: fill missing subfields so Pydantic validation passes
            cs = item["camera_setup"]
            cs.setdefault("shot_size", item.pop("shot_size", "MS"))
            cs.setdefault("camera_angle", "Eye-level")
            cs.setdefault("movement", "Static")
        item["camera_setup"]["movement"] = _normalize_camera_movement(item["camera_setup"].get("movement", "Static"))
        if "dialogue" in item and "audio_reference" not in item:
            dlg = item.pop("dialogue")
            item["audio_reference"] = {
                "type": "dialogue" if dlg else None,
                "content": dlg,
            }
        elif item.get("audio_reference") is None:
            # Consume legacy dialogue key even when audio_reference key exists but is null
            dlg = item.pop("dialogue", None)
            if dlg:
                item["audio_reference"] = {"type": "dialogue", "content": dlg}
        if "visual_elements" not in item:
            item["visual_elements"] = {
                "subject_and_clothing": "",
                "action_and_expression": "",
                "environment_and_props": "",
                "lighting_and_color": "",
            }
        else:
            # Partial nested dict: fill missing subfields
            ve = item["visual_elements"]
            ve.setdefault("subject_and_clothing", "")
            ve.setdefault("action_and_expression", "")
            ve.setdefault("environment_and_props", "")
            ve.setdefault("lighting_and_color", "")
        if "scene_intensity" not in item:
            item["scene_intensity"] = "low"
        # 清理旧格式残留的顶层字段，避免 Pydantic 报错
        for old_key in ("shot_size", "camera_motion", "dialogue",
                        "visual_prompt", "visual_description_zh"):
            item.pop(old_key, None)
        shots.append(_postprocess_shot(Shot(**item)))
    return shots


async def parse_script_to_storyboard(
    script: str,
    provider: str,
    model: str | None = None,
    api_key: str = "",
    base_url: str = "",
    character_info: Optional[dict] = None,
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

    Returns:
        tuple: (list of Shot objects, usage dict with prompt_tokens and completion_tokens)
    """
    character_section = build_character_section(character_info)
    llm = get_llm_provider(provider, model=model, api_key=api_key, base_url=base_url)
    raw, usage = await llm.complete_with_usage(
        system=SYSTEM_PROMPT,
        user=USER_TEMPLATE.format(character_section=character_section, script=script),
        temperature=0.2,
    )
    shots = _parse_shots(raw)
    return shots, usage
