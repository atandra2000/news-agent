# Pipeline

> The single end-to-end pipeline: parse a prompt, plan queries, search
> sources, retrieve past-report context, synthesize each section in
> parallel with a per-section critic loop, then assemble the final report.
> One command. One file.

---

## 1. The pipeline

```
parse_prompt → plan_queries → search (+ collector fallback)
        → rag (past-report retrieval)
        → synthesize (per-section, parallel, with critic loop + CoT backstop)
        → assemble_report → archive
```

Defined in `hermes/pipeline/orchestrator.py` (`run_news_pipeline`). Every
stage exchanges structured artifacts (not prompt text). The pipeline is
flat: no cognition-core detour, no evidence-graph pass, no story editor —
the per-section synthesizer goes straight from selected sources to prose.

---

## 2. Stage details

### Always run

#### 2.1 Parse prompt

**Module:** `hermes/pipeline/spec.py` (`parse_prompt`)

Reads the Markdown prompt file and produces a `BriefSpec`:

```python
@dataclass
class BriefSpec:
    title: str
    instructions: str           # Research Instructions prose
    source_names: list[str]     # flattened from Official/Research/Community
    sections: list[SectionSpec]
    deliverables: list[str]
    quality: list[str]
    raw: str
    cadence: str | None         # detected from body ("monthly"/"weekly"/"daily")

@dataclass
class SectionSpec:
    number: int
    title: str
    bullets: list[str]
```

**Cadence detection** — `parse_prompt` scans the title + the first 800
chars of the body for `_CADENCE_HINTS` (`"monthly"`, `"past 30 days"`,
`"weekly"`, `"past 7 days"`, `"daily"`, `"today"`, …). The first hit
wins; longer/more specific cadences are checked first. The orchestrator
prefers `spec.cadence` over `HERMES_CADENCE` so the lookback window
always matches the prompt body. (The 2026-07-13 monthly report's
"`past 30 days`" prompt body was previously overridden by a `daily`
env setting → 24h lookback → empty monthly report.)

#### 2.2 Plan queries

**Module:** `hermes/pipeline/planner.py` (`plan_queries`)

Turns each `SectionSpec` into a list of `ResearchQuery`s (section title +
bullets → focused web search queries, with the per-section source budget
set by `CadenceSpec`).

#### 2.3 Search

**Modules:** `hermes/pipeline/search.py` (Tavily backend) +
`hermes/collectors/registry.py` (7 free-collector fallback: HN, Lobsters,
Dev.to, arXiv, GitHub Releases, Context7, HuggingFace)

```
sources = await search.run_queries(queries, since=run_date - window)
if not sources:
    sources = await _gather_sources_fallback(queries)  # 7 free collectors
```

Each fallback collector runs with `asyncio.wait_for` timeout + one retry.
Sources are then **deduped** in two passes:

1. `dedup_sources_with_cross_posts` (`search.py`) — URL-dedup first
   (so two different articles on the same story don't double-count),
   then **content-fingerprint** dedup keyed on `(host, normalized_title)`
   to collapse cross-posts of the same story on the same host (the
   2026-07-13 monthly report cited the Cat's-grant HN repost 3× as
   if it were 3 independent signals — each repost has a unique
   `item?id=…` URL, so URL-dedup misses them).
2. `select_relevant` (`synthesize.py`) — per-section keyword ranking
   + domain cap (`HERMES_SEARCH_DOMAIN_CAP`, default 3) +
   **source-priority boost** (`official_labs=5, research=4, news=2,
   community=1`) + **diversity floor** (`min_source_types=3`) so a
   section cannot be dominated by HN even when 110 arxiv items exist
   in the corpus.

#### 2.4 RAG (past-report retrieval)

**Module:** `hermes/pipeline/retrieval.py`

Pulls the most recent past reports from storage, embeds their section
chunks with the configured embedder, and returns top-K similar chunks for
each new section. Past-report context is injected into the synthesizer's
prompt so the writer can connect to prior coverage.

#### 2.5 Per-section synthesis (parallel + critic loop + CoT backstop)

**Modules:** `hermes/pipeline/synthesize.py` (`synthesize_section_with_review`,
`extract_prose`) + `hermes/pipeline/coverage.py` (`evaluate_coverage`)

For each `SectionSpec` in parallel (bounded by an `asyncio.Semaphore`):

0. **Coverage verdict short-circuit** — before the LLM call, the
   orchestrator's pre-computed coverage verdict is checked. If a
   section's required source category (research / official / news /
   community) has **zero** sources, the section is dropped with a
   transparent `Section omitted: source coverage verdict is CRITICAL`
   marker — no LLM call, no fabricated prose. THIN sections proceed
   but the writer is told the corpus is thin.
1. **Build prompt** — `build_section_prompt` composes the writer prompt
   with section title/bullets, research priorities, quality bar, retrieved
   sources, RAG context, the coverage verdict, and the **citation
   discipline** requirement: every factual claim must be EITHER cited
   with `[src:URL]` OR explicitly tagged `[unsourced — industry knowledge]`.
2. **Writer call** — the `brief_write` LLM role generates the section.
3. **CoT backstop** — `extract_prose` strips any reasoning scratchpad
   before the real `## ` heading (and collapses "heading-first dithering"
   where the model emits the heading, dithers, then re-emits it with real
   prose).
4. **Sanitize** — phrase-level sanitizer drops planning markers (e.g.
   "we need to write", "let's assume", "fabricate") and the round-3
   CoT class ("now, for each factual claim", "ignore that rule", "so
   we can weave", "let us go ahead", "the user demanded", …). The
   `is_synthesis_failure_stub` detector catches the orchestrator's
   last-resort placeholder so the renderer can replace it with a
   clean dropped-section marker.
5. **Critic** — `critique_section` evaluates the section against the
   quality bar + cadence + citation density. On rejection, the section
   is rewritten with the critic's feedback appended (up to `max_rewrites`,
   default 2).
6. **Validity gate** — `clean_section_text` rejects sections that fail
   structural checks (no heading, all-CoT, residual markers); the
   synthesizer retries, then placeholders.

#### 2.6 Assemble report

**Module:** `hermes/pipeline/report.py` (`assemble_report`)

Combines the per-section prose into a single Markdown document:

- **Replaces synthesis-failure stubs** with a clean
  `_Section omitted: synthesis failed after retry in this run._` marker
  (the 2026-07-13 monthly report had the stub render in §6 and §7
  because nothing detected it).
- **Drops empty subheadings** (`drop_empty_subheadings`) so a
  placeholder line after a `## ` heading doesn't render.
- **Strips non-URL citation fig-leaves** (`_LABEL_BRACKET_RE`) — bare
  `[Analyst assessment]`, `[src]`, `[source]` brackets the writer emits
  when it has no real URL.
- **Resolves `[src:URL]` citation tokens** to inline `[n]` markers.
- **Renumbers citations** across the whole report (not per-section).
- **Required Deliverables gate** — `check_required_deliverables` soft-
  checks each entry in `spec.deliverables` against the rendered text
  (looking for matching table headers, subheadings, or required
  keywords). Missing items are appended as a
  `_Required Deliverables — Coverage Check_` tail so the gap is
  transparent to readers. (The 2026-07-13 monthly report's "Required
  Deliverables" list was never enforced — model comparison matrix,
  funding tables, benchmark tables, key statistics were all missing
  and nothing told the reader.)
- **Thin-corpus banner** — when `total_sources < 5 × section_count`
  or any section is `CRITICAL`, a
  `> ⚠️ Thin-corpus run: N sources for M sections…` callout is
  inserted just under the report title. Distinguishes "nothing
  happened" from "we didn't see enough."
- **Suppressed duplicate `## **References & Provenance**` sections**
  (rendered once at the end).
- **Writes** to `storage/reports/<title-slug>.md` (plus the Obsidian
  vault when configured).

#### 2.7 Archive + manifest

A `Report` row is written with `path`, `md_sha256`, `sections_count`,
`sources_checked_json`, `sources_failed_json`,
`duplication_collapse_rate`, `token_usage`. Per-stage stats go to
`storage/run_manifests/<timestamp>.json` for resumability.

- `sources_checked_json` / `sources_failed_json` — real collector
  names. `_gather_sources_fallback` returns `(results, checked,
  failed)` so the manifest reflects what actually ran, not `[]`
  (the 2026-07-13 monthly report's manifest had both fields
  hardcoded to `[]`).
- `duplication_collapse_rate` — fraction of sources dropped as
  URL or cross-post dupes (0.0 = no dedup, 1.0 = all dupes). The
  Cat's-grant run had 3 HN reposts collapse to 1 → 0.67 collapse
  rate.

---

## 3. Self-critique loop

The pipeline bounds criticism **inside the per-section synthesis stage**.
This is the only critic loop — there is no separate post-render pass.

1. `synthesize_section_with_review(section, sources, …)` produces the prose
   for one section from the section's selected sources + RAG context.
2. `critique_section()` reviews the output and either approves it or returns
   `rewrite_instructions` + a `score` + `gaps` + `missing_citations`.
3. On rejection, the synthesizer is called again with the critic's
   instructions appended to the prompt (up to `max_rewrites`). This lets the
   loop actually improve a rejected section instead of regenerating identical
   text.
4. If all retries fail, the last accepted output is kept.

(The legacy `_self_critique` post-render pass and the separate
`critique_report()` whole-report critic are gone — criticism is
section-scoped.)

---

## 4. Quality self-assessment

**Module:** `hermes/pipeline/quality.py`

Separate CLI command: `hermes quality [--date YYYY-MM-DD]`.

1. Reads the day's report from `storage/reports/YYYY-MM-DD.md`.
2. **LLM judge** — scores the report on 6 dimensions (1-5):
   `coverage`, `accuracy_verification`, `depth`, `synthesis`, `usefulness`,
   `trust`.
3. **Heuristic fallback** — if LLM unavailable, lexical scorer:
   - coverage: link count
   - accuracy: verification badge count
   - depth: report length
   - synthesis: trends/clusters present
   - usefulness: takeaways/insights present
   - trust: references/method present
4. Persists improvement notes to the `Lesson` table.
5. Writes `storage/quality/YYYY-MM-DD.md` + `.json`.

---

## 5. Self-improving memory

The `Lesson` table persists critiques and quality findings across runs:

| Column | Description |
|--------|-------------|
| `run_date` | When the lesson was learned |
| `kind` | `critic` (from self-critique) or `quality` (from quality stage) |
| `text` | The improvement note |
| `dimension` | Optional quality dimension |
| `resolved` | `False` — lessons are loaded into the next run's `memory_lessons` |

At the start of each `run_news_pipeline()`, lessons are pulled into
`ctx.memory_lessons`. The writer and critic prompts include a memory block:
"In past runs the report was criticised for: ... Avoid those weaknesses
explicitly."

---

## 6. Resumability

`run_news_pipeline()` writes a run manifest to `storage/run_manifests/<timestamp>.json`
with per-stage stats. If a run crashes, the manifest shows which stages
completed.

---

## 7. Profiles

Profiles (`hermes/profiles.py`) parameterize the pipeline without code changes:

```python
PROFILES = {
    "daily": ReportProfile(top_k_analysis=25, depth="standard", ...),
    "weekly": ReportProfile(top_k_analysis=60, depth="deep", ...),
    "minimal": ReportProfile(top_k_analysis=10, sections=["executive_summary", "major_news"]),
    "deep_dive": ReportProfile(sections=["executive_summary", "technical_deep_dives", ...]),
    "trend_report": ReportProfile(sections=["emerging_trends", ...]),
}
```

A profile overrides:
- `settings.collectors.enabled` (if `profile.collectors` is set)
- `settings.pipeline.top_k_analysis`
- `settings.pipeline.report_top_k`

Cadence is set via `HERMES_CADENCE` in `.env` (not via profile). When
the prompt body contains its own cadence hint (e.g. "the past 30
days"), `spec.cadence` takes precedence over the env (see §2.1).

---

## 8. Report-quality defenses

The 2026-07-13 monthly report exposed a family of failure modes that
weren't covered by the basic critic loop. Each scope below is the
minimum change to close one of them. They are layered — Scope 1
(cadence) feeds the search budget, Scope 2 (coverage) gates Scope 4
(dedup), Scope 7 (manifest) records what Scope 4 collapsed, etc.

| Scope | Where it lives | What it prevents |
|---|---|---|
| 1. Cadence → lookback | `spec.py::_detect_cadence`, `orchestrator.py::run_news_pipeline` | A "monthly" prompt body being run with a `daily` lookback window. |
| 2. Source coverage verdict | `coverage.py::evaluate_coverage`, `orchestrator.py` | Sections with 0 sources being filled with fabricated prose. |
| 3. Sanitizer (placeholders + round-3 CoT) | `sanitizer.py`, `report.py` | The orchestrator's last-resort stub rendering as real prose, and the §12 round-3 CoT tail ("now, for each factual claim", "ignore that rule", "so we can weave", …) leaking through. |
| 4. Cross-post dedup | `search.py::content_fingerprint`, `dedup_sources_with_cross_posts`, `duplication_collapse_rate` | HN-style reposts (unique URLs, same story on the same host) being cited as independent signals. |
| 5. Citation discipline | `synthesize.py::build_section_prompt`, `report.py::audit_citation_discipline` | Parametric-knowledge facts being passed off as cited evidence. The writer must tag unsourced claims with `[unsourced — industry knowledge]`. |
| 6. Required Deliverables gate | `report.py::check_required_deliverables`, `format_missing_deliverables_note` | Brief-mandated deliverables (model comparison matrix, funding tables, benchmark tables, key statistics) being silently missing. The gate appends a Coverage Check tail listing them. |
| 7. Run manifest observability | `orchestrator.py::_gather_sources_fallback` | The `Report` row's `sources_checked_json` / `sources_failed_json` being hardcoded to `[]`. |
| 8. Source-priority boost + diversity floor | `synthesize.py::_SOURCE_PRIORITY_BOOST`, `select_relevant(min_source_types=3)` | All 13 sections being cited from HN + GitHub Trending despite 110 arxiv + 94 huggingface + 90 RSS items being in the corpus. |
| 9. Thin-corpus banner | `report.py::thin_corpus_banner` | A 20-source / 13-section report rendering without a warning that the corpus was thin. |

Each scope has unit tests pinning the behavior. See
[REPORT_QUALITY_REVIEW.md](./REPORT_QUALITY_REVIEW.md) for the full
post-mortem of the 2026-07-13 report, including the exact failing
output and the minimum change for each fix.