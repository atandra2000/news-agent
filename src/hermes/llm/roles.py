"""Role -> model-chain table. Chains reference tiers (writer/critic/plan/cheap)
from :mod:`hermes.llm.catalog` so the fleet points at real models; repoint in one place.
"""

from __future__ import annotations

from dataclasses import dataclass

from hermes.llm.catalog import TIER_KEEP_ALIVE, TIER_NUM_CTX, OLLAMA_CATALOG, OPENCODE_GO_CATALOG


@dataclass(frozen=True)
class RoleSpec:
    name: str
    # Ordered fallback chain; first success wins.
    chain: tuple[str, ...]
    temperature: float = 0.2
    max_tokens: int = 2048
    # Context window in tokens, passed to the provider.
    num_ctx: int = 8192
    # Keep the model resident between calls (Ollama-only; e.g. "10m").
    keep_alive: str | None = "5m"


def _chain(tier: str, provider: str = "ollama") -> tuple[str, ...]:
    """Model chain for a tier + provider."""
    catalog = OPENCODE_GO_CATALOG if provider == "opencode_go" else OLLAMA_CATALOG
    return tuple(catalog[tier])


def _spec(
    name: str,
    tier: str,
    *,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    provider: str = "ollama",
    num_ctx: int | None = None,
    keep_alive: str | None = None,
) -> RoleSpec:
    return RoleSpec(
        name=name,
        chain=_chain(tier, provider),
        temperature=temperature,
        max_tokens=max_tokens,
        # Per-role overrides win; otherwise fall back to the tier default.
        num_ctx=num_ctx if num_ctx is not None else TIER_NUM_CTX.get(tier, 8192),
        keep_alive=keep_alive if keep_alive is not None else TIER_KEEP_ALIVE.get(tier, "5m"),
    )


# Default roles use Ollama; backend="opencode_go" overrides with catalog models.
# Chains go capable -> smaller so a slow/unavailable big model falls back.
ROLES: dict[str, RoleSpec] = {
    # Per-item typed analysis (25-60 calls/run). Structured JSON doesn't need the
    # biggest model; critic tier is ~3-5x cheaper and sufficient. Largest cost sink.
    "research": _spec("research", "critic", temperature=0.2, max_tokens=3000, num_ctx=8192),
    "reason": _spec("reason", "critic", temperature=0.2, max_tokens=2500),
    "summarize": _spec("summarize", "cheap", temperature=0.2, max_tokens=1200),
    "compare": _spec("compare", "critic", temperature=0.2, max_tokens=2000),
    "markdown": _spec("markdown", "cheap", temperature=0.2, max_tokens=2500),
    "proofread": _spec("proofread", "cheap", temperature=0.1, max_tokens=1500),
    # Critic emits a structured JSON verdict. The critic-tier models are reasoning
    # models (kimi-k2.6/deepseek-v4-pro/glm-5.2): the verdict lands in ``content``
    # only AFTER ``reasoning_content`` completes, so the budget must cover BOTH.
    # 2000 was too small — reasoning exhausted it, ``content`` came back empty, the
    # provider fell back to reasoning_content (CoT), json.loads failed → {} → the
    # critic silently rubber-stamped every section (2026-07-13: all scores = 0.7
    # fallback). 4000 leaves room for reasoning + the JSON object.
    "critic": _spec("critic", "critic", temperature=0.1, max_tokens=4000),
    "plan": _spec("plan", "plan", temperature=0.2, max_tokens=1500),
    "verify": _spec("verify", "critic", temperature=0.1, max_tokens=1500),
    "label": _spec("label", "cheap", temperature=0.2, max_tokens=300),
    "write": _spec("write", "writer", temperature=0.3, max_tokens=4000),
    # Cluster-level synthesis (~10-20 calls/run). Demoted writer->critic; quality
    # preserved, cost drops. Right-sized num_ctx (8k).
    "cluster_synth": _spec("cluster_synth", "critic", temperature=0.3, max_tokens=2500, num_ctx=8192),
    # Final reasoning stage; largest token budget. Quality is paramount here.
    "chief_analyst": _spec("chief_analyst", "writer", temperature=0.3, max_tokens=8000),
    "brief_write": _spec("brief_write", "writer", temperature=0.3, max_tokens=5000),
    "brief_plan": _spec("brief_plan", "plan", temperature=0.2, max_tokens=1500),
    # Compiler-pipeline roles.
    # Extraction: structured JSON only, needs enough tokens for complete objects.
    "extract": _spec("extract", "cheap", temperature=0.1, max_tokens=2000),
    # Story discovery: one JSON call synthesizing the graph into story objects.
    "discover": _spec("discover", "critic", temperature=0.2, max_tokens=3000),
    # Chief-analyst reasoning: pure structured review, no prose.
    "analyze": _spec("analyze", "critic", temperature=0.1, max_tokens=3000),
    # Report editor: consistency-check JSON, deterministic.
    "edit": _spec("edit", "cheap", temperature=0.1, max_tokens=2000),
    # Story editor: large context to synthesize all stories, claims, and graph.
    "story_edit": _spec("story_edit", "critic", temperature=0.2, max_tokens=4000),
    # Report critic: structured JSON approval/rejection against pro standards.
    "report_critic": _spec("report_critic", "critic", temperature=0.1, max_tokens=2500),
    # Thesis formation: one structured call forming the report spine (plan tier).
    "thesis": _spec("thesis", "plan", temperature=0.2, max_tokens=1500),
    # Editorial board: structured section commissioning (critic tier, deterministic).
    "editorial": _spec("editorial", "critic", temperature=0.1, max_tokens=3000),
}


def get_role(name: str) -> RoleSpec:
    if name not in ROLES:
        raise KeyError(f"Unknown role: {name}")
    return ROLES[name]


def get_role_for_provider(name: str, provider: str) -> RoleSpec:
    """Role spec resolved to the given provider's models."""
    if name not in ROLES:
        raise KeyError(f"Unknown role: {name}")
    base_role = ROLES[name]
    tier_map = {
        "research": "writer",
        "reason": "critic",
        "summarize": "cheap",
        "compare": "critic",
        "markdown": "cheap",
        "proofread": "cheap",
        "critic": "critic",
        "plan": "plan",
        "verify": "critic",
        "label": "cheap",
        "write": "writer",
        "cluster_synth": "writer",
        "chief_analyst": "writer",
        "brief_write": "writer",
        "brief_plan": "plan",
        "extract": "cheap",
        "discover": "critic",
        "analyze": "critic",
        "edit": "cheap",
        "story_edit": "critic",
        "report_critic": "critic",
        "thesis": "plan",
        "editorial": "critic",
    }
    tier = tier_map.get(name, "cheap")
    return _spec(
        name,
        tier,
        temperature=base_role.temperature,
        max_tokens=base_role.max_tokens,
        provider=provider,
        # Preserve per-role overrides (e.g. research/cluster_synth num_ctx=8192).
        num_ctx=base_role.num_ctx,
        keep_alive=base_role.keep_alive,
    )
