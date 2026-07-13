# Hermes — Autonomous AI Research Intelligence Agent

> Hermes runs once a day, researches the entire AI ecosystem across 15+ sources,
> reasons over every top item with LLMs, and writes one extensive Markdown report
> — no human interaction, no daemon, no database server.

[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-237%20passing-brightgreen.svg)](tests/)

**Version 0.1.0** · Python ≥ 3.11 · SQLite + httpx + structlog · Author: Atandra Bharati

---

## What Hermes does

Every `hermes news <prompt.md>` invocation executes the **unified research
pipeline** (`run_news_pipeline` in `src/hermes/pipeline/orchestrator.py`). It
turns raw web signal into an institutional-grade intelligence report driven by
a Markdown prompt:

```
parse_prompt → collect → search → synthesize (per-section, with critic loop)
        → report_editor → renderer → archive
```

1. **Collect** — 15 source adapters (arXiv, HuggingFace, GitHub Trending/Releases,
   RSS, Hacker News, Reddit-excluded, Semantic Scholar, OpenReview, Papers-With-Code-excluded,
   Bluesky, YouTube, blogs, Dev.to, Lobsters, Tavily, Context7) pull raw items for the
   lookback window.
2. **Search** — brief-path `pipeline/search.py` runs Tavily queries per section
   (backed by fallback collectors) and dedupes the merged source set.
3. **Synthesize** — per section, an LLM turns the curated sources into prose;
   a bounded Critic can reject and request a rewrite (up to 2 retries). Claims
   flagged `re-research` are routed back to a single bounded web-search pass.
4. **Report editor + renderer** — consistency fixes, citation normalization, and
   Markdown assembly → sinks (file + optional Obsidian) → archive + manifest.

The brief pipeline always runs the same phases — collect, search, per-section
synthesize with critic loop, report assembly, archive — regardless of the
prompt's section count. Cadence (`HERMES_CADENCE=daily|weekly|monthly`)
controls lookback window, per-section source count, and citation thresholds.

---

## Key features

- **Fully autonomous prompt-driven report** — one CLI command
  (`hermes news <prompt.md>`), scheduled by the OS (launchd / systemd / cron).
  No daemon, no broker.
- **Structured, artifact-passing pipeline** — every stage exchanges typed
  dataclasses, never prompt text. Only the Section Writer may emit prose.
- **Provenance on every claim** — each claim carries `{text, sources, confidence,
  status}`; the renderer normalizes citations to a global numbered `References`
  section.
- **Bounded self-critique** — a professional-standards Critic rejects reports that
  leak planning, merely summarize, or lack synthesis, and feeds rewrite
  instructions back to the Writer.
- **Partial tolerance** — any stage may return a partial result. One dead API
  never blocks the report; one LLM outage falls back to heuristics.
- **Self-improving memory** — critique/quality lessons persist in the `lessons`
  table and are fed into the next run's writer/critic prompts.
- **Zero-infra storage** — a single SQLite file + optional numpy/Qdrant vectors.
  No Postgres, no server.
- **Role-routed LLM** — one backend at a time (Ollama / OpenCode Go /
  OpenAI-compatible) with a per-tier model chain and token budget.

---

## Quickstart

```bash
# 1. Clone + install (editable, with dev deps).
git clone <repo> && cd hermes
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Configure.
cp .env.example .env
# Edit .env — set HERMES_LLM_BACKEND, api key, (optional) search keys.

# 3. Verify your LLM provider + model catalog is live.
hermes models

# 4. Verify your LLM provider + model catalog is live.
hermes models

# 5. Run the unified pipeline.
hermes news example_prompt.md

# 6. Read the report.
open storage/reports/$(date +%Y-%m-%d).md
```

Evaluate the report or record a feedback rating:

```bash
hermes eval storage/reports/ai-state-of-the-industry-2026.md \
  --prompt example_prompt.md --cadence weekly
hermes eval example_prompt.md --rate 4
```

> **Test/tooling note:** the test suite and linters must be run with the project
> virtualenv's Python (`.venv/bin/python`), because the base `python`/`python3`
> may lack `structlog` and the dev extras:
> ```bash
> .venv/bin/python -m pytest tests/ -q      # 237 tests, offline, no network/LLM
> .venv/bin/python -m ruff check src tests
> ```

---

## Architecture at a glance

```
                         hermes news <prompt.md>
                                       │
   ┌────────── PARSE PROMPT ────────────┴───────────────────┐
   │  pipeline/spec.py: parse_prompt(md) → BriefSpec          │
   │  (title, source_names, sections, deliverables, quality)   │
   └──────────┬─────────────────────────────────────────────┘
              │ BriefSpec
   ┌────────── COLLECT ──────────────────────────────────────┐
   │  collectors/*  →  RawItem[]  (15 sources, timeout +    │
   │  retry-once + skip-on-failure per source)              │
   └──────────┬─────────────────────────────────────────────┘
              │ RawItem[]
   ┌────────── SEARCH ──────────────────────────────────────┐
   │  pipeline/search.py (Tavily) + fallback collectors     │
   │  → deduped SearchResult[] for the brief                │
   └──────────┬─────────────────────────────────────────────┘
              │ per-section sources
   ┌────────── SYNTHESIZE / CRITIQUE / EDIT / RENDER ────────┐
   │  synthesize (per section, with critic loop) → edit_report│
   │  → render_report → sinks → archive                      │
   └──────────────────────────────────────────────────────────┘
```

---

## CLI commands

| Command | What it does |
|---------|--------------|
| `hermes news <prompt.md>` | Unified research pipeline (collect → ingest → evidence → graph → synthesize → report) |
| `hermes eval <report.md> --prompt <prompt.md> [--cadence] [--rate 1-5]` | Evaluate a brief report / record user feedback |
| `hermes status` | DB stats: items, reports, evals, adapter state |
| `hermes sources` | List registered + enabled collectors |
| `hermes models` | List models on the live endpoint + catalog check |
| `hermes profiles` | List available report profiles |
| `hermes quality [--date YYYY-MM-DD]` | Self-assess a report on 6 quality dimensions |
| `hermes help` | Usage |

See [docs/CLI.md](docs/CLI.md) for flags and scheduler setup.

---

## Project layout

```
hermes/
├── src/hermes/
│   ├── cli.py                 # Entry points (hermes news|eval|quality|status|sources|models|profiles)
│   ├── config.py              # Pydantic settings (HERMES_ env prefix)
│   ├── collectors/            # 15 source adapters + registry
│   ├── dedup.py               # 64-bit SimHash + SHA-256 exact dedup
│   ├── llm/                   # catalog, roles, router, providers, embed, prompts
│   ├── pipeline/
│   │   ├── orchestrator.py    # run_news_pipeline — the unified pipeline
│   │   ├── spec.py            # parse_prompt(md) → BriefSpec
│   │   ├── cadence.py         # CadenceSpec + HERMES_CADENCE loader
│   │   ├── planner.py, search.py, synthesize.py, report.py, eval.py, adapter.py
│   │   ├── retrieval.py      # past-report RAG chunks
│   │   └── models.py          # Structured intermediate artifacts
│   ├── storage/               # Async SQLite + vectors + KG (KG tables are defined but not written)
│   ├── output.py              # Sinks: MarkdownFileSink + ObsidianSink
│   └── profiles.py            # daily / weekly / minimal / deep_dive / trend_report
├── docs/                      # This documentation set (see index below)
├── tests/                     # 237 tests (unit + integration), offline
├── prompts/                   # Example brief prompts
├── scheduler/                 # launchd / systemd / cron templates
└── storage/                   # SQLite DB, reports, manifests, quality (gitignored)
```

---

## Documentation index

| Document | Covers |
|----------|--------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture, module map, data flow, component contracts, design decisions |
| [docs/PIPELINE.md](docs/PIPELINE.md) | pipeline stages, evidence graph, story blueprint, bounded self-critique |
| [docs/REPORT_QUALITY_REVIEW.md](docs/REPORT_QUALITY_REVIEW.md) | 2026-07-13 monthly report post-mortem — the 9 report-quality scopes |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Every env var, settings groups, profiles, `.env` reference |
| [docs/COLLECTORS.md](docs/COLLECTORS.md) | Collector registry, source list, adding a new collector |
| [docs/LLM_PROVIDERS.md](docs/LLM_PROVIDERS.md) | Catalog, roles, tiers, provider wiring, reasoning-starvation pitfall |
| [docs/STORAGE.md](docs/STORAGE.md) | SQLite schema, vector store, KG, forward-migration |
| [docs/TESTING.md](docs/TESTING.md) | Test layout, fixtures, helpers, running the suite, adding tests |
| [docs/CLI.md](docs/CLI.md) | All CLI commands, flags, scheduler setup |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Dev setup, testing, lint, code style |
| [CHANGELOG.md](CHANGELOG.md) | Release history |

> **Historical / design references:** [`docs/HERMES_DESIGN.md`](docs/HERMES_DESIGN.md)
> (original architecture & migration design) and
> [`docs/COGNITION_DESIGN.md`](docs/COGNITION_DESIGN.md) (cognitive architecture)
> describe the evolution and are kept for context. The **current** pipeline is
> the design documented in ARCHITECTURE.md / PIPELINE.md.

---

## Design principles

| # | Principle | What it means |
|---|-----------|----------------|
| P1 | **Quality is the only acceptance test** | Every agent is justified by a rubric dimension it raises (Coverage · Accuracy · Depth · Synthesis · Usefulness · Trust). |
| P2 | **Cheap determinism, expensive intelligence** | Heuristics/SQL for type tagging, ranking, dedup, trend deltas. LLM budget goes to analysis, verification, critique, writing. |
| P3 | **Every claim carries provenance + confidence** | A claim is `{text, sources[], confidence, status}`. Status never silently upgrades. |
| P4 | **Partial tolerance** | Any stage may return a partial result with a `gaps[]` list. One dead API never blocks the report. |
| P5 | **Bounded cognition** | Hard token/cost/depth/wall-clock caps on every agent. |
| P6 | **No agent-runtime framework** | An "agent" is a focused `async` module with one job. No Autogen/CrewAI/LangGraph. |
| P7 | **Single-provider simplicity** | One LLM backend at a time (Ollama, OpenCode Go, or OpenAI-compatible) with a role-routed fallback chain. |

---

## Tech stack

| Layer | Choice | Why |
|-------|--------|-----|
| Python | ≥ 3.11 | `match`, `Self`, PEP 695 type hints |
| Settings | pydantic + pydantic-settings | Typed env validation, `HERMES_` prefix |
| Logging | structlog | Console + JSON renderer, contextvars |
| Storage | SQLAlchemy[asyncio] + aiosqlite | One file, zero infra, async |
| Vectors | numpy (default) or Qdrant (embedded) | Pluggable VectorStore |
| HTTP | httpx | Async, timeout, retry via tenacity |
| LLM | Ollama / OpenCode Go / OpenAI-compatible | Role-routed fallback chain, per-tier catalog |
| Search | Tavily (optional) | Brief pipeline live web research |
| Templates | Jinja2 | Versioned prompt templates |
| Testing | pytest + pytest-asyncio + respx | 237 tests, offline, no network/LLM server |

---

## License

MIT.
