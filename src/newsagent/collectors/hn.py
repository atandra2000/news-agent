"""Hacker News collector via the Algolia HN search API (no auth)."""

from __future__ import annotations
from datetime import datetime

import httpx

from newsagent.collectors.base import CollectorAdapter, RawItem
from newsagent.logging import get_logger

log = get_logger("collector.hn")
URL = "https://hn.algolia.com/api/v1/search_by_date"
QUERY = "ai OR llm OR machine learning OR deep learning"


class HNCollector(CollectorAdapter):
    source_type = "hacker_news"

    def __init__(self, query: str | None = None, tags: str = "story"):
        self.query = query or QUERY
        self.tags = tags

    async def collect(self, *, since: datetime, limit: int = 50) -> list[RawItem]:
        items: list[RawItem] = []
        params = {"query": self.query, "tags": self.tags, "hitsPerPage": min(limit, 50)}
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(URL, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            log.warning("hn.fetch_failed", error=str(exc))
            return items

        for hit in data.get("hits", []):
            title = hit.get("title") or hit.get("story_title") or ""
            if not title:
                continue
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID','')}"
            points = hit.get("points") or 0
            num_comments = hit.get("num_comments") or 0
            items.append(
                RawItem(
                    source_type=self.source_type,
                    title=title,
                    url=url,
                    content=(hit.get("story_text") or "")[:1000],
                    author=hit.get("author"),
                    published_at=since,
                    extra={"points": points, "comments": num_comments, "hn_id": hit.get("objectID")},
                )
            )
        log.info("hn.collected", count=len(items))
        return items[:limit]
