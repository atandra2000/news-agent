"""RSS/Atom collector using stdlib (no feedparser); curated AI feeds, override via config."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx

from hermes.collectors.base import CollectorAdapter, RawItem
from hermes.logging import get_logger

log = get_logger("collector.rss")

# Curated AI/ML feeds; override via HERMES_COLLECTOR_RSS_FEEDS.
# Grouped by cluster so future maintainers can tell why a feed is on the list.
# Ponytail: list beats config file; one place to read, no second file to keep in sync.
DEFAULT_FEEDS = [
    # --- Lab blogs (cited in prompts as Official Sources) ---
    "https://openai.com/news/rss.xml",
    "https://deepmind.google/blog/rss.xml",
    "https://blog.google/technology/ai/rss/",
    "https://www.microsoft.com/en-us/research/feed/",
    "https://research.facebook.com/feed/",
    "https://huggingface.co/blog/feed.xml",
    "https://bair.berkeley.edu/blog/feed.xml",
    "https://ai.meta.com/blog/rss/",
    "https://www.anthropic.com/news/rss.xml",
    "https://simonwillison.net/atom/everything/",
    "https://lilianweng.github.io/index.xml",
    "https://distill.pub/rss.xml",
    "https://thegradient.pub/rss/",
    "https://magazine.sebastianraschka.com/feed",
    "https://www.interconnects.ai/feed",
    "https://aiguide.substack.com/feed",
    "https://www.marktechpost.com/feed/",
    "https://machinelearningmastery.com/feed/",
    "https://nlp.elvissaravia.com/feed",
    "https://blog.einstein.ai/feed",
    # --- AI-focused news outlets (cited in prompts as Trusted News Sources) ---
    "https://www.theinformation.com/feed",  # paywalled; some free posts in feed
    "https://www.technologyreview.com/feed/",
    "https://venturebeat.com/category/ai/feed/",
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",
    "https://arstechnica.com/ai/feed/",
    "https://www.wired.com/feed/tag/ai/latest/rss",
    "https://www.theregister.com/headlines.atom",
    "https://www.zdnet.com/topic/artificial-intelligence/rss.xml",
    "https://siliconangle.com/category/ai/feed/",
    "https://thenextweb.com/section/ai/feed/",
    "https://www.engadget.com/tag/ai/rss.xml",
    "https://www.thurrott.com/ai/feed",
    # --- Substacks (cited in prompts as Community Intelligence) ---
    "https://stratechery.com/feed/",
    "https://importai.substack.com/feed",
    "https://www.latent.space/feed",
    "https://www.deeplearning.ai/the-batch/feed/",
    "https://bensbites.substack.com/feed",
    "https://alphasignal.substack.com/feed",
    "https://thezvi.substack.com/feed",
    "https://www.oneusefulthing.substack.com/feed",
    "https://www.aisnakeoil.com/feed",
    "https://thealgorithmicbridge.substack.com/feed",
    # --- Hardware-focused (matches ai_hardware_infra brief) ---
    "https://hpcwire.com/feed/",
    "https://www.tomshardware.com/feeds/tag/ai/latest",
    "https://www.anandtech.com/feed",
    "https://developer.nvidia.com/blog/feed/",
    "https://rocm.blogs.amd.com/feed",
    "https://aws.amazon.com/blogs/machine-learning/feed/",
    # --- Policy / regulation (matches ai_regulation_policy brief) ---
    "https://www.europarl.europa.eu/rss/documents/topics/AI.xml",
    "https://www.whitehouse.gov/feed/",
    "https://digital-strategy.ec.europa.eu/en/rss.xml",
    # --- Aggregators (catch-all daily AI digests) ---
    "https://www.therundown.ai/feed",
    "https://www.superhuman.ai/feed",
    "https://www.aiweekly.co/rss.xml",
]

ATOM = "{http://www.w3.org/2005/Atom}"


def _parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


class RSSCollector(CollectorAdapter):
    source_type = "rss"

    def __init__(self, feeds: list[str] | None = None):
        self.feeds = feeds or DEFAULT_FEEDS

    async def collect(self, *, since: datetime, limit: int = 50) -> list[RawItem]:
        items: list[RawItem] = []
        cutoff = since.timestamp()
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            for feed in self.feeds:
                try:
                    resp = await client.get(feed)
                    resp.raise_for_status()
                    root = ET.fromstring(resp.text)
                except Exception as exc:  # noqa: BLE001
                    log.warning("rss.feed_failed", feed=feed, error=str(exc))
                    continue
                items.extend(self._parse(root, feed, cutoff))
        items.sort(key=lambda it: it.published_at.timestamp() if it.published_at else 0.0, reverse=True)
        log.info("rss.collected", count=len(items), feeds=len(self.feeds))
        return items[:limit]

    def _parse(self, root: ET.Element, feed: str, cutoff: float) -> list[RawItem]:
        out: list[RawItem] = []
        # RSS 2.0
        channel = root.find("channel")
        if channel is not None:
            for item in channel.findall("item"):
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                desc = item.findtext("description") or ""
                pub = _parse_date(item.findtext("pubDate"))
                if not link or not title:
                    continue
                if pub and pub.timestamp() < cutoff:
                    continue
                out.append(
                    RawItem(
                        source_type=self.source_type,
                        title=title,
                        url=link,
                        content=_strip_html(desc)[:2000],
                        author=item.findtext("author"),
                        published_at=pub,
                        extra={"feed": feed},
                    )
                )
            return out
        # Atom
        for entry in root.findall(f"{ATOM}entry"):
            title = (entry.findtext(f"{ATOM}title") or "").strip()
            summary = entry.findtext(f"{ATOM}summary") or entry.findtext(f"{ATOM}content") or ""
            pub = _parse_date(entry.findtext(f"{ATOM}updated") or entry.findtext(f"{ATOM}published"))
            url = ""
            for link in entry.findall(f"{ATOM}link"):
                if link.get("rel") in (None, "alternate"):
                    url = link.get("href", "")
                    break
            if not url or not title:
                continue
            if pub and pub.timestamp() < cutoff:
                continue
            out.append(
                RawItem(
                    source_type=self.source_type,
                    title=title,
                    url=url,
                    content=_strip_html(summary)[:2000],
                    published_at=pub,
                    extra={"feed": feed},
                )
            )
        return out


def _strip_html(s: str) -> str:
    import re

    return re.sub(r"<[^>]+>", " ", s or "").strip()
