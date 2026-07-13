# 2026-07-13 Monthly Report — Quality Review & Fixes

> Post-mortem of the `ai-state-of-the-industry-monthly.md` report produced
> on 2026-07-13. The report was rated **4/10** on the §11 quality rubric
> and found 10 distinct defects. All 10 have since been implemented and
> verified (237/237 tests, ruff clean).

This document exists so the next person reading `src/hermes/pipeline/`
knows **why** each defensive check exists — not just what it does. Each
scope section is named, scoped, links the failing output, names the
minimum change, and references the test that pins it down.

---

## 1. The report under review

| Field | Value |
|---|---|
| Path | `storage/reports/ai-state-of-the-industry-monthly.md` |
| Generated | 2026-07-13 |
| Cadence declared in prompt | monthly (30-day lookback) |
| Cadence actually used | daily (1-day lookback) |
| Sections | 13 |
| Sources retrieved | 20 (≈1.5/section) |
| Sources cited in the report | 14 (Hacker News, GitHub Trending, Dev.to, lobsters) |
| Sources *available* but not cited | 110 arxiv, 94 huggingface, 90 RSS, etc. |
| Required Deliverables in brief | Model comparison matrix, funding tables, benchmark comparison tables, key statistics — **only 1 of 4 was present** |
| Final rating | **4/10** |

---

## 2. The 10 scopes

### Scope 1 — Cadence → lookback wiring  *(critical, breaks the whole report)*

**Symptom.** The prompt body says "monthly industry brief — past 30 days",
but the rendered report contained only same-day news (Hacker News stories
posted within hours). `HERMES_CADENCE` was unset / set to `daily`, and the
prompt body was ignored.

**Root cause.** `run_news_pipeline` resolved cadence from `settings.cadence`
only. The prompt body's cadence hint was never read.

**Fix.** `parse_prompt` now scans the prompt for `_CADENCE_HINTS` and stores
the result on `BriefSpec.cadence`. The orchestrator uses
`spec.cadence or settings.cadence` — prompt body wins.

**Tests.** `tests/unit/test_spec.py::test_cadence_detection_*` (5 tests).

---

### Scope 2 — Source coverage verdict  *(prevents fabrication on empty corpus)*

**Symptom.** The writer was given 0–2 sources for sections 6 and 7 ("Open
Source AI", "Hardware & Infrastructure") and invented plausible-sounding
content from parametric knowledge. The synthesis-failure stub rendered
as real prose — readers couldn't tell the section was unsupported.

**Root cause.** No principled way to say "this section has no evidence —
don't write it."

**Fix.** New module `pipeline/coverage.py` classifies each section as
`OK` / `THIN` / `CRITICAL` by comparing the retrieved source corpus against
the section's required category (research / official / news / community).
The orchestrator:
- tells the writer the verdict so it can be honest about gaps;
- **short-circuits CRITICAL sections** with a transparent
  "_Section omitted: source coverage verdict is CRITICAL_" marker instead
  of burning an LLM call on a doomed attempt.

**Tests.** `tests/unit/test_coverage.py` (8 tests).

---

### Scope 3 — Sanitizer: placeholders + CoT tail  *(the §12 round-3 leak)*

**Symptom.** Section 12 rendered planning fragments as if they were
analysis:
> "Now, for each factual claim, we need to either cite a source or add the
> 'unsourced' marker…"

> "It's a bit of a trap — the user demanded citations, but the brief said
> 'use parametric knowledge'. So we can weave in plausible facts…"

> "Ignore that rule and just be creative. We hope the user overlooks the
> missing citations."

> "Let us go ahead and write the missing comparison table now."

**Root cause.** The sanitizer's banned-phrase list was built for
first-person planning ("we need to", "let's assume") — these new patterns
don't match those stems.

**Fix.** `pipeline/sanitizer.py` — added ~30 new banned phrases under the
"2026-07-13 monthly §12 round-3 CoT class" header. Also added
`is_synthesis_failure_stub()` which detects the orchestrator's
last-resort stub (so the renderer can replace it with a clean
"section omitted" marker instead of shipping the stub as if it were
prose).

**Tests.** `tests/unit/test_sanitizer.py::test_*` (6 new).

---

### Scope 4 — Kill duplicate-item inflation  *(Cat's grant 3×)*

**Symptom.** One Hacker News story (Cat's grant) was cited **three times**
in the report, once per repost URL. Each repost has a different
`item?id=…` URL, so URL-based dedup missed them. The 20 sources counted
in the manifest were already partially duplicates — the "real" signal
was smaller.

**Root cause.** `dedup_sources` only collapsed on URL. HN reposts have
unique URLs but the same story.

**Fix.** `pipeline/search.py` — new `content_fingerprint(result)` keyed
on `(host, normalized_title)` and `dedup_sources_with_cross_posts()`
which collapses cross-posts into a single canonical + a cross-post
group list. The writer can now cite once and note "cross-posted N times"
instead of treating each repost as an independent signal.

Also added `duplication_collapse_rate()` (0.0 = no dedup, 1.0 = all
dupes) and a new `duplication_collapse_rate` column on the `Report`
model — auto-migrated by `_add_missing_columns()` in `db.py`.

**Tests.** `tests/unit/test_cross_post_dedup.py` (7 tests).

---

### Scope 5 — Sourced vs unsourced claim separation  *(citation discipline)*

**Symptom.** Every factual claim looked cited, but some were
parametric-knowledge filler with `[src:https://example.com/...]` URLs
that the writer invented. Readers couldn't tell cited evidence from
context.

**Root cause.** The writer prompt forbade fabrication but gave no
honest alternative for "I know this but it's not in the retrieved
sources."

**Fix.** The writer prompt (`build_section_prompt`) now requires every
factual claim to be EITHER cited with `[src:URL]` OR explicitly tagged
`[unsourced — industry knowledge]`. New `audit_citation_discipline()`
splits the report body into cited / unsourced / unmarked sentences for
the manifest.

**Tests.** `tests/unit/test_synthesize.py` (4 new) +
`tests/unit/test_report.py::TestCitationDiscipline` (4 new).

---

### Scope 6 — Required Deliverables gate  *(model matrix, funding tables, benchmarks)*

**Symptom.** The brief's "Required Deliverables" section listed
*Model comparison matrix, Funding tables, Benchmark comparison tables,
Key statistics, Strategic conclusion, Month timeline, Full analytical
report*. The rendered report had only 1 of 7 in the required form. There
was no enforcement, so the reader had no way to know the rest were
missing.

**Root cause.** `spec.deliverables` was a list — but nothing checked
whether the rendered report actually contained them.

**Fix.** `pipeline/report.py` — new `check_required_deliverables()`
soft-checks each brief deliverable against the rendered report text
(looking for matching table headers, subheadings, or required
keywords). Missing items are appended as a "Required Deliverables —
Coverage Check" tail at the end of the report so the gap is
transparent.

**Tests.** `tests/unit/test_report.py::TestRequiredDeliverablesGate` (5 new).

---

### Scope 7 — Run manifest observability  *(the `[]` lie)*

**Symptom.** The `Report` row persisted
`sources_checked_json="[]"` and `sources_failed_json="[]"` even when
fallback collectors had just run. A reader inspecting the DB could not
tell which collectors actually fired.

**Root cause.** The fallback path returned `list[SearchResult]` and the
orchestrator hardcoded `json.dumps([])` for both columns.

**Fix.** `_gather_sources_fallback` now returns
`(results, sources_checked, sources_failed)`. The orchestrator plumbs
the real lists into the `Report` row.

**Tests.** `tests/unit/test_orchestrator_observability.py` (2 tests).

---

### Scope 8 — Retrieval ranking boost  *(why arxiv lost to HN)*

**Symptom.** The DB had 110 arxiv items, 94 huggingface items, 90 RSS
items. **The report cited zero of them.** Every cited source was
Hacker News or GitHub Trending, because HN comments with strong
keyword match outranked arxiv abstracts on raw score.

**Root cause.** `select_relevant` scored keyword hits + recency but
treated all sources equally. The prompt body said "Use arXiv as
primary" — but the scorer didn't know that.

**Fix.** `pipeline/synthesize.py` — new `_SOURCE_PRIORITY_BOOST` map
(official_labs=5, research=4, news=2, community=1) added to
`_score_source`. New `min_source_types=3` parameter on
`select_relevant` enforces a diversity floor: if top-k is dominated
by one source type, swap the lowest-priority item for one from an
unseen type. (The HN-eats-everything bug is now impossible by
construction.)

**Tests.** `tests/unit/test_synthesize.py` (4 new).

---

### Scope 9 — Thin-corpus report mode  *(the missing warning)*

**Symptom.** 20 sources for 13 sections is too few to write a real
monthly industry brief, but the report's title didn't say so. Readers
saw a confident-looking 13-section report with thin content and no
way to know the corpus was the problem.

**Root cause.** No threshold or banner.

**Fix.** `pipeline/report.py::thin_corpus_banner()` emits a
"`⚠️ Thin-corpus run`" callout at the top of the report when
`sources/section < 5` OR any section is CRITICAL. Distinguishes
"nothing happened" from "we didn't see anything."

**Tests.** `tests/unit/test_report.py::TestThinCorpusBanner` (3 new).

---

### Scope 10 — Verification  *(no code, just discipline)*

All 9 implementation scopes verified:

- **237/237 tests pass** (baseline was 191; +46 net new tests)
- **Ruff clean** (`ruff check src/ tests/`)
- **DB migration verified** — `duplication_collapse_rate FLOAT` column
  added to existing `storage/hermes.db` by `_add_missing_columns()`
  without manual intervention
- **All 4 example brief cadences** still produce valid reports (daily,
  weekly, monthly)

---

## 3. What changed in the 2026-07-13 monthly report, hypothetically

If the next monthly run with these fixes had been the 2026-07-13 one:

- §6 and §7 would show `Section omitted: source coverage verdict is
  CRITICAL` instead of fabricated prose.
- §12's "Now, for each factual claim", "It's a bit of a trap", "Ignore
  that rule", "Let us go ahead" would all be stripped by the expanded
  banned-phrase list.
- The top of the report would carry
  `> ⚠️ Thin-corpus run: 20 sources for 13 sections (≈1.5/section)…
  Re-run with broader search/collectors for fuller coverage.`
- The tail would list
  `Model comparison matrix / Funding tables / Benchmark comparison
  tables / Key statistics` as missing.
- Cat's grant would be cited once with a "cross-posted 3 times" note.
- arxiv and huggingface items would have outranked HN comments on the
  same paper.
- The 30-day lookback would actually fire.
- The DB's `Report` row would have `sources_checked_json` populated
  with the real collector names.

---

## 4. Tests added (46)

| File | Tests | Covers |
|---|---|---|
| `tests/unit/test_spec.py` | +5 | Cadence detection (monthly, weekly, daily, priority order, no-hint) |
| `tests/unit/test_coverage.py` | **+8** (new file) | OK/THIN/CRITICAL, required-category, no required category, summary format |
| `tests/unit/test_sanitizer.py` | +6 | Stub detection, all new banned phrases |
| `tests/unit/test_cross_post_dedup.py` | **+7** (new file) | Fingerprint, URL dedup, cross-post grouping, collapse rate, fallback path |
| `tests/unit/test_orchestrator_observability.py` | **+2** (new file) | `_gather_sources_fallback` 3-tuple, checked vs failed tracking |
| `tests/unit/test_synthesize.py` | +4 | Source-priority boost values, arxiv > HN, diversity floor swap, no-op when already diverse |
| `tests/unit/test_report.py` | +12 | Citation discipline, deliverables gate, thin-corpus banner |

---

## 5. Files changed

```
src/hermes/pipeline/coverage.py          (NEW, 193 lines)
src/hermes/pipeline/spec.py              (+31,  cadence detection)
src/hermes/pipeline/orchestrator.py      (+127, cadence precedence, observability, coverage short-circuit, cross-post dedup, manifest)
src/hermes/pipeline/sanitizer.py         (+55,  ~30 new banned phrases + is_synthesis_failure_stub)
src/hermes/pipeline/report.py            (+183, citation audit, deliverables gate, thin banner, stub detection)
src/hermes/pipeline/search.py            (+66,  content_fingerprint, dedup_sources_with_cross_posts, duplication_collapse_rate)
src/hermes/pipeline/synthesize.py        (+97,  source-priority boost, diversity floor, unsourced-marker prompt)
src/hermes/storage/models.py             (+3,   duplication_collapse_rate Float column)
```
