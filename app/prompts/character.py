
# -*- coding: utf-8 -*-
"""
角色视觉相关提示词与构建函数（Step 2.5 / Step 5）
"""
from typing import Optional


# ============================================================================
# 角色设计图 prompt 构建
# ============================================================================

def build_character_prompt(name: str, role: str, description: str) -> str:
    """构建角色设计图生成 prompt（含 role 自动映射）。"""
    role = role or ""
    description = description or ""
    role_lower = role.lower()
    if any(k in role_lower for k in ("反派", "villain", "antagonist", "boss")):
        role_cue = "villain, sinister expression, dark presence"
    elif any(k in role_lower for k in ("主角", "protagonist", "hero", "主人公")):
        role_cue = "protagonist, determined expression, heroic bearing"
    elif any(k in role_lower for k in ("配角", "supporting", "助手", "sidekick")):
        role_cue = "supporting character, approachable expression"
    else:
        role_cue = f"{role}"
    return (
        f"Character portrait of {name}, {role_cue}, "
        f"character description: {description}, "
        "unique individual character design, distinctive appearance, "
        "cinematic portrait, highly detailed, professional character concept art, "
        "clean background, studio lighting, 8k resolution, photorealistic"
    )


# ============================================================================
# 分镜角色参考信息块构建
# ============================================================================

def build_character_section(character_info: Optional[dict]) -> str:
    """构建传给分镜 LLM 的角色参考信息块。"""
    if not character_info:
        return ""
    characters = character_info.get("characters", [])
    character_images = character_info.get("character_images", {})
    if not characters:
        return ""

    lines = ["## Character Reference (maintain consistency across all shots)"]
    for c in characters:
        name = c.get("name", "")
        role = c.get("role", "")
        desc = c.get("description", "")
        lines.append(f"- **{name}**（{role}）：{desc}")
        portrait = (
            character_images.get(name, {}).get("portrait_prompt")
            or character_images.get(name, {}).get("prompt", "")
        ) if isinstance(character_images, dict) else ""
        if portrait:
            lines.append(f"  Portrait prompt: {portrait}")
    return "\n".join(lines)
