"""Collector registry + safe runner. No persistent circuit-breaker (HERMES_DESIGN §11.2): per-source timeout + retry-once + skip-on-failure — fine for a daily batch and guarantees "one dead API ≠ no report". Defaults exclude unreliable public-web sources (Reddit JSON, Papers-with-Code); gaps filled by Tavily/Context7/GitHub releases/Dev.to/Lobsters."""

from __future__ import annotations

import asyncio
from datetime import datetime

import httpx

from hermes.collectors.base import CollectorAdapter, RawItem
from hermes.collectors.arxiv import ArxivCollector
from hermes.collectors.bluesky import BlueskyCollector
from hermes.collectors.blog import BlogCollector
from hermes.collectors.context7 import Context7Collector
from hermes.collectors.devto import DevToCollector
from hermes.collectors.github_releases import GitHubReleaseCollector
from hermes.collectors.github_topic_search import GithubTopicSearchCollector
from hermes.collectors.github_trending import GithubTrendingCollector
from hermes.collectors.hn import HNCollector
from hermes.collectors.huggingface import HuggingFaceCollector
from hermes.collectors.lobsters import LobstersCollector
from hermes.collectors.openreview import OpenReviewCollector
from hermes.collectors.reddit import RedditCollector
from hermes.collectors.rss import RSSCollector
from hermes.collectors.semantic_scholar import SemanticScholarCollector
from hermes.collectors.tavily_search import TavilySearchCollector
from hermes.collectors.youtube import YouTubeCollector
from hermes.collectors.x_twitter import XTwitterCollector
from hermes.config import CollectorConfig, SearchConfig
from hermes.logging import get_logger

log = get_logger("collector.registry")


def _build_collectors() -> dict[str, type[CollectorAdapter]]:
    """Build registry, parametrizing collectors with search + collector config (resolved once at import; CLI loads .env at start, tests set collectors.enabled=[])."""
    search_cfg = SearchConfig()
    collector_cfg = CollectorConfig()

    tavily_cls = type(
        "TavilySearchCollectorConfigured",
        (TavilySearchCollector,),
        {"__init__": lambda self, **kw: TavilySearchCollector.__init__(
            self,
            api_key=search_cfg.tavily_api_key,
            base_url=search_cfg.tavily_base_url,
            max_results_per_query=6,
            search_depth="advanced",
            topic="news",
            days=7,
            timeout=search_cfg.timeout_seconds,
            **kw,
        )},
    )
    github_releases_cls = type(
        "GitHubReleaseCollectorConfigured",
        (GitHubReleaseCollector,),
        {"__init__": lambda self, **kw: GitHubReleaseCollector.__init__(
            self,
            github_token=collector_cfg.github_token,
            **kw,
        )},
    )
    context7_cls = type(
        "Context7CollectorConfigured",
        (Context7Collector,),
        {"__init__": lambda self, **kw: Context7Collector.__init__(
            self,
            api_key=collector_cfg.context7_api_key,
            **kw,
        )},
    )
    github_topic_search_cls = type(
        "GithubTopicSearchCollectorConfigured",
        (GithubTopicSearchCollector,),
        {"__init__": lambda self, **kw: GithubTopicSearchCollector.__init__(
            self,
            github_token=collector_cfg.github_token,
            **kw,
        )},
    )
    reddit_cls = type(
        "RedditCollectorConfigured",
        (RedditCollector,),
        {"__init__": lambda self, **kw: RedditCollector.__init__(self, **kw)},
    )
    x_twitter_cls = type(
        "XTwitterCollectorConfigured",
        (XTwitterCollector,),
        {"__init__": lambda self, **kw: XTwitterCollector.__init__(self, **kw)},
    )
    return {
        "arxiv": ArxivCollector,
        "rss": RSSCollector,
        "github_trending": GithubTrendingCollector,
        "github_topic_search": github_topic_search_cls,
        "huggingface": HuggingFaceCollector,
        "blog": BlogCollector,
        "hacker_news": HNCollector,
        "semantic_scholar": SemanticScholarCollector,
        "openreview": OpenReviewCollector,
        "bluesky": BlueskyCollector,
        "youtube": YouTubeCollector,
        "tavily": tavily_cls,
        "context7": context7_cls,
        "github_releases": github_releases_cls,
        "devto": DevToCollector,
        "lobsters": LobstersCollector,
        "reddit": reddit_cls,
        "x_twitter": x_twitter_cls,
    }


REGISTRY: dict[str, type[CollectorAdapter]] = _build_collectors()


def get_collector(name: str) -> CollectorAdapter:
    if name not in REGISTRY:
        raise KeyError(f"Unknown collector: {name}")
    return REGISTRY[name]()


async def run_collector(
    name: str,
    *,
    since: datetime,
    limit: int = 50,
    timeout: float = 30.0,
    retry_once: bool = True,
) -> list[RawItem]:
    """Run one collector with timeout + retry-once + skip-on-failure."""
    try:
        collector = get_collector(name)
    except KeyError as exc:
        log.error("collector.unknown", name=name, error=str(exc))
        return []
    attempt = 0
    max_attempts = 2 if retry_once else 1
    last_err: Exception | None = None
    while attempt < max_attempts:
        try:
            return await asyncio.wait_for(collector.collect(since=since, limit=limit), timeout=timeout)
        except (asyncio.TimeoutError, httpx.HTTPError, Exception) as exc:  # noqa: BLE001
            last_err = exc
            attempt += 1
            log.warning("collector.attempt_failed", name=name, attempt=attempt, error=str(exc))
    log.error("collector.skipped", name=name, error=str(last_err))
    return []
