"""arXiv collector via the public Atom API (no API key)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime

import httpx

from hermes.collectors.base import CollectorAdapter, RawItem
from hermes.logging import get_logger

log = get_logger("collector.arxiv")
ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"


class ArxivCollector(CollectorAdapter):
    source_type = "arxiv"
    BASE = "http://export.arxiv.org/api/query"

    CATEGORIES = (
        "cs.LG cs.AI cs.CL cs.CV cs.RO stat.ML cs.NE"
    )

    async def collect(self, *, since: datetime, limit: int = 50) -> list[RawItem]:
        params = {
            "search_query": f"({self.CATEGORIES.replace(' ', ' OR ')})",
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": str(min(limit, 200)),
        }
        items: list[RawItem] = []
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(self.BASE, params=params)
                resp.raise_for_status()
                root = ET.fromstring(resp.text)
        except Exception as exc:  # noqa: BLE001
            log.warning("arxiv.fetch_failed", error=str(exc))
            return items

        cutoff = since.timestamp()
        for entry in root.findall(f"{ATOM}entry"):
            published = entry.findtext(f"{ATOM}published") or ""
            try:
                pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            except ValueError:
                pub_dt = None
            if pub_dt is not None and pub_dt.timestamp() < cutoff:
                continue
            title = (entry.findtext(f"{ATOM}title") or "").strip().replace("\n", " ")
            summary = (entry.findtext(f"{ATOM}summary") or "").strip()
            url = ""
            for link in entry.findall(f"{ATOM}link"):
                if link.get("rel") == "alternate":
                    url = link.get("href", "")
                    break
            authors = [a.findtext(f"{ATOM}name", "").strip() for a in entry.findall(f"{ATOM}author")]
            if not url and title:
                continue
            items.append(
                RawItem(
                    source_type=self.source_type,
                    title=title,
                    url=url,
                    content=summary,
                    author=", ".join(a for a in authors if a) or None,
                    published_at=pub_dt,
                    extra={"categories": [c.text for c in entry.findall(f"{ATOM}category")]},
                )
            )
        log.info("arxiv.collected", count=len(items))
        return items[:limit]
