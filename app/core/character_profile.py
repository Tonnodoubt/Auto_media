from __future__ import annotations

import re

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_FRAGMENT_SPLIT_RE = re.compile(r"[。！？；;，,\n]+")
_PRECISION_NOISE_RE = re.compile(
    r"(?:±\s*)?\d+(?:\.\d+)?\s*(?:mm|cm|毫米|厘米|公分|percent|%)",
    re.IGNORECASE,
)
_RITUAL_NOISE_RE = re.compile(
    r"(?:每次|每回|每逢|总会|总是|必以|必会|always|every time|ritually|without fail)",
    re.IGNORECASE,
)
_LOCATION_NOISE_RE = re.compile(
    r"(?:第[一二三四五六七八九十百\d]+(?:级|层|块|步|格|阶|道)"
    r"|同一块|固定(?:在)?同一|东侧|西侧|南侧|北侧|左侧|右侧|内侧|外侧"
    r"|砖缝|石阶|台阶|门槛|墙角|地窖|暗格"
    r"|same loose brick|same brick|third stair|east(?:ern)? side|west(?:ern)? side"
    r"|north(?:ern)? side|south(?:ern)? side|cellar|threshold)",
    re.IGNORECASE,
)
_FORENSIC_NOISE_RE = re.compile(
    r"(?:划痕|刮擦|裂痕|偏差|误差|痕迹|scratch|scrape|error margin|deviation)",
    re.IGNORECASE,
)
_VISUAL_HINTS = (
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
    "eye",
    "eyes",
    "skin",
    "face",
    "facial",
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
    "hairpin",
    "brooch",
    "25岁",
    "40岁",
    "年轻",
    "青年",
    "中年",
    "老人",
    "男性",
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
    "脸",
    "面容",
    "五官",
    "身形",
    "体型",
    "清瘦",
    "高瘦",
    "健壮",
    "发福",
    "胡",
    "疤",
    "穿着",
    "戴着",
    "披着",
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
    "耳坠",
    "项链",
    "手镯",
    "戒指",
    "靴",
    "衣",
    "袍",
    "衫",
    "裙",
    "甲",
    "服",
)


def _collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _split_profile_fragments(text: str) -> list[str]:
    return [
        _collapse_spaces(fragment).strip(" ,，;；")
        for fragment in _FRAGMENT_SPLIT_RE.split(text or "")
        if _collapse_spaces(fragment).strip(" ,，;；")
    ]


def _is_over_specific_profile_fragment(fragment: str) -> bool:
    normalized = _collapse_spaces(fragment)
    if not normalized:
        return False

    has_precision = bool(_PRECISION_NOISE_RE.search(normalized))
    has_ritual = bool(_RITUAL_NOISE_RE.search(normalized))
    has_location = bool(_LOCATION_NOISE_RE.search(normalized))
    has_forensic = bool(_FORENSIC_NOISE_RE.search(normalized))

    return (
        (has_precision and (has_ritual or has_location or has_forensic))
        or (has_ritual and has_location)
        or (has_location and has_forensic)
    )


def sanitize_character_profile_description(text: str, *, keep_original_if_empty: bool = True) -> str:
    normalized = _collapse_spaces(text)
    if not normalized:
        return ""

    fragments: list[str] = []
    seen: set[str] = set()
    filtered = False
    for fragment in _split_profile_fragments(normalized):
        if _is_over_specific_profile_fragment(fragment):
            filtered = True
            continue
        if fragment in seen:
            filtered = True
            continue
        seen.add(fragment)
        fragments.append(fragment)

    if not fragments:
        return normalized if keep_original_if_empty else ""
    if not filtered:
        return normalized

    delimiter = "，" if _CJK_RE.search(normalized) else ", "
    cleaned = delimiter.join(fragments).strip()
    return cleaned or (normalized if keep_original_if_empty else "")


def extract_character_visual_description(text: str) -> str:
    cleaned = sanitize_character_profile_description(text, keep_original_if_empty=False)
    if not cleaned:
        return ""

    visual_fragments: list[str] = []
    seen: set[str] = set()
    for fragment in _split_profile_fragments(cleaned):
        lowered = fragment.lower()
        if not any(hint in lowered for hint in _VISUAL_HINTS):
            continue
        if fragment in seen:
            continue
        seen.add(fragment)
        visual_fragments.append(fragment)

    if not visual_fragments:
        return ""

    delimiter = "，" if _CJK_RE.search(cleaned) else ", "
    return delimiter.join(visual_fragments)
