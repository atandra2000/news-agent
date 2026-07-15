"""Dev.to collector — no-auth public JSON, AI/ML tagged top articles. Fills the "community signal" gap left by Reddit removal."""

from __future__ import annotations

import asyncio

from newsagent.collectors.base import CollectorAdapter, RawItem
from newsagent.logging import get_logger

log = get_logger("collector.devto")

API = "https://dev.to/api/articles"

DEFAULT_TAGS = ["ai", "machinelearning", "llm", "deeplearning", "openai", "rag"]


class DevToCollector(CollectorAdapter):
    source_type = "devto"

    def __init__(
        self,
        tags: list[str] | None = None,
        *,
        per_page: int = 15,
        top_window_days: int = 7,
        timeout: float = 15.0,
    ):
        self.tags = tags or DEFAULT_TAGS
        self.per_page = per_page
        self.top_window = top_window_days
        self.timeout = timeout

    async def collect(self, *, since, limit: int = 50) -> list[RawItem]:
        import httpx

        sem = asyncio.Semaphore(4)
        seen: set[str] = set()
        items: list[RawItem] = []

        async def _one(tag: str) -> list[dict]:
            async with sem:
                try:
                    async with httpx.AsyncClient(timeout=self.timeout) as client:
                        resp = await client.get(
                            API,
                            params={"tag": tag, "top": self.top_window, "per_page": self.per_page},
                        )
                    if resp.status_code != 200:
                        return []
                    return resp.json() or []
                except Exception as exc:  # noqa: BLE001
                    log.warning("devto.tag_failed", tag=tag, error=str(exc))
                    return []

        results = await asyncio.gather(*[_one(t) for t in self.tags])
        for tag, batch in zip(self.tags, results):
            for a in batch:
                url = a.get("url", "")
                if not url or url in seen:
                    continue
                seen.add(url)
                title = a.get("title", "").strip()
                if not title:
                    continue
                items.append(
                    RawItem(
                        source_type=self.source_type,
                        title=f"[dev.to/{tag}] {title}",
                        url=url,
                        content=(a.get("description") or "")[:1500],
                        author=a.get("user", {}).get("username"),
                        published_at=since,
                        extra={
                            "reactions": a.get("public_reactions_count"),
                            "comments": a.get("comments_count"),
                            "tags": a.get("tag_list", []),
                        },
                    )
                )
                if len(items) >= limit:
                    break
            if len(items) >= limit:
                break

        log.info("devto.collected", count=len(items), tags=len(self.tags))
        return items[:limit]
