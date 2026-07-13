"""Model registry — resolves a role's model id to a provider + concrete model name.

Backends: ``ollama`` (default), ``opencode_go``, ``openai`` (any OpenAI-compatible
endpoint). With ``openai``/``opencode_go`` set, every role uses the single
configured model and the role chains are ignored; a blank opencode_go_model routes
each role to its tier-specific chain.
"""

from __future__ import annotations

from hermes.llm.providers.base import BaseProvider
from hermes.llm.providers.ollama import OllamaProvider
from hermes.llm.providers.openai_compatible import OpenAICompatibleProvider
from hermes.llm.providers.opencode_go import OpenCodeGoProvider


class ModelRegistry:
    def __init__(
        self,
        providers: dict[str, BaseProvider],
        default: str,
        default_model: str | None = None,
    ):
        self.providers = providers
        self.default = default
        self.default_model = default_model

    def provider_for(self, model: str) -> BaseProvider:
        if ":" in model:
            pfx = model.split(":", 1)[0]
            if pfx in self.providers:
                return self.providers[pfx]
        return self.providers[self.default]

    def model_name(self, model: str) -> str:
        if ":" in model:
            pfx = model.split(":", 1)[0]
            if pfx in self.providers:
                return model.split(":", 1)[1]
        # OpenAI/OpenCode Go: ignore role chains, use the configured model.
        if self.default in ("openai", "opencode_go") and self.default_model:
            return self.default_model
        # Ollama: strip a redundant "ollama:" prefix.
        if self.default == "ollama" and model.startswith("ollama:"):
            return model.split(":", 1)[1]
        return model


def build_registry(
    *,
    ollama_base_url: str = "https://api.ollama.com",
    ollama_api_key: str | None = None,
    backend: str = "ollama",
    opencode_go_base_url: str = "https://api.opencode.ai/v1",
    opencode_go_api_key: str | None = None,
    opencode_go_model: str | None = None,
    openai_base_url: str | None = None,
    openai_api_key: str | None = None,
    openai_model: str | None = None,
) -> ModelRegistry:
    providers: dict[str, BaseProvider] = {
        "ollama": OllamaProvider(base_url=ollama_base_url, api_key=ollama_api_key),
    }
    default = "ollama"
    default_model = None
    if backend == "opencode_go":
        if not opencode_go_api_key:
            raise ValueError("backend='opencode_go' requires opencode_go_api_key")
        providers["opencode_go"] = OpenCodeGoProvider(
            base_url=opencode_go_base_url, api_key=opencode_go_api_key
        )
        default = "opencode_go"
        default_model = opencode_go_model
    elif backend == "openai":
        if not openai_base_url or not openai_model:
            raise ValueError("backend='openai' requires openai_base_url and openai_model")
        providers["openai"] = OpenAICompatibleProvider(
            base_url=openai_base_url, api_key=openai_api_key
        )
        default = "openai"
        default_model = openai_model
    return ModelRegistry(providers, default, default_model)
