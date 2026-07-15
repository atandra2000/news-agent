"""Ollama provider — local server or Ollama Pro (hosted) via API key.

Auth: ``Authorization: Bearer <key>`` when ``api_key`` is set. Default base URL is
the Ollama Pro hosted endpoint. Uses the **chat** endpoint (``/api/chat``); the
legacy ``/api/generate`` endpoint is an automatic fallback if chat is unavailable.
"""

from __future__ import annotations

import httpx

from newsagent.llm.providers.base import BaseProvider, ProviderResult


class OllamaProvider(BaseProvider):
    name = "ollama"

    def __init__(
        self,
        base_url: str = "https://api.ollama.com",
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

    def _chat_payload(
        self,
        model: str,
        prompt: str,
        *,
        system: str | None,
        temperature: float,
        max_tokens: int,
        num_ctx: int | None,
        keep_alive: str | None,
        format: str | None,
        cache: bool = False,
    ) -> dict:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        options: dict = {"temperature": temperature, "num_predict": max_tokens}
        if num_ctx is not None:
            options["num_ctx"] = num_ctx
        # Prompt caching reuses the KV cache for identical prompt prefixes — the
        # biggest token saver for many small repeated-prefix calls. Needs keep_alive
        # so the model + cache stay resident.
        if cache and keep_alive is not None:
            options["cache_prompt"] = True
        payload: dict = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": options,
        }
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive
        if format is not None:
            payload["format"] = format
        return payload

    def _generate_payload(
        self,
        model: str,
        prompt: str,
        *,
        system: str | None,
        temperature: float,
        max_tokens: int,
        num_ctx: int | None,
        keep_alive: str | None,
        format: str | None,
        cache: bool = False,
    ) -> dict:
        payload: dict = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if system:
            payload["system"] = system
        if num_ctx is not None:
            payload["options"]["num_ctx"] = num_ctx
        if cache and keep_alive is not None:
            payload["options"]["cache_prompt"] = True
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive
        if format is not None:
            payload["format"] = format
        return payload

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
        to = timeout or self.timeout
        chat_payload = self._chat_payload(
            model,
            prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            num_ctx=num_ctx,
            keep_alive=keep_alive,
            format=format,
            cache=cache,
        )
        async with httpx.AsyncClient(timeout=to) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/api/chat", json=chat_payload, headers=self._headers()
                )
                resp.raise_for_status()
                data = resp.json()
                msg = data.get("message", {})
                text = msg.get("content", "")
                # Reasoning models may exhaust tokens on ``reasoning_content``
                # and leave ``content`` empty — fall back to avoid a false empty.
                if not text:
                    text = msg.get("reasoning_content", "") or ""
                return ProviderResult(
                    text=text,
                    model=model,
                    provider=self.name,
                    prompt_tokens=data.get("prompt_eval_count", 0),
                    completion_tokens=data.get("eval_count", 0),
                )
            except Exception:
                # Fallback to the legacy generate endpoint (local servers, older API).
                gen_payload = self._generate_payload(
                    model,
                    prompt,
                    system=system,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    num_ctx=num_ctx,
                    keep_alive=keep_alive,
                    format=format,
                    cache=cache,
                )
                resp = await client.post(
                    f"{self.base_url}/api/generate", json=gen_payload, headers=self._headers()
                )
                resp.raise_for_status()
                data = resp.json()
                return ProviderResult(
                    text=data.get("response", ""),
                    model=model,
                    provider=self.name,
                    prompt_tokens=data.get("prompt_eval_count", 0),
                    completion_tokens=data.get("eval_count", 0),
                )

    async def list_models(self) -> list[dict]:
        """Return the raw ``/api/tags`` model list (used by ``newsagent models``)."""
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(f"{self.base_url}/api/tags", headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
        return data.get("models", [])
