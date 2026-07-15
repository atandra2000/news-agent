"""Hugging Face collector — trending models and papers via the public API."""

from __future__ import annotations
from datetime import datetime

import httpx

from newsagent.collectors.base import CollectorAdapter, RawItem
from newsagent.logging import get_logger

log = get_logger("collector.huggingface")
MODELS_API = "https://huggingface.co/api/models"
PAPERS_API = "https://huggingface.co/api/papers"


class HuggingFaceCollector(CollectorAdapter):
    source_type = "huggingface"

    async def collect(self, *, since: datetime, limit: int = 50) -> list[RawItem]:
        items: list[RawItem] = []
        items.extend(await self._models(since, limit // 2 + 5))
        items.extend(await self._papers(since, limit // 2 + 5))
        log.info("huggingface.collected", count=len(items))
        return items[:limit]

    async def _models(self, since: datetime, n: int) -> list[RawItem]:
        out: list[RawItem] = []
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    MODELS_API,
                    params={"sort": "trendingScore", "direction": "-1", "limit": n, "full": "false"},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            log.warning("hf.models_failed", error=str(exc))
            return out
        for m in data:
            model_id = m.get("id", "")
            if not model_id:
                continue
            likes = m.get("likes", 0)
            downloads = m.get("downloads", 0)
            out.append(
                RawItem(
                    source_type=self.source_type,
                    title=f"Model: {model_id}",
                    url=f"https://huggingface.co/{model_id}",
                    content=(m.get("pipeline_tag") or "")
                    + (" " + (m.get("cardData", {}) or {}).get("license", "")),
                    published_at=since,
                    extra={
                        "model_id": model_id,
                        "likes": likes,
                        "downloads": downloads,
                        "task": m.get("pipeline_tag"),
                        "subtype": "model",
                    },
                )
            )
        return out

    async def _papers(self, since: datetime, n: int) -> list[RawItem]:
        out: list[RawItem] = []
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(PAPERS_API, params={"page": 1, "perPage": n})
                resp.raise_for_status()
                data = resp.json() if resp.text.strip().startswith("[") else resp.json().get("papers", [])
        except Exception as exc:  # noqa: BLE001
            log.warning("hf.papers_failed", error=str(exc))
            return out
        for p in data:
            title = p.get("title")
            if not title:
                continue
            pid = p.get("id") or p.get("paper", {}).get("id") or title
            upvotes = p.get("upvotes", 0)
            out.append(
                RawItem(
                    source_type=self.source_type,
                    title=f"Paper: {title}",
                    url=f"https://huggingface.co/papers/{pid}",
                    content=title,
                    published_at=since,
                    extra={"paper_id": pid, "upvotes": upvotes, "subtype": "paper"},
                )
            )
        return out
