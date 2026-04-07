from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal, Mapping

from app.core.config import settings
from app.services.llm.factory import get_llm_provider


logger = logging.getLogger(__name__)

PromptFamily = Literal[
    "story_outline",
    "storyboard_parse",
    "character_appearance_extract",
    "scene_style_extract",
    "generation_payload",
    "scene_reference_prompt",
    "character_design_prompt",
]
_QUALITY_ARTIFACT_PATH = Path(__file__).resolve().parents[1] / "quality_artifacts.json"

_FAMILY_FLAGS: dict[PromptFamily, str] = {
    "story_outline": "quality_outline_enabled",
    "storyboard_parse": "quality_storyboard_enabled",
    "character_appearance_extract": "quality_character_appearance_enabled",
    "scene_style_extract": "quality_scene_style_enabled",
    "generation_payload": "quality_generation_payload_enabled",
    "scene_reference_prompt": "quality_scene_reference_enabled",
    "character_design_prompt": "quality_character_design_enabled",
}

_JUDGE_RUBRICS: dict[PromptFamily, dict[str, Any]] = {
    "story_outline": {
        "label": "Story Outline",
        "minimum_overall_score": 3.0,
        "criteria": [
            {
                "name": "logline_and_conflict",
                "label": "Logline / 冲突清晰度",
                "description": "主角、目标、阻碍与核心冲突是否明确。",
                "minimum_score": 3,
            },
            {
                "name": "beat_progression",
                "label": "Beats / 推进节奏",
                "description": "每集 beats 是否体现递进、转折与结果，而不是重复剧情复述。",
                "minimum_score": 3,
            },
            {
                "name": "scene_stability",
                "label": "Scene List / 场景切分稳定性",
                "description": "scene_list 是否稳定可执行，场景命名是否利于后续环境复用。",
                "minimum_score": 3,
            },
            {
                "name": "cross_episode_cohesion",
                "label": "跨集连贯性",
                "description": "6 集是否形成清晰季弧线，没有明显断裂或前后矛盾。",
                "minimum_score": 3,
            },
        ],
    },
    "storyboard_parse": {
        "label": "Storyboard Parse",
        "minimum_overall_score": 3.0,
        "criteria": [
            {
                "name": "visible_state",
                "label": "可见状态",
                "description": "storyboard_description 是否只描述当前镜头可见状态，没有整段剧情复述。",
                "minimum_score": 3,
            },
            {
                "name": "camera_actionability",
                "label": "镜头可执行性",
                "description": "camera_setup、visual_elements、scene_position 是否足够明确，镜头可以直接执行。",
                "minimum_score": 3,
            },
            {
                "name": "continuity_anchors",
                "label": "连续性锚点",
                "description": "角色、环境、关键道具和过渡锚点是否足够支撑连续生成。",
                "minimum_score": 3,
            },
            {
                "name": "prompt_separation",
                "label": "Prompt 分工",
                "description": "image_prompt 与 final_video_prompt 是否各司其职，而不是简单复制。",
                "minimum_score": 3,
            },
        ],
    },
    "character_appearance_extract": {
        "label": "Character Appearance Cache",
        "minimum_overall_score": 3.0,
        "criteria": [
            {
                "name": "identity_constraints",
                "label": "Immutable Traits / 外观约束",
                "description": "body 是否只保留稳定物理外观锚点，没有混入性格、剧情、镜头或光影信息。",
                "minimum_score": 3,
            },
            {
                "name": "default_costume",
                "label": "Default Outfit / 默认服装",
                "description": "clothing 是否只保留默认服装与常驻配饰，不混入临时动作、表情或场景状态。",
                "minimum_score": 3,
            },
            {
                "name": "prompt_readiness",
                "label": "Prompt 适配度",
                "description": "字段是否简洁、可直接用于 image/video prompt，没有冗余修辞与无关标签。",
                "minimum_score": 3,
            },
            {
                "name": "coverage_alignment",
                "label": "Coverage / 对齐度",
                "description": "是否保留输入角色 id，并尽量覆盖所有输入角色，不发生错配或串角色。",
                "minimum_score": 3,
            },
        ],
    },
    "scene_style_extract": {
        "label": "Scene Style Cache",
        "minimum_overall_score": 3.0,
        "criteria": [
            {
                "name": "production_design_anchors",
                "label": "Production Design / 美术锚点",
                "description": "是否提炼出可复用的建筑、材质、道具、时代与氛围锚点，而不是剧情复述。",
                "minimum_score": 3,
            },
            {
                "name": "image_video_split",
                "label": "Image / Video 分工",
                "description": "image_extra 与 video_extra 是否同源但不机械重复，兼顾静帧与视频可执行性。",
                "minimum_score": 3,
            },
            {
                "name": "reusability",
                "label": "Reusable / 可复用性",
                "description": "输出是否足够紧凑、通用，可跨多个镜头复用，而不是只适配单一剧情瞬间。",
                "minimum_score": 3,
            },
            {
                "name": "contamination_control",
                "label": "污染控制",
                "description": "是否避免镜头语言、对白、艺术风格标签与现代污染项混入环境锚点。",
                "minimum_score": 3,
            },
        ],
    },
    "generation_payload": {
        "label": "Runtime Generation Payload",
        "minimum_overall_score": 3.0,
        "criteria": [
            {
                "name": "opening_frame_readability",
                "label": "Opening Frame / 首帧可读性",
                "description": "image_prompt 是否聚焦单一清晰的首帧，而不是混入多段动作或剧情复述。",
                "minimum_score": 3,
            },
            {
                "name": "video_motion_continuity",
                "label": "Video Motion / 动作连续性",
                "description": "final_video_prompt 是否从首帧自然起步，只覆盖短时连续动作，没有跳镜或突变。",
                "minimum_score": 3,
            },
            {
                "name": "reference_anchor_usage",
                "label": "Reference Anchors / 参考锚点",
                "description": "角色、环境、reference_images 与开场状态锚点是否被明确利用。",
                "minimum_score": 3,
            },
            {
                "name": "constraint_hygiene",
                "label": "Constraints / 约束卫生",
                "description": "negative_prompt 与正向 prompt 是否分工清晰，没有互相污染或缺失关键约束。",
                "minimum_score": 3,
            },
        ],
    },
    "scene_reference_prompt": {
        "label": "Scene Reference Prompt",
        "minimum_overall_score": 3.0,
        "criteria": [
            {
                "name": "environment_only",
                "label": "Environment Only / 纯环境",
                "description": "prompt 是否严格保持纯环境图，没有角色、动作、叙事瞬间或镜头表演。",
                "minimum_score": 3,
            },
            {
                "name": "location_specificity",
                "label": "Specific Location / 具体场景",
                "description": "是否保留该地点独有的建筑、材质、道具与布局，而不是退化成泛化场景。",
                "minimum_score": 3,
            },
            {
                "name": "reusable_layout",
                "label": "Reusable Layout / 可复用布局",
                "description": "是否清楚表达后续镜头复用所需的主空间、入口、背景结构和稳定光向。",
                "minimum_score": 3,
            },
            {
                "name": "contamination_control",
                "label": "Contamination / 污染控制",
                "description": "prompt 与 negative_prompt 是否足够排除人物特写、道具特写和构图污染。",
                "minimum_score": 3,
            },
        ],
    },
    "character_design_prompt": {
        "label": "Character Design Prompt",
        "minimum_overall_score": 3.0,
        "criteria": [
            {
                "name": "identity_lock",
                "label": "Identity Lock / 身份锁定",
                "description": "是否稳定锁定角色脸型、发型、体型、服装轮廓和标志性配饰，没有泛化重设计。",
                "minimum_score": 3,
            },
            {
                "name": "three_view_sheet",
                "label": "Three-View Sheet / 三视图约束",
                "description": "是否明确要求同一时刻、同一人物的 front / side / back 三视图，而不是三张不同重设计。",
                "minimum_score": 3,
            },
            {
                "name": "style_consistency",
                "label": "Style Consistency / 风格一致性",
                "description": "是否保证三视图的渲染风格、材质、光照和媒介语言统一。",
                "minimum_score": 3,
            },
            {
                "name": "contamination_control",
                "label": "Contamination / 污染控制",
                "description": "是否排除环境道具、文字水印、额外首饰盔甲或无关装饰污染。",
                "minimum_score": 3,
            },
        ],
    },
}

_JUDGE_SYSTEM_PROMPT = """
你是 AutoMedia 的质量裁判。你会按照给定 rubric 审核候选产物，并返回严格 JSON。

要求：
1. 只返回一个 JSON object，不要输出 Markdown，不要输出解释性前缀。
2. `criteria[*].score` 必须是 0 到 5 的数字。
3. `issues` 与 `feedback_instructions` 都必须是字符串数组。
4. `feedback_instructions` 必须是“可直接回灌给生成器的局部修复指令”，禁止笼统空话。
5. 当候选总体可用但仍有改进空间时，可以 `passed=true`，但要明确保留问题。
""".strip()


def _strip_code_fence(text: str) -> str:
    normalized = str(text or "").strip()
    if not normalized.startswith("```"):
        return normalized
    parts = normalized.split("```")
    candidate = parts[1] if len(parts) > 1 else normalized
    if candidate.startswith("json"):
        candidate = candidate[4:]
    return candidate.strip()


def _parse_json_text(text: str) -> Any:
    return json.loads(_strip_code_fence(text))


def _coerce_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_text_list(raw_items: Any) -> list[str]:
    if not isinstance(raw_items, list):
        return []
    return [str(item).strip() for item in raw_items if str(item or "").strip()]


def _append_overlay_text(base_text: Any, overlay: str) -> str:
    base = str(base_text or "").strip()
    addition = str(overlay or "").strip()
    if not addition:
        return base
    if not base:
        return addition
    if addition in base:
        return base
    return f"{base}\n\n{addition}"


def _overlay_generation_payload(payload: Mapping[str, Any], overlay: str) -> dict[str, Any]:
    candidate = dict(payload or {})
    addition = str(overlay or "").strip()
    if not addition:
        return candidate
    if candidate.get("image_prompt"):
        candidate["image_prompt"] = _append_overlay_text(candidate.get("image_prompt"), addition)
    if candidate.get("final_video_prompt"):
        candidate["final_video_prompt"] = _append_overlay_text(candidate.get("final_video_prompt"), addition)
    return candidate


def _overlay_prompt_payload(
    payload: Mapping[str, Any],
    overlay: str,
    *,
    prompt_key: str = "prompt",
) -> dict[str, Any]:
    candidate = dict(payload or {})
    addition = str(overlay or "").strip()
    if not addition:
        return candidate
    if candidate.get(prompt_key):
        candidate[prompt_key] = _append_overlay_text(candidate.get(prompt_key), addition)
    return candidate


def _generation_payload_judge_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    references: list[dict[str, Any]] = []
    for item in list(payload.get("reference_images") or [])[:4]:
        if not isinstance(item, Mapping):
            continue
        references.append(
            {
                "kind": str(item.get("kind", "")).strip(),
                "image_url": str(item.get("image_url", "")).strip(),
                "weight": item.get("weight"),
                "source_scene_key": str(item.get("source_scene_key", "")).strip(),
            }
        )
    return {
        "shot_id": str(payload.get("shot_id", "")).strip(),
        "source_scene_key": str(payload.get("source_scene_key", "")).strip(),
        "image_prompt": str(payload.get("image_prompt", "")).strip(),
        "final_video_prompt": str(payload.get("final_video_prompt", "")).strip(),
        "negative_prompt": str(payload.get("negative_prompt", "")).strip(),
        "reference_images": references,
    }


_DEFAULT_PROVIDER_CONFIG_ATTRS: dict[str, tuple[str, str]] = {
    "claude": ("anthropic_api_key", "anthropic_base_url"),
    "openai": ("openai_api_key", "openai_base_url"),
    "qwen": ("qwen_api_key", "qwen_base_url"),
    "zhipu": ("zhipu_api_key", "zhipu_base_url"),
    "gemini": ("gemini_api_key", "gemini_base_url"),
    "siliconflow": ("siliconflow_api_key", "siliconflow_base_url"),
}


def resolve_default_quality_llm_config(
    *,
    provider: str = "",
    model: str | None = None,
) -> tuple[str, str | None, str, str]:
    resolved_provider = str(provider or settings.default_llm_provider or "").strip().lower()
    api_key = ""
    base_url = ""
    attrs = _DEFAULT_PROVIDER_CONFIG_ATTRS.get(resolved_provider)
    if attrs:
        api_key = str(getattr(settings, attrs[0], "") or "").strip()
        base_url = str(getattr(settings, attrs[1], "") or "").strip()
    return resolved_provider, model, api_key, base_url


@dataclass
class DSPyCompiledProfile:
    family: PromptFamily
    version: str
    prompt_suffix: str = ""
    feedback_prefix: str = ""


@dataclass
class JudgeCriterionResult:
    name: str
    label: str
    score: float
    passed: bool
    reason: str


@dataclass
class JudgeResult:
    family: PromptFamily
    label: str
    enabled: bool
    skipped: bool
    shadow_mode: bool
    passed: bool
    overall_score: float
    summary: str
    issues: list[str] = field(default_factory=list)
    feedback_instructions: list[str] = field(default_factory=list)
    criteria: list[JudgeCriterionResult] = field(default_factory=list)
    error: str = ""
    usage: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "criteria": [asdict(item) for item in self.criteria],
        }


@dataclass
class QualityAttempt:
    attempt: int
    prompt_suffix_applied: bool
    feedback_applied: bool
    feedback_instruction: str
    generation_usage: dict[str, Any]
    judge: dict[str, Any] | None = None


@dataclass
class QualityRunResult:
    family: PromptFamily
    enabled: bool
    dspy_enabled: bool
    judge_enabled: bool
    shadow_mode: bool
    feedback_enabled: bool
    profile_version: str = ""
    final_passed: bool = True
    final_attempt: int = 1
    attempts: list[QualityAttempt] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "enabled": self.enabled,
            "dspy_enabled": self.dspy_enabled,
            "judge_enabled": self.judge_enabled,
            "shadow_mode": self.shadow_mode,
            "feedback_enabled": self.feedback_enabled,
            "profile_version": self.profile_version,
            "final_passed": self.final_passed,
            "final_attempt": self.final_attempt,
            "warnings": list(self.warnings),
            "attempts": [
                {
                    "attempt": attempt.attempt,
                    "prompt_suffix_applied": attempt.prompt_suffix_applied,
                    "feedback_applied": attempt.feedback_applied,
                    "feedback_instruction": attempt.feedback_instruction,
                    "generation_usage": dict(attempt.generation_usage),
                    "judge": dict(attempt.judge or {}) if attempt.judge is not None else None,
                }
                for attempt in self.attempts
            ],
        }


def _build_compiled_dspy_profiles(raw: Mapping[str, Any]) -> dict[str, DSPyCompiledProfile]:
    version = str(raw.get("version") or "").strip() or "unknown"
    profiles: dict[str, DSPyCompiledProfile] = {}
    for family, payload in dict(raw.get("profiles") or {}).items():
        if family not in _FAMILY_FLAGS:
            continue
        profile_payload = dict(payload or {})
        profiles[family] = DSPyCompiledProfile(
            family=family,  # type: ignore[arg-type]
            version=version,
            prompt_suffix=str(profile_payload.get("prompt_suffix") or "").strip(),
            feedback_prefix=str(profile_payload.get("feedback_prefix") or "").strip(),
        )
    return profiles


@lru_cache(maxsize=8)
def _load_compiled_dspy_profiles_cached(
    artifact_path: str,
    artifact_mtime_ns: int,
    artifact_size: int,
) -> dict[str, DSPyCompiledProfile]:
    del artifact_mtime_ns, artifact_size
    raw = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("quality artifacts root must be a JSON object")
    return _build_compiled_dspy_profiles(raw)


def load_compiled_dspy_profiles() -> dict[str, DSPyCompiledProfile]:
    if not _QUALITY_ARTIFACT_PATH.exists():
        return {}

    try:
        artifact_stat = _QUALITY_ARTIFACT_PATH.stat()
        return _load_compiled_dspy_profiles_cached(
            str(_QUALITY_ARTIFACT_PATH),
            artifact_stat.st_mtime_ns,
            artifact_stat.st_size,
        )
    except Exception as exc:
        logger.warning(
            "Failed to load quality artifacts path=%s; continuing without compiled DSPy profiles. error=%s",
            _QUALITY_ARTIFACT_PATH,
            exc,
        )
        return {}


load_compiled_dspy_profiles.cache_clear = _load_compiled_dspy_profiles_cached.cache_clear  # type: ignore[attr-defined]


def get_compiled_dspy_profile(family: PromptFamily) -> DSPyCompiledProfile | None:
    return load_compiled_dspy_profiles().get(family)


def is_quality_layer_enabled_for_family(family: PromptFamily) -> bool:
    if not settings.quality_layer_enabled:
        return False
    return bool(getattr(settings, _FAMILY_FLAGS[family], True))


def _build_prompt_suffix(
    family: PromptFamily,
    *,
    profile: DSPyCompiledProfile | None,
    feedback_instruction: str = "",
) -> str:
    parts: list[str] = []
    if profile and settings.quality_dspy_enabled and profile.prompt_suffix:
        parts.append(profile.prompt_suffix)
    if feedback_instruction and settings.quality_feedback_loop_enabled:
        feedback_prefix = profile.feedback_prefix if profile and profile.feedback_prefix else "请重点修复以下问题："
        parts.append(f"{feedback_prefix}\n{feedback_instruction}")
    return "\n\n".join(part for part in parts if str(part or "").strip())


def _resolve_judge_provider_config(
    *,
    provider: str,
    model: str | None,
    api_key: str,
    base_url: str,
) -> tuple[str, str | None, str, str]:
    primary_provider = str(provider or settings.default_llm_provider or "").strip().lower()
    primary_model = str(model or "").strip() or None
    primary_api_key = str(api_key or "").strip()
    primary_base_url = str(base_url or "").strip()

    configured_judge_provider = str(settings.quality_judge_provider or "").strip().lower()
    configured_judge_model = str(settings.quality_judge_model or "").strip() or None
    configured_judge_api_key = str(settings.quality_judge_api_key or "").strip()
    configured_judge_base_url = str(settings.quality_judge_base_url or "").strip()

    judge_provider = configured_judge_provider or primary_provider or ""
    _, _, default_judge_api_key, default_judge_base_url = resolve_default_quality_llm_config(provider=judge_provider)
    inherit_primary_config = judge_provider == primary_provider

    if inherit_primary_config:
        judge_model = configured_judge_model or primary_model
        judge_api_key = configured_judge_api_key or primary_api_key or str(default_judge_api_key or "").strip()
        judge_base_url = configured_judge_base_url or primary_base_url or str(default_judge_base_url or "").strip()
    else:
        judge_model = configured_judge_model
        judge_api_key = configured_judge_api_key or str(default_judge_api_key or "").strip()
        judge_base_url = configured_judge_base_url or str(default_judge_base_url or "").strip()

    return judge_provider, judge_model, judge_api_key, judge_base_url


def _build_judge_prompt(family: PromptFamily, candidate_payload: Any) -> str:
    rubric = _JUDGE_RUBRICS[family]
    criteria_lines = []
    for criterion in rubric["criteria"]:
        criteria_lines.append(
            f"- {criterion['name']} / {criterion['label']} / 最低分 {criterion['minimum_score']}: {criterion['description']}"
        )
    return (
        f"Prompt family: {family}\n"
        f"Label: {rubric['label']}\n"
        f"Minimum overall score: {rubric['minimum_overall_score']}\n"
        "Rubric:\n"
        f"{chr(10).join(criteria_lines)}\n\n"
        "Candidate JSON:\n"
        f"{json.dumps(candidate_payload, ensure_ascii=False, indent=2)}\n\n"
        "Return JSON with this schema:\n"
        "{\n"
        '  "passed": true,\n'
        '  "overall_score": 0,\n'
        '  "summary": "",\n'
        '  "issues": ["..."],\n'
        '  "feedback_instructions": ["..."],\n'
        '  "criteria": [\n'
        '    {"name": "criterion_name", "score": 0, "passed": true, "reason": ""}\n'
        "  ]\n"
        "}\n"
    )


def _normalize_judge_result(
    family: PromptFamily,
    raw_payload: Mapping[str, Any],
    *,
    shadow_mode: bool,
    usage: Mapping[str, Any] | None = None,
) -> JudgeResult:
    rubric = _JUDGE_RUBRICS[family]
    criterion_config = {criterion["name"]: criterion for criterion in rubric["criteria"]}

    criteria: list[JudgeCriterionResult] = []
    for raw_item in raw_payload.get("criteria") or []:
        if not isinstance(raw_item, Mapping):
            continue
        name = str(raw_item.get("name") or "").strip()
        if not name or name not in criterion_config:
            continue
        config = criterion_config[name]
        score = max(0.0, min(5.0, _coerce_float(raw_item.get("score"), default=0.0)))
        reason = str(raw_item.get("reason") or "").strip()
        criteria.append(
            JudgeCriterionResult(
                name=name,
                label=str(config["label"]),
                score=score,
                passed=score >= float(config["minimum_score"]),
                reason=reason,
            )
        )

    if not criteria:
        for config in rubric["criteria"]:
            criteria.append(
                JudgeCriterionResult(
                    name=str(config["name"]),
                    label=str(config["label"]),
                    score=0.0,
                    passed=False,
                    reason="Judge did not return this criterion.",
                )
            )

    overall_score = max(0.0, min(5.0, _coerce_float(raw_payload.get("overall_score"), default=0.0)))
    summary = str(raw_payload.get("summary") or "").strip()
    passed = (
        bool(raw_payload.get("passed"))
        and overall_score >= float(rubric["minimum_overall_score"])
        and all(item.passed for item in criteria)
    )

    return JudgeResult(
        family=family,
        label=str(rubric["label"]),
        enabled=True,
        skipped=False,
        shadow_mode=shadow_mode,
        passed=passed,
        overall_score=overall_score,
        summary=summary,
        issues=_normalize_text_list(raw_payload.get("issues")),
        feedback_instructions=_normalize_text_list(raw_payload.get("feedback_instructions")),
        criteria=criteria,
        usage=dict(usage or {}),
    )


async def run_quality_judge(
    *,
    family: PromptFamily,
    candidate_payload: Any,
    provider: str,
    model: str | None,
    api_key: str,
    base_url: str,
    telemetry_context: Mapping[str, Any] | None = None,
) -> JudgeResult:
    if not settings.quality_judge_enabled:
        return JudgeResult(
            family=family,
            label=_JUDGE_RUBRICS[family]["label"],
            enabled=False,
            skipped=True,
            shadow_mode=bool(settings.quality_judge_shadow_mode),
            passed=True,
            overall_score=0.0,
            summary="Judge disabled",
        )

    judge_provider, judge_model, judge_api_key, judge_base_url = _resolve_judge_provider_config(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
    )
    if not judge_provider or not judge_api_key:
        return JudgeResult(
            family=family,
            label=_JUDGE_RUBRICS[family]["label"],
            enabled=True,
            skipped=True,
            shadow_mode=bool(settings.quality_judge_shadow_mode),
            passed=True,
            overall_score=0.0,
            summary="Judge skipped because no usable provider or API key was available.",
        )

    llm = get_llm_provider(
        judge_provider,
        model=judge_model,
        api_key=judge_api_key,
        base_url=judge_base_url,
    )
    try:
        raw_text, usage = await llm.complete_with_usage(
            _JUDGE_SYSTEM_PROMPT,
            _build_judge_prompt(family, candidate_payload),
            temperature=0.0,
            telemetry_context={
                **dict(telemetry_context or {}),
                "operation": "quality.judge",
                "quality_family": family,
                "quality_shadow_mode": bool(settings.quality_judge_shadow_mode),
            },
        )
        raw_payload = _parse_json_text(raw_text)
        if not isinstance(raw_payload, Mapping):
            raise ValueError("Judge did not return a JSON object")
        return _normalize_judge_result(
            family,
            raw_payload,
            shadow_mode=bool(settings.quality_judge_shadow_mode),
            usage=usage,
        )
    except Exception as exc:
        logger.warning("Quality judge failed family=%s provider=%s model=%s error=%s", family, judge_provider, judge_model or "(default)", exc)
        return JudgeResult(
            family=family,
            label=_JUDGE_RUBRICS[family]["label"],
            enabled=True,
            skipped=True,
            shadow_mode=bool(settings.quality_judge_shadow_mode),
            passed=True,
            overall_score=0.0,
            summary="Judge failed and was bypassed to preserve the primary generation flow.",
            error=str(exc),
        )


async def run_quality_guarded_generation(
    *,
    family: PromptFamily,
    provider: str,
    model: str | None,
    api_key: str,
    base_url: str,
    generate_candidate: Callable[[str, int], Awaitable[tuple[Any, dict[str, Any]]]],
    candidate_payload_builder: Callable[[Any], Any] | None = None,
    telemetry_context: Mapping[str, Any] | None = None,
) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    enabled = is_quality_layer_enabled_for_family(family)
    profile = get_compiled_dspy_profile(family) if enabled and settings.quality_dspy_enabled else None
    judge_enabled = enabled and bool(settings.quality_judge_enabled)
    shadow_mode = enabled and bool(settings.quality_judge_shadow_mode)
    feedback_enabled = (
        enabled
        and judge_enabled
        and bool(settings.quality_feedback_loop_enabled)
        and not shadow_mode
    )
    max_attempts = 1 + max(0, _coerce_int(settings.quality_feedback_max_retries, default=1)) if feedback_enabled else 1

    quality_run = QualityRunResult(
        family=family,
        enabled=enabled,
        dspy_enabled=bool(enabled and settings.quality_dspy_enabled and profile),
        judge_enabled=judge_enabled,
        shadow_mode=shadow_mode,
        feedback_enabled=feedback_enabled,
        profile_version=profile.version if profile else "",
    )

    if not enabled:
        candidate, usage = await generate_candidate("", 1)
        quality_run.attempts.append(
            QualityAttempt(
                attempt=1,
                prompt_suffix_applied=False,
                feedback_applied=False,
                feedback_instruction="",
                generation_usage=dict(usage or {}),
            )
        )
        return candidate, usage, quality_run.to_dict()

    feedback_instruction = ""
    last_successful_candidate: Any | None = None
    last_successful_usage: dict[str, Any] = {}

    for attempt in range(1, max_attempts + 1):
        prompt_suffix = _build_prompt_suffix(
            family,
            profile=profile,
            feedback_instruction=feedback_instruction,
        )
        try:
            candidate, usage = await generate_candidate(prompt_suffix, attempt)
        except Exception as exc:
            if last_successful_candidate is None:
                raise
            quality_run.warnings.append(
                f"attempt {attempt} generation failed after an earlier successful candidate: {exc}"
            )
            break

        last_successful_candidate = candidate
        last_successful_usage = dict(usage or {})

        judge_result: JudgeResult | None = None
        if judge_enabled:
            judge_result = await run_quality_judge(
                family=family,
                candidate_payload=(
                    candidate_payload_builder(candidate)
                    if callable(candidate_payload_builder)
                    else candidate
                ),
                provider=provider,
                model=model,
                api_key=api_key,
                base_url=base_url,
                telemetry_context={
                    **dict(telemetry_context or {}),
                    "quality_family": family,
                    "quality_attempt": attempt,
                },
            )

        quality_run.attempts.append(
            QualityAttempt(
                attempt=attempt,
                prompt_suffix_applied=bool(prompt_suffix),
                feedback_applied=bool(feedback_instruction),
                feedback_instruction=feedback_instruction,
                generation_usage=dict(usage or {}),
                judge=judge_result.to_dict() if judge_result is not None else None,
            )
        )

        if judge_result is None or judge_result.skipped or judge_result.passed or shadow_mode or not feedback_enabled:
            quality_run.final_passed = judge_result.passed if judge_result is not None else True
            quality_run.final_attempt = attempt
            break

        feedback_instruction = "\n".join(judge_result.feedback_instructions).strip()
        quality_run.final_passed = False
        quality_run.final_attempt = attempt
        if not feedback_instruction:
            quality_run.warnings.append(
                f"attempt {attempt} judge failed candidate but returned no usable feedback instructions"
            )
            break

    return last_successful_candidate, last_successful_usage, quality_run.to_dict()


async def run_quality_guarded_runtime_payload(
    *,
    provider: str,
    model: str | None,
    api_key: str,
    base_url: str,
    base_payload_builder: Callable[[], Mapping[str, Any]],
    telemetry_context: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    async def _generate_candidate(prompt_suffix: str, _attempt: int) -> tuple[dict[str, Any], dict[str, Any]]:
        base_payload = dict(base_payload_builder() or {})
        candidate = _overlay_generation_payload(base_payload, prompt_suffix)
        overlay_text = str(prompt_suffix or "").strip()
        return candidate, {
            "overlay_applied": bool(overlay_text),
            "overlay_chars": len(overlay_text),
            "overlay_text": overlay_text,
        }

    payload, _, quality = await run_quality_guarded_generation(
        family="generation_payload",
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        generate_candidate=_generate_candidate,
        candidate_payload_builder=_generation_payload_judge_payload,
        telemetry_context=telemetry_context,
    )
    return dict(payload or {}), quality


async def run_quality_guarded_prompt_payload(
    *,
    family: Literal["scene_reference_prompt", "character_design_prompt"],
    provider: str,
    model: str | None,
    api_key: str,
    base_url: str,
    base_payload_builder: Callable[[], Mapping[str, Any]],
    prompt_key: str = "prompt",
    telemetry_context: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    async def _generate_candidate(prompt_suffix: str, _attempt: int) -> tuple[dict[str, Any], dict[str, Any]]:
        base_payload = dict(base_payload_builder() or {})
        candidate = _overlay_prompt_payload(base_payload, prompt_suffix, prompt_key=prompt_key)
        overlay_text = str(prompt_suffix or "").strip()
        return candidate, {
            "overlay_applied": bool(overlay_text),
            "overlay_chars": len(overlay_text),
            "overlay_text": overlay_text,
        }

    payload, _, quality = await run_quality_guarded_generation(
        family=family,
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        generate_candidate=_generate_candidate,
        candidate_payload_builder=lambda candidate: dict(candidate or {}),
        telemetry_context=telemetry_context,
    )
    return dict(payload or {}), quality
