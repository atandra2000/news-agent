"""Context7 docs collector. REST API at /api/v2, unauthenticated for low-volume
use; set HERMES_COLLECTOR_CONTEXT7_API_KEY for higher limits. Skip-safe.
"""

from __future__ import annotations

import asyncio

from hermes.collectors.base import CollectorAdapter, RawItem
from hermes.logging import get_logger

log = get_logger("collector.context7")

BASE = "https://context7.com/api/v2"

# AI/ML libraries resolved via /api/v2/libs/search.
DEFAULT_LIBRARIES = [
    "pytorch",
    "tensorflow",
    "transformers",
    "diffusers",
    "vllm",
    "langchain",
    "langgraph",
    "llama-index",
    "openai-python",
    "anthropic-sdk-python",
    "google-generativeai",
    "litellm",
    "sentence-transformers",
    "unsloth",
    "trl",
    "axolotl",
    "sglang",
    "dspy",
    "autogen",
    "letta",
]


class Context7Collector(CollectorAdapter):
    source_type = "context7"

    def __init__(
        self,
        libraries: list[str] | None = None,
        base_url: str = BASE,
        *,
        timeout: float = 15.0,
        api_key: str | None = None,
        snippet_chars: int = 1500,
    ):
        self.libraries = libraries or DEFAULT_LIBRARIES
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.api_key = api_key
        self.snippet_chars = snippet_chars

    def _headers(self) -> dict:
        h = {"Accept": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    async def collect(self, *, since, limit: int = 50) -> list[RawItem]:
        import httpx

        sem = asyncio.Semaphore(6)

        async def _one(lib: str) -> RawItem | None:
            async with sem:
                try:
                    async with httpx.AsyncClient(timeout=self.timeout) as client:
                        # Resolve canonical library id.
                        s = await client.get(
                            f"{self.base_url}/libs/search",
                            params={"libraryName": lib, "query": "getting started"},
                            headers=self._headers(),
                        )
                    if s.status_code == 429:
                        log.warning("context7.rate_limited", hint="set HERMES_COLLECTOR_CONTEXT7_API_KEY for higher limits")
                        return None
                    if s.status_code != 200:
                        log.debug("context7.search_non_200", library=lib, status=s.status_code)
                        return None
                    sdata = s.json() or {}
                    results = sdata.get("results") or []
                    if not results:
                        return None
                    best = results[0]
                    lib_id = best.get("id") or best.get("libraryId") or lib
                    title = best.get("title") or best.get("name") or lib
                    description = best.get("description") or ""

                    # Pull docs snippet (v2 /context).
                    snippet = description
                    try:
                        async with httpx.AsyncClient(timeout=self.timeout) as client:
                            c = await client.get(
                                f"{self.base_url}/context",
                                params={"libraryId": lib_id, "query": "getting started", "type": "txt"},
                                headers=self._headers(),
                            )
                        if c.status_code == 200:
                            snippet = (c.text or "")[: self.snippet_chars]
                    except Exception:
                        # /context is unreliable without a key; fall back to description.
                        pass

                    url = f"https://context7.com{lib_id if lib_id.startswith('/') else '/' + lib_id}"
                    return RawItem(
                        source_type=self.source_type,
                        title=f"[docs] {title} — latest documentation",
                        url=url,
                        content=snippet or description,
                        published_at=since,
                        extra={"library_id": lib_id, "trust_score": best.get("trustScore")},
                    )
                except Exception as exc:  # noqa: BLE001
                    log.warning("context7.lib_failed", library=lib, error=str(exc))
                    return None

        results = await asyncio.gather(*[_one(lib) for lib in self.libraries])
        items = [r for r in results if r is not None]
        log.info("context7.collected", count=len(items), libraries=len(self.libraries))
        return items[:limit]
