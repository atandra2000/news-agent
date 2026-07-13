# Changelog

All notable changes to Hermes are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/); this project adheres to
semantic versioning in spirit (the package is pre-1.0).

---

## [Unreleased] — 2026-07-13

### Tavily outage routing (2026-07-14)

Tavily API quota exhausted for the month. Routes around it without code
changes to the brief path.

- **Collector fan-out:** removed `tavily` from `CollectorConfig.enabled`
  defaults (`src/hermes/config.py`). The collector still exists in the
  registry as opt-in — add it back via `HERMES_COLLECTOR_ENABLED=tavily,...`
  when the quota resets. Skipping it stops the per-brief Tavily HTTP
  round-trips that were erroring on every run.
- **Brief path:** `HERMES_SEARCH_BACKEND` flipped from `tavily` to `none`
  in `.env`. The orchestrator's existing `if not sources: fallback_collectors`
  branch already routes to 7 free collectors (arxiv, hacker_news,
  github_trending, huggingface, semantic_scholar, devto, lobsters) when
  Tavily returns nothing — no code change needed.
- **Removed misnamed env var:** `HERMES_COLLECTOR_CONTEXT7_API_KEY` was
  holding a Tavily key by mistake. Context7 reads from
  `HERMES_CONTEXT7_API_KEY` (the env var that was actually set).

**Behavior:** unchanged for the report. Synthesis still pulls from the
7 free collectors; Tavily was just an aggregator on top.

### Dead-code cleanup (2026-07-14)

A second cleanup pass removes dead code that accumulated after the
cognition-core stages/ package was deleted.

- **Removed** `src/hermes/storage/kg.py` (193 LoC) — KG query helpers
  (`search_entities`, `relations_for`); the `Entity` / `Relationship` /
  `EntityHistoryRow` / `TimelineRow` tables were never written after the
  KG-writes drop.
- **Removed** `src/hermes/pipeline/models.py` (540 LoC) — cognition-core
  dataclasses / enums (24 classes including `StoryBlueprint`,
  `ChiefReview`, `Evidence`, `Claim`, `EvidenceGraph`); unreferenced
  after the stages/ removal.
- **Removed** `src/hermes/pipeline/metrics.py` (171 LoC) — `PipelineMetrics`,
  `StageTiming`, `PerfTimer`; wired into `RunContext` but never read or
  written.
- **Removed** `src/hermes/collectors/reddit.py` +
  `src/hermes/collectors/papers_with_code.py` (116 LoC) — excluded from
  the registry by design; coverage filled by Tavily, Context7, GitHub
  Releases, Dev.to, Lobsters.
- **Removed** `ground_historical` / `ground_competitive` from
  `src/hermes/pipeline/retrieval.py` (60 LoC) — KG-grounding helpers with
  zero callers.
- **Slimmed** `src/hermes/errors.py` (39 → 11 LoC) — only `HermesError` +
  `LLMError` remain; 6 unused subclasses removed.
- **Removed** `BaseProvider.available()` + `OllamaProvider.available()` +
  `LLMRouter._available_cache` (~20 LoC) — never called.
- **Removed** `sanitize_section` / `sanitize_sections` from
  `src/hermes/pipeline/sanitizer.py` + `WrittenSection` dependency
  (~30 LoC) — only test callers.
- **Removed** `FULL_COGNITION_MIN_SECTIONS` constant from
  `src/hermes/pipeline/orchestrator.py`; rewrote orchestrator docstring
  to a one-liner. Dropped the two `tests/integration/test_news_run.py`
  tests that exercised the constant.
- **Removed** cognition-core notes from `docs/PIPELINE.md` (the
  "Note (2026-07-14)" block) and `docs/ARCHITECTURE.md` (the
  `hermes.analyzers — removed` and `hermes.pipeline.stages — removed`
  subsections; the COGNITION CORE block in the §1 data-flow diagram).

**Test count:** 218 → 193 (-25 tests: `test_v2_models.py` deletion,
`test_extended.py` kg seeds removal, `test_sanitizer.py` `WrittenSection`
removal, `test_llm.py` `available()` removal, and the two
`test_news_run.py` constant tests).

**Source LoC:** ~7,548 → ~6,400 (net -1,150 lines / -5 files).

**Behavior:** unchanged. Brief path was already going straight from
search results to per-section synthesis; this is a pure deletion of dead
code and stale documentation references.

### Cognition-core cleanup (2026-07-14)

The 14-stage cognition core (`src/hermes/pipeline/stages/`) — evidence
extraction, claim extraction, evidence graph, story discovery, research
planner, chief analyst, story editor, section writer, critic, report
editor, renderer, thesis, editorial board — was already orphaned after
the 2026-07-13 unification (the orchestrator did not call any of it; the
`StoryBlueprint` was computed and discarded). The package and its
exclusively-stage test files are now deleted.

- **Removed:** `src/hermes/pipeline/stages/` (14 files, ~3,200 LoC).
- **Removed:** `tests/unit/test_critic.py`, `test_cognition_refactor.py`,
  `test_story_editor.py` (~470 LoC, 39 tests).
- **Moved:** `extract_prose` (CoT scratchpad backstop) →
  `src/hermes/pipeline/synthesize.py` alongside the related CoT-marker
  sanitizer logic. `_HEADING_RE`, `_SCRATCHPAD_HEADINGS`,
  `_TRAIL_SEPARATORS` constants travel with it. `orchestrator.py` import
  updated.
- **Retained:** the `extract_prose` tests in `test_synthesize.py` (5
  tests, all originally from `test_cognition_refactor.py::TestCoTDumpFix`)
  so the CoT-dump regression coverage survives.
- **Test count:** 252 → 218 (net -34: -39 cognition tests + 5 extract_prose
  tests retained in their new home).
- **Source LoC:** 10,699 → ~7,500 (cumulative across the two cleanup
  passes: -43% from the 12,200 baseline).
- **Behavior:** unchanged. The brief path was already going straight from
  search results to per-section synthesis; this is purely a deletion of
  dead code and a relocation of one utility function.

### Pipeline unification (2026-07-13)

The two-pipeline structure (daily `hermes run` + brief `hermes news`) collapses
into a single, brief-driven pipeline.

- **Removed subcommands:** `hermes run`, `hermes backfill`, `hermes research`.
- **Removed CLI flags:** `--daily`, `--weekly`, `--monthly`, `--rate` on `news`.
  Cadence is configured via `HERMES_CADENCE` in `.env`; `--rate 1-5` moved to
  `hermes eval --rate 1-5`.
- **Removed files:** `src/hermes/brief/`, `src/hermes/analyzers/`,
  `src/hermes/renderers/`, `src/hermes/pipeline/cluster.py`,
  `rank.py`, `planning.py`, `research.py`, `quality_gates.py`, `prioritize.py`.
- **Slimmed settings:** `PipelineConfig` (8 fields dropped), `SearchConfig`
  (6 fields dropped), `HERMES_CADENCE` added.
- **Optional cognition core:** briefs with 3+ sections run the artifact-passing
  cognition stages (`discover_stories` → `plan_research` → `analyze_chief` →
  `edit_story`); shallow briefs (1-2 sections) go straight to per-section
  synthesis.
- **KG writes dropped:** the `Entity`, `Relationship`, `EntityHistoryRow`,
  `TimelineRow` tables remain defined but no code writes to them. The
  in-memory `EvidenceGraph` is the only graph; past-reports RAG is the only
  cross-run memory.
- **Test count:** 263 → 252 (added 35 new tests in test_cadence, test_embed,
  test_synthesize, test_report, test_news_run; lost 23 in test_brief_citations →
  test_report rename, 4 in test_pipeline.py deletion, 3 in
  TestPrioritize removal, 5 in test_brief_run.py supersession by
  test_news_run.py). Net: -11 tests, but coverage of the unified pipeline
  is more focused — no test references the deleted daily-path code.

### Documentation
- **Added** root `README.md` (GitHub landing page: features, quickstart,
  architecture diagram, CLI table, layout, doc index, design principles, tech
  stack).
- **Added** `CONTRIBUTING.md` (dev environment, checks, layout, architecture
  conventions, how to add collectors/profiles).
- **Added** `CHANGELOG.md`.
- **Fixed** collector count everywhere: 12 → **15** registered collectors. The
  `reddit` and `papers_with_code` modules exist but are **excluded from the
  registry by design** (unreliable public APIs); their coverage is filled by
  Tavily, Context7, GitHub Releases, Dev.to, and Lobsters.
- **Fixed** report profiles: added the missing **`minimal`** profile (5 total:
  daily, weekly, minimal, deep_dive, trend_report).
- **Clarified** legacy vs primary path: `hermes.analyzers`, `hermes.renderers`
  (18 sections), `pipeline/cluster.py`, `pipeline/rank.py`, `pipeline/planning.py`,
  and `pipeline/research.py` are **fallback only** and are not on the daily
  path. The pipeline uses `stages/` (evidence/claim extraction, evidence
  graph, story discovery, research planner, section writer, critic, report
  editor, renderer). *(Note: the `stages/` package was itself removed on
  2026-07-14 — see "Cognition-core cleanup" below.)*
- **Clarified** the Chief Analyst is **review-only** in the pipeline; the Section Writer
  is the sole prose producer.
- **Removed** the deleted `HERMES_RESEARCH_INTEL_` config group from
  `docs/CONFIGURATION.md` (the config group was removed from `config.py`).
- **Clarified** persistence: only 6 tables are written by the daily
  pipeline (`items`, `item_aliases`, `vectors`, `trend_snapshots`, `reports`,
  `lessons`). The other 12 tables are legacy (analyzer / Research-Intelligence /
  brief path).
- **Clarified** the research mechanism: `plan_research` → bounded
  `research_gaps` for `re-research`-flagged claims (in-memory), not the legacy
  `planning.plan()` / `research.run_research()`.
- **Fixed** test count references: 162 → **227** passing.
- **Fixed** `run.py` module docstring stage count (was "11-stage"; the code
  has ~14 stages).

---

## Pipeline Consolidation

### Added
- Unified evidence/claim extraction stages (`stages/evidence_extraction.py`,
  `stages/claim_extraction.py`) producing in-memory `Evidence` / `Claim`
  artifacts with verification status.
- Cross-document `EvidenceGraph` (`stages/evidence_graph.py`) as the shared
  context for story discovery, chief-analyst review, and the story editor.
- `StoryBlueprint` + `edit_story` (story editor) as the single structured input
  to the writer.
- Bounded self-critique loop (`stages/critic.py` + `stages/section_writer.py`)
  with `_MAX_CRITIC_RETRIES`.
- Bounded re-research gap pass (`stages/research.py::research_gaps`) for
  `re-research`-flagged claims.
- Dynamic report rendering (`stages/renderer.py::render_report`) with inline
  `[n]` citations + a single `## **References & Provenance**` section.
- Self-improving memory: `lessons` table loaded into `memory_lessons` and fed to
  the writer/critic prompts.
- Run manifests (`storage/run_manifests/<timestamp>.json`) for resumability.

### Changed
- Chief Analyst (`analyze_chief`) is now **review-only** (returns `ChiefReview`,
  no prose).
- Report structure is dynamic (Executive Summary + blueprint-driven analytical
  sections + References), not the fixed 18 sections.

### Removed
- legacy `pipeline/run.py` (10-stage orchestrator) and its `_self_critique` /
  `_rag_excerpts` post-render passes.
- The standalone "Research Intelligence Layer" (`research_intel.py`, `graph.py`,
  `render.py`, `research_plan.py`) — consolidated into the `stages/`.
- The `HERMES_RESEARCH_INTEL_` config group.

### Fixed
- Citation renumbering / duplicate-References suppression in `report_editor`.
- `_remap_section_citations` now renumbers across the whole report, not
  per-section.
- `references` section filtered out of analytical sections (rendered once).
- `graph_context` truncation guard (no negative slice on tiny contexts).
- `discover_stories` empty-graph guard (returns `[]` instead of crashing).
- `analyze_chief` empty-evidence guard (returns an approval instead of crashing).
