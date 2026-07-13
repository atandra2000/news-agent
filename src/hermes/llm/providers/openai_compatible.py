"""OpenAI-compatible provider (e.g. OpenCode Zen, OpenRouter, local vLLM).

Targets any OpenAI-compatible ``/chat/completions`` endpoint; used as a free
backend when Ollama Pro quota is exhausted.
"""

from __future__ import annotations

import httpx

from hermes.llm.providers.base import BaseProvider, ProviderResult


class OpenAICompatibleProvider(BaseProvider):
    name = "openai"

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: float = 120.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    async def complete(
        self,
        model: str,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        timeout: float | None = None,
        num_ctx: int | None = None,
        keep_alive: str | None = None,
        format: str | None = None,
        cache: bool = False,
    ) -> ProviderResult:
        messages = []
        if system:
            # Best-effort prompt caching via ephemeral cache_control; servers that
            # don't support it just ignore the extra field (safe across backends).
            if cache:
                messages.append(
                    {
                        "role": "system",
                        "content": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                )
            else:
                messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        # OpenAI JSON mode; num_ctx/keep_alive are Ollama-only and ignored here.
        if format == "json":
            payload["response_format"] = {"type": "json_object"}
        to = timeout or self.timeout
        async with httpx.AsyncClient(timeout=to) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions", json=payload, headers=self._headers()
            )
            resp.raise_for_status()
            data = resp.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return ProviderResult(
            text=text or "",
            model=model,
            provider=self.name,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )
