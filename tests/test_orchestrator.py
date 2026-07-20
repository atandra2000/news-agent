"""Orchestrator section-synthesis tests.

The 2026-07-14 monthly report had 4 sections (Funding, Regulation, Enterprise,
Predictions) short-circuited to an 18-word "section omitted" placeholder. The
brief explicitly lists these as Required Deliverables — short-circuiting means
the writer never tries. These tests pin down the thin-synthesis path: the
section is always attempted, the writer prompt carries the verdict, and a
named-category placeholder is rendered only if the result fails the substance
floor.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from newsagent.config import NewsAgentSettings
from newsagent.llm.providers.base import ProviderResult
from newsagent.pipeline.cadence import resolve_cadence
from newsagent.pipeline.orchestrator import _synthesize_section_parallel
from newsagent.pipeline.search import SearchResult
from newsagent.pipeline.spec import BriefSpec, SectionSpec


async def test_thin_section_attempts_synthesis(monkeypatch, tmp_path):
    """A section with coverage verdict=THIN must be ATTEMPTED, not short-circuited.

    The previous short-circuit (``if coverage_verdict == "CRITICAL": return ...``)
    silently dropped the section. Now: the section is always attempted; the
    writer prompt receives a "thin corpus" flag; a substantial synthesis wins.
    """
    sec = SectionSpec(number=6, title="Funding, M&A & Business", bullets=["rounds"])
    spec = BriefSpec(title="T", sections=[sec])
    sources = [
        SearchResult(
            title="F", url="https://example.com/1", source="theinformation",
            extra={"category": "news"},
        )
    ]
    router = MagicMock()
    router.stats.total_tokens = 0

    # Router emits a real-looking section with 100+ content words + a citation.
    # The substance floor in the orchestrator is 80 words; we emit well above.
    text = (
        "## **6. Funding, M&A & Business**\n\n"
        + ("Funding analysis paragraph with concrete content for the section. " * 15)
        + "[src:https://example.com/1]"
    )
    router.complete = AsyncMock(return_value=ProviderResult(
        text=text, model="t", provider="t", prompt_tokens=10, completion_tokens=20,
    ))
    # Critic returns a passing verdict so synthesize_section_with_review ships.
    router.json_complete = AsyncMock(return_value={
        "pass": True, "score": 0.9, "gaps": [], "missing_citations": False,
        "cadence_ok": True, "has_cot_or_stub": False, "feedback": "",
    })

    settings = NewsAgentSettings()
    settings.storage.dir = tmp_path
    cad = resolve_cadence("monthly")
    semaphore = asyncio.Semaphore(1)

    out = await _synthesize_section_parallel(
        sec, sources, [], None, router, None, spec, settings,
        cad=cad, date_label="July 2026", cadence_note="past 30 days",
        per_section_sources=12, extra_queries=2, year="2026",
        search_enabled=False, semaphore=semaphore,
        coverage_verdict="THIN",
    )

    # Real synthesis wins: writer's content is preserved.
    assert "Funding analysis" in out
    # The "section omitted" placeholder must NOT be rendered on a THIN verdict.
    assert "section omitted" not in out.lower()


async def test_critical_section_attempts_synthesis(monkeypatch, tmp_path):
    """A section with coverage verdict=CRITICAL must be ATTEMPTED, not short-circuited.

    Why this test exists: the previous short-circuit was keyed on
    ``coverage_verdict == "CRITICAL"`` and silently dropped the section. The
    THIN test above would have passed on the old code too (THIN was never
    short-circuited), so it cannot prove the short-circuit is gone. This test
    uses ``CRITICAL`` to exercise the exact code path that was removed; it
    would fail on the old code.
    """
    sec = SectionSpec(number=6, title="Funding, M&A & Business", bullets=["rounds"])
    spec = BriefSpec(title="T", sections=[sec])
    sources = [
        SearchResult(
            title="F", url="https://example.com/1", source="theinformation",
            extra={"category": "news"},
        )
    ]
    router = MagicMock()
    router.stats.total_tokens = 0

    # Router emits a real-looking section with 100+ content words + a citation.
    text = (
        "## **6. Funding, M&A & Business**\n\n"
        + ("Funding analysis paragraph with concrete content for the section. " * 15)
        + "[src:https://example.com/1]"
    )
    router.complete = AsyncMock(return_value=ProviderResult(
        text=text, model="t", provider="t", prompt_tokens=10, completion_tokens=20,
    ))
    # Critic returns a passing verdict so synthesize_section_with_review ships.
    router.json_complete = AsyncMock(return_value={
        "pass": True, "score": 0.9, "gaps": [], "missing_citations": False,
        "cadence_ok": True, "has_cot_or_stub": False, "feedback": "",
    })

    settings = NewsAgentSettings()
    settings.storage.dir = tmp_path
    cad = resolve_cadence("monthly")
    semaphore = asyncio.Semaphore(1)

    out = await _synthesize_section_parallel(
        sec, sources, [], None, router, None, spec, settings,
        cad=cad, date_label="July 2026", cadence_note="past 30 days",
        per_section_sources=12, extra_queries=2, year="2026",
        search_enabled=False, semaphore=semaphore,
        coverage_verdict="CRITICAL",
    )

    # Real synthesis wins: writer's content is preserved (the old short-circuit
    # would have returned a "section omitted" placeholder instead).
    assert "Funding analysis" in out
    # The "section omitted" placeholder must NOT be rendered on a CRITICAL verdict.
    assert "section omitted" not in out.lower()


async def test_thin_corpus_flag_reaches_writer_prompt(monkeypatch, tmp_path):
    """The writer prompt must carry the THIN CORPUS honesty note on THIN/CRITICAL.

    Capture the prompt the writer is given; assert the thin-corpus note is
    present so the writer is honest about gaps rather than fabricating.
    """
    sec = SectionSpec(number=6, title="Funding, M&A & Business", bullets=["rounds"])
    spec = BriefSpec(title="T", sections=[sec])
    sources = [
        SearchResult(title="F", url="https://example.com/1", source="theinformation",
                      extra={"category": "news"})
    ]
    router = MagicMock()
    router.stats.total_tokens = 0
    captured: dict = {}

    text = (
        "## **6. Funding, M&A & Business**\n\n"
        + ("Funding analysis paragraph with concrete content for the section. " * 15)
        + "[src:https://example.com/1]"
    )

    async def capture_complete(role, prompt, **kwargs):
        captured["prompt"] = prompt
        return ProviderResult(
            text=text, model="t", provider="t", prompt_tokens=10, completion_tokens=20,
        )

    router.complete = AsyncMock(side_effect=capture_complete)
    router.json_complete = AsyncMock(return_value={
        "pass": True, "score": 0.9, "gaps": [], "missing_citations": False,
        "cadence_ok": True, "has_cot_or_stub": False, "feedback": "",
    })

    settings = NewsAgentSettings()
    settings.storage.dir = tmp_path
    cad = resolve_cadence("monthly")
    semaphore = asyncio.Semaphore(1)

    await _synthesize_section_parallel(
        sec, sources, [], None, router, None, spec, settings,
        cad=cad, date_label="July 2026", cadence_note="past 30 days",
        per_section_sources=12, extra_queries=2, year="2026",
        search_enabled=False, semaphore=semaphore,
        coverage_verdict="THIN",
    )

    # The thin-corpus honesty note must reach the writer.
    assert "THIN CORPUS" in captured["prompt"]


async def test_ok_section_has_no_thin_corpus_flag(tmp_path):
    """OK sections (well-covered) must NOT carry the THIN CORPUS flag — they
    are not thin, and the writer is free to write normally.
    """
    sec = SectionSpec(number=6, title="Funding, M&A & Business", bullets=["rounds"])
    spec = BriefSpec(title="T", sections=[sec])
    sources = [
        SearchResult(title="F", url="https://example.com/1", source="theinformation",
                      extra={"category": "news"})
    ]
    router = MagicMock()
    router.stats.total_tokens = 0
    captured: dict = {}

    text = (
        "## **6. Funding, M&A & Business**\n\n"
        + ("Funding analysis paragraph with concrete content for the section. " * 15)
        + "[src:https://example.com/1]"
    )

    async def capture_complete(role, prompt, **kwargs):
        captured["prompt"] = prompt
        return ProviderResult(
            text=text, model="t", provider="t", prompt_tokens=10, completion_tokens=20,
        )

    router.complete = AsyncMock(side_effect=capture_complete)
    router.json_complete = AsyncMock(return_value={
        "pass": True, "score": 0.9, "gaps": [], "missing_citations": False,
        "cadence_ok": True, "has_cot_or_stub": False, "feedback": "",
    })

    settings = NewsAgentSettings()
    settings.storage.dir = tmp_path
    cad = resolve_cadence("monthly")
    semaphore = asyncio.Semaphore(1)

    await _synthesize_section_parallel(
        sec, sources, [], None, router, None, spec, settings,
        cad=cad, date_label="July 2026", cadence_note="past 30 days",
        per_section_sources=12, extra_queries=2, year="2026",
        search_enabled=False, semaphore=semaphore,
        coverage_verdict="OK",
    )

    # OK sections get no THIN CORPUS flag.
    assert "THIN CORPUS" not in captured["prompt"]
