"""Tavily web-search collector (live AI/ML news). Skip-safe: returns [] when
HERMES_SEARCH_TAVILY_API_KEY is unset. Key sourced from SearchConfig.
"""

from __future__ import annotations

import asyncio

from hermes.collectors.base import CollectorAdapter, RawItem
from hermes.config import SearchConfig
from hermes.logging import get_logger

log = get_logger("collector.tavily")

# High-signal AI/ML news queries.
DEFAULT_QUERIES = [
    "new large language model release",
    "open source LLM benchmark result",
    "AI agent framework release",
    "multimodal model launch",
    "machine learning research paper breakthrough",
    "AI startup funding announcement",
    "GPU training infrastructure announcement",
]


class TavilySearchCollector(CollectorAdapter):
    source_type = "tavily"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.tavily.com",
        queries: list[str] | None = None,
        *,
        max_results_per_query: int = 8,
        search_depth: str = "advanced",
        topic: str = "news",
        days: int = 7,
        timeout: float = 30.0,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.queries = queries or DEFAULT_QUERIES
        self.max_results_per_query = max_results_per_query
        self.search_depth = search_depth
        self.topic = topic
        self.days = days
        self.timeout = timeout

    @classmethod
    def from_config(cls, cfg: SearchConfig | None = None) -> "TavilySearchCollector":
        """Build from SearchConfig (key source of truth)."""
        cfg = cfg or SearchConfig()
        return cls(
            api_key=cfg.tavily_api_key,
            base_url=cfg.tavily_base_url,
            max_results_per_query=6,
            search_depth="advanced",
            topic="news",
            days=7,
            timeout=cfg.timeout_seconds,
        )

    async def collect(self, *, since, limit: int = 50) -> list[RawItem]:
        if not self.api_key:
            log.info("tavily.skipped_no_key", hint="set HERMES_SEARCH_TAVILY_API_KEY to enable")
            return []

        import httpx

        sem = asyncio.Semaphore(4)

        def payload_for(q: str) -> dict:
            return {
                "api_key": self.api_key,
                "query": q,
                "max_results": self.max_results_per_query,
                "search_depth": self.search_depth,
                "topic": self.topic,
                "days": self.days,
                "include_raw_content": False,
            }

        async def _post(q: str) -> list[dict]:
            async with sem:
                try:
                    async with httpx.AsyncClient(timeout=self.timeout) as client:
                        resp = await client.post(f"{self.base_url}/search", json=payload_for(q))
                        resp.raise_for_status()
                        return resp.json().get("results", [])
                except Exception as exc:  # noqa: BLE001
                    log.warning("tavily.query_failed", query=q, error=str(exc))
                    return []

        batches = await asyncio.gather(*[_post(q) for q in self.queries])

        # Dedupe by URL.
        seen: set[str] = set()
        items: list[RawItem] = []
        for batch in batches:
            for r in batch or []:
                url = r.get("url", "")
                if not url or url in seen:
                    continue
                seen.add(url)
                title = (r.get("title") or "").strip()
                if not title:
                    continue
                items.append(
                    RawItem(
                        source_type=self.source_type,
                        title=f"[tavily] {title}",
                        url=url,
                        content=(r.get("content") or "")[:2000],
                        published_at=since,
                        extra={
                            "host": _host(url),
                            "score": r.get("score"),
                            "query": r.get("query"),
                        },
                    )
                )
                if len(items) >= limit:
                    break
            if len(items) >= limit:
                break

        log.info("tavily.collected", count=len(items), queries=len(self.queries))
        return items[:limit]


def _host(url: str) -> str:
    import re

    m = re.match(r"https?://([^/]+)/?", url)
    return m.group(1) if m else url
