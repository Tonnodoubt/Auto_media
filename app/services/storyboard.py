import json
import re
from typing import List, Optional

from app.services.llm.factory import get_llm_provider
from app.schemas.storyboard import Shot
from app.prompts.storyboard import SYSTEM_PROMPT, USER_TEMPLATE
from app.prompts.character import build_character_section


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
        shots.append(Shot(**item))
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
