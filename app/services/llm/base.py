from __future__ import annotations

import logging

from abc import ABC, abstractmethod
from typing import Any, Iterable, Optional, Tuple


logger = logging.getLogger(__name__)


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                chunks.append(str(item.get("text", "")))
            else:
                chunks.append(str(item))
        return "\n".join(chunk for chunk in chunks if chunk)
    return str(content)


def estimate_tokens(payload: str | dict[str, Any] | Iterable[dict[str, Any]]) -> int:
    if isinstance(payload, str):
        normalized = payload.strip()
        return max(1, len(normalized) // 2) if normalized else 0
    if isinstance(payload, dict):
        return estimate_tokens(_message_text(payload))
    return sum(estimate_tokens(item) for item in payload)


class BaseLLMProvider(ABC):
    """Abstract base for all LLM providers."""

    @abstractmethod
    async def complete(self, system: str, user: str, temperature: float = 0.3) -> str:
        """Send a prompt and return the text response."""
        ...

    @abstractmethod
    async def complete_with_usage(
        self, system: str, user: str, temperature: float = 0.3
    ) -> Tuple[str, dict]:
        """
        Send a prompt and return both text response and usage information.

        Returns:
            Tuple[str, dict]: (text_response, {"prompt_tokens": int, "completion_tokens": int})
        """
        ...

    async def complete_messages(
        self,
        messages: list[dict[str, Any]],
        system: str = "",
        temperature: float = 0.3,
        enable_caching: bool = False,
        cache_key: str = "",
        cache_threshold_tokens: int = 1024,
    ) -> str:
        text, _ = await self.complete_messages_with_usage(
            messages=messages,
            system=system,
            temperature=temperature,
            enable_caching=enable_caching,
            cache_key=cache_key,
            cache_threshold_tokens=cache_threshold_tokens,
        )
        return text

    async def complete_messages_with_usage(
        self,
        messages: list[dict[str, Any]],
        system: str = "",
        temperature: float = 0.3,
        enable_caching: bool = False,
        cache_key: str = "",
        cache_threshold_tokens: int = 1024,
    ) -> Tuple[str, dict]:
        del enable_caching, cache_key, cache_threshold_tokens
        if not messages:
            message = (
                "BaseLLMProvider.complete_messages_with_usage requires at least one message; "
                "refusing to call complete_with_usage with an empty user prompt."
            )
            logger.warning(message)
            raise ValueError(message)

        if len(messages) == 1 and messages[0].get("role") == "user":
            user = _message_text(messages[0])
        else:
            user = "\n\n".join(
                f"[{str(message.get('role', 'user')).upper()}]\n{_message_text(message)}"
                for message in messages
                if _message_text(message)
            )
        return await self.complete_with_usage(system, user, temperature)
