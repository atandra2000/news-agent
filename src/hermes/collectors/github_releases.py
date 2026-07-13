"""GitHub releases for AI/ML orgs (fills gap from removed Reddit/PapersWithCode sources). Public /repos/{owner}/{repo}/releases works unauthenticated at 60 req/hr/IP; we fan out in parallel."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from hermes.collectors.base import CollectorAdapter, RawItem
from hermes.logging import get_logger

log = get_logger("collector.github_releases")

API = "https://api.github.com"

# Curated AI/ML repos shipping meaningful releases. ~20 to stay under GitHub's 60 req/hr unauth limit; set HERMES_COLLECTOR_GITHUB_TOKEN for more.
DEFAULT_REPOS = [
    # Frontier model labs
    "deepseek-ai/DeepSeek-V3",
    "openai/whisper",
    "openai/gpt-oss",
    "meta-llama/llama-models",
    "QwenLM/Qwen3",
    "google-gemini/gemini-cli",
    "xai-org/grok-1",
    # Frameworks
    "huggingface/transformers",
    "huggingface/diffusers",
    "vllm-project/vllm",
    "ggerganov/llama.cpp",
    "ml-explore/mlx",
    "langchain-ai/langchain",
    "langchain-ai/langgraph",
    "run-llama/llama_index",
    # Training / RL
    "huggingface/trl",
    "pytorch/pytorch",
    "Lightning-AI/pytorch-lightning",
]


class GitHubReleaseCollector(CollectorAdapter):
    source_type = "github_releases"

    def __init__(
        self,
        repos: list[str] | None = None,
        base_url: str = API,
        *,
        timeout: float = 15.0,
        max_releases_per_repo: int = 3,
        github_token: str | None = None,
    ):
        self.repos = repos or DEFAULT_REPOS
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_releases_per_repo = max_releases_per_repo
        self.github_token = github_token

    async def collect(self, *, since, limit: int = 50) -> list[RawItem]:
        import httpx

        cutoff = since.timestamp()
        sem = asyncio.Semaphore(8)
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "hermes-collector/1.0",
        }
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"

        async def _one(repo: str) -> list[RawItem]:
            async with sem:
                try:
                    async with httpx.AsyncClient(timeout=self.timeout) as client:
                        resp = await client.get(
                            f"{self.base_url}/repos/{repo}/releases",
                            params={"per_page": self.max_releases_per_repo},
                            headers=headers,
                        )
                    if resp.status_code == 403:
                        # Rate-limited; skip so the rest of the batch still runs.
                        log.warning("github_releases.rate_limited", repo=repo)
                        return []
                    if resp.status_code != 200:
                        return []
                    out: list[RawItem] = []
                    for rel in resp.json() or []:
                        tag = rel.get("tag_name") or ""
                        name = rel.get("name") or tag or repo
                        url = rel.get("html_url") or ""
                        pub = rel.get("published_at")
                        pub_dt: datetime | None = None
                        if pub:
                            try:
                                pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                                if pub_dt.tzinfo is None:
                                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                            except ValueError:
                                pub_dt = None
                        if pub_dt and pub_dt.timestamp() < cutoff:
                            continue
                        body = (rel.get("body") or "")[:2000]
                        if not url:
                            continue
                        out.append(
                            RawItem(
                                source_type=self.source_type,
                                title=f"[release] {repo} {tag}: {name}".strip(),
                                url=url,
                                content=body,
                                author=(rel.get("author") or {}).get("login"),
                                published_at=pub_dt or since,
                                extra={"repo": repo, "tag": tag, "prerelease": rel.get("prerelease", False)},
                            )
                        )
                    return out
                except Exception as exc:  # noqa: BLE001
                    log.warning("github_releases.repo_failed", repo=repo, error=str(exc))
                    return []

        batches = await asyncio.gather(*[_one(r) for r in self.repos])
        items: list[RawItem] = []
        for batch in batches:
            items.extend(batch)
        items.sort(
            key=lambda it: it.published_at.timestamp() if it.published_at else 0.0,
            reverse=True,
        )
        log.info("github_releases.collected", count=len(items), repos=len(self.repos))
        return items[:limit]
