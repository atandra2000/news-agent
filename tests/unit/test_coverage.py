"""Unit tests for the source-coverage verdict module.

These pin down the categorization heuristics and the OK/THIN/CRITICAL
classification. The verdicts drive the orchestrator's CRITICAL short-circuit
and the writer's honesty about thin evidence.
"""

from __future__ import annotations

from hermes.pipeline.coverage import (
    _category_for,
    _section_required_category,
    evaluate_coverage,
)
from hermes.pipeline.search import SearchResult
from hermes.pipeline.spec import BriefSpec, SectionSpec


def _src(source: str, url: str = "https://x/1") -> SearchResult:
    return SearchResult(title="t", url=url, source=source)


def test_category_for_known_sources():
    assert _category_for("arxiv") == "research"
    assert _category_for("openai") == "official"
    assert _category_for("reuters") == "news"
    assert _category_for("hacker_news") == "community"
    assert _category_for("huggingface") == "official"  # it's a lab too


def test_category_for_unknown_defaults_to_community():
    """Conservative default — unknown sources count as community (lowest bar)."""
    assert _category_for("some_random_thing") == "community"


def test_section_required_category_matches_title():
    """Section title hints map to required categories."""
    assert _section_required_category(SectionSpec(1, "Frontier Models")) == "official"
    assert _section_required_category(SectionSpec(2, "Research Breakthroughs")) == "research"
    assert _section_required_category(SectionSpec(3, "Regulation & Policy")) == "news"
    assert _section_required_category(SectionSpec(4, "Community & Ecosystem")) == "community"
    # Universal sections have no required category.
    assert _section_required_category(SectionSpec(5, "Executive Summary")) is None
    assert _section_required_category(SectionSpec(6, "Month Timeline")) is None


def test_evaluate_coverage_ok_when_category_satisfied():
    """≥5 official sources → OK for the Frontier Models section."""
    spec = BriefSpec(
        title="T",
        sections=[SectionSpec(1, "Frontier Models"), SectionSpec(2, "Executive Summary")],
    )
    sources = [_src("openai", f"https://x/{i}") for i in range(6)]
    verdicts = evaluate_coverage(spec, sources)
    assert verdicts[0].verdict == "OK"
    assert verdicts[1].verdict == "OK"  # universal


def test_evaluate_coverage_critical_when_category_empty():
    """Zero official sources for a section that needs official → CRITICAL."""
    spec = BriefSpec(
        title="T",
        sections=[SectionSpec(1, "Frontier Models")],
    )
    sources = [_src("hacker_news", f"https://x/{i}") for i in range(10)]
    verdicts = evaluate_coverage(spec, sources)
    assert verdicts[0].verdict == "CRITICAL"
    assert verdicts[0].required_category == "official"


def test_evaluate_coverage_thin_when_partial():
    """1-2 sources in required category → THIN."""
    spec = BriefSpec(
        title="T",
        sections=[SectionSpec(1, "Frontier Models")],
    )
    sources = (
        [_src("openai", f"https://x/{i}") for i in range(2)]
        + [_src("hacker_news", f"https://x/{i}") for i in range(5)]
    )
    verdicts = evaluate_coverage(spec, sources)
    assert verdicts[0].verdict == "THIN"
    assert verdicts[0].sources_in_section == 2


def test_evaluate_coverage_universal_section_with_zero_sources():
    """Universal sections need any source; with none → CRITICAL."""
    spec = BriefSpec(
        title="T",
        sections=[SectionSpec(1, "Executive Summary")],
    )
    verdicts = evaluate_coverage(spec, [])
    assert verdicts[0].verdict == "CRITICAL"
    assert verdicts[0].required_category is None


def test_evaluate_coverage_realistic_monthly():
    """Mirrors the 2026-07-13 monthly report's source mix (mostly HN + GitHub Trending,
    no arxiv). The 'Research Breakthroughs' section should be CRITICAL — exactly
    the gap the new verdict system is designed to surface."""
    spec = BriefSpec(
        title="AI Monthly",
        sections=[
            SectionSpec(1, "Executive Summary"),
            SectionSpec(2, "Frontier Models"),
            SectionSpec(3, "Research Breakthroughs"),
            SectionSpec(4, "Open Source AI"),
            SectionSpec(5, "Hardware & Infrastructure"),
            SectionSpec(6, "Community & Ecosystem"),
        ],
    )
    sources = (
        [_src("hacker_news", f"https://hn/{i}") for i in range(8)]
        + [_src("github_trending", f"https://gh/{i}") for i in range(6)]
    )
    verdicts = evaluate_coverage(spec, sources)
    by_num = {v.section_number: v.verdict for v in verdicts}
    # Research-required sections are CRITICAL.
    assert by_num[3] == "CRITICAL"  # Research Breakthroughs
    # Open Source is research-required too.
    assert by_num[4] == "CRITICAL"
    # Hardware requires official_lab.
    assert by_num[5] == "CRITICAL"
    # Community section is satisfied.
    assert by_num[6] in ("OK", "THIN")
    # Universal sections are OK.
    assert by_num[1] == "OK"
