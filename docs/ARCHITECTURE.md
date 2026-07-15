# Architecture

> System architecture, module map, data flow, and component contracts for newsagent.

---

## 1. High-level data flow

```
                          newsagent news <prompt.md>
                                       │
   ┌── PARSE PROMPT ────────┴──────────────────┐
   │  pipeline/spec.py: parse_prompt(md) →      │
   │  BriefSpec (title, sources, sections, ...)  │
   └──────────┬──────────────────────────────────┘
              │
   ┌── COLLECT ┴──────────────────────────────────┐
   │  collectors/*  →  RawItem[]                   │
   │  (15 sources, timeout + retry-once)          │
   └──────────┬──────────────────────────────────┘
              │
   ┌── INGEST ┴───────────────────────────────────┐
   │  Deduper (SHA-256 + SimHash)                  │
   │  → Embedder (hashing / sentence-transformers) │
   │  → Store: Item + ItemAlias + VectorRow        │
   └──────────┬───────────────────────────────────┘
              │ canonical Item[]
   ┌── SEARCH ┴────────────────────────────────────┐
   │  pipeline/search.py (Tavily) + fallback       │
   │  collectors → deduped SearchResult[] per      │
   │  section                                       │
   └──────────┬───────────────────────────────────┘
              │ per-section sources
   ┌── SYNTHESIZE / CRITIQUE / EDIT / RENDER ────┐
   │  synthesize() (per-section, critic loop) →    │
   │  edit_report() (citations, dedup) →           │
   │  render_report() → sinks (Markdown + Obsidian)│
   │  → Store: Report archive + Lesson memory      │
   └────────────────────────────────────────────────┘
```

---

## 2. Module responsibilities

### 2.1 `newsagent.collectors` — Source plugins

**Contract:** `CollectorAdapter.collect(since, limit) -> list[RawItem]`.

Each collector is a class in `collectors/<name>.py` with a `source_type`
class attribute. The `registry.py` maps string names to classes and provides
`run_collector()` with per-source timeout + retry-once + skip-on-failure.

| Collector | Source | Adapter type |
|-----------|--------|---------------|
| `arxiv` | arXiv API | HTTP (XML parsing) |
| `rss` | RSS/Atom feeds | HTTP (feedparser) |
| `github_trending` | GitHub Trending HTML | HTTP (HTML scraping) |
| `github_releases` | GitHub Releases API | HTTP (JSON) |
| `huggingface` | HuggingFace Hub API | HTTP (JSON) |
| `blog` | Curated blog RSS | RSS collector |
| `hacker_news` | HN Algolia API | HTTP (JSON) |
| `semantic_scholar` | Semantic Scholar API | HTTP (JSON) |
| `openreview` | OpenReview API | HTTP (JSON) |
| `bluesky` | Bluesky AT Protocol | HTTP (JSON) |
| `youtube` | YouTube Data API | HTTP (JSON) |
| `tavily` | Tavily Search API | HTTP (JSON) |
| `context7` | Context7 library docs | HTTP (JSON) |
| `devto` | Dev.to articles | HTTP (JSON) |
| `lobsters` | Lobsters curated tech | HTTP (JSON) |

15 collectors are registered (all enabled by default). The `papers_with_code`
and `reddit` modules exist but are **excluded from the registry by design**
(unreliable public web APIs); the gaps they leave are filled by Tavily,
Context7, GitHub Releases, Dev.to, and Lobsters. To add a collector: see
[COLLECTORS.md](./COLLECTORS.md).

### 2.2 `newsagent.dedup` — Deduplication

- **`simhash(text) -> int`** — 64-bit SimHash from token bigrams.
- **`Deduper`** — in-memory `{simhash: uid}` registry with Hamming-distance
  near-dup check. Seeded from existing canonical items' SimHashes at ingest start.
- Near-duplicates become `ItemAlias` rows, not re-analyzed.

### 2.3 `newsagent.llm` — LLM layer

```
catalog.py          → tier → model chain (OLLAMA_CATALOG, OPENCODE_GO_CATALOG)
roles.py            → role → tier → RoleSpec (chain, temperature, max_tokens)
router.py           → LLMRouter: walks chain, fallback, token budget, accounting
providers/
  base.py           → BaseProvider + ProviderResult
  ollama.py         → OllamaProvider (/api/chat + /api/generate fallback)
  opencode_go.py    → OpenCodeGoProvider (/chat/completions, OpenCode Zen)
  openai_compatible → OpenAICompatibleProvider (generic /chat/completions)
  registry.py       → build_registry() wires providers by backend setting
embed.py           → Embedder (hashing or sentence-transformers)
prompts/            → Jinja2 templates
```

For provider wiring details: see [LLM_PROVIDERS.md](./LLM_PROVIDERS.md).

### 2.6 `newsagent.pipeline` — The unified pipeline

Orchestrated by `run_news_pipeline()` in `pipeline/orchestrator.py`. Every
stage passes structured artifacts (not prompt text). The pipeline has a
single phase — the brief path — that runs for every prompt.

| Phase | Stage | Module(s) | Output |
|-------|-------|-----------|--------|
| **ALWAYS** | **parse_prompt** | `pipeline/spec.py` | `BriefSpec` (title, sources, sections, deliverables, quality) |
| | **plan_queries** | `pipeline/planner.py` | `ResearchQuery` list |
| | **search** | `pipeline/search.py` + fallback collectors | `SearchResult` list |
| | **rag** | `pipeline/retrieval.py` | past-report chunks + similarity context |
| | **synthesize** | `pipeline/synthesize.py` (parallel) | per-section prose with critic loop + CoT backstop |
| | **assemble_report** | `pipeline/report.py` | final Markdown report |
| | **sinks** | `output/*.py` | Markdown + Obsidian delivery |
| | **archive** | `pipeline/orchestrator.py` | `Report` row |

Cadence is read once at the top of the orchestrator from
`settings.cadence` (env: `NEWSAGENT_CADENCE=daily|weekly|monthly`) and yields a
`CadenceSpec` that drives the lookback window, per-section source count,
citation thresholds, and synthesis budget.

The brief spec format, search/backfill behavior, citation resolution, eval,
and adaptive adapter are part of the same orchestrator — they used to live
in the `newsagent/brief/` package and have moved into `newsagent/pipeline/`:

| Module (was) | Module (now) | Job |
|--------------|--------------|-----|
| `brief/spec.py` | `pipeline/spec.py` | `parse_prompt(md) -> BriefSpec` (title, source_names, sections, deliverables, quality) |
| `brief/planner.py` | `pipeline/planner.py` | section / source query planning |
| `brief/search.py` | `pipeline/search.py` | `SearchProvider` (Tavily) + `dedup_sources` + `select_relevant` |
| `brief/synthesize.py` | `pipeline/synthesize.py` | `synthesize_section_with_review` (synth → critic → optional rewrite) + `count_citations` |
| `brief/report.py` | `pipeline/report.py` | `resolve_citations` ([src:URL] → [n]) + `assemble_report` |
| `brief/eval.py` | `pipeline/eval.py` | `evaluate_report` (coverage · citation · quality · cadence scores) |
| `brief/adapter.py` | `pipeline/adapter.py` | `PromptAdapter` — per-prompt adaptive state (per_section_sources, extra_queries) |
| `brief/run.py` | `pipeline/orchestrator.py` | `run_news_pipeline` — orchestrates the full pipeline |

Stage details: [PIPELINE.md](./PIPELINE.md).

### 2.7 `newsagent.storage` — Persistence

| Module | Role |
|--------|------|
| `models.py` | 18 SQLAlchemy tables (Item, Analysis, Cluster, Report, Entity, Relationship, Lesson, ReportEval, ResearchPlanRow, ClaimRow, EvidenceRow, EntityAliasRow, EntityHistoryRow, TimelineRow, ...) |
| `db.py` | `Store` (async SQLite engine + session factory + schema create + forward-migrate) |
| `vectorstore.py` | `VectorStore` protocol + NumpyVectorStore + QdrantVectorStore |
| `kg.py` | Knowledge graph queries (`search_entities`, `relations_for`) |

Schema details: [STORAGE.md](./STORAGE.md).

### 2.8 `newsagent.output` — Sinks

| Sink | Delivery |
|------|----------|
| `MarkdownFileSink` | `storage/reports/YYYY-MM-DD.md` (canonical) |
| `ObsidianSink` | `<vault>/newsagent_YYYY-MM-DD.md` with frontmatter + tags |

`build_sinks(settings)` returns the active sink list based on whether
`NEWSAGENT_STORAGE_OBSIDIAN_VAULT` is set.

### 2.9 `newsagent.config` — Settings

Pydantic settings with `NEWSAGENT_` env prefix. Groups: `collectors`, `llm`,
`embed`, `pipeline`, `storage`, `search`, `rag`, `cadence`. See
[CONFIGURATION.md](./CONFIGURATION.md).

### 2.10 `newsagent.profiles` — Report profiles

| Profile | top_k_analysis | depth | description |
|---------|----------------|-------|-------------|
| `daily` | 25 | standard | Default autonomous daily report. |
| `weekly` | 60 | deep | Weekly deep-dive with higher top-k. |
| `minimal` | 15 | standard | No-API-key minimum: arxiv, rss, github trending/releases, huggingface, hn. |
| `deep_dive` | 10 | exhaustive | Focused exhaustive analysis of the top items. |
| `trend_report` | 40 | standard | Trend-focused report. |

Profiles still carry a `sections` list, but the unified pipeline builds a
**dynamic** report from the parsed brief — that column does not constrain
the output.

### 2.11 `newsagent.cli` — Entry points

| Command | What it does |
|---------|---------------|
| `newsagent news <prompt.md>` | The unified brief pipeline: collect → search → synthesize → render → archive |
| `newsagent eval <report.md> --prompt <prompt.md> [--cadence] [--rate 1-5]` | Evaluate a brief report / record user feedback |
| `newsagent status` | Show DB stats: items, reports, evals |
| `newsagent sources` | List registered + enabled collectors |
| `newsagent models` | List models on the live endpoint + catalog check |
| `newsagent profiles` | List available report profiles |
| `newsagent quality [--date]` | Self-assess a report on 6 quality dimensions |

CLI details: [CLI.md](./CLI.md).

---

## 3. RunContext — the shared bus

```python
@dataclass
class RunContext:
    settings: NewsAgentSettings
    store: Store
    router: LLMRouter
    embedder: Embedder
    vectorstore: VectorStore
    run_date: datetime
    sources_checked: list[str]      # filled by collect
    sources_failed: list[str]       # filled by collect
    notes: dict                     # per-run accumulation
    memory_lessons: list[str]       # loaded from Lesson table at start
```

Every pipeline stage receives `RunContext` and reads/writes through it. No stage
touches settings env vars or constructs its own DB connection.

---

## 4. Failure model

| Failure | Behavior |
|---------|---------|
| One collector API down | `run_collector` skips it after `retry_once`; logged; report continues |
| All collectors fail | Ingest gets 0 items; render writes a "no items today" report |
| LLM provider down | Router walks the fallback chain → if all fail, heuristic fallback (labeled "heuristic") |
| LLM returns empty text | Router treats as a failure → tries next model/heuristic |
| Token budget exceeded | Router raises `LLMError`; stage catches → heuristic analysis |
| Analyzer LLM fails for one item | Heuristic analysis (importance from source prestige + stars/likes) |
| Critic LLM fails | Self-critique returns the original body (no rewrite) |
| Brief search API down | `search.failed` logged; synthesize uses parametric knowledge |
| Research loop finds no extra sources | Re-synthesize with existing sources; gaps noted |

---

## 5. Design decisions

### Why SQLite over Postgres?
One file, zero infra, async via aiosqlite. The daily corpus is <100K items —
SQLite handles this in milliseconds on CPU. No Alembic; `db.py` forward-migrates
missing columns on startup.

### Why numpy vectors over Qdrant server?
Brute-force cosine over <100K 768-d vectors is <50ms on an M2. Qdrant-embedded
(local mode, no server) is available via `NEWSAGENT_STORAGE_VECTOR_BACKEND=qdrant`
for larger corpora.

### Why a one-shot CLI over a daemon?
A research report doesn't need a long-running process. `launchd` (macOS) or
`systemd` (Linux) invokes `newsagent news <prompt.md>` once a day. No broker
(Celery/Redis), no worker crashes, no memory leaks across days.

### Why role-routed models instead of one big model?
Cheap roles (label, summarize) use a fast cheap model; expensive roles (write,
research) use a capable writer model. This avoids paying reasoning-token
overhead on 64-token label tasks. See [LLM_PROVIDERS.md](./LLM_PROVIDERS.md).

### Why a single dynamic report instead of 18 fixed renderers?
The previous 18-section `newsagent/renderers` system forced every report into the
same fixed structure. The report is now assembled dynamically by
`pipeline/report.py::assemble_report` from the per-section prose — sections
appear because the prompt defines them, not because a renderer `section_id`
was registered. The 18 renderers are gone as of the pipeline unification;
the report structure is now: brief title + sections (synthesized per-prompt)
+ References & Provenance.

### Why deterministic-first Research Intelligence Layer?
Claims, entities, and timelines can be extracted with heuristics (keyword
matching, Levenshtein, date patterns) at zero LLM cost. The LLM budget goes to
analysis and writing, not graph construction.

### Why cluster-based synthesis instead of per-item summaries?
A daily report with 25 items producing 25 individual summaries reads like a news
aggregator, not a research briefing. Cluster-based synthesis groups related items
(embedding similarity) and generates one unified narrative per topic. This:
- Reduces LLM calls from N per-item to ~K per cluster (K << N).
- Produces cross-document reasoning (comparisons, contradictions, context).
- Eliminates repetitive boilerplate and "single-source" noise.
- Prioritizes significance (cluster aggregate score) over recency.
- Resembles an industry research analyst's briefing, not a feed reader.

### Why story-driven rendering instead of item-driven rendering?
Cluster synthesis still produced item-centric narratives — "here are N articles
about X." Story-driven rendering goes further: it produces `Story` objects that
answer *questions about the ecosystem* (what happened, why it matters, who wins,
what's next). Each story is a unit of intelligence, not a unit of content.
Renderers ask "what research frontiers emerged?" not "which papers were posted?"
This makes the report read like Deep Research, not like an expanded RSS feed.

### Why a cross-document entity graph?
Per-item analysis extracts entities and relationships, but they're isolated.
The StoryGraph connects entities AND claims across items — "FakeLab" in an
arXiv paper and "FakeLab" in a funding announcement become the same node.
Claims are deduplicated and corroborated across sources. This enables:
- Significance scoring based on entity centrality.
- Cross-story links (stories that share entities are probably related).
- Claim corroboration (same claim from 2+ sources = CORROBORATED).
- A shared evidence pool built once and used by all LLM calls.
- The synthesizer can identify contradictions and second-order effects.

### Why a research planning stage?
Without planning, story synthesis discovers stories ad-hoc from clusters.
The research planner runs ONE LLM call after graph construction to:
- Identify the 5-10 major stories before any writing happens.
- Assign key questions each story should answer.
- Flag evidence gaps and contradictions to resolve.
- Filter noise (incremental marketing, duplicate coverage).
This plan guides the story synthesizer, ensuring
the final report focuses on what matters rather than what happened to be clustered.

### Why batched story synthesis?
The original synthesizer made one LLM call per cluster. With 10 clusters,
that's 10 LLM calls. The batched synthesizer groups small clusters (≤3 items)
into batches of 3, reducing calls from 10 to ~4. Large clusters (≥4 items)
still get their own call for quality. This cuts LLM cost by ~60% while
preserving synthesis quality.