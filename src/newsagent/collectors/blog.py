"""Curated researcher/lab blogs, reusing RSS parsing. Conservative feeds to finish within 30s. Override via NEWSAGENT_COLLECTOR_BLOG_FEEDS."""
from __future__ import annotations

from newsagent.collectors.rss import RSSCollector

DEFAULT_BLOG_FEEDS = [
    "https://karpathy.github.io/feed.xml",
    "https://lilianweng.github.io/index.xml",
    "https://sebastianraschka.com/rss_feed.xml",
    "https://www.fast.ai/index.xml",
    "https://bair.berkeley.edu/blog/feed.xml",
    "https://www.interconnects.ai/feed",
    "https://magazine.sebastianraschka.com/feed",
    "https://aiguide.substack.com/feed",
    "https://simonwillison.net/atom/everything/",
]


class BlogCollector(RSSCollector):
    source_type = "blog"

    def __init__(self, feeds: list[str] | None = None):
        super().__init__(feeds=feeds or DEFAULT_BLOG_FEEDS)
