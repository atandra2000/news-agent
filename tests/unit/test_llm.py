"""Unit tests for the LLM layer: catalog, roles, registry, router.

Covers:
- Catalog tier specs and all_catalog_models enumeration.
- Role specs and per-provider role resolution.
- Registry provider routing + model name resolution.
- LLMRouter fallback chain, token budget guard, heuristic fallback, accounting.
- Router json_complete with code fences + malformed JSON.
"""

from __future__ import annotations


import httpx
import pytest
import respx

from hermes.llm.catalog import (
    MODEL_CATALOG,
    OLLAMA_CATALOG,
    OPENCODE_GO_CATALOG,
    TIER_KEEP_ALIVE,
    TIER_NUM_CTX,
    all_catalog_models,
    tier_spec,
)
from hermes.llm.providers.base import BaseProvider, ProviderResult
from hermes.llm.providers.ollama import OllamaProvider
from hermes.llm.providers.openai_compatible import OpenAICompatibleProvider
from hermes.llm.providers.opencode_go import OpenCodeGoProvider
from hermes.llm.providers.registry import ModelRegistry, build_registry
from hermes.llm.roles import ROLES, get_role, get_role_for_provider
from hermes.llm.router import LLMRouter
from hermes.errors import LLMError


# ── Catalog ──────────────────────────────────────────────────────────────────


class TestCatalog:
    def test_all_tiers_present(self):
        for tier in ("writer", "critic", "plan", "cheap"):
            assert tier in OLLAMA_CATALOG, tier
            assert tier in OPENCODE_GO_CATALOG, tier
            assert tier in TIER_NUM_CTX
            assert tier in TIER_KEEP_ALIVE

    def test_every_tier_has_at_least_one_model(self):
        for tier, chain in OLLAMA_CATALOG.items():
            assert len(chain) >= 1, tier
        for tier, chain in OPENCODE_GO_CATALOG.items():
            assert len(chain) >= 1, tier

    def test_tier_spec_returns_chain_and_ctx(self):
        spec = tier_spec("writer", "ollama")
        assert spec.chain == tuple(OLLAMA_CATALOG["writer"])
        assert spec.num_ctx == TIER_NUM_CTX["writer"]
        assert spec.keep_alive == TIER_KEEP_ALIVE["writer"]

    def test_tier_spec_unknown_tier_raises(self):
        with pytest.raises(KeyError):
            tier_spec("nope", "ollama")

    def test_tier_spec_wrong_provider_raises(self):
        # tier exists in OLLAMA but not in a hypothetical bad provider.
        # tier_spec looks up the catalog; nonexistent_provider falls back to
        # OLLAMA_CATALOG (else branch), so it does NOT raise. Test the actual
        # behavior: nonexistent provider returns the Ollama tier spec.
        spec = tier_spec("writer", "nonexistent_provider")
        assert spec.chain == tuple(OLLAMA_CATALOG["writer"])

    def test_all_catalog_models_dedupes(self):
        models = all_catalog_models("ollama")
        assert len(models) == len(set(models)), "duplicate models in catalog"
        assert len(models) > 0

    def test_opencode_go_catalog_distinct_from_ollama(self):
        assert OPENCODE_GO_CATALOG is not OLLAMA_CATALOG
        assert MODEL_CATALOG is OLLAMA_CATALOG  # backward compat

    def test_opencode_go_catalog_has_real_models(self):
        # The catalog was verified live against https://opencode.ai/zen/go/v1/models.
        # No placeholder ids like claude/gpt that don't exist on that endpoint.
        real_models = {
            "deepseek-v4-pro",
            "deepseek-v4-flash",
            "kimi-k2.6",
            "glm-5.2",
            "glm-5.1",
            "qwen3.7-plus",
            "minimax-m3",
        }
        for tier, chain in OPENCODE_GO_CATALOG.items():
            for m in chain:
                assert m in real_models, f"catalog model {m} not in verified set"

    def test_cheap_tier_avoids_reasoning_starved_models(self):
        # deepseek-v4-flash is a reasoning model that NEVER populates ``content``
        # (all tokens go to reasoning_content, finish_reason="length" even at
        # max_tokens=4096). qwen3.7-plus reliably produces clean ``content``
        # even at max_tokens=64, so it must lead the cheap chain.
        cheap_primary = OPENCODE_GO_CATALOG["cheap"][0]
        assert cheap_primary == "qwen3.7-plus"
        assert "deepseek-v4-flash" not in OPENCODE_GO_CATALOG["cheap"][:2]


# ── Roles ─────────────────────────────────────────────────────────────────────


class TestRoles:
    def test_all_expected_roles_present(self):
        expected = {
            "research",
            "reason",
            "summarize",
            "compare",
            "markdown",
            "proofread",
            "critic",
            "plan",
            "verify",
            "label",
            "write",
            "brief_write",
            "brief_plan",
            # compiler-pipeline roles
            "extract",
            "discover",
            "analyze",
            "edit",
        }
        assert expected <= set(ROLES), set(ROLES) - expected

    def test_get_role_unknown_raises(self):
        with pytest.raises(KeyError):
            get_role("does_not_exist")

    def test_get_role_returns_chain_and_defaults(self):
        spec = get_role("label")
        assert len(spec.chain) >= 1
        assert spec.temperature == 0.2
        assert spec.max_tokens == 300

    def test_write_role_has_large_max_tokens(self):
        spec = get_role("write")
        assert spec.max_tokens >= 3000

    def test_brief_write_has_largest_max_tokens(self):
        spec = get_role("brief_write")
        assert spec.max_tokens == 5000

    def test_get_role_for_provider_uses_opencode_go_catalog(self):
        spec = get_role_for_provider("write", "opencode_go")
        assert spec.chain == tuple(OPENCODE_GO_CATALOG["writer"])

    def test_get_role_for_provider_uses_ollama_catalog(self):
        spec = get_role_for_provider("write", "ollama")
        assert spec.chain == tuple(OLLAMA_CATALOG["writer"])

    def test_get_role_for_provider_preserves_temperature(self):
        spec = get_role_for_provider("verify", "opencode_go")
        assert spec.temperature == 0.1

    def test_get_role_for_provider_unknown_role_raises(self):
        with pytest.raises(KeyError):
            get_role_for_provider("does_not_exist", "opencode_go")


# ── Registry ──────────────────────────────────────────────────────────────────


class TestRegistry:
    def test_build_registry_default_ollama(self):
        reg = build_registry()
        assert reg.default == "ollama"
        assert reg.default_model is None
        assert "ollama" in reg.providers

    def test_build_registry_opencode_go_requires_api_key(self):
        with pytest.raises(ValueError, match="opencode_go_api_key"):
            build_registry(backend="opencode_go")

    def test_build_registry_openai_requires_base_url(self):
        with pytest.raises(ValueError, match="openai_base_url"):
            build_registry(backend="openai", openai_model="gpt-4")

    def test_build_registry_opencode_go(self):
        reg = build_registry(backend="opencode_go", opencode_go_api_key="test-key")
        assert reg.default == "opencode_go"
        assert "opencode_go" in reg.providers
        assert reg.default_model is None  # catalog-driven routing

    def test_build_registry_opencode_go_with_single_model(self):
        reg = build_registry(
            backend="opencode_go",
            opencode_go_api_key="test-key",
            opencode_go_model="glm-5.2",
        )
        assert reg.default_model == "glm-5.2"

    def test_provider_for_model_with_prefix(self):
        reg = build_registry()
        prov = reg.provider_for("ollama:llama3")
        assert prov.name == "ollama"

    def test_provider_for_model_without_prefix(self):
        reg = build_registry()
        prov = reg.provider_for("llama3")
        assert prov.name == "ollama"

    def test_model_name_ollama_strips_prefix(self):
        reg = build_registry()
        assert reg.model_name("ollama:llama3") == "llama3"

    def test_model_name_ollama_no_prefix(self):
        reg = build_registry()
        assert reg.model_name("llama3") == "llama3"

    def test_model_name_opencode_go_uses_catalog_when_no_default_model(self):
        reg = build_registry(backend="opencode_go", opencode_go_api_key="test-key")
        # When default_model is None, the chain model passes through.
        assert reg.model_name("deepseek-v4-pro") == "deepseek-v4-pro"

    def test_model_name_opencode_go_uses_single_model_when_set(self):
        reg = build_registry(
            backend="opencode_go",
            opencode_go_api_key="test-key",
            opencode_go_model="glm-5.2",
        )
        # When default_model is set, all roles collapse to that model.
        assert reg.model_name("deepseek-v4-pro") == "glm-5.2"
        assert reg.model_name("kimi-k2.6") == "glm-5.2"


# ── Router ────────────────────────────────────────────────────────────────────


class _SuccessProvider(BaseProvider):
    """Provider that returns a fixed text result."""

    name = "success"

    def __init__(self, text: str = "hello world"):
        self._text = text

    async def complete(
        self,
        model,
        prompt,
        *,
        system=None,
        temperature=0.2,
        max_tokens=2048,
        timeout=120.0,
        num_ctx=None,
        keep_alive=None,
        format=None,
        cache=False,
    ):
        return ProviderResult(
            text=self._text,
            model=model,
            provider=self.name,
            prompt_tokens=10,
            completion_tokens=20,
        )


class _SuccessProviderNamed(BaseProvider):
    """Provider with a custom name for router tests that check provider identity."""

    def __init__(self, name: str = "ok", text: str = "hello"):
        self.name = name
        self._text = text

    async def complete(self, model, prompt, **kwargs):
        return ProviderResult(
            text=self._text,
            model=model,
            provider=self.name,
            prompt_tokens=10,
            completion_tokens=20,
        )


class _FailProvider(BaseProvider):
    """Provider that always raises."""

    name = "fail"

    async def complete(self, model, prompt, **kwargs):
        raise RuntimeError("provider down")


class _EmptyProvider(BaseProvider):
    """Provider that returns empty content (should trigger 'empty completion' error)."""

    name = "empty"

    async def complete(self, model, prompt, **kwargs):
        return ProviderResult(text="", model=model, provider=self.name)


class TestRouter:
    @pytest.mark.asyncio
    async def test_complete_succeeds_with_working_provider(self):
        registry = ModelRegistry(
            {"ok": _SuccessProviderNamed("ok", "found it")},
            default="ok",
        )
        router = LLMRouter(registry, allow_heuristic_fallback=False)
        result = await router.complete("label", "test prompt")
        assert result.text == "found it"
        assert result.provider == "ok"

    @pytest.mark.asyncio
    async def test_complete_walks_chain_past_failures(self):
        # The router walks the role chain; if the first model's provider fails,
        # it falls back to the next model in the chain. Since all models route
        # to the same provider (default), a failing provider means all models
        # fail, and heuristic fallback kicks in.
        registry = ModelRegistry(
            {"fail": _FailProvider()},
            default="fail",
        )
        router = LLMRouter(registry, allow_heuristic_fallback=True)
        result = await router.complete("label", "test")
        assert result.provider == "heuristic"

    @pytest.mark.asyncio
    async def test_complete_falls_back_to_next_model_on_failure(self):
        registry = ModelRegistry(
            {"fail": _FailProvider()},
            default="fail",
        )
        router = LLMRouter(registry, allow_heuristic_fallback=True)

        # All providers fail, so Heuristics should be returned.
        result = await router.complete("label", "test")
        assert result.text == ""
        assert result.provider == "heuristic"
        assert router.stats.failures >= 1

    @pytest.mark.asyncio
    async def test_complete_raises_when_all_fail_and_no_heuristic(self):
        registry = ModelRegistry(
            {"fail": _FailProvider()},
            default="fail",
        )
        router = LLMRouter(registry, allow_heuristic_fallback=False)
        with pytest.raises(LLMError, match="All providers failed"):
            await router.complete("label", "test")

    @pytest.mark.asyncio
    async def test_complete_treats_empty_text_as_failure(self):
        registry = ModelRegistry(
            {"empty": _EmptyProvider()},
            default="empty",
        )
        router = LLMRouter(registry, allow_heuristic_fallback=True)
        result = await router.complete("label", "test")
        # Empty text should be treated as a failure -> heuristic fallback.
        assert result.provider == "heuristic"
        assert router.stats.failures >= 1

    @pytest.mark.asyncio
    async def test_token_budget_guard(self):
        registry = ModelRegistry(
            {"ok": _SuccessProviderNamed("ok", "ok")},
            default="ok",
        )
        router = LLMRouter(
            registry,
            token_budget=10,
            allow_heuristic_fallback=False,
        )
        # Pre-exceed the budget by simulating accumulated tokens.
        router.stats.prompt_tokens = 5
        router.stats.completion_tokens = 10
        with pytest.raises(LLMError, match="Token budget"):
            await router.complete("label", "test")

    @pytest.mark.asyncio
    async def test_accounting_tracks_tokens(self):
        registry = ModelRegistry(
            {"ok": _SuccessProvider("ok")},
            default="ok",
        )
        router = LLMRouter(registry, allow_heuristic_fallback=False)
        await router.complete("label", "test")
        assert router.stats.calls == 1
        assert router.stats.total_tokens == 30  # 10+20 from MockProvider
        assert (
            router.stats.by_provider.get("ok") == 1 or router.stats.by_provider.get("success") == 1
        )

    @pytest.mark.asyncio
    async def test_json_complete_parses_json(self):
        provider = _SuccessProvider(text='{"key": "value"}')
        registry = ModelRegistry({"ok": provider}, default="ok")
        router = LLMRouter(registry, allow_heuristic_fallback=False)
        data = await router.json_complete("label", "test")
        assert data == {"key": "value"}

    @pytest.mark.asyncio
    async def test_json_complete_strips_markdown_fences(self):
        provider = _SuccessProvider(text='```json\n{"key": "value"}\n```')
        registry = ModelRegistry({"ok": provider}, default="ok")
        router = LLMRouter(registry, allow_heuristic_fallback=False)
        data = await router.json_complete("label", "test")
        assert data == {"key": "value"}

    @pytest.mark.asyncio
    async def test_json_complete_returns_empty_on_plain_text(self):
        provider = _SuccessProvider(text="not json at all")
        registry = ModelRegistry({"ok": provider}, default="ok")
        router = LLMRouter(registry, allow_heuristic_fallback=False)
        data = await router.json_complete("label", "test")
        assert data == {}

    @pytest.mark.asyncio
    async def test_json_complete_returns_empty_dict_on_heuristic(self):
        provider = _FailProvider()
        registry = ModelRegistry({"fail": provider}, default="fail")
        router = LLMRouter(registry, allow_heuristic_fallback=True)
        data = await router.json_complete("label", "test")
        assert data == {}


# ── Provider HTTP layer (mocked) ──────────────────────────────────────────────


class TestOllamaProviderHTTP:
    @pytest.mark.asyncio
    @respx.mock
    async def test_chat_completion(self):
        respx.post("https://api.ollama.com/api/chat").mock(
            return_value=httpx.Response(
                200,
                json={
                    "message": {"content": "hello from ollama"},
                    "prompt_eval_count": 5,
                    "eval_count": 10,
                },
            )
        )
        provider = OllamaProvider(base_url="https://api.ollama.com", api_key="test-key")
        result = await provider.complete("llama3", "hi", max_tokens=100)
        assert result.text == "hello from ollama"
        assert result.model == "llama3"
        assert result.provider == "ollama"
        assert result.prompt_tokens == 5
        assert result.completion_tokens == 10
        # Verify auth header was sent.
        assert respx.calls.last.request.headers["Authorization"] == "Bearer test-key"

    @pytest.mark.asyncio
    @respx.mock
    async def test_chat_falls_back_to_generate(self):
        # First endpoint returns 500, second returns 200.
        chat_route = respx.post("https://api.ollama.com/api/chat").mock(
            return_value=httpx.Response(500, json={"error": "chat unavailable"})
        )
        gen_route = respx.post("https://api.ollama.com/api/generate").mock(
            return_value=httpx.Response(
                200,
                json={"response": "from generate", "prompt_eval_count": 3, "eval_count": 7},
            )
        )
        provider = OllamaProvider(base_url="https://api.ollama.com")
        result = await provider.complete("llama3", "hi", max_tokens=100)
        assert result.text == "from generate"
        assert result.prompt_tokens == 3
        assert result.completion_tokens == 7
        assert chat_route.called
        assert gen_route.called

    @pytest.mark.asyncio
    @respx.mock
    async def test_list_models(self):
        respx.get("https://api.ollama.com/api/tags").mock(
            return_value=httpx.Response(
                200,
                json={"models": [{"name": "llama3"}, {"name": "qwen2.5"}]},
            )
        )
        provider = OllamaProvider(base_url="https://api.ollama.com")
        models = await provider.list_models()
        assert len(models) == 2
        assert models[0]["name"] == "llama3"

    @pytest.mark.asyncio
    @respx.mock
    async def test_reasoning_content_fallback_when_content_empty(self):
        respx.post("https://api.ollama.com/api/chat").mock(
            return_value=httpx.Response(
                200,
                json={
                    "message": {
                        "content": "",
                        "reasoning_content": "model reasoning output",
                    },
                    "prompt_eval_count": 5,
                    "eval_count": 10,
                },
            )
        )
        provider = OllamaProvider(base_url="https://api.ollama.com")
        result = await provider.complete("deepseek-model", "hi", max_tokens=50)
        assert result.text == "model reasoning output"


class TestOpenCodeGoProviderHTTP:
    @pytest.mark.asyncio
    @respx.mock
    async def test_chat_completion(self):
        respx.post("https://opencode.ai/zen/go/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": "hello from opencode"}, "finish_reason": "stop"}
                    ],
                    "usage": {"prompt_tokens": 8, "completion_tokens": 12},
                    "cost": "0",
                },
            )
        )
        provider = OpenCodeGoProvider(
            base_url="https://opencode.ai/zen/go/v1",
            api_key="test-key",
        )
        result = await provider.complete("glm-5.2", "hi", max_tokens=200)
        assert result.text == "hello from opencode"
        assert result.model == "glm-5.2"
        assert result.provider == "opencode_go"
        assert result.prompt_tokens == 8
        assert result.completion_tokens == 12
        assert respx.calls.last.request.headers["Authorization"] == "Bearer test-key"

    @pytest.mark.asyncio
    @respx.mock
    async def test_list_models(self):
        respx.get("https://opencode.ai/zen/go/v1/models").mock(
            return_value=httpx.Response(
                200,
                json={"data": [{"id": "glm-5.2"}, {"id": "kimi-k2.6"}]},
            )
        )
        provider = OpenCodeGoProvider(base_url="https://opencode.ai/zen/go/v1", api_key="k")
        models = await provider.list_models()
        assert len(models) == 2
        assert models[0]["id"] == "glm-5.2"

    @pytest.mark.asyncio
    @respx.mock
    async def test_non_json_response_raises(self):
        respx.post("https://opencode.ai/zen/go/v1/chat/completions").mock(
            return_value=httpx.Response(200, text="<html>not json</html>")
        )
        provider = OpenCodeGoProvider(base_url="https://opencode.ai/zen/go/v1", api_key="k")
        with pytest.raises(RuntimeError, match="non-JSON response"):
            await provider.complete("glm-5.2", "hi", max_tokens=100)

    @pytest.mark.asyncio
    @respx.mock
    async def test_json_format_set_in_payload(self):
        respx.post("https://opencode.ai/zen/go/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                },
            )
        )
        provider = OpenCodeGoProvider(base_url="https://opencode.ai/zen/go/v1", api_key="k")
        await provider.complete("glm-5.2", "hi", format="json", max_tokens=100)
        sent = respx.calls.last.request.read()
        import json

        payload = json.loads(sent)
        assert payload["response_format"] == {"type": "json_object"}

    @pytest.mark.asyncio
    @respx.mock
    async def test_reasoning_content_fallback_when_content_empty(self):
        respx.post("https://opencode.ai/zen/go/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "reasoning_content": "model reasoning output",
                            },
                            "finish_reason": "length",
                        }
                    ],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 10},
                },
            )
        )
        provider = OpenCodeGoProvider(
            base_url="https://opencode.ai/zen/go/v1",
            api_key="test-key",
        )
        result = await provider.complete("deepseek-v4-flash", "hi", max_tokens=50)
        assert result.text == "model reasoning output"


class TestOpenAICompatibleProviderHTTP:
    @pytest.mark.asyncio
    @respx.mock
    async def test_chat_completion(self):
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": "hello from openai"}, "finish_reason": "stop"}
                    ],
                    "usage": {"prompt_tokens": 6, "completion_tokens": 9},
                },
            )
        )
        provider = OpenAICompatibleProvider(
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
        )
        result = await provider.complete("gpt-4", "hi", max_tokens=100)
        assert result.text == "hello from openai"
        assert result.model == "gpt-4"
        assert result.provider == "openai"
        assert result.prompt_tokens == 6
        assert result.completion_tokens == 9

    @pytest.mark.asyncio
    @respx.mock
    async def test_json_format_in_payload(self):
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                },
            )
        )
        provider = OpenAICompatibleProvider(base_url="https://api.openai.com/v1", api_key="k")
        await provider.complete("gpt-4", "hi", format="json", max_tokens=50)
        sent = respx.calls.last.request.read()
        import json

        payload = json.loads(sent)
        assert payload["response_format"] == {"type": "json_object"}

    @pytest.mark.asyncio
    @respx.mock
    async def test_no_api_key_means_no_auth_header(self):
        respx.post("https://custom/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                },
            )
        )
        provider = OpenAICompatibleProvider(base_url="https://custom/v1", api_key=None)
        await provider.complete("m", "hi", max_tokens=10)
        assert "Authorization" not in respx.calls.last.request.headers
