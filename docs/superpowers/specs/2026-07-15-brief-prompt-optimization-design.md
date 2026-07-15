# Brief prompt optimization — design

**Date:** 2026-07-15
**Status:** Design (approved)
**Scope:** All 14 brief prompts in `prompts/`
**Approach:** B — synthesis-first rewrite

## 1. Context

`newsagent` runs the unified pipeline (`run_news_pipeline` in
`src/newsagent/pipeline/orchestrator.py`) driven by a Markdown brief prompt.
The brief contributes source priorities, section structure, deliverables, and
quality rules. The pipeline injects the brief's content into the per-section
writer prompt at runtime (`build_section_prompt` in
`src/newsagent/pipeline/synthesize.py:230`).

There are 14 brief prompts in `prompts/` — 3 cadence briefs (daily/weekly/
monthly) and 11 topical briefs (frontier models, hardware, research papers,
safety, funding, agents, open-source, industry adoption, multimodal,
regulation, companies/startups). They share structure but drift in detail.

The 2026-07-13 monthly report post-mortem (`docs/REPORT_QUALITY_REVIEW.md`)
names 9 report-quality scopes. Several of them have brief-level interventions
that reinforce the code-level fixes already in place:
- Scope 5 (citation discipline): brief-level citation rule reinforces the
  system-level rule.
- Scope 6 (Required Deliverables gate): brief's deliverables list determines
  what the gate checks for.
- Scope 8 (source-priority boost): brief's source list tells the writer
  which sources to anchor on.
- Scope 9 (thin-corpus banner): brief's section list determines when the
  banner fires.

This spec rewrites the 14 briefs to (a) fix recurring prompt-level defects,
(b) reinforce the 9 quality scopes at the brief layer, and (c) raise the
editorial quality bar.

## 2. Goals

1. **Quality:** Every rewritten brief produces a report that addresses the 9
   quality scopes from `docs/REPORT_QUALITY_REVIEW.md` at the brief layer.
2. **Measurability:** Re-running `newsagent eval` on the most recent existing
   report shows a measurable lift in `synthesis` (≥ 4.0) and `usefulness`
   (≥ 4.0).
3. **Editorial:** Each rewritten brief passes a per-brief editorial checklist
   (see §6).

## 3. Non-goals

- **No changes to `src/newsagent/pipeline/spec.py`** — the parser shape is
  preserved. The new "Synthesis Directives" block lives inside the existing
  `instructions` block and is consumed by the writer at runtime.
- **No changes to `src/newsagent/pipeline/synthesize.py`** — the writer prompt
  construction is unchanged.
- **No changes to `.j2` system templates** in `src/newsagent/llm/prompts/` —
  per the user decision to keep the WHAT/HOW split.
- **No changes to `coverage.py`, `cadence.py`, `report.py`, `sanitizer.py`**.

## 4. Diagnosis — defects across the 14 briefs

| # | Defect | Where it shows | Briefs affected |
|---|---|---|---|
| D1 | Trailing `#` on H1 (e.g. `# AI NEWS MONTHLY RETROSPECTIVE#`) | All H1s | 12/14 |
| D2 | Citation-token inconsistency: `[src:URL]` in instructions vs `[src:EXACT_URL]` in deliverables | Required Deliverables block | 14/14 |
| D3 | Source lists duplicated across briefs | Official/Research/News/Community lists | 14/14 |
| D4 | Required Deliverables + Output Quality Requirements are essentially copy-pasted | Top of file | 14/14 |
| D5 | No explicit "use a comparison table for X" trigger | Inline section bullets | 11/14 (except frontier_models.md) |
| D6 | No per-section source-budget guidance | Inline section bullets | 14/14 |
| D7 | No synthesis-verbs (compare, rank, contrast, quantify) | Inline section bullets | 14/14 |
| D8 | No "tag unsourced facts" instruction in the brief's quality bar | Output Quality Requirements | 13/14 |
| D9 | Cadence hint lives in 1-2 lines of prose; no explicit lookback window | Research Instructions | 11/14 |
| D10 | "Predictions" sections labelled as predictions but sometimes drift into news | Report Structure | 6/14 |

## 5. Per-brief severity tier

| Tier | Briefs | Why |
|---|---|---|
| Tier 1 (worst) | `ai_news_monthly.md`, `frontier_models.md`, `ai_hardware_infra.md` | Heavy table reliance; the 2026-07-13 post-mortem subject; comparison-table triggers weak |
| Tier 2 | `ai_agents_coding.md`, `ai_open_source_ecosystem.md`, `ai_funding_ma.md` | Table-heavy but writer dodges; synthesis-verb gap |
| Tier 3 | `ai_research_papers.md`, `ai_safety_alignment.md`, `ai_regulation_policy.md` | Citation-discipline gaps; section-coverage gaps |
| Tier 4 | `ai_news_daily.md`, `ai_industry_adoption.md`, `ai_multimodal_vision.md`, `ai_companies_startups.md`, `ai_news_weekly.md` | Already lean; minor polish needed |

## 6. Target state — what each rewritten brief looks like

Every rewritten brief is a Markdown file with **the same 6-block structure**
(parser-dependent) **plus one new block**:

1. `# <H1 title without trailing #>` — clean heading
2. `**Cadence:** <daily/weekly/monthly retrospective, N-day lookback window.>` — explicit cadence line
3. `## Research Instructions` — keeps the existing prose
4. `## Official Sources` / `## Research Sources` / `## Trusted News Sources` / `## Community Intelligence` — trimmed to brief-relevant entries, with a `_Why these sources_` one-liner per tier
5. `## Report Structure` — sections with bullets, plus inline `_→ render as Markdown table._` markers on entity-comparison bullets, plus per-section `_use N sources; prefer X tier mix_` hint
6. **`## Synthesis Directives`** — **NEW** — a 4-6 item numbered list of synthesis verbs the writer must apply (compare, rank, quantify, contrast, etc.)
7. `## Required Deliverables` — names comparison tables explicitly per section
8. `## Output Quality Requirements` — includes the unsourced-fact tagging rule

**Per-section inline markers:**
- `_→ render as Markdown table._` on any bullet that compares entities.
- `_(use 5-7 sources; prefer 1 official + 2 research + 1 news + 1 community)_` as
  a parenthetical at the start of the bullets block.

**Citation token convention:** `[src:URL]` everywhere in the brief.
`[src:EXACT_URL]` is deprecated at the brief layer; only the system template
keeps that exact wording.

**Per-brief specific changes:**

| Brief | Big changes |
|---|---|
| `example_prompt.md` | Canonical example: clean H1, synthesis directives, table trigger, citation discipline, unsourced-fact rule |
| `ai_news_monthly.md` | Synthesis directives; table triggers on §3 (frontier+silicon), §6 (funding), §9 (benchmarks); explicit "compare with prior month" in §1 |
| `ai_news_weekly.md` | Mirror monthly's synthesis directives; table triggers on §2 (models) and §7 (funding) |
| `ai_news_daily.md` | Keep lean; table trigger on §6 (benchmarks); synthesis directives |
| `frontier_models.md` | Already does tables well — keep structure; add synthesis directives; tighten §3 to 2-3 models |
| `ai_hardware_infra.md` | Table trigger on §2 (silicon), §3 (rack-scale); synthesis directives |
| `ai_agents_coding.md` | Table trigger on §4 (benchmarks); synthesis directives with "rank by production adoption" |
| `ai_funding_ma.md` | Table trigger on §2 (mega-rounds); synthesis directives with "rank by capital deployed" |
| `ai_research_papers.md` | Per-paper synthesis template (problem/method/innovation/impact) explicitly per section bullet |
| `ai_safety_alignment.md` | Synthesis directives distinguishing "research / incident / policy" |
| `ai_open_source_ecosystem.md` | Table triggers on §2 (model release) and §4 (serving); synthesis directives |
| `ai_industry_adoption.md` | Synthesis directives distinguishing "deployed / piloted / announced" |
| `ai_multimodal_vision.md` | Table triggers on §2 (VLM), §3 (image), §4 (video), §5 (audio) |
| `ai_regulation_policy.md` | Per-jurisdiction table trigger; "quantify fines / deadlines / effective dates" |
| `ai_companies_startups.md` | Table triggers on §3 (startup) and §7 (public markets); distinguish "confirmed / rumored / reported" |

## 7. Architecture & rollout

**Files that change (15 total):**
```
prompts/example_prompt.md            (rewrite — canonical example)
prompts/ai_news_daily.md             (rewrite — Tier 4)
prompts/ai_news_weekly.md            (rewrite — Tier 4)
prompts/ai_news_monthly.md           (rewrite — Tier 1)
prompts/frontier_models.md           (rewrite — Tier 1)
prompts/ai_hardware_infra.md         (rewrite — Tier 1)
prompts/ai_agents_coding.md          (rewrite — Tier 2)
prompts/ai_open_source_ecosystem.md  (rewrite — Tier 2)
prompts/ai_funding_ma.md             (rewrite — Tier 2)
prompts/ai_research_papers.md        (rewrite — Tier 3)
prompts/ai_safety_alignment.md       (rewrite — Tier 3)
prompts/ai_regulation_policy.md      (rewrite — Tier 3)
prompts/ai_industry_adoption.md      (rewrite — Tier 4)
prompts/ai_multimodal_vision.md      (rewrite — Tier 4)
prompts/ai_companies_startups.md     (rewrite — Tier 4)
```

**New test files (2):**
```
tests/unit/test_briefs.py            (3 unit tests — see §8)
tests/snapshots/briefs.json          (size + section-count snapshot)
```

**Out of scope (per the "keep current split" decision):**
- `src/newsagent/pipeline/spec.py`
- `src/newsagent/pipeline/synthesize.py`
- `src/newsagent/llm/prompts/*.j2`
- `src/newsagent/pipeline/coverage.py`, `cadence.py`, `report.py`, `sanitizer.py`

**Rollout order (matches severity tier):**

1. Write `example_prompt.md` as the canonical example.
2. Rewrite Tier 1: `ai_news_monthly.md`, `frontier_models.md`,
   `ai_hardware_infra.md`.
3. Rewrite Tier 2: `ai_agents_coding.md`, `ai_open_source_ecosystem.md`,
   `ai_funding_ma.md`.
4. Rewrite Tier 3: `ai_research_papers.md`, `ai_safety_alignment.md`,
   `ai_regulation_policy.md`.
5. Rewrite Tier 4: `ai_industry_adoption.md`, `ai_multimodal_vision.md`,
   `ai_companies_startups.md`, `ai_news_daily.md`, `ai_news_weekly.md`.
6. Run full test suite, run `newsagent eval` smoke, update `CHANGELOG.md`,
   update `README.md` to point at the new example.

## 8. Testing strategy

**Layer 1 — Existing test suite:**
- `pytest tests/ -q` must still pass (283 tests).
- The brief rewrites don't change `spec.py`, `synthesize.py`, or `.j2`
  templates, so existing parse tests, coverage tests, critic tests should
  pass unchanged.
- Failure mode to watch: if a brief rename causes `parse_prompt` to return a
  different section count for any existing parse test, the rewrite is
  structurally wrong.

**Layer 2 — New prompt-test harness (3 small tests in
`tests/unit/test_briefs.py`):**
1. `test_each_brief_parses_with_expected_section_count` — every brief
   parses to a `BriefSpec` with `len(spec.sections) >= 3` (the floor for a
   useful report). Section counts are stored in
   `tests/snapshots/briefs.json` keyed by brief filename; the test reads
   the snapshot, asserts `actual >= expected` so accidental section
   deletions are caught but renames (e.g. consolidating §3+§4) are allowed.
   Catches D1 (H1 bug) and accidental section renames.
2. `test_each_brief_has_synthesis_directives_block` — every brief has a
   `## Synthesis Directives` block. The test asserts the heading is
   present in `spec.raw`; the `4-6 items` count is a recommendation
   enforced by review, not by automated test.
3. `test_each_brief_has_required_deliverables_block` — every brief's
   Required Deliverables includes a comparison-table mention for every
   section that compares entities (mapped per the diagnosis tier). The
   mapping lives in `tests/snapshots/briefs.json` under
   `comparison_sections: [<section_number>, ...]`.

Plus a snapshot test:
4. `test_briefs_byte_count_snapshot` — brief sizes stay in the expected
   range; catches accidental large diffs and accidental deletions of the
   Synthesis Directives block. The snapshot stores per-brief `{filename:
   {min_bytes, max_bytes, section_count, comparison_sections: [...]}}`
   keyed by brief filename; the test asserts each metric is in range
   (fails on ±20% drift or any item count = 0).

**Layer 3 — End-to-end smoke (manual, time-boxed):**
- `newsagent eval` on the most recent existing report — record baseline
  scores, target lift documented in CHANGELOG.
- `newsagent news prompts/ai_news_monthly.md` — full run, time-boxed at
  ~40min. Score the resulting report against the editorial checklist.
- One `newsagent news prompts/frontier_models.md` run to verify the Tier 1
  brief lands cleanly.

## 9. Success criteria

**A. 9 quality scopes (qualitative):**
- Scope 5 (citation discipline): every factual claim is either `[src:URL]`
  or `[unsourced — industry knowledge]`.
- Scope 6 (Required Deliverables): every listed deliverable renders in the
  report (or is explicitly flagged in the Coverage Check tail).
- Scope 8 (source-priority boost): writer cites official/research sources
  at least 30% of the time when the brief lists them.
- Scope 9 (thin-corpus banner): a thin-corpus run produces the banner.

**B. `newsagent eval` rubric lift (quantitative):**
- Target: `synthesis` ≥ 4.0, `usefulness` ≥ 4.0, `trust` ≥ 4.0.
- Documented in CHANGELOG.

**C. Editorial quality (per-brief checklist, applies to all 14 briefs;
N/A if a brief has no entity-comparison sections, e.g. `ai_news_daily.md`
§3-§5):**
- [ ] No trailing `#` in H1.
- [ ] Citation token consistent throughout the file (`[src:URL]`).
- [ ] Source list is brief-relevant (no copy-paste from another brief).
- [ ] Each section that compares entities has a `_→ render as Markdown
      table._` marker (N/A for briefs with no comparison sections).
- [ ] Synthesis Directives block is present, has 4-6 items, no boilerplate.
- [ ] No filler, no duplicate sentences, no contradictory instructions.
- [ ] Required Deliverables names comparison tables explicitly.
- [ ] Output Quality Requirements includes the unsourced-fact tagging rule.

## 10. Risks

| Risk | Mitigation |
|---|---|
| A rewritten brief's "Synthesis Directives" parse-fails the orchestrator | Directives live in the `instructions` block (freeform prose); unit test confirms block exists |
| Writer's per-call token budget gets blown by denser brief content | Directives fit in ~30 lines / ~500 words — well under per-section budget; verified by end-to-end run |
| Rewrite breaks `parse_prompt._CADENCE_HINTS` detection | Each rewrite keeps the existing cadence-hint phrase verbatim; unit test confirms `spec.cadence` is detected |
| Snapshot test is too brittle | Snapshot stores ranges, not exact byte counts; only fails on ±20% drift |
| End-to-end re-run fails for reasons unrelated to brief content | Time-boxed; failure documented but not blocking if existing report is acceptable |

## 11. Out of scope (deliberate)

- Changes to `src/newsagent/pipeline/spec.py` — the parser shape is
  preserved. The "Synthesis Directives" block lives inside the existing
  `instructions` block and is consumed by the writer at runtime.
- Changes to `.j2` system templates — per the user decision to keep the
  WHAT/HOW split.
- Adding a YAML/JSON brief format — that's a larger restructure (Approach C
  in the brainstorming session), out of scope here.
- Auto-generating briefs from templates — that's a tooling change, out of
  scope here.
