"""Unit tests for the brief Markdown parser."""

from __future__ import annotations

from pathlib import Path

from hermes.pipeline.spec import parse_prompt

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
