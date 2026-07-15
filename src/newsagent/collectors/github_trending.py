"""GitHub Trending collector. Scrapes the public trending page (no auth)."""

from __future__ import annotations
from datetime import datetime

import re

import httpx

from newsagent.collectors.base import CollectorAdapter, RawItem
from newsagent.logging import get_logger

log = get_logger("collector.github_trending")
URL = "https://github.com/trending"


class GithubTrendingCollector(CollectorAdapter):
    source_type = "github_trending"

    async def collect(self, *, since: datetime, limit: int = 50) -> list[RawItem]:
        items: list[RawItem] = []
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(URL)
                resp.raise_for_status()
                html = resp.text
        except Exception as exc:  # noqa: BLE001
            log.warning("github_trending.fetch_failed", error=str(exc))
            return items

        for block in re.findall(r"<article class=\"Box-row\">(.*?)</article>", html, re.S):
            m = re.search(r"<h2[^>]*>\s*<a[^>]*href=\"/([^\"]+)\"", block)
            if not m:
                continue
            repo = m.group(1).strip("/")
            url = f"https://github.com/{repo}"
            desc_m = re.search(r"<p[^>]*class=\"col-9[^>]*>(.*?)</p>", block, re.S)
            desc = re.sub(r"<[^>]+>", "", desc_m.group(1)).strip() if desc_m else ""
            stars_m = re.search(r"([\d,]+)\s*stars today", block)
            stars_today = int(stars_m.group(1).replace(",", "")) if stars_m else None
            lang_m = re.search(r"itemprop=\"programmingLanguage\">([^<]+)<", block)
            language = lang_m.group(1).strip() if lang_m else None
            topics = re.findall(r"data-ga-click=\"Topic\"[^>]*>([^<]+)<", block)
            items.append(
                RawItem(
                    source_type=self.source_type,
                    title=f"{repo} (trending on GitHub)",
                    url=url,
                    content=desc,
                    published_at=since,
                    extra={
                        "repo": repo,
                        "stars_today": stars_today,
                        "language": language,
                        "topics": topics,
                    },
                )
            )
        log.info("github_trending.collected", count=len(items))
        return items[:limit]
