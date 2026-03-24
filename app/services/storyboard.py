import json
import re
from typing import List, Optional

from app.services.llm.factory import get_llm_provider
from app.schemas.storyboard import Shot
from app.prompts.storyboard import SYSTEM_PROMPT, USER_TEMPLATE
from app.prompts.character import build_character_section


def _parse_shots(raw: str) -> List[Shot]:
    cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
    data = json.loads(cleaned)
    return [Shot(**item) for item in data]


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
        provider: LLM provider name (claude, openai, qwen, zhipu, gemini)
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
