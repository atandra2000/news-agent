"""Simplified Pydantic settings. ``HERMES_`` env prefix. No pg/redis/email/otel."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_STORAGE_DIR = Path("storage")


class CollectorConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HERMES_COLLECTOR_", env_file=".env", extra="ignore")

    enabled: list[str] = Field(
        default_factory=lambda: [
            "arxiv",
            "rss",
            "github_trending",
            "github_topic_search",  # GitHub search API by topic; uses HERMES_GITHUB_TOKEN
            "github_releases",
            "huggingface",
            "blog",
            "hacker_news",
            "semantic_scholar",
            "openreview",
            "devto",
            "lobsters",
            "reddit",  # public JSON for r/MachineLearning, r/LocalLLaMA, r/singularity, r/StableDiffusion; per-subreddit timeout + fail-open
            "x_twitter",  # requires HERMES_X_BEARER_TOKEN; no-ops gracefully if unset
            # "tavily" — opt-in: gated on HERMES_COLLECTOR_TAVILY_API_KEY being set
            # AND the Tavily API quota not being exhausted. Disabled by default so
            # a quota-exhausted key doesn't waste HTTP round-trips on every brief.
            # Add it back when quota resets.
            "context7",
            "bluesky",
            "youtube",
        ]
    )
    # Wide weekly lookback; dedup collapses repeats across runs.
    lookback_hours: int = 168
    # Max items pulled per source per run.
    per_source_limit: int = 60
    # Concurrent collector fan-out.
    concurrency: int = 12
    # Per-source HTTP timeout (seconds).
    timeout_seconds: float = 30.0
    # Retry a failed source once before skipping.
    retry_once: bool = True
    # GitHub PAT lifts github_releases rate limit 60 -> 5000 req/hr.
    github_token: str | None = None
    # Context7 API key; skipped silently when unset.
    context7_api_key: str | None = None


class LLMConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HERMES_LLM_", env_file=".env", extra="ignore")

    # Supported backends: "ollama" (default), "opencode_go", "openai".
    ollama_base_url: str = "https://api.ollama.com"
    ollama_api_key: str | None = None
    # Backend selector; "openai" = any /chat/completions endpoint.
    backend: str = "ollama"
    # OpenCode Go backend (backend="opencode_go").
    opencode_go_base_url: str = "https://opencode.ai/zen/go/v1"
    opencode_go_api_key: str | None = None
    # None = per-role tier chain from OPENCODE_GO_CATALOG (cheap roles skip big-model
    # reasoning overhead); set to force one model for all roles.
    opencode_go_model: str | None = None
    # OpenAI-compatible backend (backend="openai").
    openai_base_url: str | None = None
    openai_api_key: str | None = None
    openai_model: str | None = None
    # Hard safety cap: abort if cumulative tokens exceed this.
    token_budget: int = 2_000_000
    # Fall back to heuristics if Ollama is unreachable so a report is always produced.
    allow_heuristic_fallback: bool = True
    # Request timeout per LLM call (seconds).
    timeout_seconds: float = 180.0
    # Cost per 1k tokens (USD); 0 disables cost tracking.
    cost_per_1k_tokens: float = 0.0
    # Prefix caching (KV reuse of identical prompt prefixes); needs keep_alive.
    # Cuts tokens for the many repeated-prefix pipeline calls.
    prompt_cache: bool = True


class EmbedderConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HERMES_EMBED_", env_file=".env", extra="ignore")

    # "hashing" (default, zero-dep) or a sentence-transformers model id.
    model: str = "hashing"
    # Dimension for the hashing embedder.
    dim: int = 768
    # Unit-length vectors (required for cosine).
    normalize: bool = True
    # Embedding batch size.
    batch_size: int = 32


class PipelineConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HERMES_PIPELINE_", env_file=".env", extra="ignore")

    # Top items receiving deep typed analysis.
    top_k_analysis: int = 25
    # Top items receiving cluster labels.
    top_k_clusters: int = 40
    # Top items included in the report body.
    report_top_k: int = 25
    # Similarity threshold for clustering / verifier retrieval.
    similarity_threshold: float = 0.78
    # Max cluster label length.
    cluster_label_max_chars: int = 80
    # Bounded concurrency for parallel section synthesis.
    section_concurrency: int = 3
    # Cap on cross-document graph context injected per prompt; the graph is shared
    # across all calls, so an unbounded graph would bloat every one.
    graph_context_max_chars: int = 4000
    # --- New cognition stages (defaults preserve behavior when off) ---
    # Form an overarching thesis before editorial decisions.
    thesis_enabled: bool = True
    # Editorial board decides sections from thesis + stories (acts on chief review).
    editorial_board_enabled: bool = True
    # Deterministic CoT backstop in the section writer (strip reasoning scratchpad).
    writer_extract_cot: bool = True


class StorageConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HERMES_STORAGE_", env_file=".env", extra="ignore")

    dir: Path = DEFAULT_STORAGE_DIR
    # SQLite filename inside storage dir.
    sqlite_file: str = "hermes.db"
    # "numpy" (default, zero-dep) or "qdrant" (embedded local, enables RAG/search).
    vector_backend: str = "numpy"
    # Qdrant local on-disk path inside storage dir.
    qdrant_dir: str = "vectors"
    # Qdrant collection name.
    qdrant_collection: str = "hermes"
    # Optional Obsidian vault dir to mirror reports into.
    obsidian_vault: str | None = None


class SearchConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HERMES_SEARCH_", env_file=".env", extra="ignore")

    # "tavily" needs HERMES_SEARCH_TAVILY_API_KEY; "none" grounds only in the LLM's
    # parametric knowledge (labelled as such).
    backend: str = "none"
    tavily_api_key: str | None = None
    tavily_base_url: str = "https://api.tavily.com"
    # Max sources from any single host, so one outlet can't dominate a section.
    domain_cap: int = 3
    # Per-source HTTP timeout (seconds).
    timeout_seconds: float = 30.0
    # If a section has < this many citations post-synthesis, spawn gap-filling
    # queries. 0 disables the research loop.
    min_citations: int = 3
    # Max extra queries per section when citations are thin.
    extra_queries: int = 2


class RAGConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HERMES_RAG_", env_file=".env", extra="ignore")

    # Retrieve past reports for style/consistency anchoring.
    enabled: bool = True
    # Max past reports to load (most recent first).
    max_reports: int = 20
    # Top-k similar past sections to retrieve per section.
    top_k: int = 3
    # Cosine similarity threshold for retrieval.
    threshold: float = 0.3
    # Max RAG context chars injected into the writer prompt.
    max_context_chars: int = 2000


class ReportConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HERMES_REPORT_", env_file=".env", extra="ignore")

    # Critic score floor: after the rewrite loop exhausts ``max_rewrite_iterations``,
    # a section whose final score is below this threshold is replaced with the
    # standard _placeholder(section) instead of being shipped. Pin defaults
    # match ``SectionRewriteBudget`` in pipeline/synthesize.py.
    min_section_score: float = 0.5
    # Hard cap on the number of critic→rewrite iterations. 2 is enough to
    # let one full rewrite happen after the initial draft fails the floor.
    max_rewrite_iterations: int = 2


class HermesSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HERMES_",
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    log_level: str = "INFO"
    json_logs: bool = False

    # Cadence drives the lookback window + per-section source counts.
    # One of: daily | weekly | monthly. Invalid values fall back to daily at the
    # orchestrator boundary; the field defaults to daily for unset .env.
    cadence: str = "daily"

    collectors: CollectorConfig = CollectorConfig()
    llm: LLMConfig = LLMConfig()
    embed: EmbedderConfig = EmbedderConfig()
    pipeline: PipelineConfig = PipelineConfig()
    storage: StorageConfig = StorageConfig()
    search: SearchConfig = SearchConfig()
    rag: RAGConfig = RAGConfig()
    report: ReportConfig = ReportConfig()

    @property
    def sqlite_url(self) -> str:
        path = self.storage.dir / self.storage.sqlite_file
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite+aiosqlite:///{path}"

    @property
    def qdrant_path(self) -> Path:
        p = self.storage.dir / self.storage.qdrant_dir
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def reports_dir(self) -> Path:
        p = self.storage.dir / "reports"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def manifests_dir(self) -> Path:
        p = self.storage.dir / "run_manifests"
        p.mkdir(parents=True, exist_ok=True)
        return p


def load_settings() -> HermesSettings:
    """Load merged settings from env + .env."""
    return HermesSettings()
