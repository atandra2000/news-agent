"""Unit tests for the brief Markdown parser."""

from __future__ import annotations

from pathlib import Path

from newsagent.pipeline.spec import parse_prompt

_REPO = Path(__file__).resolve().parents[2]
_PROMPT = _REPO / "example_prompt.md"


def _spec():
    return parse_prompt(_PROMPT.read_text(encoding="utf-8"))


def test_parses_title():
    assert _spec().title == "AI STATE OF THE INDUSTRY 2026"


def test_parses_all_eighteen_sections():
    spec = _spec()
    assert len(spec.sections) == 18
    assert spec.sections[0].title == "Executive Summary"
    assert spec.sections[-1].title == "Predictions"
    assert all(s.number == i + 1 for i, s in enumerate(spec.sections))


def test_parses_section_bullets():
    spec = _spec()
    sec = spec.sections[0]
    assert any("breakthroughs" in b.lower() for b in sec.bullets)


def test_parses_prioritized_sources():
    spec = _spec()
    assert "OpenAI" in spec.source_names
    assert "Reuters" in spec.source_names
    assert "r/LocalLLaMA" in spec.source_names


def test_parses_deliverables_and_quality():
    spec = _spec()
    assert len(spec.deliverables) > 5
    assert any("synthesize" in q.lower() for q in spec.quality)


def test_detects_cadence_monthly():
    """Brief body explicitly saying 'monthly' / 'past 30 days' sets cadence."""
    spec = parse_prompt(
        "# AI MONTHLY BRIEF\n\nSynthesize the past 30 days into a report.\n"
    )
    assert spec.cadence == "monthly"


def test_detects_cadence_weekly():
    spec = parse_prompt(
        "# AI WEEKLY DIGEST\n\nThe past 7 days of AI news.\n"
    )
    assert spec.cadence == "weekly"


def test_detects_cadence_daily():
    spec = parse_prompt(
        "# AI DAILY PULSE\n\nWhat happened in the last 24 hours.\n"
    )
    assert spec.cadence == "daily"


def test_cadence_none_when_unambiguous():
    spec = parse_prompt("# SOME BRIEF\n\nNo time hint anywhere.\n")
    assert spec.cadence is None


def test_monthly_wins_over_weekly_when_both_present():
    """If the body mentions both, the longer/more-specific cadence wins
    (monthly hint list is checked first)."""
    spec = parse_prompt(
        "# BRIEF\n\nThe past 7 days were busy; the past 30 days show a trend.\n"
    )
    assert spec.cadence == "monthly"
