"""Offline unit tests for dedup + embedding + collector registry."""

from __future__ import annotations

from datetime import datetime, timezone

from hermes.collectors.base import RawItem
from hermes.collectors.registry import REGISTRY, get_collector, run_collector
from hermes.dedup import Deduper, simhash
from hermes.llm.embed import Embedder, cosine


def test_simhash_near_dup():
    a = simhash("the quick brown fox jumps over the lazy dog")
    b = simhash("the quick brown fox jumps over the lazy dog.")
    c = simhash("completely different sentence about quantum computing gravity")
    assert simhash("").bit_length() >= 0
    assert (a ^ b).bit_count() <= 3  # punctuation-only diff is near-dup
    assert (a ^ c).bit_count() > 10


def test_deduper():
    d = Deduper()
    r1 = RawItem(source_type="rss", title="Same story", url="https://x/1", content="the model improves accuracy a lot today")
    r2 = RawItem(source_type="rss", title="Same story", url="https://x/2", content="the model improves accuracy a lot today")
    assert d.check(r1.uid, "the model improves accuracy a lot today").is_new
    d.add("the model improves accuracy a lot today", r1.uid)
    res = d.check(r2.uid, "the model improves accuracy a lot today")
    assert not res.is_new and res.is_near_dup


def test_embedder_normalized():
    e = Embedder(model="hashing", dim=128, normalize=True)
    v = e.encode_one("hello world")
    assert abs(float((v**2).sum() ** 0.5) - 1.0) < 1e-5
    assert 0.0 <= cosine(e.encode_one("hello world"), e.encode_one("hello world")) <= 1.0 + 1e-6


def test_collector_registry():
    assert set(REGISTRY) >= {"arxiv", "rss", "github_trending", "huggingface", "blog"}
    assert get_collector("arxiv").source_type == "arxiv"


def test_run_collector_skip_on_failure():
    import asyncio

    # Force a bad collector name path -> skip gracefully returns [].
    out = asyncio.run(run_collector("does_not_exist", since=datetime.now(timezone.utc)))
    assert out == []


def test_rss_collector_continues_after_per_feed_404(monkeypatch):
    """One feed 404s, the other returns 200: collect() returns the 200 feed's items
    and does not raise. Locks in the per-feed fail-open contract from Task 6."""
    import asyncio
    import httpx

    from hermes.collectors.rss import RSSCollector

    bad_url = "https://example.invalid/rss-broken.xml"
    good_url = "https://example.valid/rss-good.xml"
    good_xml = (
        '<?xml version="1.0"?>'
        '<rss version="2.0"><channel>'
        '<title>Good feed</title>'
        '<link>https://example.valid</link>'
        '<description>Test feed</description>'
        '<item>'
        '<title>Survivor item</title>'
        '<link>https://example.valid/post-1</link>'
        '<description>Survivor content</description>'
        '<pubDate>Mon, 14 Jul 2026 10:00:00 +0000</pubDate>'
        '</item>'
        '</channel></rss>'
    )

    class FakeResponse:
        def __init__(self, status_code: int, text: str = ""):
            self.status_code = status_code
            self.text = text

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"{self.status_code} {bad_url}", request=None, response=None
                )

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url, *a, **kw):
            if url == bad_url:
                return FakeResponse(404)
            return FakeResponse(200, text=good_xml)

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    collector = RSSCollector(feeds=[bad_url, good_url])
    items = asyncio.run(collector.collect(since=datetime(2026, 7, 1, tzinfo=timezone.utc), limit=10))
    assert len(items) == 1
    assert items[0].title == "Survivor item"
    assert items[0].url == "https://example.valid/post-1"
    assert items[0].source_type == "rss"
