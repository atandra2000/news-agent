"""Per-cadence tuning: lookback window, days, per-section fan-out, max_tokens.

A single table — anything that scales with the lookback window lives here.
The orchestrator looks up the entry once at the start of a run.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CadenceSpec:
    window: str         # human-readable, e.g. "the last 24 hours"
    days: int           # lookback window in days (for Tavily `days` param)
    per_section: int    # queries per section
    sources: int        # source-priority probes
    max_tokens: int     # writer max_tokens (scales with window length)
    min_citations: int  # per-section citation floor (post-synthesis)


# Daily = pulse, weekly = digest, monthly = deep dive. Max_tokens scales with
# window because the writer has more ground to cover. Per-section + sources
# scale so a monthly deep dive gets a richer source pool per section.
CADENCE: dict[str, CadenceSpec] = {
    "daily": CadenceSpec(
        window="the last 24 hours",
        days=1,
        per_section=1,
        sources=4,
        max_tokens=5000,
        min_citations=3,
    ),
    "weekly": CadenceSpec(
        window="the past 7 days",
        days=7,
        per_section=2,
        sources=8,
        max_tokens=6000,
        min_citations=3,
    ),
    "monthly": CadenceSpec(
        window="the past 30 days",
        days=30,
        per_section=3,
        sources=12,
        max_tokens=8000,
        min_citations=3,
    ),
}


def resolve_cadence(value: str | None) -> CadenceSpec:
    """Look up a cadence by name; fall back to daily on any invalid value."""
    if value and value in CADENCE:
        return CADENCE[value]
    return CADENCE["daily"]
