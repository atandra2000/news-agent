"""Role-routed LLM router with cross-provider fallback + token counter.

Cost safety via a token counter so the agent stays alive (NEWSAGENT_DESIGN §11.2).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from newsagent.errors import LLMError
from newsagent.llm.providers.base import ProviderResult
from newsagent.llm.providers.registry import ModelRegistry
from newsagent.llm.roles import get_role, get_role_for_provider

log = structlog.get_logger("llm.router")


@dataclass
class RouterStats:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0
    failures: int = 0
    by_provider: dict[str, int] = field(default_factory=dict)
    cost_per_1k_tokens: float = 0.0  # USD per 1k tokens
    # Per-role token accounting.
    by_role: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def estimated_cost_usd(self) -> float:
        """Estimated cost in USD."""
        return (self.total_tokens / 1000.0) * self.cost_per_1k_tokens

    def role_stats(self, role: str) -> dict[str, int]:
        return self.by_role.setdefault(role, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0})


class LLMRouter:
    """Complete a prompt for a role, walking the fallback chain across providers."""

    def __init__(
        self,
        registry: ModelRegistry,
        token_budget: int = 2_000_000,
        allow_heuristic_fallback: bool = True,
        timeout: float = 120.0,
        cost_per_1k_tokens: float = 0.0,
        prompt_cache: bool = True,
    ):
        self.registry = registry
        self.token_budget = token_budget
        self.allow_heuristic_fallback = allow_heuristic_fallback
        self.timeout = timeout
        self.stats = RouterStats(cost_per_1k_tokens=cost_per_1k_tokens)
        self.prompt_cache = prompt_cache

    async def complete(
        self,
        role: str,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        num_ctx: int | None = None,
        keep_alive: str | None = None,
        format: str | None = None,
        cache: bool | None = None,
    ) -> ProviderResult:
        # Provider-specific role spec when not on Ollama.
        if self.registry.default != "ollama":
            spec = get_role_for_provider(role, self.registry.default)
        else:
            spec = get_role(role)
        temp = temperature if temperature is not None else spec.temperature
        mtok = max_tokens if max_tokens is not None else spec.max_tokens
        n_ctx = num_ctx if num_ctx is not None else spec.num_ctx
        k_alive = keep_alive if keep_alive is not None else spec.keep_alive
        # Router-wide cache default; callers may override per call.
        use_cache = self.prompt_cache if cache is None else cache

        if self.stats.total_tokens > self.token_budget:
            raise LLMError(f"Token budget {self.token_budget} exceeded; halting generation.")

        last_err: Exception | None = None
        for model in spec.chain:
            provider = self.registry.provider_for(model)
            real_model = self.registry.model_name(model)
            try:
                result = await provider.complete(
                    real_model,
                    prompt,
                    system=system,
                    temperature=temp,
                    max_tokens=mtok,
                    timeout=self.timeout,
                    num_ctx=n_ctx,
                    keep_alive=k_alive,
                    format=format,
                    cache=use_cache,
                )
                self._account(result, role)
                if not result.text.strip():
                    raise LLMError("Empty completion")
                return result
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                self.stats.failures += 1
                log.warning("llm.call_failed", role=role, model=model, error=str(exc))
                continue

        if self.allow_heuristic_fallback:
            log.warning("llm.all_providers_failed", role=role, fallback="heuristic")
            return ProviderResult(text="", model="heuristic", provider="heuristic")
        raise LLMError(f"All providers failed for role={role}: {last_err}")

    def _account(self, result: ProviderResult, role: str = "unknown") -> None:
        self.stats.calls += 1
        self.stats.prompt_tokens += result.prompt_tokens
        self.stats.completion_tokens += result.completion_tokens
        self.stats.by_provider[result.provider] = self.stats.by_provider.get(result.provider, 0) + 1
        rs = self.stats.role_stats(role)
        rs["calls"] += 1
        rs["prompt_tokens"] += result.prompt_tokens
        rs["completion_tokens"] += result.completion_tokens

    async def json_complete(self, role: str, prompt: str, *, system: str | None = None, cache: bool | None = None) -> dict:
        """Complete and parse a JSON object. Returns {} on failure / fallback."""
        result = await self.complete(role, prompt, system=system, format="json", cache=cache)
        if result.provider == "heuristic" or not result.text.strip():
            return {}
        import json

        text = result.text
        # Strip markdown code fences if present.
        if "```" in text:
            text = text.split("```", 2)[1]
            if text.startswith("json"):
                text = text[4:]
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            # Fall back to the first {...} span.
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    return {}
            return {}
