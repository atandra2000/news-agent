"""LLM provider plugin contract. ``complete`` returns text + usage."""

from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderResult:
    text: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class BaseProvider(abc.ABC):
    """A concrete LLM backend (Ollama / OpenAI / Anthropic / ...)."""

    name: str = "base"

    @abc.abstractmethod
    async def complete(
        self,
        model: str,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        timeout: float = 120.0,
        num_ctx: int | None = None,
        keep_alive: str | None = None,
        format: str | None = None,
        cache: bool = False,
    ) -> ProviderResult: ...
