"""Integration test for the unified news pipeline orchestrator.

Mocks the LLM router and search provider so the test is offline and fast.
The orchestrator is the only thing under test; the underlying stages are
unit-tested in their own files.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from hermes.config import HermesSettings
from hermes.pipeline.orchestrator import run_news_pipeline
from hermes.pipeline.search import SearchResult
from hermes.pipeline.spec import BriefSpec, SectionSpec


SIMPLE_PROMPT = """# Test Report

## Research Instructions
- Source A
- Source B

## Report Structure
## 1. Pulse
- bullet one
- bullet two

## 2. Trends
- bullet one
"""


DEEP_PROMPT = """# Test Deep Report

## Research Instructions
- Source A

## Report Structure
## 1. Pulse
- a

## 2. Trends
- b

## 3. Frontier
- c

## 4. Regulation
- d
"""


def _fake_search_provider(results: list[SearchResult]) -> MagicMock:
    sp = MagicMock()
    sp.name = "fake"
    sp.search = AsyncMock(return_value=results)
    return sp


def _fake_router(text: str = "synthesized prose") -> MagicMock:
    r = MagicMock()
    r.stats.total_tokens = 0
    r.complete = AsyncMock()
    r.json_complete = AsyncMock(return_value={})

    from hermes.llm.providers.base import ProviderResult

    r.complete.return_value = ProviderResult(
        text=text, model="test", provider="test", prompt_tokens=10, completion_tokens=20
    )
    return r


def _make_settings(tmp_path: Path) -> HermesSettings:
    s = HermesSettings()
    s.storage.dir = tmp_path
    return s


@pytest.mark.asyncio
async def test_orchestrator_writes_file_for_simple_prompt(tmp_path):
    settings = _make_settings(tmp_path)
    spec = BriefSpec(
        title="Test Report",
        sections=[
            SectionSpec(number=1, title="Pulse", bullets=["a", "b"]),
            SectionSpec(number=2, title="Trends", bullets=["c"]),
        ],
    )
    search = _fake_search_provider([
        SearchResult(title="S1", url="https://example.com/1", content="x"),
    ])
    router = _fake_router()
    out = await run_news_pipeline(
        spec, settings=settings, router=router, search=search,
        out_path=tmp_path / "out.md",
    )
    assert out.exists()
    text = out.read_text()
    assert "## **Test Report**" in text
    assert "## **1. Pulse**" in text
    assert "## **2. Trends**" in text


async def test_orchestrator_refuses_write_when_required_deliverable_missing(tmp_path):
    # The 2026-07-13 monthly report shipped with a "Required Deliverables —
    # Coverage Check" footer that listed missing items AFTER the file was
    # already on disk. Task 4 makes the gate a pre-write refusal: any
    # required deliverable that didn't make it into the assembled text
    # raises PipelineRefusedError and the report file is never written.
    from hermes.errors import PipelineRefusedError

    settings = _make_settings(tmp_path)
    out_file = tmp_path / "out.md"
    spec = BriefSpec(
        title="Test Report",
        sections=[SectionSpec(number=1, title="Pulse", bullets=["a"])],
        # The brief mandates a "Model comparison matrix". The fake router
        # below emits no table, so the deliverable is absent from the
        # assembled report.
        deliverables=["Model comparison matrix"],
    )
    search = _fake_search_provider([
        SearchResult(title="S1", url="https://example.com/1", content="x"),
    ])
    router = _fake_router(text="## **1. Pulse**\nJust prose. [src:https://example.com/1]")

    with pytest.raises(PipelineRefusedError) as excinfo:
        await run_news_pipeline(
            spec, settings=settings, router=router, search=search,
            out_path=out_file,
        )
    # The refused error names the missing deliverable.
    assert "Model comparison matrix" in str(excinfo.value)
    # Critically: the file was NOT written.
    assert not out_file.exists()


async def test_orchestrator_writes_when_required_deliverable_present(tmp_path, monkeypatch):
    # Sanity: the gate does not false-positive when the deliverable is
    # genuinely in the report. Bypasses the section-level validity gate
    # (which is intentionally strict on a fake LLM router) by replacing
    # _synthesize_section_parallel with a stub that emits a section that
    # includes a model-comparison table — the brief's deliverable keyword.
    from hermes.pipeline import orchestrator

    settings = _make_settings(tmp_path)
    out_file = tmp_path / "out.md"
    spec = BriefSpec(
        title="Test Report",
        sections=[SectionSpec(number=1, title="Pulse", bullets=["a"])],
        deliverables=["Model comparison matrix"],
    )
    search = _fake_search_provider([
        SearchResult(title="S1", url="https://example.com/1", content="x"),
    ])
    router = _fake_router()

    section_text = (
        "## **1. Pulse**\n\n"
        "Real analysis of the pulse, with a citation. [src:https://example.com/1]\n\n"
        "## **Model comparison matrix**\n\n"
        "| Model | Org | Score |\n|---|---|---|\n| A | X | 90 |\n"
    )

    async def _fake_synth(*args, **kwargs):
        return section_text

    monkeypatch.setattr(orchestrator, "_synthesize_section_parallel", _fake_synth)

    out = await run_news_pipeline(
        spec, settings=settings, router=router, search=search,
        out_path=out_file,
    )
    assert out.exists()
