"""Web search providers for live research grounding.

Default backend is ``none`` (no network) so the pipeline always writes a report;
set ``HERMES_SEARCH_BACKEND=tavily`` + ``HERMES_SEARCH_TAVILY_API_KEY`` for real
web research via the Tavily API.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from hermes.config import SearchConfig
from hermes.logging import get_logger

log = get_logger("brief.search")

_URL_RE = re.compile(r"https?://\S+")

# Tavily request defaults — kept here as module-level constants so the
# ``SearchConfig`` surface stays minimal (Task 4 removed ``topic``,
# ``include_raw_content``, and ``search_depth`` from config).
_TAVILY_TOPIC = "news"
_TAVILY_INCLUDE_RAW_CONTENT = True
_TAVILY_SEARCH_DEPTH = "advanced"


@dataclass
class SearchResult:
    title: str
    url: str
    content: str = ""
    published_date: str | None = None
    source: str | None = None
    # Per-item extras carried from the collector (e.g. RSS per-feed category
    # stamp). Coverage logic consults this first before falling back to
    # source-type → category mapping.
    extra: dict = field(default_factory=dict)


class SearchProvider(Protocol):
    name: str

    async def search(self, query: str, *, max_results: int) -> list[SearchResult]:
        ...


class NullSearch:
    """No live search. Returns nothing; synthesis falls back to parametric knowledge."""

    name = "null"

    async def search(self, query: str, *, max_results: int) -> list[SearchResult]:
        return []


class TavilySearch:
    name = "tavily"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.tavily.com",
        timeout: float = 30.0,
        *,
        days: int | None = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.topic = _TAVILY_TOPIC
        self.days = days
        self.include_raw_content = _TAVILY_INCLUDE_RAW_CONTENT
        self.search_depth = _TAVILY_SEARCH_DEPTH

    async def search(self, query: str, *, max_results: int) -> list[SearchResult]:
        payload: dict = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": self.search_depth,
            "include_raw_content": self.include_raw_content,
        }
        if self.topic:
            payload["topic"] = self.topic
        if self.days is not None:
            payload["days"] = self.days
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.base_url}/search", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            log.warning("tavily.failed", query=query, error=str(exc))
            return []

        out: list[SearchResult] = []
        for r in data.get("results", []):
            url = r.get("url", "")
            if not url:
                continue
            # Prefer longer raw content; fall back to snippet.
            raw = r.get("raw_content") or ""
            content = (raw or r.get("content") or "")
            out.append(
                SearchResult(
                    title=r.get("title", ""),
                    url=url,
                    content=content[:2000],
                    published_date=r.get("published_date"),
                    source=_host(url),
                )
            )
        return out


def _host(url: str) -> str:
    m = re.match(r"https?://([^/]+)/?", url)
    return m.group(1) if m else url


def build_search_provider(settings: SearchConfig | None = None, *, days: int | None = None) -> SearchProvider:
    cfg = settings or SearchConfig()
    if cfg.backend == "tavily":
        if not cfg.tavily_api_key:
            log.warning("search.tavily_no_key", falling_back="null")
            return NullSearch()
        return TavilySearch(
            api_key=cfg.tavily_api_key,
            base_url=cfg.tavily_base_url,
            timeout=cfg.timeout_seconds,
            days=days,
        )
    return NullSearch()


def dedup_sources(results: list[SearchResult], *, limit: int = 60) -> list[SearchResult]:
    """Collapse duplicates by URL and cap to ``limit`` (first-seen order)."""
    seen: set[str] = set()
    out: list[SearchResult] = []
    for r in results:
        if r.url in seen:
            continue
        seen.add(r.url)
        out.append(r)
        if len(out) >= limit:
            break
    return out


def content_fingerprint(result: SearchResult) -> str:
    """Stable fingerprint for cross-posts of the SAME story on the SAME host.

    Hacker News reposts (e.g. Cat's grant posted 3×) get unique URLs because
    each repost has its own item ID, so URL-dedup misses them. They share a
    normalized title on the same host though — this captures that.

    Two ``SearchResult``s with the same fingerprint are the same story
    posted more than once; the dedup pass below keeps the first and treats
    the rest as cross-posts.
    """
    title = re.sub(r"\W+", " ", (result.title or "").lower()).strip()
    return f"{_host(result.url)}::{title}"


def dedup_sources_with_cross_posts(
    results: list[SearchResult],
    *,
    limit: int = 60,
) -> tuple[list[SearchResult], list[list[SearchResult]]]:
    """URL-dedup + cross-post-dedup. Returns (deduped, cross_post_groups).

    ``cross_post_groups`` is a list of groups where each group contains the
    canonical first-seen result and its duplicates (URLs that pointed to
    the same story on the same host). The writer prompt can use this list
    to cite a story once and note "cross-posted N times" instead of treating
    each repost as an independent signal — the 2026-07-13 monthly report
    cited the Cat's grant HN repost 3× as if it were 3 independent signals.
    """
    url_seen: set[str] = set()
    fp_seen: dict[str, SearchResult] = {}
    out: list[SearchResult] = []
    cross_posts: list[list[SearchResult]] = []
    for r in results:
        if r.url in url_seen:
            continue
        url_seen.add(r.url)
        fp = content_fingerprint(r)
        if fp in fp_seen:
            # Cross-post of an earlier story — append to that group.
            # Find the existing group and append; or create a new one for the
            # canonical (the canonical is in `out`, find it there).
            for grp in cross_posts:
                if content_fingerprint(grp[0]) == fp:
                    grp.append(r)
                    break
            else:
                # Canonical isn't yet in a group — start one. (URL-dedup
                # already accepted the canonical on its first pass; the
                # cross-post dedup is the second pass.)
                cross_posts.append([fp_seen[fp], r])
            continue
        fp_seen[fp] = r
        out.append(r)
        if len(out) >= limit:
            break
    return out, cross_posts


def duplication_collapse_rate(original: int, deduped: int) -> float:
    """Fraction of sources dropped as duplicates (0.0 = no dedup, 1.0 = all dupes)."""
    if original <= 0:
        return 0.0
    return max(0.0, min(1.0, (original - deduped) / original))
