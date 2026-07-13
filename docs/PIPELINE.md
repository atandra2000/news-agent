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

@dataclass
class SectionSpec:
    number: int
    title: str
    bullets: list[str]
```

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
Sources are then deduped (`dedup_sources` in `search.py`) and passed
through `select_relevant` (`synthesize.py`) for per-section keyword
ranking + domain diversification.

#### 2.4 RAG (past-report retrieval)

**Module:** `hermes/pipeline/retrieval.py`

Pulls the most recent past reports from storage, embeds their section
chunks with the configured embedder, and returns top-K similar chunks for
each new section. Past-report context is injected into the synthesizer's
prompt so the writer can connect to prior coverage.

#### 2.5 Per-section synthesis (parallel + critic loop + CoT backstop)

**Module:** `hermes/pipeline/synthesize.py` (`synthesize_section_with_review`,
`extract_prose`)

For each `SectionSpec` in parallel (bounded by an `asyncio.Semaphore`):

1. **Build prompt** — `build_section_prompt` composes the writer prompt
   with section title/bullets, research priorities, quality bar, retrieved
   sources, and RAG context.
2. **Writer call** — the `brief_write` LLM role generates the section.
3. **CoT backstop** — `extract_prose` strips any reasoning scratchpad
   before the real `## ` heading (and collapses "heading-first dithering"
   where the model emits the heading, dithers, then re-emits it with real
   prose).
4. **Sanitize** — phrase-level sanitizer drops planning markers (e.g.
   "we need to write", "let's assume", "fabricate") and CoT-style stubs.
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

- Resolves `[src:URL]` citation tokens to inline `[n]` markers.
- Renumbers citations across the whole report (not per-section).
- Suppresses duplicate `## **References & Provenance**` sections (rendered
  once at the end).
- Writes to `storage/reports/<title-slug>-<cadence>.md` (plus the Obsidian
  vault when configured).

#### 2.7 Archive + manifest

A `Report` row is written with `path`, `md_sha256`, `sections_count`,
`sources_checked_json`, `sources_failed_json`, `token_usage`. Per-stage
stats go to `storage/run_manifests/<timestamp>.json` for resumability.

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

Cadence is set via `HERMES_CADENCE` in `.env` (not via profile).