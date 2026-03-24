# -*- coding: utf-8 -*-
"""
提示词统一导出入口。

用法：
    from app.prompts import ANALYZE_PROMPT, OUTLINE_PROMPT, ...
    from app.prompts import build_character_prompt, build_character_section
"""

from app.prompts.story import (
    ANALYZE_PROMPT,
    WB_SYSTEM_PROMPT,
    WB_USER_TEMPLATE,
    OUTLINE_PROMPT,
    SCRIPT_PROMPT,
    REFINE_PROMPT,
    build_apply_chat_prompt,
)

from app.prompts.storyboard import (
    SYSTEM_PROMPT as STORYBOARD_SYSTEM_PROMPT,
    USER_TEMPLATE as STORYBOARD_USER_TEMPLATE,
)

from app.prompts.character import (
    build_character_prompt,
    build_character_section,
)

__all__ = [
    # story
    "ANALYZE_PROMPT",
    "WB_SYSTEM_PROMPT",
    "WB_USER_TEMPLATE",
    "OUTLINE_PROMPT",
    "SCRIPT_PROMPT",
    "REFINE_PROMPT",
    "build_apply_chat_prompt",
    # storyboard
    "STORYBOARD_SYSTEM_PROMPT",
    "STORYBOARD_USER_TEMPLATE",
    # character
    "build_character_prompt",
    "build_character_section",
]
