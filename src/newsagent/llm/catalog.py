"""Curated model catalog for Ollama and OpenCode Go.

Roles reference **tiers** (not hardcoded ids) so the fleet repoints in one place.
Verify exact ids on your account with ``newsagent models``.

Tiers: writer (largest ctx, report sections), critic (strong mid, eval),
plan (mid, planning), cheap (small/fast, labels/routing).
"""

from __future__ import annotations

from dataclasses import dataclass

# Ollama fallback chains per tier (first success wins). Verified live on
# api.ollama.com/api/tags (2026-07-11). Legacy local-ollama ids (qwen2.5:72b …)
# are NOT present on the Pro endpoint. Reasoning models (glm-5.2, deepseek-v4-pro)
# write to ``reasoning_content`` and need ``max_tokens`` >= ~200 before ``content``
# populates, so ``cheap`` uses the lightweight deepseek-v4-flash instead.
OLLAMA_CATALOG: dict[str, list[str]] = {
    "writer": ["deepseek-v4-pro", "kimi-k2.6", "glm-5.2"],
    "critic": ["kimi-k2.6", "deepseek-v4-pro", "glm-5.2"],
    "plan": ["kimi-k2.6", "deepseek-v4-flash", "deepseek-v4-pro"],
    "cheap": ["deepseek-v4-flash", "kimi-k2.6", "gemma3:4b"],
}

# OpenCode Go fallback chains per tier (first success wins). Verified live on
# opencode.ai/zen/go/v1/models (2026-07-11). deepseek-v4-flash writes ALL output
# to ``reasoning_content`` and never populates ``content`` (finish_reason="length"
# even at max_tokens=4096) — unusable for roles needing completion text.
# qwen3.7-plus reasons internally but reliably produces ``content`` at low max_tokens.
OPENCODE_GO_CATALOG: dict[str, list[str]] = {
    "writer": ["deepseek-v4-pro", "kimi-k2.6", "glm-5.2"],
    "critic": ["kimi-k2.6", "deepseek-v4-pro", "glm-5.2"],
    "plan": ["kimi-k2.6", "qwen3.7-plus", "deepseek-v4-pro"],
    "cheap": ["qwen3.7-plus", "kimi-k2.6", "deepseek-v4-flash"],
}

# Default catalog (Ollama) for backward compatibility.
MODEL_CATALOG = OLLAMA_CATALOG

# Recommended context window (tokens) per tier — big enough to ingest many sources.
TIER_NUM_CTX: dict[str, int] = {
    "writer": 16384,
    "critic": 16384,
    "plan": 8192,
    "cheap": 4096,
}

# How long to keep the model resident between calls (Ollama-only; OpenCode Go ignores).
TIER_KEEP_ALIVE: dict[str, str] = {
    "writer": "10m",
    "critic": "10m",
    "plan": "5m",
    "cheap": "5m",
}


@dataclass(frozen=True)
class TierSpec:
    chain: tuple[str, ...]
    num_ctx: int
    keep_alive: str


def tier_spec(tier: str, provider: str = "ollama") -> TierSpec:
    """Tier spec for a given provider."""
    if tier not in MODEL_CATALOG:
        raise KeyError(f"Unknown model tier: {tier}")
    catalog = OPENCODE_GO_CATALOG if provider == "opencode_go" else OLLAMA_CATALOG
    if tier not in catalog:
        raise KeyError(f"Unknown model tier for {provider}: {tier}")
    return TierSpec(
        chain=tuple(catalog[tier]),
        num_ctx=TIER_NUM_CTX.get(tier, 8192),
        keep_alive=TIER_KEEP_ALIVE.get(tier, "5m"),
    )


def all_catalog_models(provider: str = "ollama") -> list[str]:
    """All models in the catalog for a given provider."""
    catalog = OPENCODE_GO_CATALOG if provider == "opencode_go" else OLLAMA_CATALOG
    seen: list[str] = []
    for chain in catalog.values():
        for m in chain:
            if m not in seen:
                seen.append(m)
    return seen
