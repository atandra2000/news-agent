"""Semantic Scholar collector. No auth by default; set NEWSAGENT_SS_API_KEY for
higher rate limits. Retries with backoff on 429."""

from __future__ import annotations
from datetime import datetime

import os

from newsagent.collectors.base import CollectorAdapter, RawItem
from newsagent.collectors.http import aget_json
from newsagent.logging import get_logger

log = get_logger("collector.semantic_scholar")
URL = "https://api.semanticscholar.org/graph/v1/paper/search"
QUERY = "large language models"


class SemanticScholarCollector(CollectorAdapter):
    source_type = "semantic_scholar"

    def __init__(self, query: str | None = None):
        self.query = query or QUERY

    async def collect(self, *, since: datetime, limit: int = 50) -> list[RawItem]:
        items: list[RawItem] = []
        params = {
            "query": self.query,
            "fields": "title,url,abstract,authors,year,publicationDate,externalIds",
            "limit": min(limit, 100),
        }
        api_key = os.environ.get("NEWSAGENT_SS_API_KEY")
        headers = {"User-Agent": "newsagent/0.1"}
        if api_key:
            headers["x-api-key"] = api_key
        try:
            data = await aget_json(URL, params=params, headers=headers, retries=3, backoff=3.0)
        except Exception as exc:  # noqa: BLE001
            log.warning("semantic_scholar.fetch_failed", error=str(exc))
            return items

        for p in data.get("data", []):
            title = p.get("title")
            if not title:
                continue
            url = p.get("url") or (
                f"https://www.semanticscholar.org/paper/{p['externalIds'].get('ArXiv','')}"
                if p.get("externalIds", {}).get("ArXiv")
                else "https://www.semanticscholar.org"
            )
            authors = ", ".join(a.get("name", "") for a in p.get("authors", []) if a.get("name"))
            items.append(
                RawItem(
                    source_type=self.source_type,
                    title=f"Paper: {title}",
                    url=url,
                    content=(p.get("abstract") or "")[:2000],
                    author=authors or None,
                    published_at=since,
                    extra={"year": p.get("year"), "publicationDate": p.get("publicationDate")},
                )
            )
        log.info("semantic_scholar.collected", count=len(items))
        return items[:limit]
