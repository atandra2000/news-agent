"""Reddit JSON collector. Public endpoints (no auth), four AI-focused
subreddits, per-subreddit timeout + fail-open.

Ponytail: reddit.com/r/{sub}/{sort}.json is the simplest API on earth —
no auth, no key, returns JSON. Each subreddit is one GET; failures on
one don't block the others. Removed in the 2026-07-14 cleanup as
"unreliable" — re-added with explicit per-call timeout (3s) so a slow
subreddit can't block the run.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx

from hermes.collectors.base import CollectorAdapter, RawItem
from hermes.logging import get_logger

log = get_logger("collector.reddit")

# Curated AI subreddits. The prompts explicitly reference 4 of these.
DEFAULT_SUBREDDITS: tuple[str, ...] = (
    "MachineLearning",
    "LocalLLaMA",
    "singularity",
    "StableDiffusion",
)

BASE_URL = "https://www.reddit.com/r/{sub}/top.json"
DEFAULT_TIMEOUT = 3.0  # seconds per subreddit
DEFAULT_LIMIT = 25  # posts per subreddit


class RedditCollector(CollectorAdapter):
    source_type = "reddit"

    def __init__(
        self,
        subreddits: tuple[str, ...] | None = None,
        per_sub_limit: int = DEFAULT_LIMIT,
        timeout_seconds: float = DEFAULT_TIMEOUT,
        user_agent: str = "hermes-research-agent/0.1 (https://github.com/AtandraBharati/hermes)",
    ):
        self.subreddits = subreddits or DEFAULT_SUBREDDITS
        self.per_sub_limit = per_sub_limit
        self.timeout_seconds = timeout_seconds
        # Reddit blocks requests with the default Python user-agent. Set a
        # custom one that points at the project.
        self.user_agent = user_agent

    async def collect(self, *, since: datetime, limit: int = 50) -> list[RawItem]:
        items: list[RawItem] = []
        cutoff = since.timestamp()
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": self.user_agent},
        ) as client:
            for sub in self.subreddits:
                try:
                    resp = await client.get(
                        BASE_URL.format(sub=sub),
                        params={"t": "week", "limit": str(self.per_sub_limit)},
                    )
                    resp.raise_for_status()
                    payload = resp.json()
                except (asyncio.TimeoutError, httpx.HTTPError, Exception) as exc:  # noqa: BLE001
                    # Per-subreddit fail-open: one slow subreddit never blocks the others.
                    log.warning("reddit.subreddit_failed", subreddit=sub, error=str(exc))
                    continue
                for child in (payload.get("data") or {}).get("children") or []:
                    data = child.get("data") or {}
                    title = (data.get("title") or "").strip()
                    url = (data.get("url_overridden_by_dest") or data.get("url") or "").strip()
                    if not title or not url:
                        continue
                    created_utc = data.get("created_utc")
                    published_at = (
                        datetime.fromtimestamp(created_utc, tz=timezone.utc)
                        if created_utc
                        else since
                    )
                    if published_at.timestamp() < cutoff:
                        continue
                    items.append(
                        RawItem(
                            source_type=self.source_type,
                            title=f"[r/{sub}] {title}",
                            url=url,
                            content=(data.get("selftext") or "")[:2000],
                            author=data.get("author"),
                            published_at=published_at,
                            extra={
                                "subreddit": sub,
                                "score": data.get("score"),
                                "num_comments": data.get("num_comments"),
                                "permalink": data.get("permalink"),
                            },
                        )
                    )
        log.info("reddit.collected", count=len(items), subreddits=len(self.subreddits))
        return items[:limit]
