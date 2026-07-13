"""Source-coverage verdict for a brief.

A "coverage verdict" classifies each section as OK / THIN / CRITICAL by
comparing the retrieved source corpus against the prompt's stated source
priorities. The writer is told the verdict so it can be honest about gaps
instead of inventing context; the orchestrator can use it to drop sections
where the evidence base is too thin to write a real analysis.

The 2026-07-13 monthly report's "Open Source AI" and "Hardware & Infrastructure"
sections both rendered the synthesis-failure stub because the writer had
nothing to work with. The coverage verdict gives us a principled way to
recognize that BEFORE we burn an LLM call on a doomed synthesis.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from hermes.pipeline.search import SearchResult
from hermes.pipeline.spec import BriefSpec, SectionSpec


# Source type → category. Coverage is computed at the category level so a
# prompt that lists "OpenAI / Anthropic / Google DeepMind" (all official_lab)
# only needs ONE of them to be present.
_OFFICIAL_LABS = {
    "openai", "anthropic", "google_deepmind", "google_ai", "microsoft_ai",
    "meta_ai", "xai", "nvidia", "amd", "intel", "apple_ml", "amazon_aws_ai",
    "ibm_research", "huggingface", "mistral", "deepseek", "qwen", "moonshot",
    "minimax", "zhipu", "perplexity", "groq", "cerebras", "databricks", "cohere",
    "openai_blog", "anthropic_blog", "google_blog", "deepmind_blog",
}
_RESEARCH = {
    "arxiv", "semantic_scholar", "papers_with_code", "nature", "science",
    "neurips", "icml", "iclr", "cvpr", "openreview", "huggingface_papers",
}
_NEWS = {
    "reuters", "bloomberg", "financial_times", "the_information", "mit_tech_review",
    "techcrunch", "ieee_spectrum", "venturebeat", "rss", "tavily",
}
_COMMUNITY = {
    "hacker_news", "r_machine_learning", "r_local_llama", "r_singularity",
    "github_trending", "huggingface_trending", "substack", "devto", "lobsters",
}


def _category_for(source: str) -> str:
    """Map a source_type to a coverage category. Unknown sources count as community."""
    s = (source or "").lower()
    if s in _OFFICIAL_LABS:
        return "official"
    if s in _RESEARCH:
        return "research"
    if s in _NEWS:
        return "news"
    if s in _COMMUNITY:
        return "community"
    return "community"  # conservative default — most "other" is community


# Section titles that map strongly to one category. When a section's title
# matches a known category, coverage in that category is REQUIRED; coverage
# in other categories is optional.
_SECTION_CATEGORY_HINTS: dict[str, str] = {
    "research": "research",
    "frontier model": "official",
    "model": "official",
    "hardware": "official",
    "open source": "research",
    "agent": "community",
    "agent & coding": "community",
    "coding": "community",
    "regulation": "news",
    "policy": "news",
    "funding": "news",
    "m&a": "news",
    "business": "news",
    "enterprise": "news",
    "adoption": "news",
    "community": "community",
    "ecosystem": "community",
    "benchmark": "research",
    "prediction": "news",
    "executive summary": None,  # any category
    "timeline": None,
}


def _section_required_category(section: SectionSpec) -> str | None:
    """Return the category most likely required for this section, or None."""
    low = section.title.lower()
    for needle, cat in _SECTION_CATEGORY_HINTS.items():
        if needle in low:
            return cat
    return None


@dataclass(frozen=True)
class CoverageVerdict:
    section_number: int
    section_title: str
    verdict: str  # "OK" | "THIN" | "CRITICAL"
    sources_in_section: int
    categories_present: tuple[str, ...]
    required_category: str | None


def evaluate_coverage(
    spec: BriefSpec,
    sources: list[SearchResult],
    *,
    min_sources_for_ok: int = 5,
    min_sources_for_critical: int = 1,
) -> list[CoverageVerdict]:
    """Compute a per-section coverage verdict for a brief.

    Heuristic: pick the section's required category (from title) and count how
    many sources in ``sources`` map to it. If 0 → CRITICAL; if < min_sources_for_ok
    → THIN; else OK. The required_category is None for sections that don't have
    a strong default (Executive Summary, Month Timeline, Predictions) — they
    are OK as long as any source exists.

    Args:
        spec: the parsed brief.
        sources: the full retrieved source corpus (the union of all sections).
        min_sources_for_ok: minimum sources in the required category for OK.
        min_sources_for_critical: minimum sources (any category) to escape
            CRITICAL when the required category is unknown.
    """
    # Per-category counts over the full corpus (no per-section split available
    # at this stage — the orchestrator computes this BEFORE dispatching to
    # per-section writers).
    cats: dict[str, int] = {}
    total = 0
    for s in sources:
        c = _category_for(s.source)
        cats[c] = cats.get(c, 0) + 1
        total += 1

    verdicts: list[CoverageVerdict] = []
    for sec in spec.sections:
        required = _section_required_category(sec)
        if required is None:
            # Universal section: any source suffices.
            if total >= min_sources_for_ok:
                verdict = "OK"
            elif total >= min_sources_for_critical:
                verdict = "THIN"
            else:
                verdict = "CRITICAL"
            verdicts.append(CoverageVerdict(
                section_number=sec.number,
                section_title=sec.title,
                verdict=verdict,
                sources_in_section=total,
                categories_present=tuple(sorted(cats.keys())),
                required_category=None,
            ))
            continue
        # Category-required section.
        in_cat = cats.get(required, 0)
        if in_cat >= min_sources_for_ok:
            verdict = "OK"
        elif in_cat >= min_sources_for_critical:
            verdict = "THIN"
        else:
            verdict = "CRITICAL"
        verdicts.append(CoverageVerdict(
            section_number=sec.number,
            section_title=sec.title,
            verdict=verdict,
            sources_in_section=in_cat,
            categories_present=tuple(sorted(cats.keys())),
            required_category=required,
        ))
    return verdicts


def coverage_summary(verdicts: Iterable[CoverageVerdict]) -> str:
    """Format a verdict list as a short human-readable summary for the writer."""
    vs = list(verdicts)
    if not vs:
        return ""
    lines = ["SOURCE COVERAGE VERDICT:"]
    for v in vs:
        cat = v.required_category or "any"
        lines.append(
            f"  §{v.section_number} {v.section_title[:40]:<40} → {v.verdict:<8} "
            f"({v.sources_in_section} {cat} sources; cats present: {','.join(v.categories_present) or 'none'})"
        )
    return "\n".join(lines)
