from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from difflib import SequenceMatcher
import re
from typing import Any, Mapping, Optional

from fastapi import HTTPException
import httpx

from app.core.api_keys import inject_art_style
from app.core.story_context import StoryContext
from app.services.image import DEFAULT_MODEL, EPISODE_DIR, generate_image
from app.services.quality import (
    resolve_default_quality_llm_config,
    run_quality_guarded_prompt_payload,
)


SCENE_REFERENCE_NEGATIVE_PROMPT = (
    "foreground hero, close-up character, dramatic action, crowd, person, human, man, woman, child, face, portrait, "
    "silhouette, hands, full body, costume, outfit, weapon, text, watermark, logo, subtitles, overdesigned clutter, "
    "excessive props, split scene, collage"
)

SCENE_REFERENCE_IMAGE_TIMEOUT_SECONDS = 180


def _extract_timeout_exception(exc: Exception) -> httpx.TimeoutException | None:
    if isinstance(exc, httpx.TimeoutException):
        return exc
    cause = getattr(exc, "__cause__", None)
    if isinstance(cause, httpx.TimeoutException):
        return cause
    return None

LOCATION_SUFFIXES = (
    "楼顶花园",
    "发布会现场",
    "会议室",
    "办公室",
    "回廊",
    "长廊",
    "走廊",
    "庭院",
    "院落",
    "花园",
    "书房",
    "客厅",
    "卧室",
    "厨房",
    "餐厅",
    "包间",
    "大厅",
    "前厅",
    "后厅",
    "房间",
    "王府",
    "府邸",
    "宅院",
    "宫殿",
    "大殿",
    "偏殿",
    "地牢",
    "刑房",
    "牢房",
    "地下室",
    "仓库",
    "库房",
    "茶馆",
    "酒馆",
    "客栈",
    "驿站",
    "店铺",
    "市集",
    "街市",
    "街道",
    "小巷",
    "巷口",
    "桥头",
    "码头",
    "湖边",
    "河边",
    "海边",
    "岸边",
    "山洞",
    "洞穴",
    "洞口",
    "森林",
    "树林",
    "林间",
    "草地",
    "山路",
    "古道",
    "城门",
    "宫门",
    "门廊",
    "门口",
    "入口",
    "出口",
    "楼顶",
    "天台",
    "屋顶",
    "阳台",
    "站台",
    "车站",
    "车厢",
    "机场",
    "候机厅",
    "实验室",
    "教室",
    "医院",
    "病房",
    "手术室",
    "展厅",
    "广场",
    "祠堂",
    "寺庙",
    "佛堂",
    "阁楼",
    "塔楼",
    "楼道",
    "楼梯间",
    "电梯厅",
    "走道",
    "现场",
)

ENV_OBJECT_TERMS = (
    "朱红立柱",
    "青石地面",
    "投影屏幕",
    "全息投影屏幕",
    "落地窗",
    "玫瑰花装饰",
    "石墙",
    "铁链",
    "牢门",
    "铁门",
    "门洞",
    "拱门",
    "门框",
    "门扇",
    "屏风",
    "纱帘",
    "窗棂",
    "栏杆",
    "台阶",
    "楼梯",
    "扶手",
    "立柱",
    "廊柱",
    "石柱",
    "灯笼",
    "宫灯",
    "烛台",
    "烛火",
    "壁灯",
    "吊灯",
    "书架",
    "书案",
    "案几",
    "桌案",
    "长桌",
    "桌面",
    "椅子",
    "沙发",
    "抱枕",
    "吧台",
    "柜台",
    "货架",
    "展台",
    "青石",
    "石板",
    "地面",
    "砖墙",
    "庭树",
    "假山",
    "池水",
    "喷泉",
    "花坛",
    "藤蔓",
    "植物",
    "盆栽",
    "屋檐",
    "瓦檐",
    "横梁",
    "梁柱",
    "穹顶",
    "天窗",
    "雾气",
    "薄雾",
    "烟雾",
    "雨幕",
    "积水",
    "水面",
    "投影",
    "幕布",
    "玫瑰",
)

MATCHING_NOISE_TERMS = (
    "男主",
    "女主",
    "主人公",
    "人物",
    "角色",
    "主角",
    "配角",
    "前景",
    "主体",
    "近景",
    "中景",
    "远景",
    "全景",
    "特写",
    "俯拍",
    "仰拍",
    "镜头",
    "机位",
    "构图",
    "景深",
    "虚化",
    "电影感",
    "戏剧张力",
    "故事感",
    "命运感",
    "气氛",
    "氛围",
    "情绪",
    "心理",
    "内心",
    "压抑",
    "克制",
    "紧绷",
    "紧张",
    "神秘",
    "宿命",
    "悲伤",
    "恐惧",
    "浪漫",
    "喧闹",
    "热烈",
    "安静",
    "孤独",
    "庄严",
    "史诗",
    "清晨",
    "凌晨",
    "早晨",
    "上午",
    "中午",
    "下午",
    "傍晚",
    "黄昏",
    "夜晚",
    "深夜",
    "白天",
    "雨后",
    "雨夜",
    "下雨",
    "暴雨",
    "雪夜",
    "阴天",
    "晴天",
    "夕阳",
    "晨光",
    "天光",
    "月光",
    "站在",
    "坐在",
    "走向",
    "走进",
    "走出",
    "快步",
    "停下",
    "回头",
    "抬头",
    "低头",
    "注视",
    "看向",
    "对视",
    "手持",
    "拿着",
)

ANCHOR_PREFIX_NOISE = (
    "古代",
    "现代",
    "现代化",
    "高档",
    "繁华",
    "温馨",
    "空旷",
    "昏暗",
    "一间",
    "一处",
    "一座",
    "一条",
    "这条",
    "那条",
    "这座",
    "那座",
    "这个",
    "那个",
    "其中",
    "以及",
    "可见",
    "的",
)

SEPARATOR_CHARS = set("，,。；;、：:／/| \n\t")


def build_scene_key(episode: int, scene_number: int) -> str:
    return f"ep{episode:02d}_scene{scene_number:02d}"


def build_environment_pack_key(episode: int, group_index: int) -> str:
    return f"ep{episode:02d}_env{group_index:02d}"


def _collapse_spaces(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _unique_normalized(values: list[Any], *, limit: int) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _collapse_spaces(value)
        if not normalized or normalized in seen:
            continue
        output.append(normalized)
        seen.add(normalized)
        if len(output) >= limit:
            break
    return output


def _top_value(values: list[Any]) -> str:
    normalized_values = [_collapse_spaces(value) for value in values if _collapse_spaces(value)]
    if not normalized_values:
        return ""
    return Counter(normalized_values).most_common(1)[0][0]


def _remove_matching_noise(text: Any) -> str:
    cleaned = _collapse_spaces(text)
    if not cleaned:
        return ""
    for term in MATCHING_NOISE_TERMS:
        cleaned = cleaned.replace(term, " ")
    return _collapse_spaces(cleaned)


def _compact_text(text: Any) -> str:
    return re.sub(r"\s+", "", _collapse_spaces(text))


def _trim_anchor_prefix(anchor: str) -> str:
    value = anchor.strip()
    changed = True
    while value and changed:
        changed = False
        for prefix in ANCHOR_PREFIX_NOISE:
            if value.startswith(prefix) and len(value) > len(prefix):
                value = value[len(prefix) :].strip()
                changed = True
    return value


def _extract_place_anchors(*texts: Any, limit: int = 6) -> list[str]:
    anchors: list[str] = []
    for text in texts:
        combined = _compact_text(_remove_matching_noise(text))
        if not combined:
            continue
        for suffix in LOCATION_SUFFIXES:
            search_from = 0
            while True:
                index = combined.find(suffix, search_from)
                if index < 0:
                    break
                left = index
                scanned = 0
                while left > 0 and combined[left - 1] not in SEPARATOR_CHARS and scanned < 6:
                    left -= 1
                    scanned += 1
                candidate = _trim_anchor_prefix(combined[left : index + len(suffix)])
                if candidate:
                    anchors.append(candidate)
                search_from = index + len(suffix)
    return _unique_normalized(anchors, limit=limit)


def _extract_object_anchors(*texts: Any, limit: int = 6) -> list[str]:
    hits: list[str] = []
    for text in texts:
        combined = _compact_text(_remove_matching_noise(text))
        if not combined:
            continue
        hits.extend(term for term in ENV_OBJECT_TERMS if term in combined)
    return _unique_normalized(hits, limit=limit)


def _build_environment_signature(environment: str, visual: str) -> str:
    place_anchors = _extract_place_anchors(environment, visual)
    object_anchors = _extract_object_anchors(environment, visual)
    if place_anchors or object_anchors:
        return " ".join(_unique_normalized(place_anchors + object_anchors, limit=8))
    return _remove_matching_noise(environment)


def _scene_place_anchors(scene: Mapping[str, Any]) -> list[str]:
    anchors = scene.get("place_anchors")
    if isinstance(anchors, list) and anchors:
        return [value for value in anchors if _collapse_spaces(value)]
    environment_anchor = _collapse_spaces(scene.get("environment_anchor", ""))
    extracted = _extract_place_anchors(environment_anchor, scene.get("environment", ""), scene.get("visual", ""))
    if environment_anchor:
        return _unique_normalized([environment_anchor, *extracted], limit=6)
    return extracted


def _scene_object_anchors(scene: Mapping[str, Any]) -> list[str]:
    anchors = scene.get("object_anchors")
    if isinstance(anchors, list) and anchors:
        return [value for value in anchors if _collapse_spaces(value)]
    return _extract_object_anchors(scene.get("environment", ""), scene.get("visual", ""))


def _scene_environment_signature(scene: Mapping[str, Any]) -> str:
    signature = _collapse_spaces(scene.get("environment_signature", ""))
    if signature:
        return signature
    environment_anchor = _collapse_spaces(scene.get("environment_anchor", ""))
    return _build_environment_signature(
        environment_anchor or _collapse_spaces(scene.get("environment", "")),
        _collapse_spaces(scene.get("visual", "")),
    )


def build_environment_group_signature(group_scenes: list[Mapping[str, Any]]) -> str:
    place_anchors = _unique_normalized(
        [anchor for scene in group_scenes for anchor in _scene_place_anchors(scene)],
        limit=8,
    )
    object_anchors = _unique_normalized(
        [anchor for scene in group_scenes for anchor in _scene_object_anchors(scene)],
        limit=8,
    )
    fallback_signatures = _unique_normalized([_scene_environment_signature(scene) for scene in group_scenes], limit=3)

    parts: list[str] = []
    if place_anchors:
        parts.append(f"places:{'|'.join(place_anchors)}")
    if object_anchors:
        parts.append(f"objects:{'|'.join(object_anchors)}")
    if fallback_signatures:
        parts.append(f"fallback:{'|'.join(fallback_signatures)}")
    return " || ".join(parts)


def _asset_reuse_signature(asset: Mapping[str, Any]) -> str:
    signature = _collapse_spaces(asset.get("reuse_signature", ""))
    if signature:
        return signature
    summary_visuals = asset.get("summary_visuals") or []
    return build_environment_group_signature(
        [
            {
                "environment": asset.get("summary_environment", ""),
                "visual": " ".join(str(item) for item in summary_visuals if _collapse_spaces(item)),
            }
        ]
    )


def _asset_is_reusable(asset: Mapping[str, Any]) -> bool:
    if asset.get("status") != "ready":
        return False
    variants = asset.get("variants") or {}
    scene_variant = variants.get("scene") or {}
    return bool(_collapse_spaces(scene_variant.get("image_url", "")))


def _asset_anchor_score(asset: Mapping[str, Any], group_scenes: list[Mapping[str, Any]]) -> float:
    asset_summary_environment = _collapse_spaces(asset.get("summary_environment", ""))
    asset_summary_visuals = " ".join(
        str(item) for item in (asset.get("summary_visuals") or []) if _collapse_spaces(item)
    )
    asset_places = _extract_place_anchors(asset_summary_environment, asset_summary_visuals)
    asset_objects = _extract_object_anchors(asset_summary_environment, asset_summary_visuals)
    group_places, group_objects = _group_environment_anchors(group_scenes)

    place_score = _anchor_similarity(group_places, asset_places)
    object_score = _anchor_similarity(group_objects, asset_objects)

    group_environment = _top_value([scene.get("environment", "") for scene in group_scenes])
    environment_score = (
        SequenceMatcher(None, group_environment, asset_summary_environment).ratio()
        if group_environment and asset_summary_environment
        else 0.0
    )
    return max(
        place_score * 0.75 + object_score * 0.25,
        place_score * 0.6 + environment_score * 0.4,
    )


def _select_reusable_asset(
    reusable_assets: list[Mapping[str, Any]],
    group_scenes: list[Mapping[str, Any]],
) -> dict[str, Any] | None:
    if not reusable_assets:
        return None

    group_signature = build_environment_group_signature(group_scenes)
    for asset in reusable_assets:
        if _asset_reuse_signature(asset) == group_signature:
            return dict(asset)

    best_asset: Mapping[str, Any] | None = None
    best_score = 0.0
    for asset in reusable_assets:
        score = _asset_anchor_score(asset, group_scenes)
        if score > best_score:
            best_asset = asset
            best_score = score

    if best_asset and best_score >= 0.72:
        return dict(best_asset)
    return None


def _group_environment_anchors(group_scenes: list[Mapping[str, Any]]) -> tuple[list[str], list[str]]:
    place_anchors = _unique_normalized(
        [anchor for scene in group_scenes for anchor in _scene_place_anchors(scene)],
        limit=4,
    )
    object_anchors = _unique_normalized(
        [anchor for scene in group_scenes for anchor in _scene_object_anchors(scene)],
        limit=4,
    )
    return place_anchors, object_anchors


def _group_environment_descriptions(group_scenes: list[Mapping[str, Any]], *, limit: int = 2) -> list[str]:
    stable_anchors = _unique_normalized(
        [scene.get("environment_anchor", "") for scene in group_scenes],
        limit=1,
    )
    if stable_anchors:
        return stable_anchors
    return _unique_normalized(
        [scene.get("environment", "") for scene in group_scenes],
        limit=limit,
    )


def _clone_group_asset_from_existing(
    asset: Mapping[str, Any],
    group: Mapping[str, Any],
    *,
    timestamp: str,
    episode_title: str,
    reuse_signature: str,
) -> dict[str, Any]:
    cloned = deepcopy(dict(asset))
    cloned["status"] = "ready"
    cloned["error"] = ""
    cloned["updated_at"] = timestamp
    cloned["environment_pack_key"] = group["environment_pack_key"]
    cloned["group_index"] = group["group_index"]
    cloned["group_label"] = group["group_label"]
    cloned["affected_scene_keys"] = list(group["scene_keys"])
    cloned["affected_scene_numbers"] = list(group["scene_numbers"])
    cloned["summary_environment"] = group["summary_environment"]
    cloned["summary_lighting"] = group["summary_lighting"]
    cloned["summary_mood"] = group["summary_mood"]
    cloned["summary_visuals"] = list(group["summary_visuals"])
    cloned["episode_title"] = episode_title
    cloned["reuse_signature"] = reuse_signature
    return cloned


def _anchor_similarity(left: list[str], right: list[str]) -> float:
    if not left or not right:
        return 0.0

    overlap_hits = 0
    best_pair = 0.0
    for candidate in left:
        matched = False
        for other in right:
            if candidate == other:
                best_pair = max(best_pair, 1.0)
                matched = True
            elif candidate in other or other in candidate:
                best_pair = max(best_pair, 0.94)
                matched = True
            else:
                ratio = SequenceMatcher(None, candidate, other).ratio()
                if ratio >= 0.85:
                    best_pair = max(best_pair, 0.78)
                    matched = True
        if matched:
            overlap_hits += 1

    overlap_score = overlap_hits / max(len(left), len(right))
    return max(best_pair, overlap_score)


def _normalize_scene_record(scene: Mapping[str, Any], episode: int) -> dict[str, Any]:
    scene_number = int(scene.get("scene_number", 0))
    environment_anchor = _collapse_spaces(scene.get("environment_anchor", ""))
    environment = _collapse_spaces(scene.get("environment", ""))
    visual = _collapse_spaces(scene.get("visual", ""))
    place_anchors = _extract_place_anchors(environment_anchor, environment, visual)
    if environment_anchor:
        place_anchors = _unique_normalized([environment_anchor, *place_anchors], limit=6)
    return {
        "episode": episode,
        "scene_number": scene_number,
        "scene_key": build_scene_key(episode, scene_number),
        "environment_anchor": environment_anchor,
        "environment": environment,
        "visual": visual,
        "lighting": _collapse_spaces(scene.get("lighting", "")),
        "mood": _collapse_spaces(scene.get("mood", "")),
        "place_anchors": place_anchors,
        "object_anchors": _extract_object_anchors(environment, visual),
        "environment_signature": _build_environment_signature(environment_anchor or environment, visual),
        "raw": dict(scene),
    }


def _scene_similarity(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    left_places = list(left.get("place_anchors") or [])
    right_places = list(right.get("place_anchors") or [])
    place_score = _anchor_similarity(left_places, right_places)

    left_signature = _collapse_spaces(left.get("environment_signature", ""))
    right_signature = _collapse_spaces(right.get("environment_signature", ""))
    env_ratio = SequenceMatcher(None, left_signature, right_signature).ratio() if left_signature and right_signature else 0.0

    left_objects = list(left.get("object_anchors") or [])
    right_objects = list(right.get("object_anchors") or [])
    object_score = _anchor_similarity(left_objects, right_objects)

    if left_places and right_places:
        if place_score < 0.55:
            return min(env_ratio * 0.2 + object_score * 0.15, 0.34)
        score = place_score * 0.7 + env_ratio * 0.2 + object_score * 0.1
        return min(score, 1.0)

    return min(env_ratio * 0.8 + object_score * 0.2, 1.0)


def group_episode_scenes_by_environment(episode: int, episode_scenes: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized_scenes = [_normalize_scene_record(scene, episode) for scene in episode_scenes]
    groups: list[dict[str, Any]] = []

    for scene in normalized_scenes:
        best_group: Optional[dict[str, Any]] = None
        best_score = 0.0
        for group in groups:
            score = _scene_similarity(scene, group["representative_scene"])
            if score > best_score:
                best_score = score
                best_group = group

        if best_group and best_score >= 0.68:
            best_group["scenes"].append(scene)
            continue

        groups.append(
            {
                "representative_scene": scene,
                "scenes": [scene],
            }
        )

    for index, group in enumerate(groups, start=1):
        scenes = group["scenes"]
        representative = group["representative_scene"]
        _, object_anchors = _group_environment_anchors(scenes)
        group["group_index"] = index
        group["environment_pack_key"] = build_environment_pack_key(episode, index)
        group["group_label"] = f"环境组 {index}"
        group["scene_keys"] = [scene["scene_key"] for scene in scenes]
        group["scene_numbers"] = [scene["scene_number"] for scene in scenes]
        group["summary_environment"] = " ".join(_group_environment_descriptions(scenes, limit=2)) or representative["environment"]
        group["summary_lighting"] = _top_value([scene["lighting"] for scene in scenes])
        group["summary_mood"] = _top_value([scene["mood"] for scene in scenes])
        group["summary_visuals"] = object_anchors or _unique_normalized([scene["visual"] for scene in scenes], limit=2)

    return groups


def _episode_scenes(story: Mapping[str, Any], episode: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    for episode_entry in story.get("scenes") or []:
        if int(episode_entry.get("episode", 0)) != int(episode):
            continue
        scenes = list(episode_entry.get("scenes") or [])
        return dict(episode_entry), scenes
    raise HTTPException(status_code=404, detail=f"未找到第 {episode} 集剧本场景")


def build_episode_environment_prompts(
    group_scenes: list[Mapping[str, Any]],
    story_context: Optional[StoryContext],
    art_style: str = "",
) -> dict[str, dict[str, str]]:
    if not group_scenes:
        raise ValueError("group_scenes 不能为空")

    place_anchors, object_anchors = _group_environment_anchors(group_scenes)
    environment_descriptions = _group_environment_descriptions(group_scenes, limit=2)
    environments = environment_descriptions or place_anchors
    visuals = object_anchors
    lighting = _top_value([scene.get("lighting", "") for scene in group_scenes])
    mood = _top_value([scene.get("mood", "") for scene in group_scenes])
    style_anchors = _unique_normalized(
        [style.image_extra for style in (story_context.scene_styles if story_context else [])],
        limit=2,
    )

    base_parts = [
        "Environment reference key art for a matched scene group inside one episode.",
        "Keep the environment readable and reusable across the matched scenes, but preserve the exact location identity.",
        "Pure environment plate only. No characters, no faces, no bodies, no costumes, no action, no narrative beat.",
    ]
    if environments:
        base_parts.append(f"Shared environment: {'; '.join(environments)}.")
    if place_anchors:
        base_parts.append(f"Stable place anchors: {'; '.join(place_anchors)}.")
    if visuals:
        base_parts.append(f"Stable prop anchors: {'; '.join(visuals)}.")
    if lighting:
        base_parts.append(f"Lighting anchor: {lighting}.")
    if mood:
        base_parts.append(f"Atmosphere anchor: {mood}.")
    if style_anchors:
        base_parts.append(f"Scene style anchors: {'; '.join(style_anchors)}.")
    base_parts.append(
        "Match the described architecture, materials, furnishing layout, and prop placement. Do not replace this with a generic room, hallway, palace, or fantasy set."
    )
    base_parts.append(
        "Environment only, no story beat, no dramatic acting, no foreground hero, no character silhouette, no text, no watermark, no clutter."
    )
    base_prompt = " ".join(part for part in base_parts if part).strip()

    return {
        "scene": {
            "prompt": inject_art_style(
                (
                    f"{base_prompt} One clean master environment reference image. "
                    "Use a balanced, readable composition that clearly presents the main space, architecture, entry points, "
                    "important background structures, and stable light direction for later shot adaptation."
                ),
                art_style,
            ),
            "negative_prompt": (
                f"{SCENE_REFERENCE_NEGATIVE_PROMPT}, extreme close-up composition, portrait framing, isolated prop macro, "
                "overly dramatic angle, split composition"
            ),
        }
    }


async def generate_episode_scene_reference(
    story: Mapping[str, Any],
    story_context: Optional[StoryContext],
    *,
    episode: int,
    model: str = DEFAULT_MODEL,
    image_api_key: str = "",
    image_base_url: str = "",
    image_provider: str = "",
    art_style: str = "",
    existing_assets: Optional[list[Mapping[str, Any]]] = None,
) -> dict[str, Any]:
    effective_model = model or DEFAULT_MODEL
    quality_provider, quality_model, quality_api_key, quality_base_url = resolve_default_quality_llm_config()
    episode_entry, episode_scenes = _episode_scenes(story, episode)
    scene_groups = group_episode_scenes_by_environment(episode, episode_scenes)
    reusable_assets = [dict(asset) for asset in (existing_assets or []) if _asset_is_reusable(asset)]

    results: list[dict[str, Any]] = []
    timestamp = datetime.now(timezone.utc).isoformat()
    for group in scene_groups:
        reuse_signature = build_environment_group_signature(group["scenes"])
        reusable_asset = _select_reusable_asset(reusable_assets, group["scenes"])
        if reusable_asset:
            reusable_assets = [
                asset
                for asset in reusable_assets
                if _asset_reuse_signature(asset) != _asset_reuse_signature(reusable_asset)
            ]
            asset = _clone_group_asset_from_existing(
                reusable_asset,
                group,
                timestamp=timestamp,
                episode_title=_collapse_spaces(episode_entry.get("title", "")),
                reuse_signature=reuse_signature,
            )
            results.append(
                {
                    "environment_pack_key": group["environment_pack_key"],
                    "affected_scene_keys": group["scene_keys"],
                    "asset": asset,
                }
            )
            continue

        prompts = build_episode_environment_prompts(group["scenes"], story_context, art_style=art_style)
        variant_results: dict[str, dict[str, Any]] = {}
        for variant, prompt_payload in prompts.items():
            guarded_prompt_payload, quality = await run_quality_guarded_prompt_payload(
                family="scene_reference_prompt",
                provider=quality_provider,
                model=quality_model,
                api_key=quality_api_key,
                base_url=quality_base_url,
                base_payload_builder=lambda prompt_payload=prompt_payload: {
                    **dict(prompt_payload),
                    "environment_pack_key": group["environment_pack_key"],
                    "group_label": group["group_label"],
                    "summary_environment": group["summary_environment"],
                    "summary_lighting": group["summary_lighting"],
                    "summary_mood": group["summary_mood"],
                    "summary_visuals": list(group["summary_visuals"]),
                },
                telemetry_context={
                    "operation": "scene_reference.build_prompt",
                    "story_id": str(story.get("id", "")).strip(),
                    "episode": episode,
                    "environment_pack_key": group["environment_pack_key"],
                    "variant": variant,
                },
            )
            try:
                result = await generate_image(
                    guarded_prompt_payload["prompt"],
                    f"{group['environment_pack_key']}_{variant}",
                    model=effective_model,
                    image_api_key=image_api_key,
                    image_base_url=image_base_url,
                    image_provider=image_provider,
                    negative_prompt=guarded_prompt_payload["negative_prompt"],
                    output_dir=EPISODE_DIR,
                    url_prefix="/media/episodes",
                    timeout_seconds=SCENE_REFERENCE_IMAGE_TIMEOUT_SECONDS,
                )
            except httpx.TimeoutException as exc:
                raise HTTPException(
                    status_code=504,
                    detail=(
                        f"环境图生成超时：{group['group_label']} 生成时间过长，请重试。"
                    ),
                ) from exc
            except RuntimeError as exc:
                timeout_exc = _extract_timeout_exception(exc)
                if timeout_exc:
                    raise HTTPException(
                        status_code=504,
                        detail=(
                            f"环境图生成超时：{group['group_label']} 生成时间过长，请重试。"
                        ),
                    ) from timeout_exc
                raise
            variant_results[variant] = {
                "prompt": guarded_prompt_payload["prompt"],
                "image_url": result["image_url"],
                "image_path": result["image_path"],
                "quality": quality,
            }

        asset = {
            "status": "ready",
            "variants": variant_results,
            "error": "",
            "updated_at": timestamp,
            "environment_pack_key": group["environment_pack_key"],
            "group_index": group["group_index"],
            "group_label": group["group_label"],
            "affected_scene_keys": group["scene_keys"],
            "affected_scene_numbers": group["scene_numbers"],
            "summary_environment": group["summary_environment"],
            "summary_lighting": group["summary_lighting"],
            "summary_mood": group["summary_mood"],
            "summary_visuals": group["summary_visuals"],
            "episode_title": _collapse_spaces(episode_entry.get("title", "")),
            "reuse_signature": reuse_signature,
        }
        results.append(
            {
                "environment_pack_key": group["environment_pack_key"],
                "affected_scene_keys": group["scene_keys"],
                "asset": asset,
            }
        )

    return {
        "episode": episode,
        "groups": results,
    }
