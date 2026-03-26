
# -*- coding: utf-8 -*-
"""
角色视觉相关提示词与构建函数（Step 2.5 / Step 5）
"""
from typing import Optional

from app.core.story_context import build_character_reference_anchor


# ============================================================================
# 角色设计图 prompt 构建
# ============================================================================

def build_character_prompt(name: str, role: str, description: str, art_style: str = "") -> str:
    """构建标准三视图角色设定图 prompt。"""
    role = role or ""
    description = description or ""
    art_style = (art_style or "").strip()
    role_lower = role.lower()
    if any(k in role_lower for k in ("反派", "villain", "antagonist", "boss")):
        role_cue = "villain, sinister expression, dark presence"
    elif any(k in role_lower for k in ("主角", "protagonist", "hero", "主人公")):
        role_cue = "protagonist, determined expression, heroic bearing"
    elif any(k in role_lower for k in ("配角", "supporting", "助手", "sidekick")):
        role_cue = "supporting character, approachable expression"
    else:
        role_cue = f"{role}"
    identity_lock = (
        "treat the character description as non-negotiable identity constraints; "
        "keep the same apparent age, face shape, facial features, hairstyle, hair color, body build, "
        "skin tone, costume silhouette, costume colors, fabric material, and accessory placement in all three views, "
        "do not redesign the face into a generic beauty look, do not change hairstyle, do not swap costume colors or materials, "
        "do not add extra jewelry, extra armor, extra props, or extra costume layers not mentioned in the description"
    )
    style_lock = (
        f"style lock: {art_style}, "
        "follow this exact art style consistently across all three views, "
        "keep the same medium language, linework or brushwork, rendering method, color palette, shading logic, "
        "surface texture treatment, and lighting language in every panel, "
        if art_style else
        "keep one unified rendering style across all three views, avoid mixed media or style drift, "
    )
    return (
        f"Standard three-view character turnaround sheet for {name}, {role_cue}, "
        f"character description: {description}, "
        f"{identity_lock}, "
        f"{style_lock}"
        "show front view, side profile, and back view of the same character on one sheet, "
        "full body in all three views, head-to-toe visible in every view, feet fully visible, "
        "neutral standing pose, centered composition, clear silhouette, no cropping, no close-up framing, "
        "consistent facial features, hairstyle, body proportions, and costume details across views, "
        "if carrying accessories or bags, keep the same item design and the same wearing position across all three views, "
        "clean neutral studio backdrop, plain background, no environmental props, no unrelated objects, "
        "no floating elements, no foreground obstruction, no blocking objects, no decorative frame, "
        "no text, no captions, no labels, no watermark, no logo, "
        "production-ready character turnaround sheet, costume construction details, fabric texture, "
        "highly detailed character concept sheet"
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
        char_id = c.get("id", "")
        name = c.get("name", "")
        role = c.get("role", "")
        desc = c.get("description", "")
        lines.append(f"- **{name}**（{role}）：{desc}")
        visual_anchor = build_character_reference_anchor(
            character_images,
            name,
            character_id=char_id,
            description=desc,
        )
        if visual_anchor:
            lines.append(f"  Visual DNA: {visual_anchor}")
    return "\n".join(lines)
