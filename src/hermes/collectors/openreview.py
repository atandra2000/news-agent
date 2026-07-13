"""OpenReview collector (public API). Surfaces recent submissions/abstracts."""

from __future__ import annotations
from datetime import datetime

import httpx

from hermes.collectors.base import CollectorAdapter, RawItem
from hermes.logging import get_logger

log = get_logger("collector.openreview")
SEARCH = "https://api.openreview.net/notes/search"
TERM = "large language model"


class OpenReviewCollector(CollectorAdapter):
    source_type = "openreview"

    def __init__(self, term: str | None = None):
        self.term = term or TERM

    async def collect(self, *, since: datetime, limit: int = 50) -> list[RawItem]:
        items: list[RawItem] = []
        params = {"term": self.term, "content": "title", "source": "forum", "limit": min(limit, 50)}
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(SEARCH, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            log.warning("openreview.fetch_failed", error=str(exc))
            return items

        for note in data.get("notes", []):
            content = note.get("content", {})
            title = (content.get("title") or {}).get("value") if isinstance(content.get("title"), dict) else content.get("title")
            if not title:
                continue
            nid = note.get("id", "")
            abstract = (content.get("abstract") or {}).get("value") if isinstance(content.get("abstract"), dict) else content.get("abstract") or ""
            items.append(
                RawItem(
                    source_type=self.source_type,
                    title=f"[OpenReview] {title}",
                    url=f"https://openreview.net/forum?id={nid}",
                    content=(abstract or "")[:2000],
                    published_at=since,
                    extra={"note_id": nid},
                )
            )
        log.info("openreview.collected", count=len(items))
        return items[:limit]
