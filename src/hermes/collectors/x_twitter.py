"""X (formerly Twitter) collector. Uses the v2 API to fetch recent tweets
from a curated watchlist of AI labs + researchers. Auth via bearer
token (HERMES_X_BEARER_TOKEN); if unset, the collector no-ops
gracefully (returns []) so the run is not blocked.

Ponytail: watchlist is a small tuple in this file, not a config blob.
Adding an account is a one-line edit; the tests can pin the watchlist
to keep the snapshot stable.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx

from hermes.collectors.base import CollectorAdapter, RawItem
from hermes.logging import get_logger

log = get_logger("collector.x_twitter")

# Curated watchlist: AI labs + researchers. Each is a Twitter user_id (numeric).
# We use numeric IDs (not handles) so a handle rename doesn't silently break
# the collector. The mapping handle -> id can be looked up via
# https://api.twitter.com/2/users/by/username/{handle} once with the bearer.
DEFAULT_WATCHLIST: tuple[tuple[str, str], ...] = (
    # (handle, label) — the id is fetched at runtime via /users/by/username
    # and cached, so the file can stay handle-based.
    ("OpenAI", "OpenAI"),
    ("AnthropicAI", "Anthropic"),
    ("GoogleDeepMind", "Google DeepMind"),
    ("AIatMeta", "Meta AI"),
    ("xai", "xAI"),
    ("MistralAI", "Mistral AI"),
    ("Alibaba_Qwen", "Alibaba Qwen"),
    ("huggingface", "Hugging Face"),
    ("perplexity_ai", "Perplexity"),
    ("cohere", "Cohere"),
    ("DeepSeek_AI", "DeepSeek"),
    ("kaboroich", "Sebastian Raschka"),
    ("sama", "Sam Altman"),
    ("demishassabis", "Demis Hassabis"),
    ("ylecun", "Yann LeCun"),
    ("karpathy", "Andrej Karpathy"),
    ("AndrewYNg", "Andrew Ng"),
    ("simonw", "Simon Willison"),
    ("swyx", "swyx (Latent Space)"),
    ("jackclarkSF", "Jack Clark (Import AI)"),
    ("balajis", "Balaji Srinivasan"),
    ("drjimfan", "Jim Fan (NVIDIA)"),
    ("jxmnop", "Jack Morris (research)"),
    ("arankomatsuzaki", "Aran Komatsuzaki"),
    ("_akhaliq", "akhaliq (papers)"),
    ("tri_dao", "Tri Dao (FlashAttention)"),
    ("rasbt", "Sebastian Raschka"),
    ("lmsysorg", "LMSYS Org"),
    ("aiaborruso", "AI community"),
    ("HuggingPapers", "Hugging Face Papers"),
)

USER_LOOKUP_URL = "https://api.twitter.com/2/users/by/username/{username}"
USER_TWEETS_URL = "https://api.twitter.com/2/users/{id}/tweets"
DEFAULT_TIMEOUT = 10.0


class XTwitterCollector(CollectorAdapter):
    source_type = "x_twitter"

    def __init__(
        self,
        bearer_token: str | None = None,
        watchlist: tuple[tuple[str, str], ...] | None = None,
        max_per_user: int = 5,
        timeout_seconds: float = DEFAULT_TIMEOUT,
    ):
        self.bearer_token = bearer_token or os.environ.get("HERMES_X_BEARER_TOKEN")
        self.watchlist = watchlist or DEFAULT_WATCHLIST
        self.max_per_user = max_per_user
        self.timeout_seconds = timeout_seconds
        # Cache username -> user_id lookups so we don't refetch on every run.
        self._id_cache: dict[str, str] = {}

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.bearer_token}"} if self.bearer_token else {}

    async def _lookup_user_id(self, client: httpx.AsyncClient, username: str) -> str | None:
        if username in self._id_cache:
            return self._id_cache[username]
        try:
            resp = await client.get(
                USER_LOOKUP_URL.format(username=username),
                params={"user.fields": "id"},
            )
            resp.raise_for_status()
            data = resp.json().get("data") or {}
        except Exception as exc:  # noqa: BLE001
            log.warning("x_twitter.user_lookup_failed", username=username, error=str(exc))
            return None
        user_id = data.get("id")
        if user_id:
            self._id_cache[username] = str(user_id)
        return str(user_id) if user_id else None

    async def collect(self, *, since: datetime, limit: int = 50) -> list[RawItem]:
        if not self.bearer_token:
            log.info("x_twitter.skipped_no_token")
            return []
        items: list[RawItem] = []
        cutoff = since.timestamp()
        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
            headers = self._headers()
            for username, label in self.watchlist:
                user_id = await self._lookup_user_id(client, username)
                if not user_id:
                    continue
                try:
                    resp = await client.get(
                        USER_TWEETS_URL.format(id=user_id),
                        params={
                            "max_results": str(max(5, self.max_per_user)),
                            "tweet.fields": "created_at,public_metrics",
                        },
                        headers=headers,
                    )
                    resp.raise_for_status()
                    payload = resp.json()
                except Exception as exc:  # noqa: BLE001
                    log.warning("x_twitter.tweets_fetch_failed", username=username, error=str(exc))
                    continue
                for tweet in payload.get("data") or []:
                    text = (tweet.get("text") or "").strip()
                    tweet_id = tweet.get("id")
                    if not text or not tweet_id:
                        continue
                    published_at = _parse_iso(tweet.get("created_at")) or since
                    if published_at.timestamp() < cutoff:
                        continue
                    items.append(
                        RawItem(
                            source_type=self.source_type,
                            title=f"@{username}: {text[:120]}",
                            url=f"https://x.com/{username}/status/{tweet_id}",
                            content=text,
                            author=username,
                            published_at=published_at,
                            extra={
                                "label": label,
                                "metrics": tweet.get("public_metrics", {}),
                            },
                        )
                    )
        log.info("x_twitter.collected", count=len(items), watchlist=len(self.watchlist))
        return items[:limit]


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None
