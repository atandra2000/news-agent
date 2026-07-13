# Hermes — Architecture & Migration Design

> Pivot plan: transform AIRIP (multi-user SaaS) into **Hermes**, a fully
> autonomous AI Research Intelligence Agent that runs daily, researches the
> entire AI ecosystem, reasons over it with LLMs, and produces one extensive
> Markdown report — no human interaction.

> **⚠️ Authoritative sections:** §11 (quality-first rubric) + §12 (architecture-review
> integration). §12 adds capability-bearing enhancements (Qdrant, knowledge graph,
> multi-agent flow, self-critique, RAG writing, research loops, report profiles,
> multi-output) with scoped implementations. §7–§9 are superseded. Read §11 then §12.

---

## 1. Codebase Analysis

The existing AIRIP is genuinely well-engineered, but it is built for the *wrong
product*. Every architectural decision in it serves a **multi-tenant SaaS with
REST APIs, auth, and per-user rankings**. Hermes needs none of that. The infra
exists to support features we are explicitly deleting.

### What is actually good (and reusable)

| Module | Why it's worth keeping | Coupling to remove |
|---|---|---|
| `llm/router.py` | Best-in-class role-routed router: retry/backoff+jitter, fallback chain, token accounting, OTel spans. **Exactly** what Hermes needs. | Hardcoded Ollama `/api/generate` → extract a `Provider` plugin. |
| `llm/roles.py` | Clean role→model-chain table with per-role caps. | Add research/reason/compare/markdown/proofread roles; drop tenant caps (use in-process semaphore). |
| `sources/base.py` | `RawItem`, `SourceAdapter`, `get_adapter`, typed HTTP error mapping. A **perfect plugin contract** already. | None — copy verbatim. |
| `sources/circuit.py` | Per-source circuit breaker. | None — copy verbatim. |
| `sources/{arxiv,rss,github_trending,blog}.py` | Four working collectors. | None — copy verbatim. |
| `dedup.py` | Vendored 64-bit SimHash + SHA-256. Zero deps, zero coupling. | None — copy verbatim. |
| `agents/analyzer.py` | The "intelligence" core: 10-field validated analysis, idempotent by version, no silent failures. | Drop `session`/`tenant_id`; route through a repository; generalize schema beyond papers. |
| `agents/trend.py` | Statistics-first trend detection (SQL deltas → LLM narration). | Drop `session`/`tenant_id`; use repository. |
| `llm/prompts/` | Jinja2 versioned prompt templates. | Keep; add new templates. |
| `logging.py`, `errors.py` | structlog + domain errors. | Copy verbatim. |

### What is over-engineered for this product (remove entirely)

- **`api/` (8 route modules), `auth.py`, `middleware/`** — no REST surface, no users, no auth. Delete.
- **`db/models.py`** — 15 tables, 4 of them tenant/user/chat/watchlist/api-key. Only ~5 are needed; all `tenant_id`/RLS/soft-delete goes.
- **Postgres + asyncpg + Alembic + psycopg** — replace with **SQLite** (one file, zero infra).
- **Redis + Celery + beat** — replace with a **one-shot CLI + OS scheduler** (launchd/systemd/cron). No broker, no long-running workers.
- **Qdrant server** — replace with a **pluggable `VectorStore`** (default: brute-force cosine over local NPY/SQLite; optional Qdrant-embedded for scale). For a daily corpus of <100K items this is milliseconds on CPU and removes a whole service.
- **`email.py`, `retention.py`, `tools/`, `agents/chat*.py`, `memory.py`, `recommender.py`, `alerts.py`, `weekly.py`** — all tenant/user/chat features. Delete (repurpose the *generator* assembly idea only).
- **`prometheus-client` / OTel exporter** — keep OTel *spans* in the router (cheap, useful), drop the Prometheus `/metrics` server and Jaeger pipeline unless wanted.

**Net effect:** the runtime dependency surface drops from ~14 heavy packages
(Postgres, Redis, Qdrant-server, Celery, FastAPI, Alembic, asyncpg, psycopg,
aiosmtplib, prometheus, opentelemetry-exporter…) to roughly: `pydantic`,
`pydantic-settings`, `structlog`, `sqlalchemy[asyncio]`+`aiosqlite`, `httpx`,
`tenacity`, `jinja2`, `qdrant-client` (optional), `sentence-transformers`
(optional embed extra). That is the single biggest reliability and simplicity
win.

---

## 2. Keep / Simplify / Remove — Decision Table

| Area | Decision | Notes |
|---|---|---|
| LLM router | **Keep + refactor** | Extract `Provider` plugin; keep fallback/backoff/accounting. |
| Role table | **Keep + extend** | research, reason, summarize, compare, markdown, proofread. |
| Source adapters | **Keep** | Copy `base.py` + 4 collectors verbatim; add more. |
| Circuit breaker | **Keep** | Verbatim. |
| Dedup (SimHash/SHA) | **Keep** | Verbatim. |
| Analyzer (10-field) | **Keep + generalize** | Typed analyses: paper/model/product/benchmark/industry/community. |
| Trend agent | **Keep + simplify** | Drop tenant/session. |
| Generator assembly | **Repurpose** | Becomes the report assembler over section renderers. |
| DB (Postgres) | **Replace** | SQLite, ~5 tables. |
| Vector store (Qdrant srv) | **Replace** | Pluggable `VectorStore`, numpy default. |
| Celery/beat/Redis | **Replace** | One-shot CLI + OS scheduler. |
| FastAPI/auth/middleware | **Remove** | No API. |
| Email/retention/tools/chat | **Remove** | No users. |
| Config | **Simplify** | `HERMES_` prefix; drop pg/redis/email/otel-server. |

---

## 3. Target Architecture — Hermes

```
                         ┌─────────────────────────────────────────────┐
                         │            hermes run  (one-shot / day)       │
                         └───────────────────────┬─────────────────────┘
                                                 │
   ┌─────────────── COLLECT ─────────────────────┼────────────────────────┐
   │  collectors/* (plugin)                       │                         │
   │  arxiv · rss · github_trending · blog · hf   │                         │
   │  · openreview · pwc · semantic_scholar · hn  │                         │
   │  · reddit · x · bluesky · youtube · …        │                         │
   │  circuit-breaker + timeout per source        │                         │
   └───────────────────────┬─────────────────────┘                         │
                            │ RawItem[]                                     │
   ┌─────────────── INGEST ─┼──────────────────────────────────────────────┘
   │  dedup (sha256 → SimHash) → embed (bge-m3) → store Item + vector       │
   └───────────────────────┬──────────────────────────────────────────────┘
                            │ Item[]
   ┌──────── ANALYZE ───────┼──────────────────────────────────────────────┐
   │  classifier → typed analyzers (paper/model/product/…)                  │
   │  verifier: retrieve similar → cross-reference → corroborate/conflict   │
   └───────────────────────┬──────────────────────────────────────────────┘
                            │ Analysis[]
   ┌──── CLUSTER / RANK / TREND ─┼─────────────────────────────────────────┐
   │  embed-similarity clusters → LLM labels                                │
   │  ranker: importance × novelty × long-term impact                       │
   │  trend: daily/weekly deltas (port trend.py)                            │
   └───────────────────────┬──────────────────────────────────────────────┘
                            │ ReportContext
   ┌──────── RENDER ────────┼──────────────────────────────────────────────┐
   │  renderers/* (plugin, one per section) → assemble → proofread          │
   │  write storage/reports/YYYY-MM-DD.md                                   │
   └───────────────────────┴──────────────────────────────────────────────┘
```

**Why this beats "ask Perplexity for today's AI news":**
- *Depth*: every top item gets a 10+ field structured analysis with two-altitude explanations (beginner analogy + expert mechanism), not a 3-sentence summary.
- *Verification*: the verifier stage explicitly marks claims **corroborated / conflicting / single-source** across independent sources — Perplexity hides this.
- *Synthesis*: clustering + trend deltas show *relationships and trajectories* across the whole ecosystem, not isolated blurbs.
- *Engineering value*: dedicated "Engineering Insights" and "Practical Takeaways" sections.
- *Provenance*: every claim cites a primary source (paper/announcement/repo) vs a signal source (tweet/Reddit), with Obsidian-friendly links.

---

## 4. Migration Strategy

**Recommendation: clean new package `src/hermes/`, not in-place surgery.** The
tenant coupling is pervasive (`tenant_id` on 8 tables, 4 Alembic migrations
with RLS, `Item.search_fts` tenant filters, analyzer/trend sessions all
tenant-scoped). In-place removal is high-risk and low-reviewability. A port lets
each phase be a small, testable, reviewable diff.

**Steps:**
1. Keep `src/airip/` intact as a reference during the build. Do not delete until Hermes produces its first real report.
2. Port the *uncoupled* modules verbatim (router logic, roles, sources/base, circuit, dedup, prompts, logging, errors).
3. Port the *algorithms* of analyzer/trend/generator with tenant/session stripped and a repository injected.
4. Build the new storage/pipeline/renderers/orchestrator/CLI around them.
5. Once `hermes run` produces a report end-to-end, delete `src/airip/`, `docker-compose.yml`, `Dockerfile*`, the 8 API modules, and the tenant migrations. Archive the old `IMPLEMENTATION_PLAN.md`/`PHASE1_DESIGN.md` to `_archive/`.

This keeps the repo always-green: every phase lands working tests.

---

## 5. New Project Structure

```
hermes/
  pyproject.toml                 # name="hermes", HERMES_ env prefix
  src/hermes/
    __init__.py
    __main__.py                  # entry: `python -m hermes run`
    config.py                    # simplified Pydantic Settings (HERMES_*)
    logging.py                   # structlog (verbatim)
    errors.py                    # domain errors (verbatim)
    cli.py                       # run / backfill / status / sources list

    llm/
      router.py                  # role-routed, provider-agnostic, fallback
      roles.py                   # role → model chain (research/reason/…)
      providers/
        base.py                  # BaseProvider.complete(prompt, model, **opts)
        ollama.py                # Ollama Pro (default)
        openai.py                # plugin stub
        anthropic.py             # plugin stub
        registry.py              # model name → provider
      prompts/                   # jinja2 templates (verbatim + new)
        analyzer_paper_v1.j2 …
      embed.py                   # lazy bge-m3 wrapper (pluggable Embedder)

    collectors/                  # PLUGIN: one file per source
      base.py                    # RawItem, CollectorAdapter, get_collector
      arxiv.py  rss.py  github_trending.py  blog.py
      huggingface.py  openreview.py  pwc.py  semantic_scholar.py
      hn.py  reddit.py  x.py  bluesky.py  youtube.py  …
      registry.py                # auto-discovery + enabled set from config

    storage/
      db.py                      # SQLite models + async session (aiosqlite)
      models.py                  # Source, Item, ItemAlias, Analysis,
                                 #   Cluster, TrendSnapshot, Report
      repository.py              # async CRUD used by every stage
      vectorstore/
        base.py                  # VectorStore interface
        numpy_store.py           # default: brute-force cosine (NPY/BLOB)
        qdrant_local.py          # optional backend

    pipeline/
      ingest.py                  # dedup → embed → store (atomic)
      analyze.py                 # classifier + typed analyzers + verifier
      cluster.py                 # similarity clustering + labels
      rank.py                    # importance × novelty × impact
      trend.py                   # port trend.py (simplified)
      render.py                  # assembler over section renderers
      run.py                     # orchestrator (stages, resume, backfill)

    analyzers/                   # PLUGIN: typed analyses
      base.py                    # AnalysisPlugin + AnalysisResult
      paper.py  model_release.py  product.py
      benchmark.py  industry_event.py  community_signal.py
      verifier.py                # cross-source claim verification
      classifier.py              # item-type tagging

    renderers/                   # PLUGIN: one section each
      base.py                    # SectionRenderer.render(ctx) -> str
      executive_summary.py  major_news.py  paper_analysis.py
      model_releases.py  open_source.py  github_highlights.py
      hf_highlights.py  company_updates.py  industry_news.py
      community_highlights.py  benchmark_changes.py  emerging_trends.py
      technical_deep_dives.py  engineering_insights.py
      practical_takeaways.py  references.py
      registry.py

    scheduler/
      launchd.plist             # macOS daily
      systemd.timer             # Linux daily
      cron.txt                  # reference

  storage/
    hermes.db                    # SQLite corpus + analyses + trends
    vectors/                     # NPY embeddings (or qdrant local dir)
    reports/
      2026-07-10.md …
    run_manifests/               # per-run: what ran, cost, failures

  tests/
    unit/  integration/          # fakes for router/embedder/vectorstore
```

---

## 6. Autonomous Execution Pipeline

`hermes run [--date YYYY-MM-DD] [--dry-run] [--stage collect|analyze|…]` runs
the full chain once. The OS scheduler invokes it daily (no daemon).

**Stage contract** — each stage is an async function over an injected
`RunContext` (repository, router, embedder, vectorstore, config, logger).
Stages are independently resumable: a run writes a `run_manifest` so a crashed
run can `--resume` from the last good stage.

1. **collect** — `asyncio.gather` over enabled collectors; per-source circuit breaker + timeout; collect into `RawItem[]`. Failures isolated per source (one dead API ≠ dead run).
2. **ingest** — for each `RawItem`: sha256 exact-dedup → SimHash near-dup (alias) → embed → store `Item` + vector in one SQLite transaction.
3. **analyze** — classifier tags each item's type; the top-N by a cheap importance heuristic get a typed analysis via the router; verifier retrieves similar recent items and emits corroboration/conflict notes. Idempotent by `analyzer_version`.
4. **cluster** — embed-similarity connected components → LLM cluster labels ("Related: …").
5. **rank** — score each analyzed item: `importance × novelty × long_term_impact` (heuristic + LLM-assisted), no per-user.
6. **trend** — daily/weekly deltas (rising/fading topics) ported from `trend.py`.
7. **render** — `ReportAssembler` calls enabled `SectionRenderer`s in order, concatenates, runs a `proofread` LLM pass, writes `storage/reports/YYYY-MM-DD.md`.
8. **archive** — commit the `Report` row + run manifest; done.

**Concurrency model:** replace the Redis per-role semaphore with an in-process
`asyncio.Semaphore` (cap per role from `roles.py`). Replace Celery retries with
the router's existing tenacity policy.

---

## 7. Plugin Architectures

### 7.1 Collectors
```python
class CollectorAdapter(ABC):
    source_type: ClassVar[str]
    async def collect(self, *, since: datetime, **kw) -> list[RawItem]: ...
# register: collectors/registry.py auto-imports subclasses of CollectorAdapter
```
Adding a source = one file + one line in the enabled list. (Exactly the existing
`sources/base.py` contract — proven.)

### 7.2 LLM Providers
```python
class BaseProvider(ABC):
    name: ClassVar[str]
    async def complete(self, model: str, prompt: str, **opts) -> ProviderResult: ...
# ModelRegistry: {"gpt-oss": OllamaProvider, "gpt-4o": OpenAIProvider, ...}
# Router.resolve(role) -> [provider for model in chain]; on failure, next model (any provider)
```
This is the one real refactor of `router.py`: move the `/api/generate` HTTP call
behind `OllamaProvider`, keep all retry/backoff/accounting/tracing in the router.
Fallback now spans *providers*, satisfying "multiple cloud models with automatic
fallback" + "easy to add new LLM providers."

### 7.3 Analyzers (typed intelligence)
```python
class AnalysisPlugin(ABC):
    analysis_type: ClassVar[str]          # "paper" | "model_release" | ...
    schema: type[BaseModel]                # extra="forbid", validated
    async def analyze(self, item, ctx) -> AnalysisResult: ...
```
The classifier routes an item to the matching plugin. Each plugin owns its Jinja2
prompt + Pydantic schema. This generalizes the 10-field `PaperAnalysisSchema`
into the full intelligence layer.

### 7.4 Renderers (report sections)
```python
class SectionRenderer(ABC):
    section_id: ClassVar[str]              # "paper_analysis"
    title: ClassVar[str]                   # "## Research Paper Analysis"
    async def render(self, ctx: ReportContext) -> str: ...
# ReportAssembler renders enabled sections in config order; one plugin = one section.
```
Adding a report section = one file. The 16 sections from the spec map 1:1 to 16
renderer plugins.

### 7.5 Storage (vector + relational)
```python
class VectorStore(ABC):
    async def upsert(self, items: list[VectorInput]) -> None
    async def search(self, vector, *, top_k, threshold) -> list[SearchHit]
# NumpyVectorStore (default) | QdrantLocalStore (optional)
```
Relational store is SQLite via a thin `repository.py` (no Alembic —
`Base.metadata.create_all` on first run, plus a tiny `schema_version` guard).

---

## 8. Phased Implementation Roadmap

Each phase is a small, independently-testable, reviewable session. Phases are
ordered so Hermes is *partially runnable early* and grows in capability.

| # | Phase | Sessions | Deliverable / Exit criterion |
|---|---|---|---|
| **0** | **Scaffold** | 1 | `src/hermes/`, simplified `config.py` (`HERMES_`), `logging.py`/`errors.py` copied, ruff/mypy/pytest green, empty `cli.py`. |
| **1** | **LLM core** | 2 | `providers/` (Ollama default + OpenAI/Anthropic stubs), `ModelRegistry`, refactored `router.py` with fallback across providers, new `roles.py` (research/reason/summarize/compare/markdown/proofread). Tests with `respx`. |
| **2** | **Collectors** | 2 | `collectors/base.py` + circuit breaker ported; `arxiv/rss/github_trending/blog` copied; `huggingface` + `github_releases` added to prove extensibility; concurrent gather. Tests with `respx`. |
| **3** | **Storage** | 2 | SQLite models (~5 tables) + `repository.py` (aiosqlite); `VectorStore` interface + `NumpyVectorStore` default; `dedup.py` ported. Round-trip + dedup tests. |
| **4** | **Ingest** | 1 | `ingest(raw) -> (item, is_new)`: exact→near dedup→embed→store atomically. |
| **5** | **Analysis engine** | 3 | Typed schemas (paper/model/product/benchmark/industry/community); `classifier`; per-type analyzers (port `analyzer.py`); `verifier` (retrieve + cross-reference). Idempotent by version. |
| **6** | **Cluster / Rank / Trend** | 2 | Embedding clustering + LLM labels; global `ranker` (importance×novelty×impact); `trend.py` ported (daily/weekly deltas). |
| **7** | **Renderers + Assembler** | 3 | 16 section renderer plugins; `ReportAssembler` (config-ordered) → rich Markdown (tables, callouts, Mermaid, timelines, citations); `proofread` pass. |
| **8** | **Orchestrator + CLI + Scheduler** | 2 | `pipeline/run.py` (stages, resume, backfill); `hermes run/backfill/status/sources`; launchd + systemd + cron files. **First end-to-end autonomous report.** |
| **9** | **Source breadth** | ongoing | Add OpenReview, PwC, Semantic Scholar, HF models/spaces, HN, Reddit, X, Bluesky, YouTube/Substack/Medium transcripts, funding/acquisitions — each a small plugin, prioritized by signal value. |
| **10** | **Hardening & quality** | ongoing | Per-stage error isolation; run manifest (cost/failures); nightly integration smoke (real sources, faked LLM); golden-report regression vs Perplexity; prompt tuning; self-critique pass. |

**First runnable milestone:** end of **Phase 8** — `hermes run` produces
`storage/reports/YYYY-MM-DD.md` with real arXiv/RSS/GitHub content, deep
analyses, clustering, trends, and all 16 sections. Everything before Phase 8 is
independently tested and mergeable.

---

## 9. Key Trade-offs (decided for the objective)

- **SQLite over Postgres** — zero infra, one file, plenty for a single-agent corpus. Loses horizontal scale you don't need.
- **Numpy vector store over Qdrant-server** — removes a service; brute-force cosine is sub-second at <100K items. Qdrant-embedded kept as an optional backend for growth.
- **One-shot CLI over Celery** — a crashed run is just a missed day, not a dead worker; OS scheduler is more reliable than a self-hosted broker. Dev loop also gets `hermes serve --loop`.
- **Local bge-m3 embeddings** — no rate limits/cost on the daily clustering/retrieval path; `embed` stays an optional extra so `uv sync` stays fast. (Note: bge-m3 is ~2GB and slow on CPU/Mac — default to a smaller embedder like `bge-small-en` and make it configurable; flag for Phase 3.)
- **Provider plugin over hardcoded Ollama** — the only real refactor of the best module, and it unlocks "automatic fallback across cloud models" + "easy to add providers" without touching the router again.

---

## 10. Open Questions for Phase 0

1. Embedder default: `bge-m3` (faithful to AIRIP) vs `bge-small-en` (fast on Mac). Recommend configurable, default small.
2. Report cadence: daily only, or also weekly deep-dive (port `weekly.py` idea as a second renderer pass)?
3. Should `storage/reports/` also mirror to Obsidian automatically (the workspace already syncs `*.md`)? Likely yes — the report is meant to be read in Obsidian.
4. Keep OTel spans in the router, or strip tracing entirely for simplicity? Recommend keep spans (cheap, no exporter needed).

---

## 11. Quality-First Revision (AUTHORITATIVE — supersedes §7–§9)

> **Principle:** optimize for report quality, not architectural purity. Every
> component exists only if it *measurably* improves the quality, accuracy,
> depth, or usefulness of the daily report. No infrastructure for elegance.

### 11.1 Quality rubric — the only test a component must pass

A component earns its place only if it raises one of these, measured against
"ask Perplexity for today's AI news":

| Dimension | What the reader gets |
|---|---|
| **Coverage** | More of the ecosystem sampled; fewer blind spots |
| **Accuracy / Verification** | Claims checked against independent sources; conflicts shown |
| **Depth** | Per-item analysis beyond a 3-line summary |
| **Synthesis** | Relationships, trends, clusters — not isolated blurbs |
| **Usefulness** | Takeaways, engineering implications, two-altitude explanations |
| **Trust / Provenance** | Primary vs signal sources labeled; citations; scope stated |

If a component maps to **none** of these, cut it.

### 11.2 Cut from the earlier design (fails the quality test)

| Cut | Why it fails |
|---|---|
| OTel tracer injection in router | Reader never sees a span. Keep `structlog` only. |
| Prometheus `/metrics` + metrics server | Not reader-facing. Keep a tiny token counter (cost safety so the agent stays alive) and drop the rest. |
| `VectorStore` plugin + Qdrant-local backend | Reader gets identical clusters from a single numpy brute-force store. Pick one, hardcode it. |
| Persistent circuit-breaker state machine | Built for a 24/7 service. For a once-a-day batch job, per-source **timeout + retry-once + skip-on-failure** achieves "one dead API ≠ no report" with zero state. |
| `repository.py` abstraction | Layering for its own sake. Use the SQLite session directly in stages; test against in-memory SQLite. |
| Embedder plugin | One `Embedder` class with a configurable model name. No plugin system. |
| LLM classifier | Heuristic (source_type + keywords) tags item type well enough. Spend the LLM budget on analysis. |
| LLM-assisted ranking | Heuristic rank (source prestige × recency × stars/citations × novelty) is as good and ~100× cheaper. |
| Auto-discovery metaclass for plugins | Explicit ordered lists — section order *is* report order, so an implicit registry is wrong. |
| `hermes serve --loop` | Dev convenience, not a product feature. Drop unless wanted. |

### 11.3 Kept — and exactly what it buys the reader

| Component | Dimension | Notes |
|---|---|---|
| Collectors (simple registry) | Coverage | 30+ sources. The single biggest lever on quality. |
| Dedup (sha256 + SimHash) | Accuracy | Don't report the same story 6 times. |
| Local embeddings | Synthesis | Enables clustering + verifier retrieval. Configurable model (default small/fast). |
| Typed analysis | Depth | **Start with ONE adaptive schema** (type passed in prompt) + free `type_specific` blob, not 6 Pydantic schemas. Validates fields that matter for rendering; avoids schema sprawl. Expand to per-type schemas only if rendering demands it. |
| Verifier (retrieve similar → corroborate/conflict) | Accuracy + Trust | Headline differentiator vs Perplexity. Flags single-source claims. |
| Clustering + cheap labels | Synthesis | Group the 6 articles about one event; label the cluster. |
| Trend deltas (rising/fading) | Synthesis | "Compare with previous work" — explicit requirement. |
| Heuristic ranker w/ source-prestige weighting | Usefulness | Decides what makes the report. Primary sources outrank signal sources. |
| Two-altitude explanations | Usefulness | Beginner analogy + expert mechanism in every deep-dive. |
| 16 section renderers (ordered list) | Usefulness | Report structure. One function per section, called in order. |
| Rich markdown (tables, callouts, *selective* Mermaid/timeline, citations) | Usefulness + Trust | Mermaid only where it clarifies; don't force it. |
| Proofread pass (cheapest model) | Usefulness | *Optional* — A/B it; keep only if it measurably improves readability. |
| Run manifest → "Coverage & Method" note | Trust | States which sources were checked and what failed. Nearly free. |
| Scheduler (launchd/systemd/cron) | — | Prerequisite for "autonomous." Not elegance. |

### 11.4 Revised minimal pipeline (only quality-bearing stages)

```
collect ─▶ ingest+dedup ─▶ analyze(top-N, adaptive schema + verifier)
                             ─▶ cluster + trend ─▶ rank
                             ─▶ render 16 sections (+optional proofread)
                             ─▶ archive + Coverage & Method note
```

The LLM router keeps only what touches the reader: **fallback across models**
(so the report always gets written) and a **token counter** (so the agent
stays alive). No plugin framework, no vector-store abstraction, no repository,
no circuit-breaker service, no metrics server.

### 11.5 Revised roadmap (quality-weighted)

| # | Phase | What it improves |
|---|---|---|
| **0** | Scaffold + config + structlog | — |
| **1** | LLM core: Ollama provider + fallback + token counter (no OTel/Prometheus) | Reliability of generation |
| **2** | Collectors: arXiv/RSS/GitHub/HF + concurrent gather + skip-on-fail | **Coverage** |
| **3** | SQLite + numpy vectors + dedup | Accuracy |
| **4** | **Analysis engine**: adaptive schema + verifier (cross-source) | **Depth + Accuracy** |
| **5** | Cluster + trend + heuristic rank (prestige-weighted) | **Synthesis + Usefulness** |
| **6** | 16 section renderers + rich markdown + Coverage note | **Usefulness + Trust** |
| **7** | Orchestrator + CLI + scheduler → first real report | Autonomy |
| **8** | **Quality loop**: diff Hermes vs Perplexity on the same day; tune prompts/selection | The actual optimization engine |
| **9** | Source breadth (OpenReview, PwC, Semantic Scholar, HN, Reddit, X, Bluesky, YouTube, funding…) | **Coverage** |
| **10** | Targeted depth: two-altitude explanations, engineering-implications prompts, benchmark tables | **Depth + Usefulness** |

Phase 8 is the key addition: the report only gets better if we **measure** it.
Periodically run both Hermes and "Perplexity: today's AI news" on the same day's
inputs and tune until Hermes wins on coverage, depth, and verification — not on
architecture.

---

## 12. Architecture-Review Integration (capability-bearing enhancements)

> **Principle (revised):** optimize for **report quality, reasoning ability, and
> future extensibility** — not minimalism for its own sake. Every component must
> still map to a quality dimension (§11.1). The difference from §11: capabilities
> that pay off in *reasoning* or *long-term continuity* (not just today's report)
> are now in scope, provided they are scoped so they don't become elegance-infra.

### 12.1 Verdict table

| # | Recommendation | Verdict | Rationale |
|---|---|---|---|
| 1 | Minimal FastAPI | **Accept (scoped)** | Operational window into an autonomous system; local-only, no auth, not in the report path. |
| 2 | Keep Qdrant | **Accept (scoped)** | Keep, but **embedded/local mode** — no server process. Enables RAG/memory/search later at ~zero ops cost. |
| 3 | Knowledge graph | **Accept (scoped)** | Lightweight SQLite-derived graph (entities + relationships), not a graph DB. Phased; resolution-quality caveat. |
| 4 | Multi-agent pipeline | **Accept (scoped)** | Adopt the *responsibility split*; **no agent-orchestration framework** (no Autogen/CrewAI/LangGraph). |
| 5 | Self-critique | **Accept** | In-pipeline Critic → Rewrite. Directly raises accuracy/structure. |
| 6 | RAG report generation | **Accept** | Writer retrieves historical reports/papers before drafting. Core differentiator vs Perplexity. |
| 7 | Long-term memory | **Accept (reframed)** | = the persistent stores Hermes already writes (SQLite + Qdrant + trend + KG). Not a new subsystem. |
| 8 | Autonomous research loops | **Accept (scoped)** | Gated by Planning Agent; partial-tolerant. Most expensive capability — bound it. |
| 9 | Multiple report types | **Accept** | Config-driven **report profiles**; no hardcoded daily-only path. |
| 10 | Multi-output rendering | **Accept (scoped)** | Clean `Renderer` + `Sink` interfaces; Markdown canonical. Notion/Telegram/Discord are *delivery sinks*, not renderers. |

### 12.2 FastAPI — minimal operational service (out of the report path)

Keep a single FastAPI app, **bound to 127.0.0.1, no auth, no users, no CRUD**.
The autonomous daily run is triggered by the OS scheduler (cron/launchd), **not**
by the API — so the API going down never stops a report. Endpoints are a window
into the system:

- `POST /runs` (trigger manual run), `GET /runs/{id}` (status + log tail)
- `GET /reports?q=` (search past reports), `GET /knowledge?q=` (search corpus + KG)
- `GET /collectors` (last-run health per source)

This supports the §11.5 Phase 8 quality loop (you must *see* runs to tune). It is
operational convenience, not report quality — so it stays minimal and optional.

### 12.3 Qdrant — keep, but embedded (no server)

Use `QdrantClient(path=...)` (on-disk local mode) or in-memory mode. This keeps
the Qdrant collection/payload-filter API the user wants for future semantic
search, RAG, report retrieval, and conversational querying, **without** running a
separate service. The §11 cut of the *numpy vector store + plugin* is reversed:
we use Qdrant directly (no `VectorStore` plugin abstraction — just the client).
If multi-process access is ever needed, promote to a server later; embedded is
the right default and adds no infra today.

### 12.4 Knowledge graph — lightweight, derived, SQLite-backed

A real graph database (Neo4j, etc.) would be elegance-infra. Instead:

- `entities` table: `(id, type, name, canonical_name, aliases_json, first_seen, last_seen)`
  where `type ∈ {company, model, paper, researcher, benchmark, framework, dataset, repo}`.
- `relationships` table: `(subject_id, predicate, object_id, confidence, source_item_id, first_seen)`
  where `predicate ∈ {released_by, beats, built_on, authored_by, competes_with, cites, part_of, succeeds}`.
- Populated **incrementally** from each analyzed item (the analysis prompt already
  emits entities/relations; we persist them). Resolution is **conservative**:
  normalize names + aliases; merge only on high-confidence match; never invent edges.

**Caveat (quality risk):** poor entity resolution *degrades* report quality
(wrong "competes_with" links). Start conservative; use LLM merge only for
ambiguous cases. Phase it **after** the core report works (§12.12, Phase 9). The
KG is what makes #6 (RAG), #7 (memory), #8 (research loops) possible — but it is
a derived index over the corpus, not a standalone system.

### 12.5 Multi-agent pipeline — responsibility split, no framework

Adopt the agent responsibilities as **focused modules** chained by a single
orchestrator. "Agent" = a module with one job + its own prompt/LLM role. **Do not
introduce an agent-runtime framework** — that is the elegance-infra §11 cut. The
flow:

```
Discovery Agent   → run enabled collectors, gather RawItems
Ingest           → dedup (sha256+SimHash) → embed → store (SQLite + Qdrant)
Planning Agent   → score importance; decide which items get deep research vs summary;
                   build the day's investigation plan (gates #8)
Research Agent   → for top items: autonomous loops (#8) + RAG retrieval (#6) → rich analysis
Verification Agent → cross-source corroborate/conflict; flag single-source claims
Trend Agent      → daily/weekly deltas + KG-based trend reasoning
Writer Agent     → RAG-augmented draft (retrieve historical reports/papers) → 16 sections
Critic Agent     → structured critique (weak explanations, unsupported claims, missing context, structure)
Writer Agent     → rewrite per critique
Markdown Renderer → final Markdown (+ optional Sink delivery, #10)
Archive          → store report; update KG (#3); write trend snapshot; Coverage & Method note
```

Each agent is a plain `async def` over `RunContext`. The orchestrator is a linear
(plus one critique→rewrite loop) sequence — easy to test and resume.

### 12.6 Self-critique (in-pipeline Critic)

Research → Draft → **Critique → Rewrite** → Final. The Critic uses a strong
reasoning role and returns a *structured* list of fixes (not prose), e.g.
`[{section, issue, fix}]`; the Writer rewrites only the flagged parts. This is a
real accuracy/structure win and dovetails with Verification (Critic can demand
"cite a source for this claim"). Cost: one extra pass on the draft — acceptable
because it directly raises published quality. Keep it; make the Critic's output
schema strict (`extra="forbid"`) so a malformed critique is caught, not silently
applied.

### 12.7 RAG-augmented report generation

Before the Writer drafts, it retrieves from the knowledge base: prior reports
(Qdrant + report index), previous papers/models/announcements (corpus), and
related entities (KG). This yields continuity Perplexity cannot match ("we covered
the preprint 3 months ago; here's what changed"; "benchmark X was last beaten by
Y"). Retrieval is bounded (top-k per section) to control cost. This is the
headline reasoning feature — accept.

### 12.8 Long-term memory — reframed, not a new subsystem

"Long-term memory" = the persistent stores Hermes already writes, queried over
time: (a) SQLite corpus + analyses, (b) Qdrant vectors, (c) trend snapshots,
(d) the §12.4 KG. **Do not build a separate memory service.** Hermes becomes more
knowledgeable simply by accumulating these every day and querying them in #6/#8.

### 12.9 Autonomous research loops — gated and partial-tolerant

The Research Agent, for items the Planning Agent marks important, runs a loop:
model → original paper → GitHub impl → benchmark results → community discussion →
competing approaches → comparative analysis. **Bound it:** only top-N by
importance score; cap loop depth/breadth; **degrade gracefully** (report what was
found, flag what wasn't, never block the report on a failed sub-step). This is the
biggest quality differentiator (depth) but the most expensive — the Planning gate
is what keeps it affordable. Phase it after the core report (§12.12, Phase 9).

### 12.10 Multiple report types — config-driven profiles

A **report profile** (YAML/pydantic) defines a report's shape; the pipeline is
parameterized by it, never hardcoded for daily:

```yaml
daily:      { collectors: [arxiv, rss, github, hf, ...], sections: [all 16], top_k: 25, research_loops: true,  depth: standard }
weekly:     { collectors: [same],                        sections: [all 16], top_k: 60, research_loops: true,  depth: deep }
deep_dive:  { trigger: manual|planning,                  sections: [focused],     top_k: 1,  research_loops: true,  depth: exhaustive }
company_profile: { trigger: manual,                      sections: [company-specific], ... }
trend_report:    { trigger: manual|schedule,             sections: [trend-focused], ... }
```

Breaking-news = a daily run with `research_loops: true` + higher top-k triggered
on a high-importance signal. No new pipeline code per type — just new profiles.

### 12.11 Multi-output rendering — Renderer + Sink

Markdown is canonical. Define two small protocols:

```python
class Renderer(Protocol):            # structured ReportModel -> formatted output
    fmt: str                         # "markdown" | "html" | "pdf"
    def render(self, report: ReportModel) -> str | bytes: ...

class Sink(Protocol):                # deliver already-rendered content somewhere
    name: str
    async def deliver(self, content: str, meta: ReportMeta) -> None: ...  # obsidian, email, telegram, discord, notion
```

Markdown first; HTML/PDF are cheap seconds (md→html→pdf); **Obsidian = Markdown
with wikilinks** (a Markdown variant, not a new renderer). Notion/Telegram/Discord
are **Sinks that deliver the Markdown** — not separate render formats. Do **not**
build 8 renderers now; build the interface + Markdown, add others only when a
sink actually needs them. This keeps the "easy to add formats" property without
the elegance cost.

### 12.12 Revised target architecture (agent flow)

```
                         ┌──────── hermes run (cron/launchd) ────────┐
                         │            [ FastAPI: optional window ]   │
                         └───────────────────────┬───────────────────┘
   Discovery ─▶ Ingest(dedup+embed) ─▶ Planning(score+plan)
        │                                     │
        ▼                                     ▼
   Collectors                            Research Agent (loops #8 + RAG #6)
   (circuit-skip)                             │
        │                                     ▼
        ▼                              Verification Agent (corroborate/conflict)
   RawItem[] ─▶ Item[] ─▶ Analysis[]       │
                                             ▼
                                        Trend Agent (deltas + KG)
                                             │
                                             ▼
                                        Writer Agent (RAG draft)
                                             │
                                             ▼
                                        Critic Agent (structured fixes)
                                             │
                                             ▼
                                        Writer Agent (rewrite)
                                             │
                                             ▼
                                        Markdown Renderer ─▶ Sink(s)
                                             │
                                             ▼
                                        Archive + KG update + trend snapshot + Coverage note
```

### 12.13 Revised roadmap (extends §11.5)

| # | Phase | What it adds |
|---|---|---|
| 0–7 | (as §11.5) | Scaffold → first real daily report (collectors, SQLite+Qdrant-embedded, dedup, analysis+verifier, cluster+trend+rank, 16 renderers, orchestrator+CLI+scheduler, quality loop) |
| **8** | **Multi-agent refactor** | Split stages into Discovery/Planning/Research/Verification/Trend/Writer/Critic agents; add in-pipeline Critic→Rewrite; RAG-augmented Writer (retrieve historical reports/papers) |
| **9** | **Knowledge graph + research loops** | `entities`/`relationships` tables; incremental extraction; Planning-gated autonomous research loops (partial-tolerant) |
| **10** | **Report profiles + multi-output** | Config-driven daily/weekly/deep-dive/company/trend profiles; `Renderer`+`Sink` interfaces; Markdown canonical, HTML/PDF/Obsidian variants, delivery sinks |
| **11** | **Minimal FastAPI** | Local-only operational endpoints (trigger/status/search/collectors); out of report path |
| **12** | **Source breadth + depth** | OpenReview, PwC, Semantic Scholar, HN, Reddit, X, Bluesky, YouTube, funding; two-altitude explanations, engineering-implications, benchmark tables |

### 12.14 What I pushed back on (kept cut from §11)

These §11 cuts **still hold** — the review does not revive them, and adding them
would be elegance-infra, not capability:

- **OTel tracer / Prometheus server** — not reader-facing. Keep structlog + a token counter only.
- **Persistent circuit-breaker state machine** — replaced by per-source timeout + retry-once + skip-on-failure (sufficient for a daily batch job).
- **`repository.py` abstraction** — use the SQLite session directly; test on in-memory SQLite.
- **Embedder plugin** — one `Embedder` class, configurable model name.
- **LLM classifier** — heuristic (source_type + keywords) tags item type; spend LLM budget on analysis.
- **LLM-assisted ranking** — heuristic rank (source prestige × recency × stars/citations × novelty); the Planning Agent may use light LLM only for top-tier tie-breaks.
- **Auto-discovery metaclass** — explicit ordered lists (section order *is* report order).
- **Separate graph DB / agent framework / memory service** — explicitly avoided (§12.3, §12.5, §12.8).

**Net:** the review's capabilities are accepted, but each is scoped to the
minimal form that delivers the reasoning/continuity benefit — Qdrant-embedded
(not a server), a SQLite-derived KG (not Neo4j), agent *modules* (not a framework),
and Renderer/Sink interfaces (not eight renderers). The report pipeline stays a
single-process orchestrated flow, independently testable and resumable.
