"""OpenCode Go provider — cloud-hosted models via the OpenCode API."""

from __future__ import annotations

import httpx

from hermes.llm.providers.base import BaseProvider, ProviderResult


class OpenCodeGoProvider(BaseProvider):
    name = "opencode_go"

    def __init__(
        self,
        base_url: str = "https://api.opencode.ai/v1",
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
            # Best-effort prompt caching (see OpenAICompatibleProvider for rationale).
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
        # OpenCode Go JSON output via response_format.
        if format == "json":
            payload["response_format"] = {"type": "json_object"}
        # num_ctx/keep_alive are Ollama-only; OpenCode Go uses the model's native context.
        to = timeout or self.timeout
        async with httpx.AsyncClient(timeout=to) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions", json=payload, headers=self._headers()
            )
            resp.raise_for_status()
            try:
                data = resp.json()
            except Exception as json_err:
                body_preview = resp.text[:500] if resp.text else "<empty>"
                raise RuntimeError(
                    f"OpenCode Go returned non-JSON response (status={resp.status_code}): {body_preview}"
                ) from json_err
        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        # Reasoning models (deepseek-v4-pro, kimi-k2.6, glm-5.2) may exhaust
        # the token budget on ``reasoning_content`` and leave ``content`` empty.
        # Fall back to it for TEXT completions so the router's empty-completion
        # guard doesn't drop them. For JSON requests (``response_format=json_object``)
        # ``reasoning_content`` is chain-of-thought prose, NEVER a JSON object —
        # returning it would feed garbage to ``json.loads`` (and a brace-scraped
        # dict could pass as a bogus critic verdict). Return empty instead so the
        # router raises "Empty completion", falls over to the next model in the
        # chain, and the critic cleanly no-ops rather than rubber-stamping on a
        # bogus parsed dict. Root cause of the 2026-07-13 critic no-op (every
        # section scored the 0.7 fallback default → fabrication survived uncited).
        if not text and format != "json":
            reasoning = data.get("choices", [{}])[0].get("message", {}).get("reasoning_content", "")
            text = reasoning or ""
        usage = data.get("usage", {})
        return ProviderResult(
            text=text or "",
            model=model,
            provider=self.name,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )

    async def available(self) -> bool:
        """Reachability check."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # No /models endpoint; just probe connectivity.
                resp = await client.get(f"{self.base_url}/models", headers=self._headers())
                return 200 <= resp.status_code < 500
        except Exception:
            return False

    async def list_models(self) -> list[dict]:
        """List available models from OpenCode Go."""
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(f"{self.base_url}/models", headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
        return data.get("data", [])
