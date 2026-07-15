"""Lobsters collector — public JSON, no auth, rarely rate-limited. Per-tag /tag/<name>.json endpoints 404 on current deploy, so we pull /hottest.json and filter client-side by AI_RELEVANT_TAGS."""

from __future__ import annotations

from newsagent.collectors.base import CollectorAdapter, RawItem
from newsagent.collectors.http import aget_json
from newsagent.logging import get_logger

log = get_logger("collector.lobsters")

API = "https://lobste.rs/hottest.json"

# AI/programming-relevant tags; keep posts matching at least one.
AI_RELEVANT_TAGS = {
    "ai", "vibecoding", "compsci", "programming", "plt", "release", "plt",
    "python", "rust", "go", "haskell", "lisp", "scala", "swift", "zig",
}


class LobstersCollector(CollectorAdapter):
    source_type = "lobsters"

    def __init__(
        self,
        *,
        relevant_tags: set[str] | None = None,
        limit: int = 50,
        timeout: float = 15.0,
    ):
        self.relevant_tags = relevant_tags or AI_RELEVANT_TAGS
        self.limit = limit
        self.timeout = timeout

    async def collect(self, *, since, limit: int = 50) -> list[RawItem]:
        try:
            data = await aget_json(API, retries=1, backoff=2.0, timeout=self.timeout)
        except Exception as exc:  # noqa: BLE001
            log.warning("lobsters.fetch_failed", error=str(exc))
            return []

        seen: set[str] = set()
        items: list[RawItem] = []
        for a in data or []:
            tags = set(a.get("tags") or [])
            if not (tags & self.relevant_tags):
                continue
            url = a.get("url") or a.get("comments_url", "")
            if not url or url in seen:
                continue
            seen.add(url)
            title = a.get("title", "").strip()
            if not title:
                continue
            submitter = a.get("submitter_user")
            author = submitter.get("username") if isinstance(submitter, dict) else None
            items.append(
                RawItem(
                    source_type=self.source_type,
                    title=f"[lobsters] {title}",
                    url=url,
                    content=(a.get("description") or "")[:1500],
                    author=author,
                    published_at=since,
                    extra={
                        "score": a.get("score"),
                        "comments": a.get("comment_count"),
                        "tags": list(tags),
                    },
                )
            )
            if len(items) >= limit:
                break

        log.info("lobsters.collected", count=len(items))
        return items[:limit]
