from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from app.core.api_keys import inject_art_style
from app.core.character_profile import sanitize_character_profile_description
from app.core.consistency_cache import (
    is_appearance_cache_entry_compatible,
    is_scene_style_cache_entry_compatible,
)
from app.core.story_assets import (
    extract_scene_index_from_shot_id,
    get_character_asset_entry,
    get_character_appearance_cache_entry,
    get_character_design_prompt,
    get_character_visual_dna,
    get_scene_reference_asset,
)


_CLOTHING_HINTS = (
    "wearing",
    "dressed",
    "coat",
    "robe",
    "shirt",
    "dress",
    "armor",
    "uniform",
    "hanfu",
    "kimono",
    "jacket",
    "cloak",
    "cape",
    "vest",
    "tunic",
    "shawl",
    "scarf",
    "gloves",
    "belt",
    "sash",
    "hat",
    "cap",
    "hood",
    "helmet",
    "headband",
    "veil",
    "mask",
    "glasses",
    "goggles",
    "necklace",
    "earrings",
    "bracelet",
    "ring",
    "boots",
    "hatband",
    "hairpin",
    "brooch",
    "帽",
    "头巾",
    "斗笠",
    "发带",
    "披风",
    "围巾",
    "腰带",
    "眼镜",
    "面具",
    "耳环",
    "衣",
    "袍",
    "衫",
    "裙",
    "甲",
    "服",
)
_WARDROBE_CHANGE_HINTS = (
    "change outfit",
    "changes outfit",
    "changed outfit",
    "puts on",
    "takes off",
    "换装",
    "换上",
    "脱下",
    "更衣",
)
_VIEW_HINT_PATTERNS: dict[str, tuple[str, ...]] = {
    "front": (
        "front view",
        "front-facing",
        "facing camera",
        "facing forward",
        "frontal",
        "正面",
        "迎面",
    ),
    "side": (
        "side view",
        "side profile",
        "profile view",
        "in profile",
        "侧面",
        "侧身",
    ),
    "back": (
        "back view",
        "rear view",
        "from behind",
        "back-facing",
        "背面",
        "背影",
        "背对",
    ),
}
_SHOT_SIZE_LABELS: dict[str, tuple[str, str]] = {
    "EWS": ("远大全景", "Extreme wide shot"),
    "WS": ("全景", "Wide shot"),
    "MWS": ("中远景", "Medium wide shot"),
    "MS": ("中景", "Medium shot"),
    "MCU": ("中近景", "Medium close-up"),
    "CU": ("近景", "Close-up"),
    "ECU": ("特写", "Extreme close-up"),
    "OTS": ("过肩镜头", "Over-the-shoulder shot"),
}
_LEADING_FRAMING_PATTERNS_EN = (
    r"^(?:extreme wide shot|wide shot|medium wide shot|medium shot|medium close[- ]up|close[- ]up|extreme close[- ]up|over[- ]the[- ]shoulder(?: shot)?|tight portrait|close portrait|portrait close[- ]up|head[- ]and[- ]shoulders portrait)\b[.,:; ]*",
)
_LEADING_FRAMING_PATTERNS_ZH = (
    r"^(?:远大全景|全景|中远景|中景|中近景|近景|特写|过肩镜头)[，。,：； ]*",
)
_HAND_ACTION_HINTS = (
    "hand",
    "hands",
    "arm",
    "arms",
    "finger",
    "fingers",
    "palm",
    "wrist",
    "push",
    "pull",
    "open",
    "close",
    "grab",
    "hold",
    "holding",
    "touch",
    "reach",
    "raise",
    "lower",
    "pick up",
    "put down",
    "pick",
    "place",
    "扶",
    "手",
    "手臂",
    "抬手",
    "抬起",
    "抬臂",
    "推",
    "拉",
    "开门",
    "关门",
    "握",
    "抓",
    "拿",
    "放下",
    "触",
    "碰",
)
_BODY_MOTION_HINTS = (
    "walk",
    "step",
    "turn",
    "enter",
    "leave",
    "sit",
    "stand",
    "kneel",
    "rise",
    "run",
    "lean",
    "crouch",
    "fall",
    "walks",
    "steps",
    "turns",
    "enters",
    "leaves",
    "sits",
    "stands",
    "kneels",
    "rises",
    "runs",
    "leans",
    "crouches",
    "falls",
    "走",
    "迈",
    "进入",
    "离开",
    "转身",
    "坐下",
    "站起",
    "起身",
    "俯身",
    "弯腰",
    "蹲",
    "跪",
    "跑",
    "后退",
    "前进",
)
_PHYSICAL_HINTS = (
    "year-old",
    "young",
    "middle-aged",
    "elderly",
    "male",
    "female",
    "man",
    "woman",
    "boy",
    "girl",
    "hair",
    "haired",
    "eyes",
    "skin",
    "build",
    "slim",
    "slender",
    "lean",
    "athletic",
    "broad",
    "tall",
    "short",
    "scar",
    "freckles",
    "beard",
    "mustache",
    "moustache",
    "wrinkle",
    "robe",
    "coat",
    "shirt",
    "dress",
    "armor",
    "uniform",
    "hanfu",
    "kimono",
    "jacket",
    "cloak",
    "boots",
    "25岁",
    "40岁",
    "青年",
    "中年",
    "老人",
    "男子",
    "女性",
    "男人",
    "女人",
    "男孩",
    "女孩",
    "头发",
    "短发",
    "长发",
    "黑发",
    "白发",
    "银发",
    "眼",
    "瞳",
    "肤",
    "身形",
    "体型",
    "清瘦",
    "高瘦",
    "健壮",
    "发福",
    "胡",
    "疤",
    "袍",
    "衫",
    "裙",
    "甲",
    "服",
    "靴",
)
_NON_PHYSICAL_HINTS = (
    "kind",
    "brave",
    "loyal",
    "smart",
    "clever",
    "talented",
    "genius",
    "lonely",
    "gentle",
    "cold",
    "cruel",
    "ruthless",
    "ambitious",
    "determined",
    "mysterious",
    "friendly",
    "supportive",
    "personality",
    "backstory",
    "ability",
    "power",
    "secret",
    "truth",
    "destiny",
    "孤僻",
    "善良",
    "勇敢",
    "忠诚",
    "聪明",
    "天才",
    "冷酷",
    "傲慢",
    "温柔",
    "野心",
    "神秘",
    "能力",
    "秘密",
    "真相",
    "命运",
    "出身",
    "背景",
    "性格",
    "好友",
    "反派",
    "主角",
    "支持",
    "敌意",
    "对抗",
    "解开",
    "卷入",
    "追杀",
)
_GENRE_STYLE_RULES: dict[str, tuple[str, str, str]] = {
    "古风": (
        "ancient Chinese architecture, traditional props, weathered wood, period-authentic details",
        "ancient Chinese environment, traditional structures, era-consistent props",
        "modern buildings, modern clothing, cars, electric lights, plastic materials",
    ),
    "仙侠": (
        "ancient Chinese fantasy setting, flowing robes, mist, mystical natural atmosphere",
        "ancient Chinese fantasy environment, flowing robes, mystical atmosphere",
        "modern buildings, modern clothing, cars, electric lights, plastic materials",
    ),
    "武侠": (
        "martial-arts period setting, traditional architecture, grounded practical props",
        "martial-arts period environment, traditional structures, grounded props",
        "modern buildings, modern clothing, cars, electric lights, plastic materials",
    ),
    "历史": (
        "period-authentic architecture, era-consistent props, historical material details",
        "historical environment, period-authentic architecture, era-consistent props",
        "modern buildings, modern clothing, cars, electric lights, plastic materials",
    ),
    "宫斗": (
        "palace interiors, court costume materials, carved wood, silk textures, period detail",
        "palace environment, court costume textures, period-authentic atmosphere",
        "modern buildings, modern clothing, cars, electric lights, plastic materials",
    ),
    "科幻": (
        "futuristic environment, advanced interfaces, coherent sci-fi production design",
        "futuristic environment, coherent sci-fi design, advanced interfaces",
        "",
    ),
    "赛博": (
        "cyberpunk urban atmosphere, neon practical lighting, dense futuristic details",
        "cyberpunk city environment, practical neon lighting, dense futuristic details",
        "",
    ),
}


@dataclass
class CharacterLock:
    name: str = ""
    body_features: str = ""
    default_clothing: str = ""
    negative_prompt: str = ""


@dataclass
class SceneStyle:
    keywords: list[str] = field(default_factory=list)
    image_extra: str = ""
    video_extra: str = ""
    negative_prompt: str = ""
    always_apply: bool = False


@dataclass
class StoryContext:
    base_art_style: str = ""
    scene_styles: list[SceneStyle] = field(default_factory=list)
    global_negative_prompt: str = ""
    character_locks: dict[str, CharacterLock] = field(default_factory=dict)
    clean_character_section: str = ""
    cache_fingerprint: str = ""


def _collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def _trim_words(text: str, limit: int) -> str:
    words = _collapse_spaces(text).split()
    if len(words) <= limit:
        return _collapse_spaces(text).strip(" ,.;:!?，。；：！？、")
    return " ".join(words[:limit]).strip(" ,.;:!?，。；：！？、")


def _trim_chars(text: str, limit: int) -> str:
    normalized = _collapse_spaces(text)
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip(" ,.;:!?，。；：！？、")


def _sentence(text: str, lang: str, prefix: str = "") -> str:
    normalized = _collapse_spaces(text)
    if not normalized:
        return ""
    if prefix:
        normalized = f"{prefix}{normalized}"
    return f"{normalized}。" if lang == "zh" else f"{normalized}."


def normalize_cache_block(text: str) -> str:
    normalized = text or ""
    normalized = re.sub(r"Generated at:\s*[^\n]+", " ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"request[_ -]?id:\s*[^\n]+", " ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
        " ",
        normalized,
        flags=re.IGNORECASE,
    )
    return _collapse_spaces(normalized)


def get_cache_fingerprint(story_ctx: StoryContext, system_prompt: str, stable_blocks: list[str]) -> str:
    normalized_blocks = [
        normalize_cache_block(system_prompt),
        normalize_cache_block(story_ctx.clean_character_section),
        normalize_cache_block(story_ctx.base_art_style),
        *[normalize_cache_block(block) for block in stable_blocks],
    ]
    payload = "\n\n".join(block for block in normalized_blocks if block)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest() if payload else ""


def _extract_description_fragment(text: str, hints: tuple[str, ...], word_limit: int) -> str:
    if not text:
        return ""
    parts = re.split(r"[，。；;,.]", text)
    matched = [part.strip() for part in parts if any(hint in part.lower() for hint in hints)]
    if matched:
        return _trim_words(", ".join(matched), word_limit)
    return ""


def _join_unique_bits(*parts: str) -> str:
    merged: list[str] = []
    for part in parts:
        normalized = _collapse_spaces(part)
        if not normalized or normalized in merged:
            continue
        merged.append(normalized)
    return "; ".join(merged)


def _looks_like_physical_detail(text: str) -> bool:
    lowered = _collapse_spaces(text).lower()
    if not lowered:
        return False
    return any(hint in lowered for hint in _PHYSICAL_HINTS)


def _looks_like_non_physical_detail(text: str) -> bool:
    lowered = _collapse_spaces(text).lower()
    if not lowered:
        return False
    return any(hint in lowered for hint in _NON_PHYSICAL_HINTS)


def _split_description_fragments(text: str) -> list[str]:
    return [
        fragment.strip()
        for fragment in re.split(r"[。；;，,\n]", text or "")
        if fragment and fragment.strip()
    ]


def sanitize_body_features(text: str, *, fallback_description: str = "") -> str:
    normalized = _collapse_spaces(text)
    fragments = _split_description_fragments(normalized)
    kept = [
        fragment
        for fragment in fragments
        if _looks_like_physical_detail(fragment) and not _looks_like_non_physical_detail(fragment)
    ]
    if not kept and fallback_description:
        kept = [
            fragment
            for fragment in _split_description_fragments(fallback_description)
            if _looks_like_physical_detail(fragment) and not _looks_like_non_physical_detail(fragment)
        ]
    if not kept and normalized and _looks_like_physical_detail(normalized) and not _looks_like_non_physical_detail(normalized):
        kept = [normalized]
    return _trim_words(", ".join(dict.fromkeys(kept)), 24)


def sanitize_default_clothing(text: str, *, fallback_description: str = "") -> str:
    normalized = _collapse_spaces(text)
    if normalized and any(hint in normalized.lower() for hint in _CLOTHING_HINTS):
        return _trim_words(normalized, 16)
    guessed = _extract_description_fragment(fallback_description, _CLOTHING_HINTS, 16)
    return _trim_words(guessed, 16)


def _guess_body_features(description: str) -> str:
    return sanitize_body_features("", fallback_description=description)


def _guess_default_clothing(description: str) -> str:
    return sanitize_default_clothing("", fallback_description=description)


_DESIGN_PROMPT_ANCHOR_BOUNDARY = (
    r"(?:show front view"
    r"|show the complete outfit"
    r"|identity(?:_lock|\s+lock)(?:\s*:)?"
    r"|style(?:_lock|\s+lock)(?:\s*:)?"
    r"|visual\s+dna(?:\s*:)?"
    r"|identity:"
    r"|style:"
    r"|treat the character description as non-negotiable identity constraints"
    r"|follow this exact art style consistently across all three views"
    r"|keep one unified rendering style across all three views)"
)


def _extract_design_prompt_description(design_prompt: str) -> str:
    normalized = _collapse_spaces(design_prompt)
    if not normalized:
        return ""

    match = re.search(
        rf"character description:\s*(.+?)(?:(?:,\s*|;\s*)(?:{_DESIGN_PROMPT_ANCHOR_BOUNDARY})|$)",
        normalized,
        flags=re.IGNORECASE,
    )
    if match:
        return _collapse_spaces(match.group(1))
    return ""


def _clean_design_prompt_anchor_source(design_prompt: str) -> str:
    normalized = _collapse_spaces(design_prompt)
    if not normalized:
        return ""

    cleanup_patterns = (
        r"^Standard three-view character turnaround sheet for [^,，]+,\s*",
        r"^Full-body character design sheet for [^,，]+,\s*",
        r"\brole reference:\s*[^,，]+(?:,\s*)?",
        r"\b(?:villain, sinister expression, dark presence|protagonist, determined expression, heroic bearing|supporting character, approachable expression)\b",
        r"character description:\s*",
        rf"(?:^|,\s*|;\s*)(?:{_DESIGN_PROMPT_ANCHOR_BOUNDARY}).*$",
        r",?\s*show front view, side profile, and back view of the same character on one sheet\b",
        r",?\s*show the complete outfit from head to toe\b",
        r",?\s*full body in all three views\b",
        r",?\s*neutral standing pose\b",
        r",?\s*front-facing hero pose\b",
        r",?\s*clear silhouette\b",
        r",?\s*consistent facial features and costume details across views\b",
        r",?\s*distinctive physical traits\b",
        r",?\s*clean neutral backdrop\b",
        r",?\s*professional character concept art\b",
        r",?\s*production-ready character turnaround sheet\b",
        r",?\s*production-ready character sheet\b",
        r",?\s*costume construction details\b",
        r",?\s*fabric texture\b",
        r",?\s*accessories\b",
        r",?\s*highly detailed\b",
        r",?\s*photorealistic\b",
    )
    cleaned = normalized
    for pattern in cleanup_patterns:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*,\s*", ", ", cleaned)
    return _collapse_spaces(cleaned).strip(" ,.;:!?，。；：！？、")


def _character_asset_fallback_description(
    character_images: Mapping[str, Any] | None,
    *,
    character_id: str = "",
    name: str = "",
    description: str = "",
) -> str:
    design_prompt = get_character_design_prompt(character_images, character_id, name=name)
    prompt_description = _extract_design_prompt_description(design_prompt)
    prompt_anchor_source = _clean_design_prompt_anchor_source(design_prompt)
    visual_dna = get_character_visual_dna(character_images, character_id, name=name)
    return _join_unique_bits(
        prompt_description,
        prompt_anchor_source,
        visual_dna,
        description,
    )


def build_character_reference_anchor(
    character_images: Mapping[str, Any] | None,
    name: str,
    *,
    character_id: str = "",
    description: str = "",
    appearance_entry: Mapping[str, Any] | None = None,
) -> str:
    def _merge_visual_bits(*bits: str) -> str:
        merged: list[str] = []
        for bit in bits:
            normalized_bit = _collapse_spaces(bit)
            if not normalized_bit:
                continue
            lowered_bit = normalized_bit.lower()
            if any(lowered_bit in existing.lower() or existing.lower() in lowered_bit for existing in merged):
                continue
            merged.append(normalized_bit)
        return "; ".join(merged)

    normalized_description = _collapse_spaces(
        sanitize_character_profile_description(description, keep_original_if_empty=False)
    )
    visual_dna_body = sanitize_body_features(
        get_character_visual_dna(character_images, character_id, name=name),
        fallback_description=normalized_description,
    )
    prompt_fallback_description = _character_asset_fallback_description(
        character_images,
        character_id=character_id,
        name=name,
        description=normalized_description,
    )
    cached_entry = dict(appearance_entry or {}) if is_appearance_cache_entry_compatible(appearance_entry) else {}
    cached_body = sanitize_body_features(
        str(cached_entry.get("body", "")),
        fallback_description=normalized_description,
    ) if cached_entry else ""
    cached_clothing = sanitize_default_clothing(
        str(cached_entry.get("clothing", "")),
        fallback_description=prompt_fallback_description,
    ) if cached_entry else ""
    if cached_body or cached_clothing:
        merged = _merge_visual_bits(
            cached_body or sanitize_body_features("", fallback_description=prompt_fallback_description),
            cached_clothing or sanitize_default_clothing("", fallback_description=prompt_fallback_description),
        )
        if merged:
            return merged

    if visual_dna_body:
        clothing = sanitize_default_clothing(
            "",
            fallback_description=prompt_fallback_description,
        )
        merged = _merge_visual_bits(visual_dna_body, clothing)
        if merged:
            return merged

    body = sanitize_body_features(
        "",
        fallback_description=prompt_fallback_description,
    )
    clothing = sanitize_default_clothing(
        "",
        fallback_description=prompt_fallback_description,
    )
    merged = _merge_visual_bits(body, clothing)
    if merged:
        return merged

    return _trim_words(normalized_description, 24)


def _build_scene_styles(story: Mapping[str, Any]) -> list[SceneStyle]:
    genre = _collapse_spaces(str(story.get("genre", "")))
    meta = dict(story.get("meta") or {})
    cached_styles = meta.get("scene_style_cache") or []
    styles: list[SceneStyle] = []

    if genre:
        for key, (image_extra, video_extra, negative_prompt) in _GENRE_STYLE_RULES.items():
            if key in genre:
                styles.append(
                    SceneStyle(
                        keywords=[key],
                        image_extra=image_extra,
                        video_extra=video_extra,
                        negative_prompt=negative_prompt,
                        always_apply=True,
                    )
                )
                break

    if isinstance(cached_styles, list):
        for entry in cached_styles:
            if not is_scene_style_cache_entry_compatible(entry):
                continue
            keywords = entry.get("keywords") or []
            if not isinstance(keywords, list):
                keywords = []
            image_extra = _collapse_spaces(str(entry.get("image_extra", "")))
            video_extra = _collapse_spaces(str(entry.get("video_extra", "")))
            negative_prompt = _collapse_spaces(str(entry.get("negative_prompt", "")))
            if image_extra or video_extra or negative_prompt:
                styles.append(
                    SceneStyle(
                        keywords=[_collapse_spaces(str(keyword)) for keyword in keywords if str(keyword).strip()],
                        image_extra=image_extra,
                        video_extra=video_extra,
                        negative_prompt=negative_prompt,
                        always_apply=bool(entry.get("always_apply", False)),
                    )
                )

    return styles


def build_clean_character_section(character_locks: dict[str, CharacterLock], characters: list[dict]) -> str:
    if not characters:
        return ""

    lines = ["## Character Reference (maintain exact physical consistency across all shots)"]
    for character in characters:
        char_id = character.get("id", "")
        name = character.get("name", "")
        role = character.get("role", "")
        desc = sanitize_character_profile_description(character.get("description", ""))
        if not char_id or not name:
            continue

        lock = character_locks.get(char_id, CharacterLock(name=name))
        if desc:
            lines.append(f"- **{name}**（{role}）：{desc}")
        else:
            lines.append(f"- **{name}**（{role}）")

        visual_bits = [bit for bit in (lock.body_features, lock.default_clothing) if bit]
        if visual_bits:
            lines.append(f"  Visual DNA: {'; '.join(visual_bits)}")
            lines.append("  Wardrobe Lock: keep the same primary outfit silhouette, colors, materials, headwear, and signature accessories unless the script explicitly shows a wardrobe change")
        else:
            lines.append("  Visual DNA: use the character description conservatively; do not invent new traits")

    return "\n".join(lines)


def build_story_context(story: Mapping[str, Any]) -> StoryContext:
    characters = list(story.get("characters") or [])
    character_images = dict(story.get("character_images") or {})
    meta = dict(story.get("meta") or {})
    cached_appearance = dict(meta.get("character_appearance_cache") or {})

    character_locks: dict[str, CharacterLock] = {}
    for character in characters:
        char_id = character.get("id", "")
        name = character.get("name", "")
        if not char_id or not name:
            continue

        cached_entry = get_character_appearance_cache_entry(cached_appearance, char_id, name=name)
        if not is_appearance_cache_entry_compatible(cached_entry):
            cached_entry = {}
        description = _collapse_spaces(
            sanitize_character_profile_description(str(character.get("description", "")))
        )
        fallback_description = _character_asset_fallback_description(
            character_images,
            character_id=char_id,
            name=name,
            description=description,
        ) or description

        cached_body = _collapse_spaces(str(cached_entry.get("body", ""))) if isinstance(cached_entry, dict) else ""
        cached_clothing = _collapse_spaces(str(cached_entry.get("clothing", ""))) if isinstance(cached_entry, dict) else ""
        negative_prompt = _collapse_spaces(str(cached_entry.get("negative_prompt", ""))) if isinstance(cached_entry, dict) else ""

        body = sanitize_body_features(cached_body, fallback_description=fallback_description) if cached_body else ""
        clothing = sanitize_default_clothing(cached_clothing, fallback_description=fallback_description) if cached_clothing else ""
        if not body:
            body = sanitize_body_features(
                get_character_visual_dna(character_images, char_id, name=name),
                fallback_description=fallback_description,
            ) or _guess_body_features(fallback_description)
        if not clothing:
            clothing = _guess_default_clothing(fallback_description)

        character_locks[char_id] = CharacterLock(
            name=name,
            body_features=body,
            default_clothing=clothing,
            negative_prompt=negative_prompt,
        )

    scene_styles = _build_scene_styles(story)
    global_negative_prompt = _collapse_spaces(
        ", ".join(
            dict.fromkeys(
                style.negative_prompt
                for style in scene_styles
                if style.negative_prompt
            )
        )
    )
    clean_character_section = build_clean_character_section(character_locks, characters)
    ctx = StoryContext(
        base_art_style=_collapse_spaces(str(story.get("art_style", ""))),
        scene_styles=scene_styles,
        global_negative_prompt=global_negative_prompt,
        character_locks=character_locks,
        clean_character_section=clean_character_section,
    )
    stable_blocks = [
        str(story.get("selected_setting", "")),
        *[style.image_extra for style in scene_styles],
        *[style.video_extra for style in scene_styles],
    ]
    ctx.cache_fingerprint = get_cache_fingerprint(ctx, "", stable_blocks)
    return ctx


def _shot_field(shot: ShotLike, field: str, default: Any = "") -> Any:
    if isinstance(shot, Mapping):
        return shot.get(field, default)
    return getattr(shot, field, default)


def _get_visual_field(shot: ShotLike, field: str) -> str:
    if isinstance(shot, Mapping):
        visual_elements = shot.get("visual_elements") or {}
        if isinstance(visual_elements, Mapping):
            return _collapse_spaces(str(visual_elements.get(field, "")))
        return ""
    visual_elements = getattr(shot, "visual_elements", None)
    if not visual_elements:
        return ""
    return _collapse_spaces(str(getattr(visual_elements, field, "")))


def _get_camera_setup_field(shot: ShotLike, field: str) -> str:
    if isinstance(shot, Mapping):
        camera_setup = shot.get("camera_setup") or {}
        if isinstance(camera_setup, Mapping):
            return _collapse_spaces(str(camera_setup.get(field, "")))
        return ""
    camera_setup = getattr(shot, "camera_setup", None)
    if not camera_setup:
        return ""
    return _collapse_spaces(str(getattr(camera_setup, field, "")))


ShotLike = Any


def _shot_character_names(shot: ShotLike) -> list[str]:
    for field_name in ("characters", "character_names", "mentioned_characters", "cast", "participants"):
        raw = _shot_field(shot, field_name, None)
        if raw is None:
            continue
        if isinstance(raw, str):
            values = [raw]
        elif isinstance(raw, (list, tuple, set)):
            values = list(raw)
        else:
            continue

        names: list[str] = []
        for value in values:
            if isinstance(value, Mapping):
                candidate = value.get("name", "")
            else:
                candidate = value
            normalized = _collapse_spaces(str(candidate))
            if normalized:
                names.append(normalized)
        if names:
            return names
    return []


def _shot_text_haystack(shot: ShotLike, *, include_last_frame: bool = True) -> str:
    del include_last_frame
    parts = [
        str(_shot_field(shot, "storyboard_description", "")),
        str(_shot_field(shot, "image_prompt", "")),
        str(_shot_field(shot, "final_video_prompt", "")),
        _get_visual_field(shot, "subject_and_clothing"),
        _get_visual_field(shot, "action_and_expression"),
    ]
    return _collapse_spaces(" ".join(parts))


def _safe_name_match(name: str, haystack: str) -> bool:
    normalized_name = _collapse_spaces(name)
    normalized_haystack = _collapse_spaces(haystack)
    if not normalized_name or not normalized_haystack:
        return False

    if re.search(r"\b" + re.escape(normalized_name) + r"\b", normalized_haystack, flags=re.IGNORECASE):
        return True

    # Fallback for CJK names where \b does not split between adjacent ideographs.
    return bool(
        re.search(
            r"(?<![A-Za-z0-9_])" + re.escape(normalized_name) + r"(?![A-Za-z0-9_])",
            normalized_haystack,
            flags=re.IGNORECASE,
        )
    )


def character_appears_in_shot(name: str, shot: ShotLike) -> bool:
    normalized_name = _collapse_spaces(name)
    if not normalized_name:
        return False

    structured_names = _shot_character_names(shot)
    if structured_names:
        return any(candidate.casefold() == normalized_name.casefold() for candidate in structured_names)

    return _safe_name_match(normalized_name, _shot_text_haystack(shot))


def should_inject_clothing_for(name: str, shot: ShotLike) -> bool:
    if not character_appears_in_shot(name, shot):
        return False

    segments = [
        str(_shot_field(shot, "storyboard_description", "")),
        str(_shot_field(shot, "image_prompt", "")),
        str(_shot_field(shot, "final_video_prompt", "")),
        _get_visual_field(shot, "action_and_expression"),
    ]
    escaped_name = re.escape(_collapse_spaces(name))
    patterns = [
        re.compile(r"\b" + escaped_name + r"\b", flags=re.IGNORECASE),
        re.compile(escaped_name, flags=re.IGNORECASE),
    ]
    relevant_contexts: list[str] = []
    for segment in segments:
        normalized_segment = _collapse_spaces(str(segment))
        if not normalized_segment or not _safe_name_match(name, normalized_segment):
            continue
        lowered_segment = normalized_segment.lower()
        segment_contexts: list[str] = []
        for pattern in patterns:
            for match in pattern.finditer(normalized_segment):
                start = max(0, match.start() - 80)
                end = min(len(normalized_segment), match.end() + 80)
                segment_contexts.append(lowered_segment[start:end])
            if segment_contexts:
                break
        relevant_contexts.extend(segment_contexts or [lowered_segment])
    if not relevant_contexts:
        return True
    return not any(
        hint in context
        for hint in _WARDROBE_CHANGE_HINTS
        for context in relevant_contexts
    )


def infer_shot_view_hint(name: str, shot: ShotLike) -> str:
    if not character_appears_in_shot(name, shot):
        return ""

    normalized_name = _collapse_spaces(name)
    structured_names = _shot_character_names(shot)
    segments = [
        str(_shot_field(shot, "storyboard_description", "")),
        str(_shot_field(shot, "image_prompt", "")),
        str(_shot_field(shot, "final_video_prompt", "")),
        _get_visual_field(shot, "subject_and_clothing"),
        _get_visual_field(shot, "action_and_expression"),
    ]
    escaped_name = re.escape(normalized_name)
    patterns = [
        re.compile(r"\b" + escaped_name + r"\b", flags=re.IGNORECASE),
        re.compile(escaped_name, flags=re.IGNORECASE),
    ]
    contexts: list[str] = []
    for segment in segments:
        normalized_segment = _collapse_spaces(str(segment))
        if not normalized_segment:
            continue
        lowered_segment = normalized_segment.lower()
        if _safe_name_match(name, normalized_segment):
            local_contexts: list[str] = []
            for pattern in patterns:
                for match in pattern.finditer(normalized_segment):
                    start = max(0, match.start() - 80)
                    end = min(len(normalized_segment), match.end() + 80)
                    local_contexts.append(lowered_segment[start:end])
                if local_contexts:
                    break
            contexts.extend(local_contexts or [lowered_segment])

    is_structured_single_character_shot = (
        len(structured_names) == 1
        and structured_names[0].casefold() == normalized_name.casefold()
    )
    if is_structured_single_character_shot:
        fallback_parts = [
            _get_visual_field(shot, "action_and_expression"),
            _get_visual_field(shot, "subject_and_clothing"),
        ]
        if not any(_collapse_spaces(part) for part in fallback_parts):
            fallback_parts.extend(
                [
                    str(_shot_field(shot, "storyboard_description", "")),
                    str(_shot_field(shot, "image_prompt", "")),
                ]
            )
        fallback_context = _collapse_spaces(" ".join(str(part) for part in fallback_parts))
        if fallback_context:
            contexts.append(fallback_context.lower())

    scores = {"front": 0, "side": 0, "back": 0}
    for context in contexts:
        for label, hints in _VIEW_HINT_PATTERNS.items():
            if any(hint in context for hint in hints):
                scores[label] += 1

    if not any(scores.values()):
        return ""

    for label in ("back", "side", "front"):
        if scores[label] == max(scores.values()) and scores[label] > 0:
            return {
                "front": "match the shot's front view",
                "side": "match the shot's side profile",
                "back": "match the shot's back view",
            }[label]
    return ""


def _join_natural_phrases(items: list[str], lang: str) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        connector = "，同时" if lang == "zh" else ", alongside "
        return f"{items[0]}{connector}{items[1]}"
    if lang == "zh":
        return "，".join(items[:-1]) + f"，以及{items[-1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _normalize_anchor_clothing(clothing: str, *, lang: str) -> str:
    normalized = _collapse_spaces(clothing)
    if not normalized:
        return ""
    if lang == "zh":
        normalized = re.sub(r"^(?:穿着|身穿|穿|戴着)\s*", "", normalized)
        return _collapse_spaces(normalized)
    normalized = re.sub(r"^(?:wearing|dressed in|dressed with|in)\s+", "", normalized, flags=re.IGNORECASE)
    return _collapse_spaces(normalized)


def _strip_redundant_clothing_from_body(body: str, clothing: str, *, lang: str) -> str:
    normalized_body = _collapse_spaces(body)
    normalized_clothing = _normalize_anchor_clothing(clothing, lang=lang)
    if not normalized_body or not normalized_clothing:
        return normalized_body

    if lang == "zh":
        patterns = (
            rf"(?:，|,)?\s*穿着{re.escape(normalized_clothing)}",
            rf"(?:，|,)?\s*身穿{re.escape(normalized_clothing)}",
            rf"(?:，|,)?\s*戴着{re.escape(normalized_clothing)}",
        )
    else:
        patterns = (
            rf"(?:,\s*)?wearing {re.escape(normalized_clothing)}",
            rf"(?:,\s*)?dressed in {re.escape(normalized_clothing)}",
            rf"(?:,\s*)?dressed with {re.escape(normalized_clothing)}",
            rf"(?:,\s*)?in {re.escape(normalized_clothing)}",
        )

    cleaned = normalized_body
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    return _collapse_spaces(cleaned).strip(" ,.;:!?，。；：！？、")


def _format_character_anchor(name: str, lock: CharacterLock, *, lang: str, include_clothing: bool) -> str:
    body = sanitize_body_features(lock.body_features)
    clothing = sanitize_default_clothing(lock.default_clothing)
    clothing = _normalize_anchor_clothing(clothing, lang=lang)
    body = _strip_redundant_clothing_from_body(body, clothing, lang=lang)
    if lang == "zh":
        if body and include_clothing and clothing:
            return f"{name}保持{body}，穿着{clothing}"
        if body:
            return f"{name}保持{body}"
        if include_clothing and clothing:
            return f"{name}穿着{clothing}"
        return ""
    if body and include_clothing and clothing:
        return f"{name} with {body}, wearing {clothing}"
    if body:
        return f"{name} with {body}"
    if include_clothing and clothing:
        return f"{name} wearing {clothing}"
    return ""


def _appearance_prefix(shot: ShotLike, ctx: StoryContext, include_clothing: bool = True) -> str:
    appearance_lines: list[str] = []
    for _, lock in ctx.character_locks.items():
        name = lock.name
        if not name:
            continue
        if not character_appears_in_shot(name, shot):
            continue
        merged = _format_character_anchor(
            name,
            lock,
            lang="zh" if _contains_cjk(" ".join([str(_shot_field(shot, "image_prompt", "")), str(_shot_field(shot, "final_video_prompt", ""))])) else "en",
            include_clothing=include_clothing and should_inject_clothing_for(name, shot),
        )
        if merged:
            appearance_lines.append(merged)

    if not appearance_lines:
        return ""

    base_prompt = " ".join(
        [
            str(_shot_field(shot, "image_prompt", "")),
            str(_shot_field(shot, "final_video_prompt", "")),
        ]
    )
    lang = "zh" if _contains_cjk(base_prompt) else "en"
    prefix = "保持角色外观一致：" if lang == "zh" else "Maintain consistent appearance: "
    suffix = "。" if lang == "zh" else "."
    continuity_clause = (
        "除非镜头明确写了换装，否则保持主衣物轮廓、外层服装、服饰颜色、材质、帽子、发型和标志性配件一致。"
        if lang == "zh"
        else "Keep the primary outfit silhouette, outer layer, colors, materials, headwear, hairstyle, and signature accessories unchanged unless the shot explicitly shows a wardrobe change."
    )
    return f"{prefix}{_join_natural_phrases(appearance_lines, lang)}{suffix} {continuity_clause}"


def _scene_style_extra(ctx: StoryContext, shot: ShotLike, mode: str) -> str:
    if not ctx.scene_styles:
        return ""
    text = " ".join(
        [
            str(_shot_field(shot, "storyboard_description", "")),
            str(_shot_field(shot, "image_prompt", "")),
            str(_shot_field(shot, "final_video_prompt", "")),
            _get_visual_field(shot, "environment_and_props"),
        ]
    ).lower()
    matched = []
    for style in ctx.scene_styles:
        style_extra = style.image_extra if mode != "video" else (style.video_extra or style.image_extra)
        if not style_extra:
            continue
        if style.always_apply or not style.keywords or any(keyword.lower() in text for keyword in style.keywords):
            matched.append(style_extra)
    if not matched and len(ctx.scene_styles) == 1:
        fallback_style = ctx.scene_styles[0]
        style_extra = fallback_style.image_extra if mode != "video" else (fallback_style.video_extra or fallback_style.image_extra)
        if style_extra:
            matched.append(style_extra)
    return _collapse_spaces("; ".join(matched))


def _merge_prompt(base_prompt: str, appearance_prefix: str, scene_extra: str, art_style: str) -> str:
    parts = [part for part in (_collapse_spaces(base_prompt), appearance_prefix, scene_extra) if part]
    merged = " ".join(parts)
    return inject_art_style(merged, art_style)


def _split_negative_terms(negative: str) -> list[str]:
    return [
        _collapse_spaces(term)
        for term in re.split(r"[,，]", negative)
        if _collapse_spaces(term)
    ]


_CHARACTER_CONSISTENCY_NEGATIVE_TERMS = (
    "wrong face",
    "changed hairstyle",
    "different primary outfit",
    "changed costume colors",
    "changed costume material",
    "missing signature accessories",
    "warped anatomy",
    "extra limbs",
    "duplicate person",
)


def _character_consistency_negative_prompt(shot: ShotLike, ctx: StoryContext | None) -> str:
    if not ctx:
        return ""
    if not any(
        lock.name and character_appears_in_shot(lock.name, shot)
        for lock in ctx.character_locks.values()
    ):
        return ""
    return ", ".join(_CHARACTER_CONSISTENCY_NEGATIVE_TERMS)


def build_negative_prompt(shot: ShotLike, ctx: StoryContext | None) -> str:
    shot_negative_prompt = _collapse_spaces(str(_shot_field(shot, "negative_prompt", "")))
    if not ctx:
        return shot_negative_prompt

    negatives: list[str] = []
    if shot_negative_prompt:
        negatives.append(shot_negative_prompt)
    if ctx.global_negative_prompt:
        negatives.append(ctx.global_negative_prompt)
    for _, lock in ctx.character_locks.items():
        name = lock.name
        if not name:
            continue
        if character_appears_in_shot(name, shot) and lock.negative_prompt:
            negatives.append(lock.negative_prompt)
    character_consistency_negative = _character_consistency_negative_prompt(shot, ctx)
    if character_consistency_negative:
        negatives.append(character_consistency_negative)
    normalized_terms: list[str] = []
    for negative in negatives:
        normalized_terms.extend(_split_negative_terms(negative))
    return _collapse_spaces(", ".join(dict.fromkeys(normalized_terms)))


def _shot_source_scene_key(shot: ShotLike) -> str:
    explicit = _collapse_spaces(str(_shot_field(shot, "source_scene_key", "")))
    if explicit:
        return explicit
    scene_index = extract_scene_index_from_shot_id(str(_shot_field(shot, "shot_id", "")))
    if scene_index is None:
        return ""
    return f"scene{scene_index}"


def _scene_reference_prompt_extra(asset: Mapping[str, Any] | None, shot: ShotLike) -> str:
    if not isinstance(asset, Mapping):
        return ""

    scene_variant = {}
    variants = asset.get("variants")
    if isinstance(variants, Mapping):
        raw_scene_variant = variants.get("scene")
        if isinstance(raw_scene_variant, Mapping):
            scene_variant = dict(raw_scene_variant)

    prompt = _collapse_spaces(str(scene_variant.get("prompt", "")))
    shared_environment = ""
    local_visual_anchors = ""
    lighting_anchor = ""
    if prompt:
        shared_match = re.search(r"Shared environment:\s*([^.]*)\.", prompt, flags=re.IGNORECASE)
        local_match = re.search(r"(?:Local visual anchors|Stable prop anchors):\s*([^.]*)\.", prompt, flags=re.IGNORECASE)
        light_match = re.search(r"Lighting anchor:\s*([^.]*)\.", prompt, flags=re.IGNORECASE)
        shared_environment = _collapse_spaces(shared_match.group(1) if shared_match else "")
        local_visual_anchors = _collapse_spaces(local_match.group(1) if local_match else "")
        lighting_anchor = _collapse_spaces(light_match.group(1) if light_match else "")

    if not shared_environment:
        shared_environment = _collapse_spaces(str(asset.get("summary_environment", "")))
    if not local_visual_anchors:
        visuals = asset.get("summary_visuals") or []
        if isinstance(visuals, list):
            local_visual_anchors = _collapse_spaces("; ".join(str(item) for item in visuals if _collapse_spaces(str(item))))
    if not lighting_anchor:
        lighting_anchor = _collapse_spaces(str(asset.get("summary_lighting", "")))

    if not any((shared_environment, local_visual_anchors, lighting_anchor)):
        return ""

    preferred_prompt_text = " ".join(
        [
            str(_shot_field(shot, "image_prompt", "")),
            str(_shot_field(shot, "final_video_prompt", "")),
        ]
    )
    fallback_text = str(_shot_field(shot, "storyboard_description", ""))
    lang = "zh" if _contains_cjk(preferred_prompt_text or fallback_text) else "en"
    parts: list[str] = [
        "把关联场景参考图当作当前镜头的环境基准，不要改成别的地点或另一套布景"
        if lang == "zh"
        else "Treat the linked scene reference image as environment canon"
    ]
    if shared_environment:
        parts.append(f"保持命中的环境布局：{shared_environment}" if lang == "zh" else f"Match the linked environment layout: {shared_environment}")
    if local_visual_anchors:
        parts.append(f"保留场景锚点：{local_visual_anchors}" if lang == "zh" else f"Keep scene anchors unchanged: {local_visual_anchors}")
    if lighting_anchor:
        parts.append(f"沿用环境光线：{lighting_anchor}" if lang == "zh" else f"Keep the scene lighting direction and color logic: {lighting_anchor}")
    separator = "；" if lang == "zh" else ". "
    return _sentence(separator.join(parts), lang)


def _character_reference_prompt_extra(story: Mapping[str, Any] | None, shot: ShotLike) -> str:
    references = _matched_character_reference_images(story, shot)
    if not references:
        return ""

    preferred_prompt_text = " ".join(
        [
            str(_shot_field(shot, "image_prompt", "")),
            str(_shot_field(shot, "final_video_prompt", "")),
        ]
    )
    fallback_text = str(_shot_field(shot, "storyboard_description", ""))
    lang = "zh" if _contains_cjk(preferred_prompt_text or fallback_text) else "en"

    if lang == "zh":
        return _sentence(
            "把关联人设参考图当作人物身份基准，保持脸部特征、发型、主衣物轮廓、颜色、材质、帽饰与标志配件一致，不要换脸或换装。",
            lang,
        )

    return _sentence(
        "Treat the linked character reference image as identity canon. Keep facial features, hairstyle, primary outfit silhouette, colors, materials, headwear, and signature accessories unchanged.",
        lang,
    )


def _character_reference_negative_prompt(story: Mapping[str, Any] | None, shot: ShotLike) -> str:
    if not _matched_character_reference_images(story, shot):
        return ""
    return ", ".join(
        [
            "wrong face",
            "changed hairstyle",
            "different primary outfit",
            "changed costume colors",
            "changed costume material",
            "missing signature accessories",
        ]
    )


def _merge_negative_prompt_parts(*values: str) -> str:
    normalized_terms: list[str] = []
    for value in values:
        normalized_terms.extend(_split_negative_terms(_collapse_spaces(value)))
    return _collapse_spaces(", ".join(dict.fromkeys(normalized_terms)))


def _scene_reference_negative_prompt(asset: Mapping[str, Any] | None) -> str:
    if not isinstance(asset, Mapping):
        return ""

    variants = asset.get("variants")
    scene_variant = variants.get("scene") if isinstance(variants, Mapping) else {}
    has_scene_variant = isinstance(scene_variant, Mapping) and any(
        _collapse_spaces(str(scene_variant.get(key, "")))
        for key in ("image_url", "image_path", "prompt")
    )
    has_scene_anchor = has_scene_variant or any(
        _collapse_spaces(str(asset.get(key, "")))
        for key in ("summary_environment", "summary_lighting")
    )
    if not has_scene_anchor:
        return ""

    return ", ".join(
        [
            "wrong location layout",
            "changed architecture",
            "generic environment swap",
            "altered prop placement",
            "missing signature props",
            "inconsistent lighting direction",
        ]
    )


def _matched_character_reference_images(story: Mapping[str, Any] | None, shot: ShotLike) -> list[dict[str, Any]]:
    if not isinstance(story, Mapping):
        return []
    characters = story.get("characters")
    character_images = story.get("character_images")
    if not isinstance(characters, list) or not isinstance(character_images, Mapping):
        return []

    references: list[dict[str, Any]] = []
    weights = (0.64, 0.56)
    for character in characters:
        if not isinstance(character, Mapping):
            continue
        name = _collapse_spaces(str(character.get("name", "")))
        if not name or not character_appears_in_shot(name, shot):
            continue
        entry = get_character_asset_entry(character_images, str(character.get("id", "")), name=name)
        image_url = _collapse_spaces(str(entry.get("image_url", "")))
        image_path = _collapse_spaces(str(entry.get("image_path", "")))
        if image_url or image_path:
            references.append(
                {
                    "kind": "character",
                    "image_url": image_url,
                    "image_path": image_path,
                    "weight": weights[min(len(references), len(weights) - 1)],
                }
            )
        if len(references) >= 2:
            break
    return references


def _build_reference_images(
    shot: ShotLike,
    story: Mapping[str, Any] | None,
    scene_asset: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    references.extend(_matched_character_reference_images(story, shot))

    if isinstance(scene_asset, Mapping):
        variants = scene_asset.get("variants")
        scene_variant = variants.get("scene") if isinstance(variants, Mapping) else {}
        if isinstance(scene_variant, Mapping):
            image_url = _collapse_spaces(str(scene_variant.get("image_url", "")))
            image_path = _collapse_spaces(str(scene_variant.get("image_path", "")))
            if image_url or image_path:
                scene_weight = 0.72 if not references else (0.5 if len(references) == 1 else 0.42)
                references.append(
                    {
                        "kind": "scene",
                        "image_url": image_url,
                        "image_path": image_path,
                        "weight": scene_weight,
                    }
                )

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in references:
        key = (_collapse_spaces(str(item.get("image_url", ""))), _collapse_spaces(str(item.get("image_path", ""))))
        if key in seen:
            continue
        deduped.append(item)
        seen.add(key)
    return deduped[:3]


def _merge_reference_images(*sources: Any) -> list[Any]:
    merged: list[Any] = []
    seen: set[tuple[str, str]] = set()

    for source in sources:
        if not isinstance(source, list):
            continue
        for item in source:
            if isinstance(item, Mapping):
                identity_value = (
                    _collapse_spaces(str(item.get("id", "")))
                    or _collapse_spaces(str(item.get("image_url", "")))
                    or _collapse_spaces(str(item.get("image_path", "")))
                )
                if not identity_value:
                    continue
                identity = ("mapping", identity_value)
                normalized_item = dict(item)
            else:
                value = _collapse_spaces(str(item))
                if not value:
                    continue
                identity = ("raw", value)
                normalized_item = item
            if identity in seen:
                continue
            seen.add(identity)
            merged.append(normalized_item)

    return merged


def _infer_prompt_language(shot: ShotLike, *, mode: str) -> str:
    preferred_fields = (
        ("image_prompt", "final_video_prompt", "storyboard_description")
        if mode == "image"
        else ("final_video_prompt", "image_prompt", "storyboard_description")
    )
    for field_name in preferred_fields:
        candidate = _collapse_spaces(str(_shot_field(shot, field_name, "")))
        if candidate:
            return "zh" if _contains_cjk(candidate) else "en"
    return "en"


def _shot_size_label(shot: ShotLike, *, lang: str) -> str:
    shot_size = _collapse_spaces(_get_camera_setup_field(shot, "shot_size")).upper()
    labels = _SHOT_SIZE_LABELS.get(shot_size)
    if not labels:
        return ""
    return labels[0] if lang == "zh" else labels[1]


def _normalize_prompt_framing(base_prompt: str, shot: ShotLike, *, lang: str) -> str:
    normalized = _collapse_spaces(base_prompt)
    if not normalized:
        return ""

    shot_size_label = _shot_size_label(shot, lang=lang)
    if not shot_size_label:
        return normalized

    patterns = _LEADING_FRAMING_PATTERNS_ZH if lang == "zh" else _LEADING_FRAMING_PATTERNS_EN
    trimmed = normalized
    for pattern in patterns:
        trimmed = re.sub(pattern, "", trimmed, count=1, flags=re.IGNORECASE)
    trimmed = _collapse_spaces(trimmed)

    if lang == "zh":
        return f"{shot_size_label}，{trimmed}" if trimmed else shot_size_label
    return f"{shot_size_label}. {trimmed}" if trimmed else shot_size_label


def _split_prompt_sentences(text: str) -> list[str]:
    normalized = _collapse_spaces(text)
    if not normalized:
        return []
    return [
        fragment.strip(" ,.;:!?，。；：！？、")
        for fragment in re.split(r"[。！？!?；;]+|(?<=\w)\.(?=\s|$)|\n+", normalized)
        if fragment and fragment.strip(" ,.;:!?，。；：！？、")
    ]


def _trim_prompt_guidance(text: str, *, lang: str, word_limit: int = 22, char_limit: int = 48) -> str:
    normalized = _collapse_spaces(text)
    if not normalized:
        return ""
    if lang == "zh":
        return _trim_chars(normalized, char_limit)
    return _trim_words(normalized, word_limit)


def _extract_opening_frame_anchor(shot: ShotLike, *, lang: str) -> str:
    description = _collapse_spaces(str(_shot_field(shot, "storyboard_description", "")))
    sentences = _split_prompt_sentences(description)
    if not sentences:
        return ""

    selected: list[str] = []
    minimum_units = 16 if lang == "zh" else 8
    joiner = "，" if lang == "zh" else ". "
    for sentence in sentences[:2]:
        selected.append(sentence)
        combined = joiner.join(selected)
        units = len(combined) if lang == "zh" else len(combined.split())
        if units >= minimum_units:
            break

    return _trim_prompt_guidance(joiner.join(selected), lang=lang)


def _extract_transition_state_anchor(shot: ShotLike, *, lang: str) -> str:
    transition = _collapse_spaces(str(_shot_field(shot, "transition_from_previous", "")))
    if not transition:
        return ""

    camera_terms = (
        "camera",
        "shot",
        "framing",
        "angle",
        "movement",
        "dolly",
        "pan",
        "tilt",
        "tracking",
        "crane",
        "static",
        "摄像机",
        "镜头",
        "机位",
        "运镜",
        "景别",
        "推近",
        "拉近",
        "拉远",
        "左摇",
        "右摇",
        "上摇",
        "下摇",
        "跟拍",
        "手持",
        "升降",
        "建立镜头",
        "远景",
        "中景",
        "近景",
        "特写",
    )
    filtered: list[str] = []
    for sentence in _split_prompt_sentences(transition):
        fragments = [
            _collapse_spaces(fragment)
            for fragment in re.split(r"[，,]+", sentence)
            if _collapse_spaces(fragment)
        ]
        kept_fragments = [
            fragment
            for fragment in fragments
            if not any(term in fragment.lower() for term in camera_terms)
        ]
        cleaned_sentence = _collapse_spaces("，".join(kept_fragments) if lang == "zh" else ", ".join(kept_fragments))
        if not cleaned_sentence:
            continue
        filtered.append(cleaned_sentence)
        if len(filtered) >= 2:
            break

    if not filtered:
        return ""

    joiner = "，" if lang == "zh" else ". "
    return _trim_prompt_guidance(joiner.join(filtered), lang=lang)


def _scene_shot_number(shot: ShotLike) -> int | None:
    shot_id = _collapse_spaces(str(_shot_field(shot, "shot_id", "")))
    match = re.match(r"scene\d+_shot(\d+)$", shot_id, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _is_scene_continuation_shot(shot: ShotLike) -> bool:
    shot_number = _scene_shot_number(shot)
    if shot_number and shot_number > 1:
        return True

    scene_position = _collapse_spaces(str(_shot_field(shot, "scene_position", ""))).lower()
    if scene_position in {"development", "climax", "resolution"}:
        return True

    return bool(_collapse_spaces(str(_shot_field(shot, "transition_from_previous", ""))))


def _requires_hand_visibility(shot: ShotLike) -> bool:
    text = " ".join(
        [
            str(_shot_field(shot, "storyboard_description", "")),
            str(_shot_field(shot, "final_video_prompt", "")),
            _get_visual_field(shot, "action_and_expression"),
        ]
    ).lower()
    return any(hint in text for hint in _HAND_ACTION_HINTS)


def _requires_extended_body_context(shot: ShotLike) -> bool:
    shot_size = _collapse_spaces(_get_camera_setup_field(shot, "shot_size")).upper()
    if shot_size in {"MS", "MWS", "WS", "EWS", "OTS"}:
        return True

    text = " ".join(
        [
            str(_shot_field(shot, "storyboard_description", "")),
            str(_shot_field(shot, "final_video_prompt", "")),
            _get_visual_field(shot, "action_and_expression"),
        ]
    ).lower()
    return any(hint in text for hint in _BODY_MOTION_HINTS)


def _opening_frame_motion_compatibility_extra(shot: ShotLike, *, mode: str, lang: str) -> str:
    shot_size_label = _shot_size_label(shot, lang=lang)
    needs_hands = _requires_hand_visibility(shot)
    needs_body_context = _requires_extended_body_context(shot)

    parts: list[str] = []
    if lang == "zh":
        if mode == "image":
            parts.append("这张图是后续视频的首帧锚点，构图必须能支撑接下来的动作")
            if shot_size_label:
                parts.append(f"保持{shot_size_label}可读构图，不要缩成只剩脸部的肖像式特写")
            if needs_hands:
                parts.append("起始画面里就要看见后续动作需要用到的手、手臂以及交互道具，不要等视频开始后再突然冒出来")
            if needs_body_context:
                parts.append("保留足够的上半身或身体运动空间，让位移和动作路径能自然展开")
        else:
            parts.append("后续动作必须从首帧已建立的构图自然长出来")
            parts.append("不要在运动中突然补出首帧没有建立的手、道具或更大范围身体裁切")
        return _sentence("；".join(parts), lang) if parts else ""

    if mode == "image":
        parts.append("This still becomes the video opening frame, so the composition must support the upcoming motion")
        if shot_size_label:
            parts.append(f"Keep readable {shot_size_label.lower()} framing instead of collapsing into a face-only portrait crop")
        if needs_hands:
            parts.append("Keep the acting hands, arms, and interacted prop already visible in the opening frame")
        if needs_body_context:
            parts.append("Keep enough torso or body context for the planned motion path to unfold naturally")
    else:
        parts.append("Let the motion grow naturally from the opening-frame composition")
        parts.append("Do not suddenly reveal missing hands, props, or a much wider body crop that was not established at the start")
    return _sentence(". ".join(parts), lang) if parts else ""


def _scene_continuity_extra(shot: ShotLike, *, mode: str, lang: str) -> str:
    if not _is_scene_continuation_shot(shot):
        return ""

    if lang == "zh":
        if mode == "image":
            return _sentence(
                "把这个镜头当作同一场景里的连续时刻，不要重新摆成独立人像、重置姿态，或拍成与前后镜头脱节的新建立镜头",
                lang,
            )
        return _sentence(
            "把这个镜头当作同一场景时间线里的连续段落，不要演成与前后镜头脱节的重置开场",
            lang,
        )

    if mode == "image":
        return _sentence(
            "Treat this shot as a continuing beat inside the same scene, not a fresh standalone portrait, reset pose, or unrelated re-establishing frame",
            lang,
        )
    return _sentence(
        "Treat this shot as a continuous beat in the same scene timeline, not a disconnected reset or fresh re-establishing start",
        lang,
    )


def _storyboard_alignment_extra(shot: ShotLike, *, mode: str) -> str:
    lang = _infer_prompt_language(shot, mode=mode)
    opening_anchor = _extract_opening_frame_anchor(shot, lang=lang)
    transition_anchor = _extract_transition_state_anchor(shot, lang=lang)
    parts: list[str] = []

    if opening_anchor:
        if lang == "zh":
            prefix = "首帧必须贴合当前镜头画面：" if mode == "image" else "视频必须从这一定格状态开始："
        else:
            prefix = "Match this exact opening frame: " if mode == "image" else "Start from this exact opening frame: "
        parts.append(prefix + opening_anchor)

    if transition_anchor:
        if lang == "zh":
            prefix = "延续上一镜头已带入的姿态、道具状态和空间关系：" if mode == "image" else "运动开始前先保持上一镜头延续下来的姿态、道具状态和空间关系："
        else:
            prefix = "Keep the carried-over pose, prop state, and spatial continuity: " if mode == "image" else "Preserve the carried-over state before motion: "
        parts.append(prefix + transition_anchor)

    continuity_extra = _scene_continuity_extra(shot, mode=mode, lang=lang)
    if continuity_extra:
        parts.append(continuity_extra.rstrip("。.") )

    motion_extra = _opening_frame_motion_compatibility_extra(shot, mode=mode, lang=lang)
    if motion_extra:
        parts.append(motion_extra.rstrip("。.") )

    if not parts:
        return ""

    separator = "；" if lang == "zh" else ". "
    return _sentence(separator.join(parts), lang)


def build_image_generation_prompt(
    shot: ShotLike,
    ctx: StoryContext | None,
    art_style: str = "",
    scene_reference_extra: str = "",
) -> str:
    lang = _infer_prompt_language(shot, mode="image")
    base_prompt = _normalize_prompt_framing(
        str(_shot_field(shot, "image_prompt", "") or _shot_field(shot, "final_video_prompt", "")),
        shot,
        lang=lang,
    )
    alignment_extra = _storyboard_alignment_extra(shot, mode="image")
    if not ctx:
        merged = " ".join(
            part for part in (base_prompt, alignment_extra, scene_reference_extra) if _collapse_spaces(part)
        )
        return inject_art_style(merged, art_style)
    scene_bits = [
        part
        for part in (alignment_extra, scene_reference_extra, _scene_style_extra(ctx, shot, "image"))
        if _collapse_spaces(part)
    ]
    return _merge_prompt(
        base_prompt,
        _appearance_prefix(shot, ctx, include_clothing=True),
        " ".join(scene_bits),
        art_style or ctx.base_art_style,
    )


def _video_execution_extra(shot: ShotLike, ctx: StoryContext | None) -> str:
    lang = _infer_prompt_language(shot, mode="video")
    movement = _get_camera_setup_field(shot, "movement").lower()
    is_static = movement in {"", "static", "固定镜头", "固定", "静止"}
    has_character = bool(
        ctx
        and any(
            lock.name and character_appears_in_shot(lock.name, shot)
            for lock in ctx.character_locks.values()
        )
    )

    if lang == "zh":
        parts = []
        if has_character:
            parts.append("人物在整段视频里保持同一张脸、同一发型、同一主衣物轮廓、颜色和标志配饰")
        parts.append("动作幅度必须清晰可见，主体位移、四肢路径、布料跟随和解剖结构保持自然稳定")
        if is_static:
            parts.append("即使固定镜头也要让动作清楚完成，不要缩成几乎看不出的轻微抖动")
        else:
            parts.append("运镜幅度必须明显可见且平滑，不能缩成几乎静止的小幅试探")
        return _sentence("；".join(parts), lang)

    parts = []
    if has_character:
        parts.append("Keep the same face, hairstyle, primary outfit silhouette, colors, and signature accessories throughout the clip")
    parts.append("Make the action clearly readable on screen with visible body travel, natural cloth follow-through, and stable limb and hand anatomy")
    if is_static:
        parts.append("Even on a static camera, the action must complete clearly instead of shrinking into tiny barely visible motion")
    else:
        parts.append("Make the camera move clearly readable and smooth instead of tiny or hesitant")
    return _sentence(". ".join(parts), lang)


def build_video_generation_prompt(
    shot: ShotLike,
    ctx: StoryContext | None,
    art_style: str = "",
    scene_reference_extra: str = "",
) -> str:
    lang = _infer_prompt_language(shot, mode="video")
    base_prompt = _normalize_prompt_framing(
        str(_shot_field(shot, "final_video_prompt", "") or _shot_field(shot, "image_prompt", "")),
        shot,
        lang=lang,
    )
    execution_extra = _video_execution_extra(shot, ctx)
    alignment_extra = _storyboard_alignment_extra(shot, mode="video")
    if not ctx:
        merged = " ".join(
            part for part in (base_prompt, execution_extra, alignment_extra, scene_reference_extra) if _collapse_spaces(part)
        )
        return inject_art_style(merged, art_style)
    scene_bits = [
        part
        for part in (execution_extra, alignment_extra, scene_reference_extra, _scene_style_extra(ctx, shot, "video"))
        if _collapse_spaces(part)
    ]
    return _merge_prompt(
        base_prompt,
        _appearance_prefix(shot, ctx, include_clothing=True),
        " ".join(scene_bits),
        art_style or ctx.base_art_style,
    )


def build_last_frame_generation_prompt(shot: ShotLike, ctx: StoryContext | None, art_style: str = "") -> str:
    base_prompt = str(_shot_field(shot, "last_frame_prompt", ""))
    if not base_prompt:
        return ""
    if not ctx:
        return inject_art_style(base_prompt, art_style)
    return _merge_prompt(
        base_prompt,
        _appearance_prefix(shot, ctx, include_clothing=True),
        _scene_style_extra(ctx, shot, "image"),
        art_style or ctx.base_art_style,
    )


def build_generation_payload(
    shot: ShotLike,
    ctx: StoryContext | None,
    art_style: str = "",
    story: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source_scene_key = _shot_source_scene_key(shot)
    scene_asset = get_scene_reference_asset(story, source_scene_key, shot_id=str(_shot_field(shot, "shot_id", "")))
    scene_reference_extra = _scene_reference_prompt_extra(scene_asset, shot)
    character_reference_extra = _character_reference_prompt_extra(story, shot)
    reference_prompt_extra = " ".join(
        part for part in (character_reference_extra, scene_reference_extra) if _collapse_spaces(part)
    )
    payload: dict[str, Any] = {
        "shot_id": str(_shot_field(shot, "shot_id", "")),
        "image_prompt": build_image_generation_prompt(
            shot,
            ctx,
            art_style=art_style,
            scene_reference_extra=reference_prompt_extra,
        ),
        "final_video_prompt": build_video_generation_prompt(
            shot,
            ctx,
            art_style=art_style,
            scene_reference_extra=reference_prompt_extra,
        ),
    }
    if source_scene_key:
        payload["source_scene_key"] = source_scene_key

    negative_prompt = _merge_negative_prompt_parts(
        build_negative_prompt(shot, ctx),
        _character_reference_negative_prompt(story, shot),
        _scene_reference_negative_prompt(scene_asset),
    )
    if negative_prompt:
        payload["negative_prompt"] = negative_prompt

    reference_images = _merge_reference_images(
        _shot_field(shot, "reference_images", None),
        payload.get("reference_images"),
        _build_reference_images(shot, story, scene_asset),
    )
    if reference_images:
        payload["reference_images"] = reference_images

    return payload
