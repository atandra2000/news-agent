"""YouTube collector (Data API v3). Env-gated: requires HERMES_YOUTUBE_API_KEY.
Skips gracefully when unset (HERMES_DESIGN §11.2).
"""

from __future__ import annotations
from datetime import datetime

import os

import httpx

from hermes.collectors.base import CollectorAdapter, RawItem
from hermes.logging import get_logger

log = get_logger("collector.youtube")
SEARCH = "https://www.googleapis.com/youtube/v3/search"
QUERY = "AI research lecture OR large language model explained"


class YouTubeCollector(CollectorAdapter):
    source_type = "youtube"

    def __init__(self, query: str | None = None):
        self.query = query or QUERY

    async def collect(self, *, since: datetime, limit: int = 50) -> list[RawItem]:
        api_key = os.environ.get("HERMES_YOUTUBE_API_KEY")
        if not api_key:
            log.info("youtube.skipped_no_key")
            return []
        items: list[RawItem] = []
        params = {
            "part": "snippet",
            "q": self.query,
            "type": "video",
            "maxResults": min(limit, 50),
            "order": "date",
            "key": api_key,
        }
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(SEARCH, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            log.warning("youtube.fetch_failed", error=str(exc))
            return items

        for v in data.get("items", []):
            snippet = v.get("snippet", {})
            vid = v.get("id", {}).get("videoId", "")
            title = snippet.get("title", "")
            if not title:
                continue
            items.append(
                RawItem(
                    source_type=self.source_type,
                    title=f"[YouTube] {title}",
                    url=f"https://www.youtube.com/watch?v={vid}",
                    content=snippet.get("description", "")[:500],
                    author=snippet.get("channelTitle"),
                    published_at=since,
                    extra={"channel": snippet.get("channelTitle")},
                )
            )
        log.info("youtube.collected", count=len(items))
        return items[:limit]
