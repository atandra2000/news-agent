# Changelog

All notable changes to newsagent are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/); this project adheres to
semantic versioning in spirit (the package is pre-1.0).

---

## [Unreleased] — 2026-07-15

### Brief prompt optimization

All 14 brief prompts in `prompts/` plus `example_prompt.md` rewritten
per the design at
[`docs/superpowers/specs/2026-07-15-brief-prompt-optimization-design.md`](docs/superpowers/specs/2026-07-15-brief-prompt-optimization-design.md).
The rewrite reinforces the 9 report-quality scopes from the
2026-07-13 post-mortem at the brief layer without changing
`src/newsagent/pipeline/*`, `.j2` system templates, or any other code
path.

- **New `## Synthesis Directives` block** in every brief — 4-6 numbered
  synthesis verbs (compare, rank, quantify, contrast, surface
  contradictions, distinguish) per section, tailored to the brief's
  domain.
- **Per-section `_→ render as Markdown table._` markers** on every
  entity-comparison bullet (models, chips, funding rounds, benchmarks,
  agents, etc.). Reinforces Scope 6 (Required Deliverables gate) at the
  brief layer.
- **Per-section source-budget hint** (e.g. "use 8-12 sources; prefer 2
  official + 2 research + 1 news + 1 community") in every brief's
  Report Structure preamble.
- **Inline unsourced-fact tagging rule** (`[unsourced — industry
  knowledge]`) added to every brief's Output Quality Requirements —
  reinforces Scope 5 (citation discipline).
- **Citation token unified** to `[src:URL]` everywhere in the briefs
  (the system template still uses `[src:EXACT_URL]`).
- **`_Why these sources_` one-liner** added to every source tier, so
  the brief documents its editorial choice rather than copy-pasting
  from another brief.
- **Clean H1** (no trailing `#`) on every brief — was present in 12/14
  briefs.
- **Tiered rollout** matched the post-mortem severity ranking: Tier 1
  (`ai_news_monthly.md`, `frontier_models.md`, `ai_hardware_infra.md`)
  first, Tier 4 (cadence briefs) last.
- **New test harness** (`tests/unit/test_briefs.py`, 8 tests +
  `tests/snapshots/briefs.json` snapshot) — every brief parses
  cleanly, has a Synthesis Directives block, has a clean H1, uses the
  canonical citation token, has a byte count in the expected range,
  lists comparison-table deliverables for every comparison section,
  and lists the unsourced-fact tagging rule. **291 tests pass**
  (283 original + 8 new).

### Project rename: hermes → newsagent

The project has been renamed end-to-end. **Action required for existing
deployments:** rename every `HERMES_*` env var in your `.env` to
`NEWSAGENT_*` (use `.env.example` as the new template). The `hermes` console
script is now `newsagent`; rerun `uv pip install -e .` so the new entry
point is on `$PATH`. Existing storage on disk (`storage/hermes.db`,
`storage/hermes.log`, `vectors/`) is left alone — fresh runs will create
`newsagent.db` and `newsagent.log` next to them.

- Package: `hermes` → `newsagent` (top-level `src/newsagent/`).
- Env-var prefix: `HERMES_` → `NEWSAGENT_` (8 pydantic-settings blocks).
- Console script: `hermes` → `newsagent`.
- Class names: `HermesError` → `NewsAgentError`, `HermesSettings` →
  `NewsAgentSettings`.
- Storage defaults: `hermes.db` → `newsagent.db`,
  qdrant collection `hermes` → `newsagent`,
  Obsidian filename `Hermes_YYYY-MM-DD.md` → `newsagent_YYYY-MM-DD.md`,
  frontmatter tag `hermes` → `newsagent`.
- All CLI subcommands, env-var docs, design docs, and scheduler configs
  updated. The 283-test suite passes.

---

## [Unreleased] — 2026-07-13

### Report-quality fixes (2026-07-14)

The 2026-07-13 monthly `ai-state-of-the-industry` report exposed a
family of failure modes that the basic critic loop didn't cover. This
release closes 9 of them in one coherent set of changes. See
[docs/REPORT_QUALITY_REVIEW.md](docs/REPORT_QUALITY_REVIEW.md) for the
full post-mortem of the failing report and the minimum change for each
fix.

- **Scope 1 — Cadence → lookback wiring** (`pipeline/spec.py`,
  `pipeline/orchestrator.py`). `BriefSpec.cadence` is now detected from
  the prompt body (`"monthly"`, `"past 30 days"`, …) and the
  orchestrator prefers it over `NEWSAGENT_CADENCE`. A "monthly" prompt
  body is no longer overridden by a `daily` env setting.
- **Scope 2 — Source coverage verdict** (`pipeline/coverage.py` — new,
  193 LoC). Per-section OK/THIN/CRITICAL classification by category
  (research / official / news / community). The orchestrator
  short-circuits CRITICAL sections with a transparent "section
  omitted" marker instead of burning an LLM call on a doomed attempt.
- **Scope 3 — Sanitizer (placeholders + round-3 CoT)**
  (`pipeline/sanitizer.py`, `pipeline/report.py`). ~30 new banned
  phrases under the "2026-07-13 monthly §12 round-3 CoT class" header
  ("now, for each factual claim", "ignore that rule", "so we can
  weave", "let us go ahead", "the user demanded", …). New
  `is_synthesis_failure_stub()` detector replaces the
  orchestrator's last-resort placeholder with a clean dropped-section
  marker instead of shipping it as if it were real prose.
- **Scope 4 — Cross-post dedup** (`pipeline/search.py`,
  `storage/models.py`). `content_fingerprint()` keyed on
  `(host, normalized_title)` collapses HN-style reposts
  (unique URLs, same story on the same host) into one canonical +
  a cross-post group. `duplication_collapse_rate` (0.0–1.0) is now
  persisted on the `Report` row and auto-migrated by
  `_add_missing_columns()`.
- **Scope 5 — Citation discipline** (`pipeline/synthesize.py`,
  `pipeline/report.py`). Writer prompt now requires every factual
  claim to be EITHER cited with `[src:URL]` OR explicitly tagged
  `[unsourced — industry knowledge]`. `audit_citation_discipline()`
  counts cited / unsourced / unmarked sentences for the manifest.
- **Scope 6 — Required Deliverables gate** (`pipeline/report.py`).
  `check_required_deliverables()` soft-checks each entry in
  `spec.deliverables` against the rendered text. Missing items are
  appended as a "Required Deliverables — Coverage Check" tail so the
  gap is transparent to readers.
- **Scope 7 — Run manifest observability** (`pipeline/orchestrator.py`).
  `_gather_sources_fallback` returns
  `(results, sources_checked, sources_failed)` so the `Report` row's
  `sources_checked_json` / `sources_failed_json` are no longer
  hardcoded to `[]`.
- **Scope 8 — Source-priority boost + diversity floor**
  (`pipeline/synthesize.py`). New `_SOURCE_PRIORITY_BOOST` map
  (official_labs=5, research=4, news=2, community=1) added to
  `_score_source`. New `min_source_types=3` parameter on
  `select_relevant` enforces a diversity floor so a section cannot be
  dominated by HN even when 110 arxiv items exist in the corpus.
- **Scope 9 — Thin-corpus banner** (`pipeline/report.py`).
  `thin_corpus_banner()` emits a "⚠️ Thin-corpus run" callout at
  the top of the report when `sources/section < 5` or any section is
  CRITICAL.

**Test count:** 191 → 237 (+46 tests across 7 files; 3 new files).

**Behavior:** changes to the report body — added CoT sanitization,
unsourced-marker rendering, dropped-section markers, source-priority
boost, diversity floor, cross-post collapse, deliverables gate, and
thin-corpus banner. The brief path is unchanged when the corpus is
healthy and the prompt is well-formed.

### Tavily outage routing (2026-07-14)

Tavily API quota exhausted for the month. Routes around it without code
changes to the brief path.

- **Collector fan-out:** removed `tavily` from `CollectorConfig.enabled`
  defaults (`src/newsagent/config.py`). The collector still exists in the
  registry as opt-in — add it back via `NEWSAGENT_COLLECTOR_ENABLED=tavily,...`
  when the quota resets. Skipping it stops the per-brief Tavily HTTP
  round-trips that were erroring on every run.
- **Brief path:** `NEWSAGENT_SEARCH_BACKEND` flipped from `tavily` to `none`
  in `.env`. The orchestrator's existing `if not sources: fallback_collectors`
  branch already routes to 7 free collectors (arxiv, hacker_news,
  github_trending, huggingface, semantic_scholar, devto, lobsters) when
  Tavily returns nothing — no code change needed.
- **Removed misnamed env var:** `NEWSAGENT_COLLECTOR_CONTEXT7_API_KEY` was
  holding a Tavily key by mistake. Context7 reads from
  `NEWSAGENT_CONTEXT7_API_KEY` (the env var that was actually set).

**Behavior:** unchanged for the report. Synthesis still pulls from the
7 free collectors; Tavily was just an aggregator on top.

### Dead-code cleanup (2026-07-14)

A second cleanup pass removes dead code that accumulated after the
cognition-core stages/ package was deleted.

- **Removed** `src/newsagent/storage/kg.py` (193 LoC) — KG query helpers
  (`search_entities`, `relations_for`); the `Entity` / `Relationship` /
  `EntityHistoryRow` / `TimelineRow` tables were never written after the
  KG-writes drop.
- **Removed** `src/newsagent/pipeline/models.py` (540 LoC) — cognition-core
  dataclasses / enums (24 classes including `StoryBlueprint`,
  `ChiefReview`, `Evidence`, `Claim`, `EvidenceGraph`); unreferenced
  after the stages/ removal.
- **Removed** `src/newsagent/pipeline/metrics.py` (171 LoC) — `PipelineMetrics`,
  `StageTiming`, `PerfTimer`; wired into `RunContext` but never read or
  written.
- **Removed** `src/newsagent/collectors/reddit.py` +
  `src/newsagent/collectors/papers_with_code.py` (116 LoC) — excluded from
  the registry by design; coverage filled by Tavily, Context7, GitHub
  Releases, Dev.to, Lobsters.
- **Removed** `ground_historical` / `ground_competitive` from
  `src/newsagent/pipeline/retrieval.py` (60 LoC) — KG-grounding helpers with
  zero callers.
- **Slimmed** `src/newsagent/errors.py` (39 → 11 LoC) — only `NewsAgentError` +
  `LLMError` remain; 6 unused subclasses removed.
- **Removed** `BaseProvider.available()` + `OllamaProvider.available()` +
  `LLMRouter._available_cache` (~20 LoC) — never called.
- **Removed** `sanitize_section` / `sanitize_sections` from
  `src/newsagent/pipeline/sanitizer.py` + `WrittenSection` dependency
  (~30 LoC) — only test callers.
- **Removed** `FULL_COGNITION_MIN_SECTIONS` constant from
  `src/newsagent/pipeline/orchestrator.py`; rewrote orchestrator docstring
  to a one-liner. Dropped the two `tests/integration/test_news_run.py`
  tests that exercised the constant.
- **Removed** cognition-core notes from `docs/PIPELINE.md` (the
  "Note (2026-07-14)" block) and `docs/ARCHITECTURE.md` (the
  `newsagent.analyzers — removed` and `newsagent.pipeline.stages — removed`
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

The 14-stage cognition core (`src/newsagent/pipeline/stages/`) — evidence
extraction, claim extraction, evidence graph, story discovery, research
planner, chief analyst, story editor, section writer, critic, report
editor, renderer, thesis, editorial board — was already orphaned after
the 2026-07-13 unification (the orchestrator did not call any of it; the
`StoryBlueprint` was computed and discarded). The package and its
exclusively-stage test files are now deleted.

- **Removed:** `src/newsagent/pipeline/stages/` (14 files, ~3,200 LoC).
- **Removed:** `tests/unit/test_critic.py`, `test_cognition_refactor.py`,
  `test_story_editor.py` (~470 LoC, 39 tests).
- **Moved:** `extract_prose` (CoT scratchpad backstop) →
  `src/newsagent/pipeline/synthesize.py` alongside the related CoT-marker
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

The two-pipeline structure (daily `newsagent run` + brief `newsagent news`) collapses
into a single, brief-driven pipeline.

- **Removed subcommands:** `newsagent run`, `newsagent backfill`, `newsagent research`.
- **Removed CLI flags:** `--daily`, `--weekly`, `--monthly`, `--rate` on `news`.
  Cadence is configured via `NEWSAGENT_CADENCE` in `.env`; `--rate 1-5` moved to
  `newsagent eval --rate 1-5`.
- **Removed files:** `src/newsagent/brief/`, `src/newsagent/analyzers/`,
  `src/newsagent/renderers/`, `src/newsagent/pipeline/cluster.py`,
  `rank.py`, `planning.py`, `research.py`, `quality_gates.py`, `prioritize.py`.
- **Slimmed settings:** `PipelineConfig` (8 fields dropped), `SearchConfig`
  (6 fields dropped), `NEWSAGENT_CADENCE` added.
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
- **Clarified** legacy vs primary path: `newsagent.analyzers`, `newsagent.renderers`
  (18 sections), `pipeline/cluster.py`, `pipeline/rank.py`, `pipeline/planning.py`,
  and `pipeline/research.py` are **fallback only** and are not on the daily
  path. The pipeline uses `stages/` (evidence/claim extraction, evidence
  graph, story discovery, research planner, section writer, critic, report
  editor, renderer). *(Note: the `stages/` package was itself removed on
  2026-07-14 — see "Cognition-core cleanup" below.)*
- **Clarified** the Chief Analyst is **review-only** in the pipeline; the Section Writer
  is the sole prose producer.
- **Removed** the deleted `NEWSAGENT_RESEARCH_INTEL_` config group from
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
- The `NEWSAGENT_RESEARCH_INTEL_` config group.

### Fixed
- Citation renumbering / duplicate-References suppression in `report_editor`.
- `_remap_section_citations` now renumbers across the whole report, not
  per-section.
- `references` section filtered out of analytical sections (rendered once).
- `graph_context` truncation guard (no negative slice on tiny contexts).
- `discover_stories` empty-graph guard (returns `[]` instead of crashing).
- `analyze_chief` empty-evidence guard (returns an approval instead of crashing).
