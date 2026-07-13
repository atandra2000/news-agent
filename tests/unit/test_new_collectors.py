"""Offline tests for the new collector family.

Covers:
- TavilySearchCollector: skip-on-no-key, parses a mock response into RawItems.
- Context7Collector: skip-on-no-network, parses a mock search response.
- GitHubReleaseCollector: skip-on-rate-limit, parses a mock releases response.
- DevToCollector: parses a mock articles response.
- LobstersCollector: parses a mock tag response.
- Registry: the new collectors are wired in and instantiable.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone


from hermes.collectors.context7 import Context7Collector
from hermes.collectors.devto import DevToCollector
from hermes.collectors.github_releases import GitHubReleaseCollector
from hermes.collectors.lobsters import LobstersCollector
from hermes.collectors.registry import REGISTRY, get_collector, run_collector
from hermes.collectors.tavily_search import TavilySearchCollector


def test_registry_includes_new_collectors():
    """All five new collectors must be wired in and instantiable."""
    expected = {
        "tavily",
        "context7",
        "github_releases",
        "devto",
        "lobsters",
    }
    missing = expected - set(REGISTRY)
    assert not missing, f"Missing collectors: {missing}"
    for name in expected:
        c = get_collector(name)
        assert c.source_type == name


def test_tavily_skips_without_key():
    """No API key -> logs and returns [] without raising."""
    c = TavilySearchCollector(api_key=None)
    items = asyncio.run(c.collect(since=datetime.now(timezone.utc), limit=10))
    assert items == []


def test_context7_returns_empty_on_unreachable(monkeypatch):
    """No network -> each lib returns None, collect returns []."""
    import httpx

    async def fake_get(*args, **kwargs):
        raise httpx.ConnectError("simulated offline")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    c = Context7Collector(libraries=["react", "pytorch"], timeout=2.0)
    items = asyncio.run(c.collect(since=datetime.now(timezone.utc), limit=10))
    assert items == []


def test_github_releases_parses_mock(monkeypatch):
    """Mock a GitHub API response and verify the parser maps it to RawItems."""
    import httpx

    mock_response = [
        {
            "tag_name": "v1.0.0",
            "name": "Major release",
            "html_url": "https://github.com/pytorch/pytorch/releases/tag/v1.0.0",
            "published_at": "2026-07-10T12:00:00Z",
            "body": "Big release notes",
            "author": {"login": "pytorch-bot"},
            "prerelease": False,
        }
    ]

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url, params=None, headers=None):
            class R:
                status_code = 200
                def json(self):
                    return mock_response
            return R()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    c = GitHubReleaseCollector(repos=["pytorch/pytorch"], timeout=2.0)
    items = asyncio.run(c.collect(since=datetime(2026, 7, 1, tzinfo=timezone.utc), limit=10))
    assert len(items) == 1
    it = items[0]
    assert it.source_type == "github_releases"
    assert "pytorch/pytorch" in it.title
    assert "v1.0.0" in it.title
    assert it.url.endswith("/releases/tag/v1.0.0")


def test_github_releases_handles_403_gracefully(monkeypatch):
    """Rate-limited (403) -> empty list, no exception."""
    import httpx

    class R:
        status_code = 403

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url, params=None, headers=None):
            return R()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    c = GitHubReleaseCollector(repos=["a/b"], timeout=2.0)
    items = asyncio.run(c.collect(since=datetime.now(timezone.utc), limit=10))
    assert items == []


def test_devto_parses_mock(monkeypatch):
    import httpx

    mock_articles = [
        {
            "url": "https://dev.to/example/llm-tips",
            "title": "10 Tips for LLM Production",
            "description": "Some great tips",
            "user": {"username": "alice"},
            "public_reactions_count": 42,
            "comments_count": 7,
            "tag_list": ["llm", "ai"],
        }
    ]

    class R:
        status_code = 200
        text = "[]"
        def json(self):
            return mock_articles

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url, params=None, headers=None):
            return R()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    c = DevToCollector(tags=["llm"], timeout=2.0)
    items = asyncio.run(c.collect(since=datetime.now(timezone.utc), limit=10))
    assert len(items) == 1
    assert items[0].source_type == "devto"
    assert "10 Tips" in items[0].title


def test_lobsters_parses_mock(monkeypatch):
    import httpx

    mock = [
        {
            "url": "https://example.com/article",
            "title": "An article about Rust and ML",
            "description": "Cool stuff",
            "submitter_user": {"username": "bob"},
            "score": 50,
            "comment_count": 5,
            "tags": ["ml", "rust"],
        }
    ]

    class R:
        status_code = 200
        headers = {"content-type": "application/json"}
        def raise_for_status(self):
            pass
        def json(self):
            return mock

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url, params=None, headers=None):
            return R()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    c = LobstersCollector(relevant_tags={"ml", "rust"}, timeout=2.0)
    items = asyncio.run(c.collect(since=datetime.now(timezone.utc), limit=10))
    assert len(items) == 1
    assert items[0].source_type == "lobsters"


def test_run_collector_unknown_returns_empty():
    """Unknown collector name -> skip gracefully returns []."""
    out = asyncio.run(run_collector("does_not_exist", since=datetime.now(timezone.utc)))
    assert out == []
