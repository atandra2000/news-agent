"""Turn a :class:`BriefSpec` into a list of targeted research queries."""

from __future__ import annotations

from dataclasses import dataclass

from newsagent.pipeline.spec import BriefSpec, SectionSpec


@dataclass
class ResearchQuery:
    text: str
    section: str | None
    kind: str  # "section" | "source"


# Per-cadence fan-out: (queries per section, source-priority probes).
# Wider windows justify deeper retrieval.
_CADENCE_FANOUT = {
    "daily": (2, 8),
    "weekly": (4, 16),
    "monthly": (6, 24),
}


def plan_queries(
    spec: BriefSpec,
    *,
    per_section: int = 2,
    source_queries: int = 8,
    year: str = "2026",
    cadence: str | None = None,
) -> list[ResearchQuery]:
    """Expand each section and the headline sources into search queries.

    When ``cadence`` is given the per-cadence fan-out table overrides the
    defaults (daily=shallow, monthly=deep) so longer windows get richer coverage.
    """
    if cadence in _CADENCE_FANOUT:
        per_section, source_queries = _CADENCE_FANOUT[cadence]
    queries: list[ResearchQuery] = []

    for sec in spec.sections:
        queries.append(
            ResearchQuery(f"{sec.title} {year}", sec.title, "section")
        )
        picks = sec.bullets[: max(0, per_section - 1)]
        for b in picks:
            queries.append(
                ResearchQuery(f"{sec.title}: {b} {year} AI", sec.title, "section")
            )

    for name in spec.source_names[:source_queries]:
        queries.append(
            ResearchQuery(f"{name} AI {year} news announcements", None, "source")
        )

    return queries


def section_keywords(sec: SectionSpec) -> set[str]:
    text = f"{sec.title} {' '.join(sec.bullets)}".lower()
    return {w for w in text.split() if len(w) > 3}
