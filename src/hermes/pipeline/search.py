"""Web search providers for live research grounding.

Default backend is ``none`` (no network) so the pipeline always writes a report;
set ``HERMES_SEARCH_BACKEND=tavily`` + ``HERMES_SEARCH_TAVILY_API_KEY`` for real
web research via the Tavily API.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
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
