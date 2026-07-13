"""Bluesky (AT Protocol) collector. Env-gated on HERMES_BLUESKY_HANDLE + HERMES_BLUESKY_APPKEY; skips when unset (HERMES_DESIGN §11.2)."""

from __future__ import annotations
from datetime import datetime

import os

import httpx

from hermes.collectors.base import CollectorAdapter, RawItem
from hermes.logging import get_logger

log = get_logger("collector.bluesky")
BASE = "https://bsky.social/xrpc"


class BlueskyCollector(CollectorAdapter):
    source_type = "bluesky"

    def __init__(self, query: str = "AI OR LLM OR machinelearning", limit: int = 30):
        self.query = query
        self.limit = limit

    async def collect(self, *, since: datetime, limit: int = 50) -> list[RawItem]:
        handle = os.environ.get("HERMES_BLUESKY_HANDLE")
        appkey = os.environ.get("HERMES_BLUESKY_APPKEY")
        if not (handle and appkey):
            log.info("bluesky.skipped_no_creds")
            return []
        items: list[RawItem] = []
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                auth = await client.post(
                    f"{BASE}/com.atproto.server.createSession",
                    json={"identifier": handle, "password": appkey},
                )
                auth.raise_for_status()
                jwt = auth.json().get("accessJwt", "")
                resp = await client.get(
                    f"{BASE}/app.bsky.feed.searchPosts",
                    params={"q": self.query, "limit": min(self.limit, 100)},
                    headers={"Authorization": f"Bearer {jwt}"},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            log.warning("bluesky.fetch_failed", error=str(exc))
            return items

        for post in data.get("posts", []):
            author = post.get("author", {}).get("handle", "")
            rec = post.get("record", {})
            text = rec.get("text", "")
            if not text:
                continue
            items.append(
                RawItem(
                    source_type=self.source_type,
                    title=f"@{author}: {text[:80]}",
                    url=f"https://bsky.app/profile/{author}/post/{post.get('uri','').split('/')[-1]}",
                    content=text,
                    author=author,
                    published_at=since,
                    extra={"likes": post.get("likeCount", 0)},
                )
            )
        log.info("bluesky.collected", count=len(items))
        return items[:limit]
