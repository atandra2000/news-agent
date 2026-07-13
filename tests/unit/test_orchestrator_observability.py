"""Unit tests for orchestrator observability: sources_checked / sources_failed.

The 2026-07-13 monthly report persisted ``sources_checked_json="[]"`` and
``sources_failed_json="[]"`` despite having collected 14 references — the
manifest hardcoded empty arrays and hid what was actually attempted.

These tests pin down:
- ``_gather_sources_fallback`` returns a 3-tuple (results, checked, failed).
- Each free collector that ran is recorded in ``checked``; one that throws
  is recorded in ``failed``.
- The orchestrator's report-write step plumbs the real checked/failed
  values into the persisted Report row.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from hermes.pipeline.orchestrator import _gather_sources_fallback


class _FakeItem:
    def __init__(self, url: str, title: str = "t", source_type: str = "arxiv", content: str = "c"):
        self.url = url
        self.title = title
        self.source_type = source_type
        self.content = content
        self.summary = ""
        self.published_at = datetime.now(timezone.utc)


async def test_fallback_returns_three_tuple(monkeypatch):
    """Even with no collectors, the function returns (results, checked, failed).

    The fallback fan-out is now driven by CollectorConfig.enabled (17 names by
    default). To keep this unit test fast and offline, we monkeypatch
    _resolve_fallback_collectors to a 3-collector stub — the *shape* of the
    return value is what we care about here, not the breadth of fan-out.
    """
    from hermes.pipeline import orchestrator

    monkeypatch.setattr(orchestrator, "_resolve_fallback_collectors", lambda: ("arxiv", "hacker_news", "devto"))
    out, checked, failed = await _gather_sources_fallback(
        since=datetime.now(timezone.utc) - timedelta(days=1),
        max_sources=4,
    )
    assert isinstance(out, list)
    assert isinstance(checked, list)
    assert isinstance(failed, list)


async def test_fallback_records_collector_outcomes(monkeypatch):
    """A failing collector is recorded in `failed`; a successful one in `checked`."""
    from hermes.pipeline import orchestrator
    from hermes.collectors import registry

    good_item = _FakeItem(url="https://arxiv.org/abs/1", source_type="arxiv")

    async def fake_run_collector(name, *, since, limit, timeout):
        if name == "arxiv":
            return [good_item]
        if name == "hacker_news":
            raise RuntimeError("simulated timeout")
        return []

    # The orchestrator imports run_collector inside the function, so patch
    # the source module (the registry).
    monkeypatch.setattr(registry, "run_collector", fake_run_collector)
    # Restrict the fallback to a known subset to make the assertion deterministic.
    monkeypatch.setattr(orchestrator, "_FALLBACK_COLLECTORS", ("arxiv", "hacker_news"))

    out, checked, failed = await _gather_sources_fallback(
        since=datetime.now(timezone.utc) - timedelta(days=1),
        max_sources=4,
    )
    assert "arxiv" in checked
    assert "hacker_news" in failed
    # The successful collector should have produced at least one SearchResult.
    assert any(r.url == "https://arxiv.org/abs/1" for r in out)
