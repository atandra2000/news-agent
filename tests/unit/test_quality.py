"""Unit tests for the quality self-assessment stage.

Covers:
- Heuristic scorer (offline, no LLM).
- LLM judge path (via FakeRouter).
- run_quality end-to-end: reads report, scores, persists lessons, writes files.
- Missing report graceful handling.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from hermes.pipeline.quality import (
    QualityReport,
    RUBRIC,
    _heuristic_scores,
    _render_quality,
    judge,
    run_quality,
)
from hermes.storage.models import Lesson
from tests.helpers import FakeRouter, _settings


class TestHeuristicScores:
    def test_returns_all_six_dimensions(self):
        scores = _heuristic_scores("# Some Report\n\nbody text here")
        assert set(scores) == set(RUBRIC)
        for dim in RUBRIC:
            assert 1.0 <= scores[dim] <= 5.0

    def test_coverage_increases_with_links(self):
        low = _heuristic_scores("no links here")
        high = _heuristic_scores(" ".join(f"https://example.com/{i}" for i in range(30)))
        assert high["coverage"] > low["coverage"]

    def test_depth_increases_with_length(self):
        short = _heuristic_scores("tiny")
        long = _heuristic_scores("x" * 8000)
        assert long["depth"] > short["depth"]

    def test_synthesis_boosted_by_trends_section(self):
        no_trends = _heuristic_scores("plain report without trends section")
        with_trends = _heuristic_scores("## Emerging Trends\n\nsome trends here")
        assert with_trends["synthesis"] > no_trends["synthesis"]

    def test_trust_boosted_by_references(self):
        no_refs = _heuristic_scores("no references section")
        with_refs = _heuristic_scores("## References\n\n[1] source")
        assert with_refs["trust"] > no_refs["trust"]

    def test_scores_capped_at_5(self):
        huge = _heuristic_scores(" ".join(f"https://x.com/{i}" for i in range(500)))
        for dim in RUBRIC:
            assert huge[dim] <= 5.0


class TestJudge:
    @pytest.mark.asyncio
    async def test_judge_uses_llm_when_available(self, tmp_path):
        from hermes.pipeline.context import RunContext
        from hermes.storage.db import Store
        from hermes.llm.embed import Embedder
        from hermes.storage.vectorstore import build_vector_store

        settings = _settings(tmp_path)
        store = Store(settings.sqlite_url)
        await store.init()
        router = FakeRouter()
        embedder = Embedder(model="hashing", dim=64, normalize=True)
        vs = build_vector_store("numpy", store.session_factory,
                                qdrant_path=str(settings.qdrant_path),
                                collection="test", dim=64)
        ctx = RunContext(settings=settings, store=store, router=router, embedder=embedder, vectorstore=vs)

        verdict = await judge(ctx, "## Some Report\n\ncontent with [links](https://x.com)")
        assert "scores" in verdict
        assert "notes" in verdict
        assert isinstance(verdict["notes"], list)
        assert len(verdict["notes"]) >= 1
        await store.close()

    @pytest.mark.asyncio
    async def test_judge_falls_back_to_heuristic_on_empty_llm(self, tmp_path):
        from hermes.pipeline.context import RunContext
        from hermes.storage.db import Store
        from hermes.llm.embed import Embedder
        from hermes.storage.vectorstore import build_vector_store

        class _EmptyRouter(FakeRouter):
            async def json_complete(self, role, prompt, *, system=None):
                return {}

        settings = _settings(tmp_path)
        store = Store(settings.sqlite_url)
        await store.init()
        router = _EmptyRouter()
        embedder = Embedder(model="hashing", dim=64, normalize=True)
        vs = build_vector_store("numpy", store.session_factory,
                                qdrant_path=str(settings.qdrant_path),
                                collection="test", dim=64)
        ctx = RunContext(settings=settings, store=store, router=router, embedder=embedder, vectorstore=vs)

        verdict = await judge(ctx, "## Report\n\nhttps://example.com link here")
        assert "scores" in verdict
        assert set(verdict["scores"]) == set(RUBRIC)
        assert any("heuristic" in n.lower() or "unavailable" in n.lower() for n in verdict["notes"])
        await store.close()


class TestRunQuality:
    @pytest.mark.asyncio
    async def test_run_quality_writes_files_and_persists_lessons(self, tmp_path):
        from hermes.pipeline.context import RunContext
        from hermes.storage.db import Store
        from hermes.llm.embed import Embedder
        from hermes.storage.vectorstore import build_vector_store

        settings = _settings(tmp_path)
        run_date = datetime(2026, 7, 11, tzinfo=timezone.utc)

        # Pre-write a report for the quality stage to read.
        settings.reports_dir.mkdir(parents=True, exist_ok=True)
        report_path = settings.reports_dir / "2026-07-11.md"
        report_text = (
            "## Executive Summary\n\n"
            "A report with [links](https://example.com/1) and substance.\n\n"
            "## References\n\n[1] source\n\n"
            "## Emerging Trends\n\nTrends here. " + "x" * 5000
        )
        report_path.write_text(report_text, encoding="utf-8")

        store = Store(settings.sqlite_url)
        await store.init()
        router = FakeRouter()
        embedder = Embedder(model="hashing", dim=64, normalize=True)
        vs = build_vector_store("numpy", store.session_factory,
                                qdrant_path=str(settings.qdrant_path),
                                collection="test", dim=64)
        ctx = RunContext(settings=settings, store=store, router=router, embedder=embedder, vectorstore=vs)

        rep = await run_quality(ctx, run_date, settings)

        # Quality report file
        assert Path(rep.path).exists()
        # JSON file
        json_path = settings.storage.dir / "quality" / f"{rep.run_date}.json"
        assert json_path.exists()
        json_data = json.loads(json_path.read_text())
        assert "hermes_score" in json_data
        assert "per_dimension" in json_data

        # Lessons persisted
        async with store.session() as s:
            lessons = (await s.execute(select(Lesson))).scalars().all()
        assert len(lessons) >= 1
        assert all(lk.kind == "quality" for lk in lessons)

        await store.close()

    @pytest.mark.asyncio
    async def test_run_quality_handles_missing_report(self, tmp_path):
        from hermes.pipeline.context import RunContext
        from hermes.storage.db import Store
        from hermes.llm.embed import Embedder
        from hermes.storage.vectorstore import build_vector_store

        settings = _settings(tmp_path)
        run_date = datetime(2026, 7, 11, tzinfo=timezone.utc)

        store = Store(settings.sqlite_url)
        await store.init()
        router = FakeRouter()
        embedder = Embedder(model="hashing", dim=64, normalize=True)
        vs = build_vector_store("numpy", store.session_factory,
                                qdrant_path=str(settings.qdrant_path),
                                collection="test", dim=64)
        ctx = RunContext(settings=settings, store=store, router=router, embedder=embedder, vectorstore=vs)

        rep = await run_quality(ctx, run_date, settings)
        assert "No report found" in rep.notes[0]
        assert rep.hermes_score == 0.0
        await store.close()


class TestRenderQuality:
    def test_render_includes_rubric_and_score(self):
        rep = QualityReport(
            run_date="2026-07-11",
            hermes_score=3.5,
            per_dimension={dim: 3.5 for dim in RUBRIC},
            notes=["note 1", "note 2"],
        )
        text = _render_quality(rep)
        assert "3.5/5" in text
        for dim in RUBRIC:
            assert dim in text
        assert "note 1" in text
        assert "note 2" in text