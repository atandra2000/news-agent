# newsagent — Pipeline Unification Design

**Date:** 2026-07-13
**Status:** Approved
**Author:** Atandra Bharati (with Claude)
**Objective:** Replace the two-pipeline structure (`newsagent run` daily + `newsagent news` brief) with a single, brief-driven pipeline. The cognition core (artifact-passing 14 stages in `pipeline/stages/`) becomes the body of the brief path. All legacy/fallback code is deleted. One command, one pipeline, one file.

---

## 1. User-facing surface

### 1.1 Commands (final)

| Command | Purpose |
|---|---|
| `newsagent news <prompt.md>` | The one production command. Reads the prompt, runs the unified pipeline, writes `<prompt-slug>.md`. **Required** arg is the prompt file. |
| `newsagent status` | DB stats (items, reports, evals). Unchanged. |
| `newsagent sources` | List registered + enabled collectors. Unchanged. |
| `newsagent models` | List models on the live endpoint. Unchanged. |
| `newsagent profiles` | List report profiles. CLI shape unchanged; content rebuilt. |
| `newsagent eval <report.md> --prompt <prompt.md>` | Score a past report. Unchanged. |
| `newsagent quality [--date YYYY-MM-DD]` | Self-assess a report. Unchanged. |
| `newsagent help` | Usage. Unchanged. |

**Removed subcommands:** `newsagent run`, `newsagent backfill`, `newsagent research`.

**Removed flags from `newsagent news`:** `--daily`, `--weekly`, `--monthly`, `--rate`, `--queries-per-section`, `--source-queries`. Cadence comes from `.env` only.

**Required argument:** `<prompt.md>`. The 9 prompts in `prompts/` become the user-editable inputs. The `example_prompt.md` in the repo root is the canonical example.

### 1.2 Output

One file: `storage/reports/<brief-slug>.md` where slug is the prompt's first H1 normalized to lowercase + hyphens (today: `ai-state-of-the-industry-monthly`). Overwrite on every run.

### 1.3 Backward compatibility

None for the removed subcommands. The `newsagent run` launchd plist is updated to call `newsagent news <path-to-prompt>`.

---

## 2. Architecture

### 2.1 One orchestrator

**`src/newsagent/pipeline/run.py`** is the orchestrator (replaces the current daily path's run.py; the brief's `brief/run.py` is deleted). The brief path's machinery moves into `pipeline/` so the cognition core can call it.

### 2.2 Module map after unification

| Module | Role | Source |
|---|---|---|
| `newsagent.pipeline.run` | The orchestrator | Renamed brief orchestrator |
| `newsagent.pipeline.spec` | `parse_prompt(md) -> BriefSpec` | Moved from `brief/spec.py` |
| `newsagent.pipeline.planner` | `plan_queries` | Moved from `brief/planner.py` |
| `newsagent.pipeline.search` | Tavily + 7-collector fallback | Moved from `brief/search.py` + `brief/run.py:_gather_sources_fallback` |
| `newsagent.pipeline.retrieval` | RAG over past reports | Already in `pipeline/retrieval.py` |
| `newsagent.pipeline.synthesize` | Per-section synthesis w/ critic loop | Moved from `brief/synthesize.py` |
| `newsagent.pipeline.report` | Citation resolution + assembly | Moved from `brief/report.py` |
| `newsagent.pipeline.eval` | Report scoring | Moved from `brief/eval.py` |
| `newsagent.pipeline.adapter` | Per-prompt adaptive state | Moved from `brief/adapter.py` |
| `newsagent.pipeline.stages.*` | The 14 cognition core stages | Unchanged |
| `newsagent.cli` | Entry points | Pruned (8 → 7 subcommands) |
| `newsagent.config` | Settings | Pruned (see §5) |
| `newsagent.storage.*` | Persistence | KG writes dropped (see §3) |

### 2.3 Orchestrator flow

```
parse prompt → plan queries (per section + per source) → search (Tavily, 7-collector fallback)
    → RAG retrieve past reports (if --date unset) → decide scope (small prompt vs full cognition core)
    → IF scope == full (cadence=weekly|monthly, section_count ≥ 3):
        build in-memory EvidenceGraph from the brief sources
        → discover_stories (optional, gate by section_count)
        → plan_research (optional)
        → analyze_chief (optional, review-only)
        → edit_story → StoryBlueprint
    → FOR each section in parallel:
        synthesize_section_with_review(sources, RAG, blueprint, critic loop)
        → CoT backstop + sanitizer + clean_section_text
    → assemble_report(spec, sections, sources)
    → write file → run sinks
```

The cognition core stages (`extract_evidence` / `extract_claims` / `discover_stories` / `plan_research` / `analyze_chief` / `edit_story`) are **optional**. Trigger: section count + cadence, governed by a named constant in the new orchestrator:

```python
FULL_COGNITION_MIN_SECTIONS = 3   # brief must have at least 3 sections to use the cognition core
```

- A "daily pulse" prompt with 1-2 sections (below the threshold) → straight to per-section synthesis.
- A "monthly deep dive" prompt with 3+ sections → full cognition core (`discover_stories` → `plan_research` → `analyze_chief` → `edit_story`).
- The trigger is exactly: `len(spec.sections) >= FULL_COGNITION_MIN_SECTIONS`. Cadence is metadata, not a trigger.

### 2.4 The cognition core is unchanged

The 14 stages in `newsagent/pipeline/stages/` stay as-is. They were built artifact-passing (no behavior change). They become the optional body of the unified pipeline.

### 2.5 No KG writes

`Entity`, `Relationship`, `EntityAliasRow`, `EntityHistoryRow`, `TimelineRow` schemas stay defined (so `db.py:init()` doesn't change) but **no code writes to them**. The cognition core's in-memory `EvidenceGraph` is the only graph. Past-reports RAG (already loaded by the brief path) is the only cross-run memory.

---

## 3. Data flow and contracts

### 3.1 Inputs to the orchestrator

1. `BriefSpec` from `parse_prompt(md)` — title, sections, bullets, deliverables, quality, instructions
2. `NewsAgentSettings` from `.env` — `NEWSAGENT_CADENCE`, `NEWSAGENT_SEARCH_BACKEND`, LLM/embed/storage/collector settings
3. `RunContext` (built once) — store, router, embedder, vectorstore

### 3.2 Stage outputs (typed dataclasses in `newsagent/pipeline/models.py`)

| Stage | Output | Used by |
|---|---|---|
| `plan_queries` | `list[ResearchQuery]` | search |
| search + fallback | `list[SearchResult]` | per-section synthesis + RAG |
| RAG | `list[RagChunk]` | per-section synthesis (style anchoring) |
| optional: `extract_evidence` | `list[Evidence]` | `build_evidence_graph` (in-memory) |
| optional: `extract_claims` | `list[Claim]` | `build_evidence_graph` |
| optional: `discover_stories` | `list[Story]` | `plan_research`, `edit_story` |
| optional: `plan_research` | `ResearchPlan` | `analyze_chief`, `edit_story` |
| optional: `analyze_chief` | `ChiefReview` | `edit_story` (redundancy flags) |
| `edit_story` (optional) | `StoryBlueprint` | per-section synthesis |
| per-section synthesis | `str` (Markdown) | assembly |
| `assemble_report` | `FinalReport` | sinks |

### 3.3 Persistence (writes to SQLite)

- `items` (from collectors) — unchanged
- `item_aliases` — unchanged
- `vectors` — unchanged
- `trend_snapshots` — kept; trends computed from the in-memory section corpus
- `reports` — now written by both paths (today only daily path writes; brief path doesn't)
- `lessons` — kept; loaded at start, written at end

### 3.4 Persistence (NOT written)

- `entities`, `relationships`, `entity_aliases`, `entity_history`, `timelines` — KG writes dropped
- `analyses`, `clusters`, `claims`, `evidence`, `evidence_relationships`, `research_plans` — legacy analyzer tables, never written by either path
- `vectors` for brief-path sources — only collector items get embedded; Tavily sources are not stored

---

## 4. Error handling

| Failure | Behavior |
|---|---|
| Prompt file missing | CLI exits 1 with clear message; no LLM call |
| `NEWSAGENT_CADENCE` unset | Default to `daily`; invalid value exits 1 |
| Tavily returns empty (HTTP 432, no key, quota) | Run 7-collector fallback (`arxiv`, `hacker_news`, `github_trending`, `huggingface`, `semantic_scholar`, `devto`, `lobsters`); synthesize sections from those |
| All collectors also return empty | One section per prompt spec gets a "no sources today" placeholder; rest continues |
| LLM call fails on role X | Router walks fallback chain → if all fail, heuristic fallback (empty `ProviderResult`); section synthesis catches and emits placeholder |
| Section word count below `_SECTION_MIN_WORDS` | Validity gate retries once with `strict_retry=True`; if still bad, drop a transparent placeholder rather than ship CoT |
| Critic rejects a section | Inner critic loop: up to 2 rewrites, fed back via `revision_notes`; if all reject, last accepted output kept |
| Synthesis emits planning/CoT | `extract_prose` strips the reasoning scratchpad before the first `## `; if `clean_section_text` finds planning leak, retry once with strict prompt |
| One section crashes | `asyncio.gather` with `return_exceptions=True`; crashed section becomes a placeholder; rest ships |
| Token budget exceeded | `LLMRouter` raises `LLMError`; orchestrator catches, writes a partial report with completed sections + a `## notes` block |
| Sinks fail (e.g. Obsidian vault missing) | Logged; canonical file write still succeeds |

**Crash policy:** the canonical Markdown file is written only when at least the title + Executive Summary are non-empty. Anything less is a hard fail with exit code 1.

---

## 5. Configuration and settings

### 5.1 `PipelineConfig` (final)

```python
# Lifted (kept as-is, already correct)
top_k_analysis: int = 25
top_k_clusters: int = 40
report_top_k: int = 25
similarity_threshold: float = 0.78
cluster_label_max_chars: int = 80
section_concurrency: int = 3
graph_context_max_chars: int = 4000
thesis_enabled: bool = True
editorial_board_enabled: bool = True
writer_extract_cot: bool = True

# REMOVED
# self_critique: bool = True        # built into the inner critic loop in synthesize
# rag_writing: bool = True          # RAG is the only writing path
# research_loops: bool = True       # research loops live in the brief path
# critic_max_chars: int = 3500      # not used outside the legacy post-render pass
# analyze_max_chars: int = 2500     # per-item analyzer is gone
# prioritizer_front_page_k: int = 5
# prioritizer_analysis_k: int = 20
# prioritizer_min_score: float = 0.05
```

### 5.2 `SearchConfig` (final)

```python
# KEPT
backend: str = "tavily"            # "tavily" or "none"
tavily_api_key: str | None = None
tavily_base_url: str = "https://api.tavily.com"
domain_cap: int = 3
timeout_seconds: float = 30.0
min_citations: int = 3
extra_queries: int = 2

# REMOVED (computed per-cadence internally)
# max_results: int = 6
# search_depth: str = "advanced"
# topic: str = "news"
# include_raw_content: bool = True
# max_sources: int = 60
# per_section_sources: int = 12
```

### 5.3 Cadence

`NEWSAGENT_CADENCE` env var (new, lives on `NewsAgentSettings`):
- `daily` (default), `weekly`, `monthly`
- Drives the `_CADENCE` table lookup
- Validated to one of the three values

The brief path's `_CADENCE` table (window, days, per-section, sources, max_tokens, min_citations) becomes the single source of per-cadence settings. It moves from `brief/run.py` to a constant in `pipeline/run.py`.

### 5.4 Removed env vars

After the cleanup, no code reads:

- `NEWSAGENT_PIPELINE_SELF_CRITIQUE`
- `NEWSAGENT_PIPELINE_RAG_WRITING`
- `NEWSAGENT_PIPELINE_RESEARCH_LOOPS`
- `NEWSAGENT_PIPELINE_CRITIC_MAX_CHARS`
- `NEWSAGENT_PIPELINE_ANALYZE_MAX_CHARS`
- `NEWSAGENT_PIPELINE_PRIORITIZER_*`
- `NEWSAGENT_SEARCH_MAX_RESULTS`, `NEWSAGENT_SEARCH_SEARCH_DEPTH`, `NEWSAGENT_SEARCH_TOPIC`, `NEWSAGENT_SEARCH_INCLUDE_RAW_CONTENT`, `NEWSAGENT_SEARCH_MAX_SOURCES`, `NEWSAGENT_SEARCH_PER_SECTION_SOURCES`

### 5.5 `NEWSAGENT_COLLECTORS_ENABLED` stays the same

The 15 collectors (or whatever subset the user enables) are still the source of items + the fallback when Tavily is off.

---

## 6. Code to delete

### 6.1 Whole files/directories

- `src/newsagent/brief/` — entire package (moved to `pipeline/`)
- `src/newsagent/analyzers/` — legacy, never on the primary path
- `src/newsagent/renderers/` — 18 classes, never on the primary path
- `src/newsagent/pipeline/cluster.py`
- `src/newsagent/pipeline/rank.py`
- `src/newsagent/pipeline/planning.py`
- `src/newsagent/pipeline/research.py`

### 6.2 Functions / classes to delete

- `pipeline/run.py` (entire file; replaced by the new orchestrator)
- `pipeline/quality_gates.py` (replaced by `extract_prose` + `clean_section_text` + per-section critic loop)
- `pipeline/prioritize.py` (replaced by an inline tier helper if needed)
- `pipeline/metrics.py` `PipelineMetrics.log_summary()` (replaced by structlog-only)

### 6.3 Tests

**Deleted:**
- `tests/unit/test_quality_gates.py` (gone)
- `tests/integration/test_pipeline.py` (old daily path)

**Renamed:**
- `tests/unit/test_brief_planner.py` → `test_planner.py`
- `tests/unit/test_brief_citations.py` → `test_report.py`
- `tests/unit/test_brief_spec.py` → `test_spec.py`

**Kept but updated:**
- `tests/unit/test_cli.py` (rewritten for 7 subcommands)
- `tests/integration/test_brief_run.py` → `test_news_run.py` (rewritten against the new orchestrator)
- `tests/integration/test_extended.py` (updated imports)

**New:**
- `tests/unit/test_synthesize.py` (per-section synthesis with critic loop)
- `tests/unit/test_embed.py` (Embedder hashing)
- `tests/unit/test_eval.py` (split from `test_brief_citations.py`)

### 6.4 Docs to update

- `docs/ARCHITECTURE.md` — rewrite §1, §2.6, §2.7 (delete renderers), §2.8 (collapse brief)
- `docs/PIPELINE.md` — rewrite §1, §2, §3, §4, §6; delete §5 (RAG legacy), §6 (research loops flag)
- `docs/BRIEF.md` — delete (content moves to `PIPELINE.md` and `CONFIGURATION.md`)
- `docs/NEWSAGENT_DESIGN.md` — leave as-is (historical design doc)
- `docs/COGNITION_DESIGN.md` — leave as-is
- `docs/STORAGE.md` — note that KG tables are no longer written
- `docs/CONFIGURATION.md` — rewrite to reflect removed env vars
- `docs/CLI.md` — rewrite
- `README.md` — rewrite "Quickstart" and "CLI commands" tables
- `CHANGELOG.md` — add a "Pipeline unification" entry

### 6.5 Scheduler templates

- `scheduler/launchd.plist` — change `newsagent run` to `newsagent news <path-to-prompt>`
- `scheduler/cron.txt` — same
- `scheduler/systemd.{service,timer}` — same

### 6.6 LoC delta

~6,000 lines deleted (renderers: ~800, analyzers: ~400, brief: ~1,200, legacy pipeline modules: ~400, tests: ~600, docs rewrites are net-zero).

---

## 7. Test strategy

**Target:** 250-280 tests passing, all offline, all fast (<10s).

### 7.1 What gets tested

| Surface | Test type | File(s) |
|---|---|---|
| `parse_prompt` (was `parse_brief`) | unit | `tests/unit/test_spec.py` |
| `plan_queries` | unit | `tests/unit/test_planner.py` |
| Citation resolution | unit | `tests/unit/test_report.py` |
| Section synthesis with critic loop | unit + integration | `tests/unit/test_synthesize.py` (new), `tests/integration/test_news_run.py` (new) |
| `LLMRouter` fallback chain, accounting | unit | `tests/unit/test_llm.py` |
| `Embedder` (hashing) | unit | `tests/unit/test_embed.py` (new) |
| CoT extraction backstop | unit | `tests/unit/test_sanitizer.py` |
| Critic loop | unit | `tests/unit/test_critic.py` |
| Sanitizer | unit | `tests/unit/test_sanitizer.py` |
| Sinks (markdown + obsidian) | unit | `tests/unit/test_sinks.py` |
| Stage artifacts (dataclass defaults) | unit | `tests/unit/test_v2_models.py` |
| Cognition core stages | unit | `tests/unit/test_cognition_refactor.py`, `tests/unit/test_story_editor.py` |
| New orchestrator end-to-end (mocked LLM) | integration | `tests/integration/test_news_run.py` |
| CLI | unit | `tests/unit/test_cli.py` |
| Quality subcommand | unit | `tests/unit/test_quality.py` |
| Eval subcommand | unit | `tests/unit/test_eval.py` (new) |
| Collector base | unit | `tests/unit/test_core.py` |
| New collectors | unit | `tests/unit/test_new_collectors.py` |

### 7.2 Linting

`ruff check src tests` clean.

---

## 8. Migration ordering

Each step keeps tests green:

1. **Move (no behavior change).** Move `brief/spec.py` → `pipeline/spec.py`, `brief/planner.py` → `pipeline/planner.py`, `brief/search.py` → `pipeline/search.py`, `brief/synthesize.py` → `pipeline/synthesize.py`, `brief/report.py` → `pipeline/report.py`, `brief/eval.py` → `pipeline/eval.py`, `brief/adapter.py` → `pipeline/adapter.py`. Update internal imports. All 263 tests pass.
2. **Add `NEWSAGENT_CADENCE` to `NewsAgentSettings`.** Wire it into the brief orchestrator (replacing the `cadence` parameter). Tests pass.
3. **Slim `PipelineConfig` and `SearchConfig`.** Remove dead flags. Tests pass.
4. **Replace `pipeline/run.py` with the new orchestrator.** It imports the moved brief modules + the cognition core stages. The old `pipeline/run.py` is deleted in step 6; during step 4 it lives as a temporary shim that calls into the new orchestrator. Test the new orchestrator end-to-end.
5. **Update `cli.py`.** Remove the 4 dead subcommands; update flags. Tests pass.
6. **Delete the old `brief/` package and `analyzers/` `renderers/` and the 4 legacy pipeline modules.** Tests pass.
7. **Update docs and scheduler templates.**
8. **Final: 250-280 tests pass; ruff clean; launchd plist works.**

---

## 9. Out of scope (deliberately)

- **Rewriting the cognition core.** Stages stay as-is. They're well-tested.
- **Adding new collectors.** 15 are enough; Tavily + 7 fallback cover the gap.
- **Switching LLM provider.** The OpenCode Go backend is configured; it works.
- **Re-enabling KG writes.** Past-reports RAG replaces the cross-run memory role.
- **Adding an HTTP API.** Not requested. CLI is the surface.
- **End-to-end LLM-call tests.** Expensive, slow, network-dependent. The 263 offline tests are the contract.
- **Removing KG table definitions.** Schemas stay so `db.py:init()` doesn't change. Future cleanup, not now.

---

## 10. Acceptance criteria

- `newsagent news <prompt.md>` produces the same kind of report the brief path produces today (e.g. `ai-state-of-the-industry-monthly.md`).
- `newsagent run` and `newsagent backfill` and `newsagent research` are gone.
- The cognition core stages are wired into the brief path (today they're dead in the daily path).
- 250-280 tests pass, all offline, all in <10s.
- `ruff check src tests` is clean.
- The 9 prompts in `prompts/` continue to work as inputs.
- The launchd plist runs `newsagent news <prompt.md>` once a day.
- No code reads the removed env vars.
- No file in `src/newsagent/brief/`, `src/newsagent/analyzers/`, or `src/newsagent/renderers/` remains.
- No file in `src/newsagent/pipeline/{cluster,rank,planning,research,quality_gates,prioritize,run}.py` remains.
