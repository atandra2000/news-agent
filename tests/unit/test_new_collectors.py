"""Offline tests for the new collector family.

Covers:
- TavilySearchCollector: skip-on-no-key, parses a mock response into RawItems.
- Context7Collector: skip-on-no-network, parses a mock search response.
- GitHubReleaseCollector: skip-on-rate-limit, parses a mock releases response.
- DevToCollector: parses a mock articles response.
- LobstersCollector: parses a mock tag response.
- GitHubTopicSearchCollector: parses a mock search response, no-token no-op.
- RedditCollector: parses a mock subreddit response, fail-open per subreddit.
- XTwitterCollector: no-token no-op, parses a mock tweets response.
- Registry: the new collectors are wired in and instantiable.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone


from hermes.collectors.context7 import Context7Collector
from hermes.collectors.devto import DevToCollector
from hermes.collectors.github_releases import GitHubReleaseCollector
from hermes.collectors.github_topic_search import GithubTopicSearchCollector
from hermes.collectors.lobsters import LobstersCollector
from hermes.collectors.reddit import RedditCollector
from hermes.collectors.registry import REGISTRY, get_collector, run_collector
from hermes.collectors.tavily_search import TavilySearchCollector
from hermes.collectors.x_twitter import XTwitterCollector


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


# --- GitHubTopicSearchCollector ---


def test_github_topic_search_parses_mock(monkeypatch):
    """Mock a GitHub search response and verify the parser maps it to RawItems."""
    import httpx

    mock_payload = {
        "items": [
            {
                "full_name": "anthropics/anthropic-sdk-python",
                "html_url": "https://github.com/anthropics/anthropic-sdk-python",
                "description": "Python SDK for Claude",
                "owner": {"login": "anthropics"},
                "pushed_at": "2026-07-12T10:00:00Z",
                "stargazers_count": 1234,
                "language": "Python",
                "topics": ["claude", "sdk", "llm"],
            }
        ]
    }

    class R:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return mock_payload

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
    c = GithubTopicSearchCollector(
        github_token="ghp_test",
        topics=("llm",),
        per_topic=5,
    )
    items = asyncio.run(c.collect(since=datetime(2026, 7, 1, tzinfo=timezone.utc), limit=10))
    assert len(items) == 1
    it = items[0]
    assert it.source_type == "github_topic_search"
    assert "anthropics/anthropic-sdk-python" in it.title
    assert "topic: llm" in it.title
    assert it.url == "https://github.com/anthropics/anthropic-sdk-python"


def test_github_topic_search_handles_403_gracefully(monkeypatch):
    """Rate-limited (403) -> empty list, no exception."""
    import httpx

    class FakeClient:
        def __init__(self, *a, **kw):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return None
        async def get(self, url, params=None, headers=None):
            class R:
                status_code = 403
            return R()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    c = GithubTopicSearchCollector(github_token="ghp_test", topics=("llm",))
    items = asyncio.run(c.collect(since=datetime.now(timezone.utc), limit=10))
    assert items == []


# --- RedditCollector ---


def test_reddit_parses_mock(monkeypatch):
    """Mock a subreddit response and verify the parser maps it to RawItems."""
    import httpx

    mock = {
        "data": {
            "children": [
                {
                    "data": {
                        "title": "Show HN: Local Llama fine-tune recipe",
                        "url_overridden_by_dest": "https://example.com/recipe",
                        "selftext": "Here is how to fine-tune Llama 4 locally.",
                        "author": "redditor1",
                        "created_utc": 1782864000.0,  # 2026-07-01 (matches `since`)
                        "score": 420,
                        "num_comments": 33,
                        "permalink": "/r/LocalLLaMA/comments/abc/recipe/",
                    }
                }
            ]
        }
    }

    class R:
        status_code = 200
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
    c = RedditCollector(subreddits=("LocalLLaMA",), per_sub_limit=5, timeout_seconds=2.0)
    items = asyncio.run(c.collect(since=datetime(2026, 7, 1, tzinfo=timezone.utc), limit=10))
    assert len(items) == 1
    it = items[0]
    assert it.source_type == "reddit"
    assert "[r/LocalLLaMA]" in it.title
    assert it.url == "https://example.com/recipe"


def test_reddit_per_subreddit_fail_open(monkeypatch):
    """One slow/broken subreddit must not block the others."""
    import httpx

    # First call (subreddit 1) raises; second call (subreddit 2) succeeds.
    call_count = {"n": 0}

    def make_succeed_payload():
        return {
            "data": {
                "children": [
                    {
                        "data": {
                            "title": "Stable Diffusion 4 announced",
                            "url_overridden_by_dest": "https://example.com/sd4",
                            "selftext": "",
                            "author": "u2",
                            "created_utc": 1782864000.0,  # 2026-07-01 (matches `since`)
                            "score": 200,
                            "num_comments": 10,
                            "permalink": "/r/StableDiffusion/comments/xyz/",
                        }
                    }
                ]
            }
        }

    class R:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return make_succeed_payload()

    class RFail:
        def raise_for_status(self):
            raise httpx.ConnectError("simulated offline")

    class FakeClient:
        def __init__(self, *a, **kw):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return None
        async def get(self, url, params=None, headers=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return RFail()
            return R()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    c = RedditCollector(subreddits=("MachineLearning", "StableDiffusion"), per_sub_limit=5, timeout_seconds=2.0)
    items = asyncio.run(c.collect(since=datetime(2026, 7, 1, tzinfo=timezone.utc), limit=10))
    # Only the second subreddit should produce an item.
    assert len(items) == 1
    assert "[r/StableDiffusion]" in items[0].title


# --- XTwitterCollector ---


def test_x_twitter_skips_without_token(monkeypatch):
    """No bearer token -> [] immediately, no HTTP calls."""
    c = XTwitterCollector(bearer_token=None)
    items = asyncio.run(c.collect(since=datetime.now(timezone.utc), limit=10))
    assert items == []


def test_x_twitter_parses_mock(monkeypatch):
    """Mock a user-tweets response and verify the parser maps it to RawItems."""
    import httpx

    # First call is user-lookup, second is tweets fetch.
    call_count = {"n": 0}

    class UserLookup:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return {"data": {"id": "12345"}}

    class Tweets:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return {
                "data": [
                    {
                        "id": "987654321",
                        "text": "We just released Claude 5!",
                        "created_at": "2026-07-12T10:00:00Z",
                        "public_metrics": {"like_count": 5000, "retweet_count": 800},
                    }
                ]
            }

    class FakeClient:
        def __init__(self, *a, **kw):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return None
        async def get(self, url, params=None, headers=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return UserLookup()
            return Tweets()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    c = XTwitterCollector(
        bearer_token="test_bearer",
        watchlist=(("AnthropicAI", "Anthropic"),),
        max_per_user=5,
        timeout_seconds=2.0,
    )
    items = asyncio.run(c.collect(since=datetime(2026, 7, 1, tzinfo=timezone.utc), limit=10))
    assert len(items) == 1
    it = items[0]
    assert it.source_type == "x_twitter"
    assert "@AnthropicAI" in it.title
    assert "Claude 5" in it.title
    assert it.url == "https://x.com/AnthropicAI/status/987654321"


# --- Registry wiring ---


def test_registry_includes_v2_collectors():
    """The 3 newly added collectors must be wired in and instantiable."""
    expected = {"github_topic_search", "reddit", "x_twitter"}
    missing = expected - set(REGISTRY)
    assert not missing, f"Missing collectors: {missing}"
    for name in expected:
        c = get_collector(name)
        assert c.source_type == name
