from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from app.core.api_keys import inject_art_style
from app.core.story_assets import (
    extract_scene_index_from_shot_id,
    get_character_asset_entry,
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

    normalized_description = _collapse_spaces(description)
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
            if not isinstance(entry, Mapping):
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
        desc = character.get("description", "")
        if not char_id or not name:
            continue

        lock = character_locks.get(char_id, CharacterLock(name=name))
        lines.append(f"- **{name}**（{role}）：{desc}")

        visual_bits = [bit for bit in (lock.body_features, lock.default_clothing) if bit]
        if visual_bits:
            lines.append(f"  Visual DNA: {'; '.join(visual_bits)}")
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

        cached_entry = cached_appearance.get(char_id) or {}
        description = _collapse_spaces(str(character.get("description", "")))
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


def _format_character_anchor(name: str, lock: CharacterLock, *, lang: str, include_clothing: bool) -> str:
    body = sanitize_body_features(lock.body_features)
    clothing = sanitize_default_clothing(lock.default_clothing)
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
        "除非镜头明确写了换装，否则保持服饰颜色、材质、帽子、发型和标志性配件一致。"
        if lang == "zh"
        else "Keep outfit colors, materials, headwear, hairstyle, and signature accessories unchanged unless the shot explicitly shows a wardrobe change."
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


def build_image_generation_prompt(
    shot: ShotLike,
    ctx: StoryContext | None,
    art_style: str = "",
    scene_reference_extra: str = "",
) -> str:
    base_prompt = str(_shot_field(shot, "image_prompt", "") or _shot_field(shot, "final_video_prompt", ""))
    if not ctx:
        merged = " ".join(part for part in (base_prompt, scene_reference_extra) if _collapse_spaces(part))
        return inject_art_style(merged, art_style)
    scene_bits = [
        part
        for part in (scene_reference_extra, _scene_style_extra(ctx, shot, "image"))
        if _collapse_spaces(part)
    ]
    return _merge_prompt(
        base_prompt,
        _appearance_prefix(shot, ctx, include_clothing=True),
        " ".join(scene_bits),
        art_style or ctx.base_art_style,
    )


def build_video_generation_prompt(
    shot: ShotLike,
    ctx: StoryContext | None,
    art_style: str = "",
    scene_reference_extra: str = "",
) -> str:
    base_prompt = str(_shot_field(shot, "final_video_prompt", "") or _shot_field(shot, "image_prompt", ""))
    if not ctx:
        merged = " ".join(part for part in (base_prompt, scene_reference_extra) if _collapse_spaces(part))
        return inject_art_style(merged, art_style)
    scene_bits = [
        part
        for part in (scene_reference_extra, _scene_style_extra(ctx, shot, "video"))
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
    payload: dict[str, Any] = {
        "shot_id": str(_shot_field(shot, "shot_id", "")),
        "image_prompt": build_image_generation_prompt(
            shot,
            ctx,
            art_style=art_style,
            scene_reference_extra=scene_reference_extra,
        ),
        "final_video_prompt": build_video_generation_prompt(
            shot,
            ctx,
            art_style=art_style,
            scene_reference_extra=scene_reference_extra,
        ),
    }
    if source_scene_key:
        payload["source_scene_key"] = source_scene_key

    negative_prompt = _merge_negative_prompt_parts(
        build_negative_prompt(shot, ctx),
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
