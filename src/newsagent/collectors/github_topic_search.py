"""GitHub topic search collector. Uses the search API to find recently
created repos for a curated topic list (llm, agent, rag, fine-tuning,
vector-database, inference, rlhf, multimodal, tts, embedding).

Auth: optional GitHub token (NEWSAGENT_GITHUB_TOKEN) for higher rate limits
(60/hr unauth, 5000/hr with token). Falls back to unauth if unset.

Distinct from github_trending: that scrapes the daily trending page (best
repos of the moment). This queries the search API by topic + created:>=
so the corpus is a steady stream of new repos across many topics, not the
single trending list.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx

from newsagent.collectors.base import CollectorAdapter, RawItem
from newsagent.logging import get_logger

log = get_logger("collector.github_topic_search")

# Curated search topics — each becomes one search call. Ponytail: a
# hand-picked short list beats any heuristic, and each topic is a real
# signal that the new repos match the prompt's expected content.
DEFAULT_TOPICS: tuple[str, ...] = (
    "llm",
    "agent",
    "rag",
    "fine-tuning",
    "vector-database",
    "inference",
    "rlhf",
    "multimodal",
    "tts",
    "embedding",
)

SEARCH_URL = "https://api.github.com/search/repositories"


class GithubTopicSearchCollector(CollectorAdapter):
    source_type = "github_topic_search"

    def __init__(
        self,
        github_token: str | None = None,
        topics: tuple[str, ...] | None = None,
        per_topic: int = 15,
    ):
        self.github_token = github_token or os.environ.get("NEWSAGENT_GITHUB_TOKEN")
        self.topics = topics or DEFAULT_TOPICS
        self.per_topic = per_topic

    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if self.github_token:
            h["Authorization"] = f"Bearer {self.github_token}"
        return h

    async def collect(self, *, since: datetime, limit: int = 50) -> list[RawItem]:
        items: list[RawItem] = []
        cutoff = since.strftime("%Y-%m-%d")
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            for topic in self.topics:
                params = {
                    "q": f"topic:{topic} created:>={cutoff}",
                    "sort": "stars",
                    "order": "desc",
                    "per_page": str(self.per_topic),
                }
                try:
                    resp = await client.get(SEARCH_URL, params=params, headers=self._headers())
                    resp.raise_for_status()
                except Exception as exc:  # noqa: BLE001
                    log.warning("github_topic_search.fetch_failed", topic=topic, error=str(exc))
                    continue
                try:
                    payload = resp.json()
                except Exception as exc:  # noqa: BLE001
                    log.warning("github_topic_search.bad_json", topic=topic, error=str(exc))
                    continue
                for repo in payload.get("items", []):
                    full_name = repo.get("full_name", "")
                    if not full_name:
                        continue
                    description = (repo.get("description") or "").strip()
                    pushed_at = repo.get("pushed_at") or repo.get("created_at")
                    items.append(
                        RawItem(
                            source_type=self.source_type,
                            title=f"{full_name} (topic: {topic})",
                            url=repo.get("html_url", f"https://github.com/{full_name}"),
                            content=description,
                            author=repo.get("owner", {}).get("login"),
                            published_at=_parse_iso(pushed_at) or since,
                            extra={
                                "repo": full_name,
                                "topic": topic,
                                "stars": repo.get("stargazers_count"),
                                "language": repo.get("language"),
                                "topics": repo.get("topics", []),
                            },
                        )
                    )
        log.info("github_topic_search.collected", count=len(items), topics=len(self.topics))
        return items[:limit]


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        # GitHub returns e.g. "2026-07-14T03:55:12Z" — Python 3.11+ handles this with fromisoformat
        # once we normalize the trailing Z.
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None
