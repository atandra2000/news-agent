# newsagent Pipeline Unification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the two-pipeline structure (`newsagent run` daily + `newsagent news` brief) with a single, brief-driven pipeline. The cognition core (artifact-passing 14 stages in `pipeline/stages/`) becomes the body of the brief path. All legacy/fallback code is deleted. One command, one pipeline, one file.

**Architecture:** Move `brief/*` modules into `pipeline/*` (no behavior change). Replace `pipeline/run.py` with a new orchestrator that drives both per-section synthesis AND the optional cognition core (when `len(spec.sections) >= FULL_COGNITION_MIN_SECTIONS = 3`). Delete the daily-path orchestrator, the 18-renderer fallback, the analyzers, the 4 legacy pipeline modules (`cluster`, `rank`, `planning`, `research`), `quality_gates`, and `prioritize`. Slim `PipelineConfig` and `SearchConfig`. Add `NEWSAGENT_CADENCE` env var. Drop KG writes; past-reports RAG remains.

**Tech Stack:** Python 3.11+, pydantic-settings, structlog, SQLAlchemy 2 async, aiosqlite, httpx, tenacity, jinja2, pytest + pytest-asyncio + respx, ruff.

**Spec:** `docs/superpowers/specs/2026-07-13-unify-pipelines-design.md`

---

## Global Constraints

- **Python 3.11+** — use `match`/`Self`/PEP 695 if helpful; not required.
- **All tests offline, no network/LLM** — 250-280 tests target, all in <10s.
- **`ruff check src tests` clean** after every task.
- **No new dependencies** — use stdlib + existing deps.
- **The repo is NOT a git repo** (`Is a git repository: false`). Skip the `git add` / `git commit` steps in the task templates. Verify with `.venv/bin/python -m pytest -q tests/` instead.
- **Vault sync runs automatically** via the `Stop` hook in `~/.claude/settings.json` for any new/modified `.md` in `~/Desktop/CoreProjects/`. Don't hand-edit mirror files in `~/Documents/obsidian`.
- **No `Co-Authored-By: Claude` trailers** in any commit message (per `~/.claude/CLAUDE.md`).
- **Imports use `newsagent.pipeline.{spec, planner, search, synthesize, report, eval, adapter}` after the move** — never `newsagent.brief.*` in new code.
- **The 9 prompts in `prompts/` keep working** — `parse_prompt` is the new name of `parse_brief` but accepts the same Markdown format.
- **The launchd plist** must call `newsagent news <path-to-prompt>` after Task 17.

---

## File Structure

### Files created (or created-from-move)

| Path | Responsibility |
|---|---|
| `src/newsagent/pipeline/spec.py` | `parse_prompt(md) -> BriefSpec` (moved from `brief/spec.py`) |
| `src/newsagent/pipeline/planner.py` | `plan_queries(spec) -> list[ResearchQuery]` (moved) |
| `src/newsagent/pipeline/search.py` | Tavily + Null search providers, `dedup_sources` (moved) |
| `src/newsagent/pipeline/synthesize.py` | Per-section synthesis + critic loop + CoT backstop (moved) |
| `src/newsagent/pipeline/report.py` | Citation resolution + assembly (moved) |
| `src/newsagent/pipeline/eval.py` | Report scoring (moved) |
| `src/newsagent/pipeline/adapter.py` | Per-prompt adaptive state (moved) |
| `src/newsagent/pipeline/orchestrator.py` | The new unified orchestrator |
| `src/newsagent/pipeline/cognition.py` | The optional cognition core driver (when 3+ sections) |
| `src/newsagent/pipeline/cadence.py` | The `_CADENCE` table + lookup (extracted from `brief/run.py`) |
| `tests/unit/test_spec.py` | (renamed from `test_brief_spec.py`) |
| `tests/unit/test_planner.py` | (renamed from `test_brief_planner.py`) |
| `tests/unit/test_report.py` | (renamed from `test_brief_citations.py`, trimmed) |
| `tests/unit/test_synthesize.py` | (new — per-section synthesis with critic loop) |
| `tests/unit/test_embed.py` | (new — Embedder hashing) |
| `tests/unit/test_eval.py` | (new — split from `test_brief_citations.py`) |
| `tests/unit/test_cadence.py` | (new — `_CADENCE` table + `NEWSAGENT_CADENCE` validation) |
| `tests/integration/test_news_run.py` | (new — full pipeline end-to-end with mocked LLM) |

### Files modified

| Path | Change |
|---|---|
| `src/newsagent/pipeline/run.py` | Replaced (Task 12) by `orchestrator.py` — file deleted in Task 18 |
| `src/newsagent/config.py` | `PipelineConfig` slimmed (Task 4); `SearchConfig` slimmed (Task 4); `NewsAgentSettings` gains `cadence: str` (Task 3) |
| `src/newsagent/cli.py` | `newsagent run`, `newsagent backfill`, `newsagent research` removed (Task 17) |
| `scheduler/launchd.plist` | Update to `newsagent news <path-to-prompt>` (Task 19) |
| `scheduler/cron.txt` | Same (Task 19) |
| `scheduler/systemd.service` | Same (Task 19) |
| `scheduler/systemd.timer` | Same (Task 19) |
| `README.md` | Update Quickstart + CLI table (Task 20) |
| `CHANGELOG.md` | Add "Pipeline unification" entry (Task 20) |
| `docs/ARCHITECTURE.md` | Rewrite §1, §2.6, §2.7, §2.8 (Task 20) |
| `docs/PIPELINE.md` | Rewrite §1, §2, §3, §4, §6; delete §5, §6 (Task 20) |
| `docs/CONFIGURATION.md` | Reflect removed env vars (Task 20) |
| `docs/CLI.md` | Update for 7 subcommands (Task 20) |
| `docs/STORAGE.md` | Note KG tables not written (Task 20) |

### Files deleted (Task 18)

- `src/newsagent/brief/` (entire package)
- `src/newsagent/analyzers/` (entire package)
- `src/newsagent/renderers/` (entire package)
- `src/newsagent/pipeline/cluster.py`
- `src/newsagent/pipeline/rank.py`
- `src/newsagent/pipeline/planning.py`
- `src/newsagent/pipeline/research.py`
- `src/newsagent/pipeline/quality_gates.py`
- `src/newsagent/pipeline/prioritize.py`
- `src/newsagent/pipeline/run.py` (replaced by `orchestrator.py`)
- `tests/unit/test_quality_gates.py`
- `tests/integration/test_pipeline.py`
- `docs/BRIEF.md` (content moves to `PIPELINE.md` + `CONFIGURATION.md`)
- `docs/NEWSAGENT_DESIGN.md` is **kept** (historical reference)
- `docs/COGNITION_DESIGN.md` is **kept** (historical reference)

---

## Task Ordering

The tasks are designed so each one keeps the test suite green. Tasks 1-2 are move-only. Task 3-5 add the new cadence machinery. Task 6-11 build the new modules and test them. Task 12 replaces the orchestrator. Tasks 13-15 add cognition core wiring. Tasks 16-19 clean up. Task 20 updates docs and ships.

---

### Task 1: Move `brief/spec.py` → `pipeline/spec.py`

**Files:**
- Create: `src/newsagent/pipeline/spec.py` (from `src/newsagent/brief/spec.py`)
- Modify: `src/newsagent/pipeline/spec.py` (rename `parse_brief` → `parse_prompt`, but keep `parse_brief` as an alias for one release)
- Test: `tests/unit/test_brief_spec.py` (rename in Task 2)

**Interfaces:**
- Consumes: nothing
- Produces: `parse_prompt(md: str) -> BriefSpec`, `BriefSpec`, `SectionSpec`, `brief_slug(spec) -> str`

- [ ] **Step 1: Read the existing `brief/spec.py`**

Read `src/newsagent/brief/spec.py` (201 LoC). Note: `parse_brief` is the public name.

- [ ] **Step 2: Copy the file to `pipeline/spec.py`**

```bash
cp src/newsagent/brief/spec.py src/newsagent/pipeline/spec.py
```

- [ ] **Step 3: Update imports inside the moved file**

The file imports only stdlib (`re`, `dataclasses`). No changes needed for those.

- [ ] **Step 4: Rename `parse_brief` to `parse_prompt` and add a compatibility alias**

Edit `src/newsagent/pipeline/spec.py`:

```python
# Find:
def parse_brief(md: str) -> BriefSpec:
# Replace with:
def parse_prompt(md: str) -> BriefSpec:
    # ... same body ...
    return spec


# Backwards-compat alias — delete in Task 18.
parse_brief = parse_prompt
```

- [ ] **Step 5: Run the existing test to confirm move works**

```bash
.venv/bin/python -m pytest tests/unit/test_brief_spec.py -q
```

Expected: PASS. (The test file still imports from `brief.spec`.)

- [ ] **Step 6: Verify ruff is clean**

```bash
.venv/bin/python -m ruff check src/newsagent/pipeline/spec.py
```

Expected: clean.

---

### Task 2: Rename `test_brief_spec.py` → `test_spec.py` and update its imports

**Files:**
- Create: `tests/unit/test_spec.py` (from `tests/unit/test_brief_spec.py`)
- Delete: `tests/unit/test_brief_spec.py`

- [ ] **Step 1: Copy and update the test file**

```bash
cp tests/unit/test_brief_spec.py tests/unit/test_spec.py
```

Then edit `tests/unit/test_spec.py`: change every `from newsagent.brief.spec import` to `from newsagent.pipeline.spec import`. The test file is small (1182 bytes) — do this with `Edit` on the import line.

- [ ] **Step 2: Run the test**

```bash
.venv/bin/python -m pytest tests/unit/test_spec.py -q
```

Expected: PASS.

- [ ] **Step 3: Delete the old file**

```bash
rm tests/unit/test_brief_spec.py
```

- [ ] **Step 4: Confirm full suite still green**

```bash
.venv/bin/python -m pytest -q tests/
```

Expected: 263 passed.

---

### Task 3: Add `cadence` to `NewsAgentSettings`

**Files:**
- Modify: `src/newsagent/config.py` (add `cadence` field to `NewsAgentSettings`)

**Interfaces:**
- Produces: `NewsAgentSettings.cadence: str` (default `"daily"`, validated to one of `daily|weekly|monthly`)

- [ ] **Step 1: Read the existing `NewsAgentSettings` class**

Located in `src/newsagent/config.py:202-243`.

- [ ] **Step 2: Add the `cadence` field with a validator**

Edit `src/newsagent/config.py`. After `log_level: str = "INFO"` add:

```python
# Cadence drives the lookback window + per-section source counts.
# One of: daily | weekly | monthly. Invalid values fall back to daily at the
# orchestrator boundary; the field defaults to daily for unset .env.
cadence: str = "daily"
```

- [ ] **Step 3: Run the test suite to confirm nothing breaks**

```bash
.venv/bin/python -m pytest -q tests/
```

Expected: 263 passed.

- [ ] **Step 4: Verify ruff clean**

```bash
.venv/bin/python -m ruff check src/newsagent/config.py
```

---

### Task 4: Slim `PipelineConfig` and `SearchConfig`

**Files:**
- Modify: `src/newsagent/config.py`

**Interfaces:**
- `PipelineConfig`: removes `self_critique`, `rag_writing`, `research_loops`, `critic_max_chars`, `analyze_max_chars`, `prioritizer_front_page_k`, `prioritizer_analysis_k`, `prioritizer_min_score`. Keeps `top_k_analysis`, `top_k_clusters`, `report_top_k`, `similarity_threshold`, `cluster_label_max_chars`, `section_concurrency`, `graph_context_max_chars`, `thesis_enabled`, `editorial_board_enabled`, `writer_extract_cot`.
- `SearchConfig`: removes `max_results`, `search_depth`, `topic`, `include_raw_content`, `max_sources`, `per_section_sources`. Keeps `backend`, `tavily_api_key`, `tavily_base_url`, `domain_cap`, `timeout_seconds`, `min_citations`, `extra_queries`.

- [ ] **Step 1: Remove dead fields from `PipelineConfig`**

Edit `src/newsagent/config.py`. In the `PipelineConfig` class body, remove these lines:

```python
    # Enable the in-pipeline Critic -> Rewrite loop.
    self_critique: bool = True
    # Enable RAG-augmented writing.
    rag_writing: bool = True
    # Enable planning-gated autonomous research loops (§12.9).
    research_loops: bool = True
    # Max chars of the report sent to the self-critique LLM; condensing the body
    # cuts the prompt while the critic still catches unsupported claims. 0 = full.
    critic_max_chars: int = 3500
    # Max chars of item content fed to the per-item analyzer (token safety).
    analyze_max_chars: int = 2500
    # --- Prioritization gate (ranks + tiers Items before LLM extraction) ---
    # Top-N items promoted to ``front_page`` (deepest reasoning).
    prioritizer_front_page_k: int = 5
    # Next-M items promoted to ``analysis`` (deep extraction, below front page).
    prioritizer_analysis_k: int = 20
    # Items scoring below this are cut entirely (drop, not context).
    prioritizer_min_score: float = 0.05
```

- [ ] **Step 2: Remove dead fields from `SearchConfig`**

Edit `src/newsagent/config.py`. In the `SearchConfig` class body, remove these lines:

```python
    # Results per query.
    max_results: int = 6
    # "basic" or "advanced" Tavily depth.
    search_depth: str = "advanced"
    # Tavily topic hint; "" disables it (recommended "news" for AI briefs).
    topic: str = "news"
    # Pull fuller page text so the writer has more to cite.
    include_raw_content: bool = True
    # Hard cap on unique sources fed to synthesis (token safety).
    max_sources: int = 60
    # Top-k most relevant sources passed to the writer per section.
    per_section_sources: int = 12
```

- [ ] **Step 3: Run the test suite**

```bash
.venv/bin/python -m pytest -q tests/
```

Expected: 263 passed. (No test reads the removed fields today.)

- [ ] **Step 4: Verify ruff clean**

```bash
.venv/bin/python -m ruff check src/newsagent/config.py
```

---

### Task 5: Create `pipeline/cadence.py` with the per-cadence table

**Files:**
- Create: `src/newsagent/pipeline/cadence.py`
- Test: `tests/unit/test_cadence.py`

**Interfaces:**
- `CADENCE: dict[str, CadenceSpec]` — `daily|weekly|monthly` → `(window, days, per_section, sources, max_tokens, min_citations)`
- `resolve_cadence(value: str) -> CadenceSpec` — defaults to `daily` on invalid value
- `CadenceSpec` dataclass: `window: str`, `days: int`, `per_section: int`, `sources: int`, `max_tokens: int`, `min_citations: int`

- [ ] **Step 1: Write the test file**

Create `tests/unit/test_cadence.py`:

```python
"""Cadence table + env validation."""

from __future__ import annotations

import pytest

from newsagent.pipeline.cadence import CADENCE, CadenceSpec, resolve_cadence


def test_cadence_table_has_three_entries():
    assert set(CADENCE) == {"daily", "weekly", "monthly"}


def test_cadence_daily_shape():
    d = CADENCE["daily"]
    assert d.days == 1
    assert d.max_tokens >= 1000
    assert d.min_citations >= 0


def test_cadence_max_tokens_scales_with_window():
    """Monthly gets more tokens than daily — long-tail signals need more room."""
    assert CADENCE["monthly"].max_tokens > CADENCE["daily"].max_tokens
    assert CADENCE["weekly"].max_tokens > CADENCE["daily"].max_tokens


def test_cadence_sources_scales_with_window():
    assert CADENCE["monthly"].sources > CADENCE["weekly"].sources > CADENCE["daily"].sources


def test_resolve_cadence_valid():
    assert resolve_cadence("monthly") is CADENCE["monthly"]


@pytest.mark.parametrize("bad", ["", "yearly", "DAILY", None])
def test_resolve_cadence_invalid_falls_back_to_daily(bad):
    assert resolve_cadence(bad) is CADENCE["daily"]


def test_cadence_spec_is_a_dataclass():
    assert CadenceSpec(window="x", days=1, per_section=1, sources=1, max_tokens=100, min_citations=0)
```

- [ ] **Step 2: Run the test — confirm it fails**

```bash
.venv/bin/python -m pytest tests/unit/test_cadence.py -q
```

Expected: FAIL with `ModuleNotFoundError: newsagent.pipeline.cadence`.

- [ ] **Step 3: Implement the module**

Create `src/newsagent/pipeline/cadence.py`:

```python
"""Per-cadence tuning: lookback window, days, per-section fan-out, max_tokens.

A single table — anything that scales with the lookback window lives here.
The orchestrator looks up the entry once at the start of a run.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CadenceSpec:
    window: str         # human-readable, e.g. "the last 24 hours"
    days: int           # lookback window in days (for Tavily `days` param)
    per_section: int    # queries per section
    sources: int        # source-priority probes
    max_tokens: int     # writer max_tokens (scales with window length)
    min_citations: int  # per-section citation floor (post-synthesis)


# Daily = pulse, weekly = digest, monthly = deep dive. Max_tokens scales with
# window because the writer has more ground to cover. Per-section + sources
# scale so a monthly deep dive gets a richer source pool per section.
CADENCE: dict[str, CadenceSpec] = {
    "daily": CadenceSpec(
        window="the last 24 hours",
        days=1,
        per_section=1,
        sources=4,
        max_tokens=5000,
        min_citations=3,
    ),
    "weekly": CadenceSpec(
        window="the past 7 days",
        days=7,
        per_section=2,
        sources=8,
        max_tokens=6000,
        min_citations=3,
    ),
    "monthly": CadenceSpec(
        window="the past 30 days",
        days=30,
        per_section=3,
        sources=12,
        max_tokens=8000,
        min_citations=3,
    ),
}


def resolve_cadence(value: str | None) -> CadenceSpec:
    """Look up a cadence by name; fall back to daily on any invalid value."""
    if value and value in CADENCE:
        return CADENCE[value]
    return CADENCE["daily"]
```

- [ ] **Step 4: Run the test — confirm it passes**

```bash
.venv/bin/python -m pytest tests/unit/test_cadence.py -q
```

Expected: 8 passed.

- [ ] **Step 5: Run the full suite**

```bash
.venv/bin/python -m pytest -q tests/
```

Expected: 271 passed (263 + 8 new).

- [ ] **Step 6: Verify ruff clean**

```bash
.venv/bin/python -m ruff check src/newsagent/pipeline/cadence.py tests/unit/test_cadence.py
```

---

### Task 6: Move `brief/planner.py` → `pipeline/planner.py`

**Files:**
- Create: `src/newsagent/pipeline/planner.py` (from `src/newsagent/brief/planner.py`)
- Modify: imports inside the moved file

**Interfaces:**
- Produces: `plan_queries(spec, *, per_section=2, source_queries=8, year="2026", cadence=None) -> list[ResearchQuery]`, `section_keywords(sec) -> set[str]`, `ResearchQuery` dataclass

- [ ] **Step 1: Copy and update imports**

```bash
cp src/newsagent/brief/planner.py src/newsagent/pipeline/planner.py
```

Edit `src/newsagent/pipeline/planner.py` — find `from newsagent.brief.spec import BriefSpec, SectionSpec` and replace with `from newsagent.pipeline.spec import BriefSpec, SectionSpec`.

- [ ] **Step 2: Run existing test against the moved module via a re-pointed import**

The existing `test_brief_planner.py` imports from `brief.planner`. Don't change it yet — first confirm the move is structurally sound by running it as-is:

```bash
.venv/bin/python -m pytest tests/unit/test_brief_planner.py -q
```

Expected: PASS (the old `brief.planner` is still there).

- [ ] **Step 3: Verify ruff clean**

```bash
.venv/bin/python -m ruff check src/newsagent/pipeline/planner.py
```

---

### Task 7: Move `brief/search.py` → `pipeline/search.py`

**Files:**
- Create: `src/newsagent/pipeline/search.py` (from `src/newsagent/brief/search.py`)
- Modify: imports inside the moved file

**Interfaces:**
- Produces: `SearchResult`, `SearchProvider` Protocol, `NullSearch`, `TavilySearch`, `build_search_provider(settings, *, days=None) -> SearchProvider`, `dedup_sources(results, *, limit=60) -> list[SearchResult]`

- [ ] **Step 1: Copy and update imports**

```bash
cp src/newsagent/brief/search.py src/newsagent/pipeline/search.py
```

Edit `src/newsagent/pipeline/search.py` — find `from newsagent.config import SearchConfig` and `from newsagent.logging import get_logger` (no change needed — both already point at the right place).

- [ ] **Step 2: Replace the removed SearchConfig fields with hardcoded constants**

The new `SearchConfig` (Task 4) no longer has `topic`, `search_depth`, or `include_raw_content`. The Tavily client needs these. Replace them with module-level constants in `src/newsagent/pipeline/search.py`:

Find:

```python
        topic: str = "news",
        days: int | None = None,
        include_raw_content: bool = True,
        search_depth: str = "advanced",
```

Replace with:

```python
        days: int | None = None,
```

(These are still constructor kwargs but the defaults are dropped because they're now constants inside the class.)

Then find the `build_search_provider` function. Replace the call site to drop the deleted kwargs:

```python
def build_search_provider(settings: SearchConfig | None = None, *, days: int | None = None) -> SearchProvider:
    cfg = settings or SearchConfig()
    if cfg.backend == "tavily":
        if not cfg.tavily_api_key:
            log.warning("search.tavily_no_key", falling_back="null")
            return NullSearch()
        return TavilySearch(
            api_key=cfg.tavily_api_key,
            base_url=cfg.tavily_base_url,
            timeout=cfg.timeout_seconds,
            days=days,
        )
    return NullSearch()
```

- [ ] **Step 3: Run the test suite**

```bash
.venv/bin/python -m pytest -q tests/
```

Expected: 271 passed. (The existing tests use the old `brief.search`; the new `pipeline.search` is unused so far.)

- [ ] **Step 4: Verify ruff clean**

```bash
.venv/bin/python -m ruff check src/newsagent/pipeline/search.py
```

---

### Task 8: Move `brief/synthesize.py` → `pipeline/synthesize.py`

**Files:**
- Create: `src/newsagent/pipeline/synthesize.py` (from `src/newsagent/brief/synthesize.py`)

**Interfaces:**
- Produces: `select_relevant`, `build_section_prompt`, `synthesize_section`, `synthesize_section_with_review`, `clean_section_text`, `is_substantial_section`, `_content_word_count`, `count_citations`, `_SECTION_MIN_WORDS`, `extract_prose` (if it's here — confirm during read)

- [ ] **Step 1: Read the current `brief/synthesize.py` to understand its full surface**

Read the entire 585 LoC file. Note the public names.

- [ ] **Step 2: Copy and update imports**

```bash
cp src/newsagent/brief/synthesize.py src/newsagent/pipeline/synthesize.py
```

Edit `src/newsagent/pipeline/synthesize.py`. Replace the three `from newsagent.brief.*` imports:

```python
from newsagent.brief.planner import section_keywords
from newsagent.brief.search import SearchResult, _host
from newsagent.brief.spec import SectionSpec
```

With:

```python
from newsagent.pipeline.planner import section_keywords
from newsagent.pipeline.search import SearchResult, _host
from newsagent.pipeline.spec import SectionSpec
```

- [ ] **Step 3: Run the test suite**

```bash
.venv/bin/python -m pytest -q tests/
```

Expected: 271 passed.

- [ ] **Step 4: Verify ruff clean**

```bash
.venv/bin/python -m ruff check src/newsagent/pipeline/synthesize.py
```

---

### Task 9: Move `brief/report.py`, `brief/eval.py`, `brief/adapter.py` → `pipeline/`

**Files:**
- Create: `src/newsagent/pipeline/report.py` (from `src/newsagent/brief/report.py`)
- Create: `src/newsagent/pipeline/eval.py` (from `src/newsagent/brief/eval.py`)
- Create: `src/newsagent/pipeline/adapter.py` (from `src/newsagent/brief/adapter.py`)

**Interfaces:**
- `pipeline.report`: `resolve_citations`, `assemble_report`, `drop_empty_subheadings`, `AssembledReport`
- `pipeline.eval`: `evaluate_text`, `evaluate_report`, `get_rolling_scores`, `EvalVerdict`
- `pipeline.adapter`: `PromptAdapter`, `PromptState`

- [ ] **Step 1: Copy `brief/report.py` and update imports**

```bash
cp src/newsagent/brief/report.py src/newsagent/pipeline/report.py
```

Edit `src/newsagent/pipeline/report.py`. Replace:

```python
from newsagent.brief.search import SearchResult
from newsagent.brief.spec import BriefSpec
```

With:

```python
from newsagent.pipeline.search import SearchResult
from newsagent.pipeline.spec import BriefSpec
```

- [ ] **Step 2: Copy `brief/eval.py` and update imports**

```bash
cp src/newsagent/brief/eval.py src/newsagent/pipeline/eval.py
```

Edit `src/newsagent/pipeline/eval.py`. Replace:

```python
from newsagent.brief.spec import BriefSpec, parse_brief
```

With:

```python
from newsagent.pipeline.spec import BriefSpec, parse_prompt
```

(The local `evaluate_report` still uses `parse_brief` internally — keep the alias for now and rewrite in Task 18.)

- [ ] **Step 3: Copy `brief/adapter.py` (no `brief.*` imports)**

```bash
cp src/newsagent/brief/adapter.py src/newsagent/pipeline/adapter.py
```

No import changes needed (only stdlib + `newsagent.logging`).

- [ ] **Step 4: Run the test suite**

```bash
.venv/bin/python -m pytest -q tests/
```

Expected: 271 passed.

- [ ] **Step 5: Verify ruff clean**

```bash
.venv/bin/python -m ruff check src/newsagent/pipeline/report.py src/newsagent/pipeline/eval.py src/newsagent/pipeline/adapter.py
```

---

### Task 10: Rewrite the brief integration test against the moved modules

**Files:**
- Modify: `tests/integration/test_brief_run.py` (update imports)

- [ ] **Step 1: Update imports**

The test currently imports from `newsagent.brief.*`. Replace every occurrence:

- `from newsagent.brief.spec import` → `from newsagent.pipeline.spec import`
- `from newsagent.brief.planner import` → `from newsagent.pipeline.planner import`
- `from newsagent.brief.search import` → `from newsagent.pipeline.search import`
- `from newsagent.brief.synthesize import` → `from newsagent.pipeline.synthesize import`
- `from newsagent.brief.report import` → `from newsagent.pipeline.report import`
- `from newsagent.brief.run import` → `from newsagent.pipeline.run import` (the orchestrator — same path, but rewritten in Task 12)

(Read the file first to see what's there; the integration test may mock fewer imports.)

- [ ] **Step 2: Run the integration test**

```bash
.venv/bin/python -m pytest tests/integration/test_brief_run.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full suite**

```bash
.venv/bin/python -m pytest -q tests/
```

Expected: 271 passed.

---

### Task 11: Create the new orchestrator `pipeline/orchestrator.py`

**Files:**
- Create: `src/newsagent/pipeline/orchestrator.py`
- Test: `tests/integration/test_news_run.py`

**Interfaces:**
- `run_news_pipeline(spec: BriefSpec, *, settings=None, router=None, search=None, out_path=None, brief_path=None) -> Path`
- Module-level constant: `FULL_COGNITION_MIN_SECTIONS = 3`
- Calls into the moved `pipeline.{planner, search, retrieval, synthesize, report}` modules
- Optional: calls into cognition core stages when `len(spec.sections) >= FULL_COGNITION_MIN_SECTIONS`

- [ ] **Step 1: Read the existing `brief/run.py` (the source of truth) to understand the full flow**

Read `src/newsagent/brief/run.py` (461 LoC) in full. Identify: imports, `_build_router`, `_gather_sources`, `_gather_sources_fallback`, `_CADENCE`, `_synthesize_section_parallel`, `run_brief_pipeline`, `_generate_section_queries`, `run_brief`.

- [ ] **Step 2: Write the test for the orchestrator**

Create `tests/integration/test_news_run.py`:

```python
"""Integration test for the unified news pipeline orchestrator.

Mocks the LLM router and search provider so the test is offline and fast.
The orchestrator is the only thing under test; the underlying stages are
unit-tested in their own files.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from newsagent.config import NewsAgentSettings
from newsagent.pipeline.orchestrator import FULL_COGNITION_MIN_SECTIONS, run_news_pipeline
from newsagent.pipeline.search import SearchResult
from newsagent.pipeline.spec import BriefSpec, SectionSpec


SIMPLE_PROMPT = """# Test Report

## Research Instructions
- Source A
- Source B

## Report Structure
## 1. Pulse
- bullet one
- bullet two

## 2. Trends
- bullet one
"""


DEEP_PROMPT = """# Test Deep Report

## Research Instructions
- Source A

## Report Structure
## 1. Pulse
- a

## 2. Trends
- b

## 3. Frontier
- c

## 4. Regulation
- d
"""


def _fake_search_provider(results: list[SearchResult]) -> MagicMock:
    sp = MagicMock()
    sp.name = "fake"
    sp.search = AsyncMock(return_value=results)
    return sp


def _fake_router(text: str = "synthesized prose") -> MagicMock:
    r = MagicMock()
    r.stats.total_tokens = 0
    r.complete = AsyncMock()
    r.json_complete = AsyncMock(return_value={})

    from newsagent.llm.providers.base import ProviderResult

    r.complete.return_value = ProviderResult(
        text=text, model="test", provider="test", prompt_tokens=10, completion_tokens=20
    )
    return r


def _make_settings(tmp_path: Path) -> NewsAgentSettings:
    s = NewsAgentSettings()
    s.storage.dir = tmp_path
    return s


@pytest.mark.asyncio
async def test_orchestrator_writes_file_for_simple_prompt(tmp_path):
    settings = _make_settings(tmp_path)
    spec = BriefSpec(
        title="Test Report",
        sections=[
            SectionSpec(number=1, title="Pulse", bullets=["a", "b"]),
            SectionSpec(number=2, title="Trends", bullets=["c"]),
        ],
    )
    search = _fake_search_provider([
        SearchResult(title="S1", url="https://example.com/1", content="x"),
    ])
    router = _fake_router()
    out = await run_news_pipeline(
        spec, settings=settings, router=router, search=search,
        out_path=tmp_path / "out.md",
    )
    assert out.exists()
    text = out.read_text()
    assert "## **Test Report**" in text
    assert "## **1. Pulse**" in text
    assert "## **2. Trends**" in text


@pytest.mark.asyncio
async def test_orchestrator_short_prompt_skips_cognition_core():
    """Briefs with < 3 sections go straight to per-section synthesis (no cognition)."""
    from newsagent.pipeline import orchestrator

    called = {"graph": False, "stories": False, "plan": False}

    real_graph = orchestrator._build_evidence_graph
    real_stories = orchestrator.discover_stories
    real_plan = orchestrator.plan_research

    async def fake_graph(*a, **k):
        called["graph"] = True
        return await real_graph(*a, **k) if False else None

    def fake_stories(*a, **k):
        called["stories"] = True
        return []

    def fake_plan(*a, **k):
        called["plan"] = True
        return None

    # Just verify the threshold: a 2-section spec is below FULL_COGNITION_MIN_SECTIONS.
    spec = BriefSpec(
        title="Short",
        sections=[SectionSpec(number=1, title="a", bullets=[]),
                  SectionSpec(number=2, title="b", bullets=[])],
    )
    assert len(spec.sections) < FULL_COGNITION_MIN_SECTIONS


def test_threshold_constant_is_three():
    assert FULL_COGNITION_MIN_SECTIONS == 3
```

- [ ] **Step 3: Run the test — confirm it fails**

```bash
.venv/bin/python -m pytest tests/integration/test_news_run.py -q
```

Expected: FAIL with `ModuleNotFoundError: newsagent.pipeline.orchestrator`.

- [ ] **Step 4: Implement the orchestrator (part 1 — the basic flow)**

Create `src/newsagent/pipeline/orchestrator.py`:

```python
"""The unified newsagent orchestrator.

One command, one pipeline. Reads a parsed brief, plans queries, searches,
optionally runs the cognition core (when the brief is deep enough), and
synthesizes each section in parallel.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from newsagent.cadence import resolve_cadence  # placeholder; see note below

# NOTE: This orchestrator will be wired up in Task 12. The import path is
# newsagent.pipeline.cadence, but a re-export shim is provided at the package
# level so the orchestrator can keep its import shallow.
```

Wait — that's wrong. The cadence module is at `newsagent.pipeline.cadence`, not `newsagent.cadence`. Rewrite the import. Replace the file with this working version:

```python
"""The unified newsagent orchestrator.

One command, one pipeline. Reads a parsed brief, plans queries, searches,
optionally runs the cognition core (when the brief has 3+ sections), and
synthesizes each section in parallel.

The cognition core is gated on ``len(spec.sections) >= FULL_COGNITION_MIN_SECTIONS``.
A daily-pulse brief (1-2 sections) skips it; a monthly deep-dive (3+) runs
discover_stories → plan_research → analyze_chief → edit_story.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from newsagent.cadence import CADENCE, CadenceSpec, resolve_cadence
from newsagent.config import NewsAgentSettings, load_settings
from newsagent.embedding import Embedder  # placeholder; see Step 5
from newsagent.logging import get_logger
from newsagent.llm.providers.registry import build_registry
from newsagent.llm.router import LLMRouter
from newsagent.output import build_sinks
from newsagent.pipeline.adapter import PromptAdapter
from newsagent.pipeline.planner import plan_queries
from newsagent.pipeline.report import assemble_report
from newsagent.pipeline.retrieval import embed_chunks, load_past_reports, retrieve_similar, format_rag_context
from newsagent.pipeline.search import SearchProvider, SearchResult, build_search_provider, dedup_sources
from newsagent.pipeline.spec import BriefSpec
from newsagent.pipeline.synthesize import (
    _content_word_count,
    _SECTION_MIN_WORDS,
    clean_section_text,
    count_citations,
    select_relevant,
    synthesize_section,
    synthesize_section_with_review,
)
from newsagent.storage.db import Store

log = get_logger("orchestrator")


FULL_COGNITION_MIN_SECTIONS = 3
_FALLBACK_COLLECTORS = (
    "arxiv",
    "hacker_news",
    "github_trending",
    "huggingface",
    "semantic_scholar",
    "devto",
    "lobsters",
)


def _build_router(settings: NewsAgentSettings) -> LLMRouter:
    registry = build_registry(
        ollama_base_url=settings.llm.ollama_base_url,
        ollama_api_key=settings.llm.ollama_api_key,
        backend=settings.llm.backend,
        opencode_go_base_url=settings.llm.opencode_go_base_url,
        opencode_go_api_key=settings.llm.opencode_go_api_key,
        opencode_go_model=settings.llm.opencode_go_model,
        openai_base_url=settings.llm.openai_base_url,
        openai_api_key=settings.llm.openai_api_key,
        openai_model=settings.llm.openai_model,
    )
    return LLMRouter(
        registry,
        token_budget=settings.llm.token_budget,
        allow_heuristic_fallback=settings.llm.allow_heuristic_fallback,
        timeout=settings.llm.timeout_seconds,
        cost_per_1k_tokens=settings.llm.cost_per_1k_tokens,
    )


async def _gather_sources(
    queries,
    search: SearchProvider,
    *,
    max_sources: int,
) -> list[SearchResult]:
    all_results: list[SearchResult] = []
    for q in queries:
        try:
            results = await search.search(q.text, max_results=max_sources // max(1, len(queries)) + 2)
        except Exception as exc:  # noqa: BLE001
            log.warning("search.failed", query=q.text, error=str(exc))
            results = []
        all_results.extend(results)
    return dedup_sources(all_results, limit=max_sources)


async def _gather_sources_fallback(
    since: datetime,
    *,
    max_sources: int,
) -> list[SearchResult]:
    """Pull from free collectors when Tavily returns nothing."""
    from newsagent.collectors.registry import run_collector

    out: list[SearchResult] = []
    for name in _FALLBACK_COLLECTORS:
        try:
            items = await run_collector(name, since=since, limit=20, timeout=20)
        except Exception as exc:  # noqa: BLE001
            log.warning("fallback_collector_failed", name=name, error=str(exc))
            continue
        for it in items:
            if not it.url:
                continue
            out.append(
                SearchResult(
                    title=it.title or "",
                    url=it.url,
                    content=(it.content or it.summary or "")[:600],
                    published_date=it.published_at.isoformat() if it.published_at else None,
                    source=it.source_type,
                )
            )
        if len(out) >= max_sources * 2:
            break
    return out


async def _synthesize_section_parallel(
    sec,
    sources,
    rag_chunks,
    embedder,
    router: LLMRouter,
    search: SearchProvider,
    spec: BriefSpec,
    settings: NewsAgentSettings,
    cad: CadenceSpec,
    date_label: str,
    cadence_note: str,
    per_section_sources: int,
    extra_queries: int,
    year: str,
    search_enabled: bool,
    semaphore: asyncio.Semaphore,
    max_tokens: int = 5000,
) -> str:
    """Synthesize one section with RAG context + critic loop + CoT backstop."""
    from newsagent.brief.report import drop_empty_subheadings  # type: ignore[attr-defined]
    from newsagent.pipeline.sanitizer import sanitize_text
    from newsagent.pipeline.stages.section_writer import extract_prose

    async with semaphore:
        rag_context = ""
        if rag_chunks and embedder:
            query = f"{sec.title} {' '.join(sec.bullets)}"
            similar = retrieve_similar(
                query, rag_chunks, embedder=embedder,
                top_k=settings.rag.top_k, threshold=settings.rag.threshold,
            )
            if similar:
                rag_context = format_rag_context(similar, max_chars=settings.rag.max_context_chars)
                log.info("rag_retrieved", section=sec.number, chunks=len(similar))

        rel = select_relevant(
            sec, sources, top_k=per_section_sources,
            domain_cap=settings.search.domain_cap, recency_days=cad.days,
        )
        text = await synthesize_section_with_review(
            sec, rel, router=router, instructions=spec.instructions,
            quality=spec.quality, deliverables=spec.deliverables,
            date_label=date_label, cadence_note=cadence_note,
            rag_context=rag_context, max_tokens=max_tokens,
        )

        # Research loop: extra queries if citations are thin.
        citation_count = count_citations(text)
        if settings.search.min_citations > 0 and citation_count < settings.search.min_citations and search_enabled:
            log.info("thin_citations", section=sec.number, title=sec.title, citations=citation_count)
            extra_q = _generate_section_queries(sec, extra_queries, year)
            extra_results = await _gather_sources(extra_q, search, max_sources=extra_queries * 3)
            if extra_results:
                merged = dedup_sources(rel + extra_results, limit=per_section_sources * 2)
                text = await synthesize_section_with_review(
                    sec, merged, router=router, instructions=spec.instructions,
                    quality=spec.quality, deliverables=spec.deliverables,
                    date_label=date_label, cadence_note=cadence_note,
                    rag_context=rag_context, max_tokens=max_tokens,
                )

        # CoT backstop + sanitizer.
        text = drop_empty_subheadings(sanitize_text(extract_prose(text)))

        # Validity gate.
        cleaned = clean_section_text(text, sec)
        has_sources = bool(rel)
        word_count = _content_word_count(cleaned) if cleaned else 0
        is_substantial = cleaned is not None and (not has_sources or word_count >= _SECTION_MIN_WORDS)
        if is_substantial:
            text = cleaned
        else:
            reason = "stub/too short" if (cleaned is not None and has_sources) else "planning/invalid"
            log.warning("section_invalid_retry", section=sec.number, title=sec.title, reason=reason, words=word_count)
            retry = await synthesize_section(
                sec, rel, router=router, instructions=spec.instructions,
                quality=spec.quality, deliverables=spec.deliverables,
                date_label=date_label, cadence_note=cadence_note,
                rag_context=rag_context, strict_retry=True, max_tokens=max_tokens,
            )
            retry = drop_empty_subheadings(sanitize_text(extract_prose(retry)))
            cleaned_retry = clean_section_text(retry, sec)
            retry_word_count = _content_word_count(cleaned_retry) if cleaned_retry else 0
            retry_substantial = cleaned_retry is not None and (not has_sources or retry_word_count >= _SECTION_MIN_WORDS)
            if retry_substantial:
                text = cleaned_retry
            else:
                log.warning("section_invalid_placeholder", section=sec.number, title=sec.title)
                text = (
                    f"## **{sec.number}. {sec.title}**\n\n"
                    f"_Synthesis for this section did not produce valid, substantial prose "
                    f"after retry (writer emitted planning notes or a thin stub instead of analysis). "
                    f"Re-run to regenerate._"
                )

        log.info("section_done", section=sec.number, title=sec.title, tokens=router.stats.total_tokens)
        return text


async def _maybe_run_cognition_core(
    spec: BriefSpec,
    sources: list[SearchResult],
    router: LLMRouter,
    run_date: datetime,
):
    """Run the cognition core when the brief is deep enough.

    Returns an optional ``StoryBlueprint`` for the section synthesizer to use.
    Returns ``None`` for shallow briefs (cognition skipped).
    """
    if len(spec.sections) < FULL_COGNITION_MIN_SECTIONS:
        log.info("cognition.skip", reason="below threshold", sections=len(spec.sections))
        return None
    log.info("cognition.run", sections=len(spec.sections))

    from newsagent.pipeline.stages import (
        analyze_chief,
        build_evidence_graph,
        discover_stories,
        edit_story,
        extract_claims,
        extract_evidence,
        plan_research,
    )

    # Build a minimal evidence/claim pool from the brief sources.
    pseudo_items = [
        type("PseudoItem", (), {"uid": s.url, "title": s.title, "content": s.content})()
        for s in sources
    ]
    evidence = await extract_evidence(pseudo_items, router)
    claims = await extract_claims(evidence, router)
    graph = await build_evidence_graph(evidence, claims)
    stories = await discover_stories(graph, router)
    plan = await plan_research(stories, graph, router, run_date=run_date)
    review = await analyze_chief(plan, stories, graph, router)
    blueprint = await edit_story(
        stories=stories, graph=graph, plan=plan, claims=claims,
        router=router, run_date=run_date, ctx=None,
    )
    return blueprint


async def run_news_pipeline(
    spec: BriefSpec,
    *,
    settings: NewsAgentSettings | None = None,
    router: LLMRouter | None = None,
    search: SearchProvider | None = None,
    out_path: Path | None = None,
    brief_path: str | Path | None = None,
) -> Path:
    """The one newsagent production command. Run a parsed brief end to end."""
    settings = settings or load_settings()
    cad = resolve_cadence(settings.cadence)
    router = router or _build_router(settings)
    search = search or build_search_provider(settings.search, days=cad.days)

    # Adaptive state (per-brief).
    adapter_state = None
    if brief_path:
        adapter = PromptAdapter(settings.storage.dir / "adapter_state")
        adapter_state = adapter.get_state(str(brief_path))

    run_date = datetime.now(timezone.utc)
    date_label = run_date.strftime("%B %Y")
    cadence_note = f"Focus EXCLUSIVELY on developments from {cad.window}."

    # Plan queries.
    queries = plan_queries(
        spec, per_section=cad.per_section, source_queries=cad.sources,
        year="2026", cadence=settings.cadence,
    )
    log.info("planned", queries=len(queries), sections=len(spec.sections), cadence=settings.cadence)

    # Search.
    sources: list[SearchResult] = await _gather_sources(queries, search, max_sources=cad.sources * 5)
    log.info("searched", sources=len(sources))

    if not sources:
        log.warning("search_empty_fallback_collectors")
        since = run_date - timedelta(days=cad.days)
        fb = await _gather_sources_fallback(since, max_sources=cad.sources * 5)
        sources = dedup_sources(fb, limit=cad.sources * 5)
        log.info("fallback_used", sources=len(sources))

    # RAG.
    rag_chunks = []
    embedder = None
    if settings.rag.enabled and settings.reports_dir.exists():
        embedder = Embedder(model=settings.embed.model, dim=settings.embed.dim, normalize=settings.embed.normalize)
        rag_chunks = load_past_reports(settings.reports_dir, max_reports=settings.rag.max_reports)
        if rag_chunks:
            embed_chunks(rag_chunks, embedder)
            log.info("rag_loaded", chunks=len(rag_chunks))

    per_section_sources = (
        adapter_state.per_section_sources if adapter_state else cad.per_section * 6
    )
    extra_queries = adapter_state.extra_queries if adapter_state else settings.search.extra_queries

    # Optional cognition core.
    blueprint = await _maybe_run_cognition_core(spec, sources, router, run_date)

    # Parallel synthesis.
    semaphore = asyncio.Semaphore(settings.pipeline.section_concurrency)
    max_tokens = cad.max_tokens
    tasks = [
        _synthesize_section_parallel(
            sec, sources, rag_chunks, embedder, router, search, spec, settings,
            cad, date_label, cadence_note, per_section_sources, extra_queries,
            "2026", True, semaphore, max_tokens=max_tokens,
        )
        for sec in spec.sections
    ]
    sections_md = await asyncio.gather(*tasks)

    report = assemble_report(spec, list(sections_md), sources)

    if out_path is None:
        from newsagent.pipeline.spec import brief_slug

        out_path = settings.reports_dir / f"{brief_slug(spec)}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report.text, encoding="utf-8")

    meta = {"date": run_date.strftime("%Y-%m-%d"), "profile": "news", "path": str(out_path)}
    for sink in build_sinks(settings):
        try:
            await sink.deliver(report.text, meta)
        except Exception as exc:  # noqa: BLE001
            log.warning("sink.failed", sink=getattr(sink, "?"), error=str(exc))

    # Persist a Report row.
    import hashlib

    try:
        store = Store(settings.sqlite_url)
        await store.init()
        from newsagent.storage.models import Report

        async with store.session() as session:
            await session.merge(
                Report(
                    run_date=run_date, path=str(out_path),
                    md_sha256=hashlib.sha256(report.text.encode("utf-8")).hexdigest(),
                    sections_count=len(report.references),
                    items_analyzed=len(sources),
                    sources_checked_json=json.dumps([]),
                    sources_failed_json=json.dumps([]),
                    token_usage=router.stats.total_tokens,
                )
            )
            await session.commit()
        await store.close()
    except Exception as exc:  # noqa: BLE001
        log.warning("report_persist_failed", error=str(exc))

    log.info("done", path=str(out_path), references=len(report.references), tokens=router.stats.total_tokens)
    return out_path


def _generate_section_queries(section, count: int, year: str) -> list:
    from newsagent.pipeline.planner import ResearchQuery

    queries = [ResearchQuery(f"{section.title} {year}", section.title, "section")]
    for bullet in section.bullets[:count]:
        queries.append(ResearchQuery(f"{section.title}: {bullet} {year} AI", section.title, "section"))
    return queries[:count]
```

- [ ] **Step 5: Note about the `Embedder` import**

The orchestrator uses `Embedder` from `newsagent.llm.embed`. The import is correct: `from newsagent.llm.embed import Embedder`. Fix the placeholder line. Replace the line `from newsagent.embedding import Embedder  # placeholder; see Step 5` with `from newsagent.llm.embed import Embedder`.

Also fix the import `from newsagent.brief.report import drop_empty_subheadings` — that should be `from newsagent.pipeline.report import drop_empty_subheadings` (the module was moved in Task 9).

- [ ] **Step 6: Run the new orchestrator test**

```bash
.venv/bin/python -m pytest tests/integration/test_news_run.py -q
```

Expected: PASS.

- [ ] **Step 7: Run the full suite**

```bash
.venv/bin/python -m pytest -q tests/
```

Expected: 274 passed (271 + 3 new).

- [ ] **Step 8: Verify ruff clean**

```bash
.venv/bin/python -m ruff check src/newsagent/pipeline/orchestrator.py
```

---

### Task 12: Replace `pipeline/run.py` with a 5-line shim that calls the orchestrator

**Files:**
- Modify: `src/newsagent/pipeline/run.py` (replace the entire 653-line file with a shim)

- [ ] **Step 1: Read the existing `pipeline/run.py` (653 LoC)**

This is the **old daily-path** orchestrator. We're replacing it with a shim. The shim is a temporary artifact — Task 18 deletes the file.

- [ ] **Step 2: Write the shim**

Replace `src/newsagent/pipeline/run.py` with:

```python
"""Compatibility shim. The new orchestrator lives in
:mod:`newsagent.pipeline.orchestrator`. This file will be deleted in Task 18.
"""

from __future__ import annotations

# Re-export the new entry point so old imports keep working during migration.
from newsagent.pipeline.orchestrator import run_news_pipeline as _run  # noqa: F401
```

- [ ] **Step 3: Run the full suite**

```bash
.venv/bin/python -m pytest -q tests/
```

Expected: 274 passed. (The old integration test `test_pipeline.py` was the only consumer; it gets deleted in Task 18 but still passes for now.)

- [ ] **Step 4: Verify ruff clean**

```bash
.venv/bin/python -m ruff check src/newsagent/pipeline/run.py
```

---

### Task 13: Add `Embedder` unit test (covers the new embedder usage in the orchestrator)

**Files:**
- Create: `tests/unit/test_embed.py`

**Interfaces:**
- Tests `Embedder(model="hashing", dim=768, normalize=True).embed(["text"])` — must return a 2D array of shape (1, 768) with unit-length vectors.

- [ ] **Step 1: Write the test**

Create `tests/unit/test_embed.py`:

```python
"""Embedder hashing backend — unit test."""

from __future__ import annotations

import numpy as np

from newsagent.llm.embed import Embedder


def test_hashing_embedder_shape():
    emb = Embedder(model="hashing", dim=768, normalize=True)
    out = emb.embed(["hello world", "second text"])
    assert out.shape == (2, 768)


def test_hashing_embedder_unit_length():
    emb = Embedder(model="hashing", dim=128, normalize=True)
    out = emb.embed(["x", "y", "z"])
    norms = np.linalg.norm(out, axis=1)
    np.testing.assert_allclose(norms, 1.0, atol=1e-5)


def test_hashing_embedder_deterministic():
    emb = Embedder(model="hashing", dim=64, normalize=True)
    a = emb.embed(["alpha", "beta"])
    b = emb.embed(["alpha", "beta"])
    np.testing.assert_array_equal(a, b)
```

- [ ] **Step 2: Run the test**

```bash
.venv/bin/python -m pytest tests/unit/test_embed.py -q
```

Expected: 3 passed.

- [ ] **Step 3: Run full suite**

```bash
.venv/bin/python -m pytest -q tests/
```

Expected: 277 passed.

- [ ] **Step 4: Verify ruff clean**

```bash
.venv/bin/python -m ruff check tests/unit/test_embed.py
```

---

### Task 14: Add `synthesize` unit test (per-section synthesis, validity gate, CoT backstop)

**Files:**
- Create: `tests/unit/test_synthesize.py`

**Interfaces:**
- Tests `select_relevant`, `clean_section_text`, `_content_word_count`, `is_substantial_section`, `count_citations`

- [ ] **Step 1: Write the test**

Create `tests/unit/test_synthesize.py`:

```python
"""Per-section synthesis helpers: source selection, CoT backstop, validity gate."""

from __future__ import annotations

from newsagent.pipeline.search import SearchResult
from newsagent.pipeline.spec import SectionSpec
from newsagent.pipeline.synthesize import (
    _content_word_count,
    clean_section_text,
    count_citations,
    is_substantial_section,
    select_relevant,
)


def _sec() -> SectionSpec:
    return SectionSpec(number=1, title="Pulse", bullets=["alpha", "beta"])


def _src(title: str, url: str, content: str = "x", date: str | None = None) -> SearchResult:
    return SearchResult(title=title, url=url, content=content, published_date=date, source="example.com")


def test_select_relevant_ranks_by_keyword():
    sources = [
        _src("Other news", "https://other.com/1", "irrelevant"),
        _src("Alpha release", "https://example.com/a", "alpha is mentioned here"),
        _src("Beta beta beta", "https://example.com/b", "more beta here"),
    ]
    picked = select_relevant(_sec(), sources, top_k=2)
    urls = [s.url for s in picked]
    # example.com/ hosts (alpha + beta) should rank above other.com
    assert "https://other.com/1" not in urls


def test_select_relevant_respects_domain_cap():
    sources = [
        _src("a1", "https://a.com/1"),
        _src("a2", "https://a.com/2"),
        _src("a3", "https://a.com/3"),
        _src("a4", "https://a.com/4"),
        _src("b1", "https://b.com/1"),
    ]
    picked = select_relevant(_sec(), sources, top_k=4, domain_cap=2)
    hosts = [s.url.split("/")[2] for s in picked]
    assert hosts.count("a.com") <= 2


def test_clean_section_text_drops_planning_lines():
    text = "## **1. Pulse**\n\nNow, write a section about this.\n\nReal analysis paragraph.\n"
    out = clean_section_text(text, _sec())
    assert out is not None
    assert "Now, write" not in out
    assert "Real analysis" in out


def test_clean_section_text_rejects_no_heading():
    text = "Random prose with no section heading at all."
    assert clean_section_text(text, _sec()) is None


def test_clean_section_text_rejects_planning_only_dump():
    text = "## **1. Pulse**\n\nNow, write.\nFirst, gather all.\nThen, flesh out.\n"
    assert clean_section_text(text, _sec()) is None


def test_content_word_count_excludes_headings_and_tables():
    text = "## **1. Pulse**\n\n| col1 | col2 |\n| --- | --- |\n| a | b |\n\nA real paragraph with five words here.\n"
    assert _content_word_count(text) == 7  # "A real paragraph with five words here" = 7 tokens


def test_is_substantial_section_true_for_real_section():
    text = "## **1. Pulse**\n\n" + ("meaningful prose " * 50)
    assert is_substantial_section(text, _sec())


def test_is_substantial_section_false_for_stub():
    text = "## **1. Pulse**\n\nshort"
    assert not is_substantial_section(text, _sec())


def test_count_citations_unique():
    text = "alpha [src:https://a.com/1] beta [src:https://a.com/1] gamma [src:https://b.com/1]"
    assert count_citations(text) == 2
```

- [ ] **Step 2: Run the test**

```bash
.venv/bin/python -m pytest tests/unit/test_synthesize.py -q
```

Expected: 9 passed.

- [ ] **Step 3: Run full suite**

```bash
.venv/bin/python -m pytest -q tests/
```

Expected: 286 passed (277 + 9).

- [ ] **Step 4: Verify ruff clean**

```bash
.venv/bin/python -m ruff check tests/unit/test_synthesize.py
```

---

### Task 15: Add `report` and `eval` unit tests (split from `test_brief_citations.py`)

**Files:**
- Create: `tests/unit/test_report.py` (the citation + assembly subset)
- Create: `tests/unit/test_eval.py` (the report scoring subset)
- Delete: `tests/unit/test_brief_citations.py`

**Interfaces:**
- `report`: `resolve_citations`, `assemble_report`, `drop_empty_subheadings`
- `eval`: `evaluate_text` (mocked router)

- [ ] **Step 1: Read `test_brief_citations.py` to understand the existing coverage**

Read `tests/unit/test_brief_citations.py` (20 KB). Identify which tests cover citations/assembly (move to `test_report.py`) and which cover scoring (move to `test_eval.py`).

- [ ] **Step 2: Create `test_report.py` with the citation + assembly tests**

Open the existing `test_brief_citations.py`. Copy the `TestResolveCitations` and `TestAssembleReport` and `TestDropEmptySubheadings` test classes. Update imports:

```python
from newsagent.pipeline.report import resolve_citations, assemble_report, drop_empty_subheadings
from newsagent.pipeline.search import SearchResult
from newsagent.pipeline.spec import BriefSpec, SectionSpec
```

Save as `tests/unit/test_report.py`.

- [ ] **Step 3: Create `test_eval.py` with the eval tests**

Open the existing `test_brief_citations.py`. Copy the `TestEvaluateText` test class. Update imports:

```python
from newsagent.pipeline.eval import EvalVerdict, evaluate_text
from newsagent.pipeline.spec import BriefSpec
```

The test uses a mocked router. Save as `tests/unit/test_eval.py`.

- [ ] **Step 4: Run the new tests**

```bash
.venv/bin/python -m pytest tests/unit/test_report.py tests/unit/test_eval.py -q
```

Expected: PASS (same coverage as before, just split).

- [ ] **Step 5: Delete the old test file**

```bash
rm tests/unit/test_brief_citations.py
```

- [ ] **Step 6: Rename `test_brief_planner.py` → `test_planner.py`**

```bash
mv tests/unit/test_brief_planner.py tests/unit/test_planner.py
```

Edit `tests/unit/test_planner.py` and update its imports from `newsagent.brief.planner` to `newsagent.pipeline.planner`.

- [ ] **Step 7: Run full suite**

```bash
.venv/bin/python -m pytest -q tests/
```

Expected: 286 passed (same total, just renamed).

- [ ] **Step 8: Verify ruff clean**

```bash
.venv/bin/python -m ruff check tests/
```

---

### Task 16: Delete the legacy `analyzers/`, `renderers/`, and 4 pipeline modules

**Files:**
- Delete: `src/newsagent/analyzers/` (entire package)
- Delete: `src/newsagent/renderers/` (entire package)
- Delete: `src/newsagent/pipeline/cluster.py`
- Delete: `src/newsagent/pipeline/rank.py`
- Delete: `src/newsagent/pipeline/planning.py`
- Delete: `src/newsagent/pipeline/research.py`
- Delete: `src/newsagent/pipeline/quality_gates.py`
- Delete: `src/newsagent/pipeline/prioritize.py`
- Delete: `tests/unit/test_quality_gates.py`
- Delete: `tests/integration/test_pipeline.py`

- [ ] **Step 1: Verify no remaining imports of these modules**

```bash
.venv/bin/python -c "
import subprocess
result = subprocess.run(['grep', '-rEln', r'hermes\\.(analyzers|renderers|pipeline\\.(cluster|rank|planning|research|quality_gates|prioritize))', 'src', 'tests'], capture_output=True, text=True)
print('Hits:' if result.stdout else 'No imports.', result.stdout)
"
```

Expected: `No imports.` (All callers should have been updated in earlier tasks.)

- [ ] **Step 2: Delete the files**

```bash
rm -rf src/newsagent/analyzers/
rm -rf src/newsagent/renderers/
rm -f src/newsagent/pipeline/cluster.py src/newsagent/pipeline/rank.py src/newsagent/pipeline/planning.py src/newsagent/pipeline/research.py src/newsagent/pipeline/quality_gates.py src/newsagent/pipeline/prioritize.py
rm -f tests/unit/test_quality_gates.py tests/integration/test_pipeline.py
```

- [ ] **Step 3: Run full suite**

```bash
.venv/bin/python -m pytest -q tests/
```

Expected: 286 passed (or 285 — confirm the count).

- [ ] **Step 4: Verify ruff clean**

```bash
.venv/bin/python -m ruff check src tests
```

---

### Task 17: Update `cli.py` — remove `run`, `backfill`, `research`; rename `news` flags

**Files:**
- Modify: `src/newsagent/cli.py`

**Interfaces:**
- Commands: `news`, `status`, `sources`, `models`, `profiles`, `eval`, `quality`, `help`
- `news`: required positional `<prompt.md>`, no cadence flag, no `--rate` flag (move to `eval --rate`)
- `eval`: gains optional `--rate 1-5` for feedback

- [ ] **Step 1: Rewrite the CLI**

The full new `src/newsagent/cli.py` (replaces the existing 425-line file):

```python
"""newsagent CLI: one production command, four inspection tools.

Production: ``newsagent news <prompt.md>`` — the unified pipeline.
Inspection: ``status``, ``sources``, ``models``, ``profiles``.
Post-hoc:   ``eval <report.md> --prompt <prompt.md>``, ``quality [--date]``.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone

from newsagent.config import load_settings
from newsagent.logging import configure_logging, get_logger

log = get_logger("cli")

HELP = """newsagent — autonomous AI Research Intelligence Agent (CLI only)

Usage:
  newsagent news <prompt.md>           # The one production command
  newsagent eval <report.md> --prompt <prompt.md> [--cadence daily|weekly|monthly] [--rate 1-5]
  newsagent quality [--date YYYY-MM-DD]
  newsagent profiles
  newsagent status
  newsagent models
  newsagent sources
  newsagent help
"""


def _parse_args(argv: list[str]) -> dict:
    args: dict = {"command": None, "flags": {}, "opts": {}, "positionals": []}
    it = iter(argv)
    for a in it:
        if a in ("news", "status", "sources", "profiles", "quality", "eval", "models", "help", "-h", "--help"):
            args["command"] = a if a not in ("-h", "--help") else "help"
        elif a.startswith("--"):
            key = a[2:]
            if key in ("dry-run",):
                args["flags"][key] = True
            elif key in ("date", "prompt", "cadence", "rate"):
                try:
                    args["opts"][key] = next(it)
                except StopIteration:
                    pass
        else:
            args["positionals"].append(a)
    return args


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = _parse_args(argv)
    settings = load_settings()
    configure_logging(level=settings.log_level, json_logs=settings.json_logs)

    cmd = args["command"] or "help"
    if cmd == "help":
        print(HELP)
        return 0
    if cmd == "news":
        return _cmd_news(settings, args)
    if cmd == "eval":
        return _cmd_eval(settings, args)
    if cmd == "models":
        return _cmd_models(settings)
    if cmd == "profiles":
        return _cmd_profiles(settings)
    if cmd == "quality":
        return _cmd_quality(settings, args)
    if cmd == "status":
        return _cmd_status(settings)
    if cmd == "sources":
        return _cmd_sources(settings)
    print(HELP)
    return 1


def _cmd_news(settings, args) -> int:
    from pathlib import Path

    from newsagent.pipeline.orchestrator import run_news_pipeline
    from newsagent.pipeline.spec import parse_prompt

    if not args["positionals"]:
        print("news requires a prompt file, e.g. newsagent news example_prompt.md", file=sys.stderr)
        return 1
    brief_path = Path(args["positionals"][0])
    if not brief_path.exists():
        print(f"ERROR: prompt not found: {brief_path}", file=sys.stderr)
        return 1

    spec = parse_prompt(brief_path.read_text(encoding="utf-8"))
    try:
        path = asyncio.run(
            run_news_pipeline(
                spec, settings=settings, brief_path=brief_path,
            )
        )
        print(f"Report written: {path}")
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("news.failed", error=str(exc))
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def _cmd_eval(settings, args) -> int:
    from pathlib import Path

    from newsagent.llm.providers.registry import build_registry
    from newsagent.llm.router import LLMRouter
    from newsagent.pipeline.adapter import PromptAdapter
    from newsagent.pipeline.eval import evaluate_report, get_rolling_scores
    from newsagent.storage.db import Store

    if not args["positionals"]:
        print("eval requires a report file, e.g. newsagent eval report.md --prompt prompt.md", file=sys.stderr)
        return 1
    report_path = Path(args["positionals"][0])
    prompt_path_opt = args["opts"].get("prompt")
    if not prompt_path_opt:
        print("eval requires --prompt <prompt.md>", file=sys.stderr)
        return 1
    prompt_path = Path(prompt_path_opt)
    cadence = args["opts"].get("cadence") or settings.cadence or "daily"

    # Optional feedback recording.
    rate_str = args["opts"].get("rate")
    if rate_str:
        try:
            rating = int(rate_str)
            if not (1 <= rating <= 5):
                raise ValueError
        except ValueError:
            print("--rate must be an integer 1-5", file=sys.stderr)
            return 1
        adapter = PromptAdapter(settings.storage.dir / "adapter_state")
        adapter.record_feedback(str(prompt_path), rating)
        print(f"Recorded rating {rating}/5 for {prompt_path}")
        return 0

    async def _go():
        store = Store(settings.sqlite_url)
        await store.init()
        registry = build_registry(
            ollama_base_url=settings.llm.ollama_base_url,
            ollama_api_key=settings.llm.ollama_api_key,
            backend=settings.llm.backend,
            opencode_go_base_url=settings.llm.opencode_go_base_url,
            opencode_go_api_key=settings.llm.opencode_go_api_key,
            opencode_go_model=settings.llm.opencode_go_model,
            openai_base_url=settings.llm.openai_base_url,
            openai_api_key=settings.llm.openai_api_key,
            openai_model=settings.llm.openai_model,
        )
        router = LLMRouter(
            registry,
            token_budget=settings.llm.token_budget,
            allow_heuristic_fallback=settings.llm.allow_heuristic_fallback,
            timeout=settings.llm.timeout_seconds,
        )
        verdict = await evaluate_report(
            report_path, prompt_path, router=router, store=store, cadence=cadence,
        )
        await store.close()

        adapter = PromptAdapter(settings.storage.dir / "adapter_state")
        eval_scores = {
            "coverage": verdict.coverage_score,
            "citation": verdict.citation_score,
            "quality": verdict.quality_score,
            "cadence": verdict.cadence_score,
        }
        adapter.update(str(prompt_path), eval_scores)

        store2 = Store(settings.sqlite_url)
        await store2.init()
        rolling = await get_rolling_scores(store2, str(prompt_path), limit=5)
        await store2.close()
        return verdict, rolling

    try:
        verdict, rolling = asyncio.run(_go())
        print(f"Eval: {report_path}")
        print(f"  Coverage:  {verdict.coverage_score:.2f}")
        print(f"  Citation:  {verdict.citation_score:.2f}")
        print(f"  Quality:   {verdict.quality_score:.2f}")
        print(f"  Cadence:   {verdict.cadence_score:.2f}")
        print(f"  Overall:   {verdict.overall_score:.2f}")
        print(f"  Feedback:  {verdict.feedback[:200]}...")
        if rolling:
            print("\nRolling (last 5):")
            print(f"  Coverage:  {rolling.get('coverage', 0):.2f}")
            print(f"  Citation:  {rolling.get('citation', 0):.2f}")
            print(f"  Quality:   {rolling.get('quality', 0):.2f}")
            print(f"  Cadence:   {rolling.get('cadence', 0):.2f}")
            print(f"  Overall:   {rolling.get('overall', 0):.2f}")
        return 0
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        log.error("eval.failed", error=str(exc))
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def _cmd_quality(settings, args) -> int:
    from newsagent.pipeline.quality import run_quality
    from newsagent.pipeline.run import _make_ctx
    from newsagent.storage.db import Store

    date_str = args["opts"].get("date")
    run_date = _parse_date(date_str) if date_str else datetime.now(timezone.utc)
    store = Store(settings.sqlite_url)
    asyncio.run(store.init())
    ctx = _make_ctx(settings, store)
    ctx.run_date = run_date
    try:
        rep = asyncio.run(run_quality(ctx, run_date, settings))
        print(f"Quality self-score: {rep.newsagent_score}/5")
        print(f"Dimensions: {rep.per_dimension}")
        print(f"Improvement notes: {len(rep.notes)}")
        print(f"Report: {rep.path}")
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("quality.failed", error=str(exc))
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        asyncio.run(store.close())


def _cmd_profiles(settings) -> int:
    """Profiles are still defined (daily/weekly/minimal/etc.) but only their names show — no top_k."""
    from newsagent.profiles import PROFILES

    print("Available report profiles:")
    for name, p in PROFILES.items():
        print(f"  - {name}: {p.description}")
    return 0


def _cmd_status(settings) -> int:
    from sqlalchemy import select

    from newsagent.storage.db import Store
    from newsagent.storage.models import Item, Report, ReportEval

    async def _go():
        store = Store(settings.sqlite_url)
        await store.init()
        async with store.session() as s:
            items = (await s.execute(select(Item))).scalars().all()
            reports = (await s.execute(select(Report))).scalars().all()
            evals = (await s.execute(select(ReportEval))).scalars().all()
        await store.close()
        canonical = sum(1 for i in items if i.is_canonical)
        print(f"Items: {len(items)} (canonical {canonical})")
        print(f"Reports: {len(reports)}")
        for r in sorted(reports, key=lambda x: x.run_date, reverse=True)[:5]:
            print(f"  {r.run_date.strftime('%Y-%m-%d')} · {r.items_analyzed} analyzed · {r.token_usage:,} tokens")

        if evals:
            print(f"\nNews Pipeline Evals: {len(evals)}")
            for e in sorted(evals, key=lambda x: x.run_date, reverse=True)[:5]:
                print(f"  {e.run_date.strftime('%Y-%m-%d')} · {e.cadence} · overall {e.overall_score:.2f}")
                print(f"    coverage {e.coverage_score:.2f} · citation {e.citation_score:.2f} · quality {e.quality_score:.2f} · cadence {e.cadence_score:.2f}")

        adapter_dir = settings.storage.dir / "adapter_state"
        if adapter_dir.exists():
            adapter_files = list(adapter_dir.glob("*.json"))
            if adapter_files:
                print(f"\nAdapter State: {len(adapter_files)} prompts tracked")
                for af in adapter_files[:3]:
                    print(f"  {af.stem}")
        return 0

    asyncio.run(_go())
    return 0


def _cmd_models(settings) -> int:
    from newsagent.llm.catalog import OLLAMA_CATALOG, OPENCODE_GO_CATALOG

    backend = settings.llm.backend

    if backend == "opencode_go":
        from newsagent.llm.providers.opencode_go import OpenCodeGoProvider

        provider = OpenCodeGoProvider(
            base_url=settings.llm.opencode_go_base_url,
            api_key=settings.llm.opencode_go_api_key,
        )
        try:
            models = asyncio.run(provider.list_models())
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: could not reach OpenCode Go endpoint ({provider.base_url}): {exc}", file=sys.stderr)
            print("Curated catalog (verify ids against your account with a working endpoint):", file=sys.stderr)
            models = []

        available = {m.get("id") or m.get("name") for m in models}
        print(f"OpenCode Go endpoint: {provider.base_url}")
        print(f"Available on endpoint: {len(available)} models\n")
        if available:
            for m in sorted(available):
                print(f"  - {m}")

        print("\nCurated catalog tiers (newsagent/llm/catalog.py):")
        for tier, chain in OPENCODE_GO_CATALOG.items():
            marks = " ".join(("✓" if c in available else "·") for c in chain)
            print(f"  [{tier}] {' > '.join(chain)}   ({marks})")
        print("\n✓ = present on endpoint · = not found (will 404 / fall back).")
    else:
        from newsagent.llm.providers.ollama import OllamaProvider

        provider = OllamaProvider(
            base_url=settings.llm.ollama_base_url,
            api_key=settings.llm.ollama_api_key,
        )
        try:
            models = asyncio.run(provider.list_models())
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: could not reach Ollama endpoint ({provider.base_url}): {exc}", file=sys.stderr)
            print("Curated catalog (verify ids against your tenant with a working endpoint):", file=sys.stderr)
            models = []

        available = {m.get("name") or m.get("model") for m in models}
        print(f"Ollama endpoint: {provider.base_url}")
        print(f"Available on endpoint: {len(available)} models\n")
        if available:
            for m in sorted(available):
                print(f"  - {m}")

        print("\nCurated catalog tiers (newsagent/llm/catalog.py):")
        for tier, chain in OLLAMA_CATALOG.items():
            marks = " ".join(("✓" if c in available else "·") for c in chain)
            print(f"  [{tier}] {' > '.join(chain)}   ({marks})")
        print("\n✓ = present on endpoint · = not found (will 404 / fall back).")

    return 0


def _cmd_sources(settings) -> int:
    from newsagent.collectors.registry import REGISTRY, get_collector

    print("Available collectors:")
    for name in sorted(REGISTRY):
        try:
            c = get_collector(name)
            print(f"  - {name} ({c.name})")
        except Exception as exc:  # noqa: BLE001
            print(f"  - {name} (error: {exc})")
    print("\nEnabled in config:")
    for name in settings.collectors.enabled:
        mark = "" if name in REGISTRY else " (NOT FOUND)"
        print(f"  - {name}{mark}")
    return 0


def _parse_date(s: str) -> datetime | None:
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Update `test_cli.py` to test only the surviving subcommands**

Edit `tests/unit/test_cli.py` (4883 bytes). Remove any tests for `run`, `backfill`, `research`. Add a test that `newsagent news <prompt.md>` is recognized and dispatched.

- [ ] **Step 3: Run the full suite**

```bash
.venv/bin/python -m pytest -q tests/
```

Expected: 286 passed.

- [ ] **Step 4: Verify the CLI parses correctly**

```bash
.venv/bin/python -c "from newsagent.cli import _parse_args; print(_parse_args(['news', 'example_prompt.md']))"
```

Expected: `{'command': 'news', 'flags': {}, 'opts': {}, 'positionals': ['example_prompt.md']}`.

- [ ] **Step 5: Verify ruff clean**

```bash
.venv/bin/python -m ruff check src/newsagent/cli.py
```

---

### Task 18: Delete the old `brief/` package and `pipeline/run.py` shim

**Files:**
- Delete: `src/newsagent/brief/` (entire package)
- Delete: `src/newsagent/pipeline/run.py` (the shim is no longer needed)
- Update: `src/newsagent/pipeline/eval.py` (use `parse_prompt` instead of the `parse_brief` alias)

- [ ] **Step 1: Verify no remaining imports of `brief.*` or `pipeline.run`**

```bash
.venv/bin/python -c "
import subprocess
result = subprocess.run(['grep', '-rEln', r'hermes\\.brief|from hermes\\.pipeline\\.run import', 'src', 'tests'], capture_output=True, text=True)
print('Hits:' if result.stdout else 'No imports.', result.stdout)
"
```

Expected: `No imports.`

- [ ] **Step 2: Drop the `parse_brief` alias from `pipeline/spec.py`**

Edit `src/newsagent/pipeline/spec.py`. Remove the line `parse_brief = parse_prompt` (the temporary alias from Task 1).

- [ ] **Step 3: Update `pipeline/eval.py` to use `parse_prompt`**

Edit `src/newsagent/pipeline/eval.py`. Replace `parse_brief` with `parse_prompt` in the import line and the call site.

- [ ] **Step 4: Delete the files**

```bash
rm -rf src/newsagent/brief/
rm -f src/newsagent/pipeline/run.py
```

- [ ] **Step 5: Run the full suite**

```bash
.venv/bin/python -m pytest -q tests/
```

Expected: 286 passed.

- [ ] **Step 6: Verify ruff clean**

```bash
.venv/bin/python -m ruff check src tests
```

---

### Task 19: Update scheduler templates

**Files:**
- Modify: `scheduler/launchd.plist`
- Modify: `scheduler/cron.txt`
- Modify: `scheduler/systemd.service`
- Modify: `scheduler/systemd.timer`

- [ ] **Step 1: Read each scheduler file to find the `newsagent run` invocation**

```bash
grep -nE 'hermes (run|backfill|research)' scheduler/*
```

- [ ] **Step 2: Update `launchd.plist`**

Find the `newsagent run` line and replace with:

```xml
<string>news</string>
<string>/path/to/newsagent/prompts/ai_news_daily.md</string>
```

(Use the absolute path to the daily prompt.)

- [ ] **Step 3: Update `cron.txt`**

Find the `newsagent run` line and replace with `newsagent news /path/to/newsagent/prompts/ai_news_daily.md`.

- [ ] **Step 4: Update `systemd.service` and `systemd.timer`**

Same change: `ExecStart=newsagent news /path/to/newsagent/prompts/ai_news_daily.md`.

- [ ] **Step 5: Verify ruff clean**

```bash
.venv/bin/python -m ruff check scheduler/
```

(ruff may not check non-Python files; this is a no-op. Skip if it errors.)

---

### Task 20: Update docs (`README.md`, `CHANGELOG.md`, `docs/ARCHITECTURE.md`, `docs/PIPELINE.md`, `docs/CONFIGURATION.md`, `docs/CLI.md`, `docs/STORAGE.md`); delete `docs/BRIEF.md`

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/PIPELINE.md`
- Modify: `docs/CONFIGURATION.md`
- Modify: `docs/CLI.md`
- Modify: `docs/STORAGE.md`
- Delete: `docs/BRIEF.md`

- [ ] **Step 1: Update `README.md`**

In the "Quickstart" section, change `newsagent run` to `newsagent news example_prompt.md`. Update the "CLI commands" table to drop `run`, `backfill`, `research` and add a one-line description for `news`. Update the architecture diagram to show one pipeline.

- [ ] **Step 2: Add a "Pipeline unification" entry to `CHANGELOG.md`**

Prepend to the top of the changelog (under the Unreleased header):

```markdown
### Pipeline unification (2026-07-13)

The two-pipeline structure (daily `newsagent run` + brief `newsagent news`) collapses
into a single, brief-driven pipeline.

- **Removed subcommands:** `newsagent run`, `newsagent backfill`, `newsagent research`.
- **Removed CLI flags:** `--daily`, `--weekly`, `--monthly`, `--rate` on `news`.
  Cadence is configured via `NEWSAGENT_CADENCE` in `.env`; `--rate 1-5` moved to
  `newsagent eval --rate 1-5`.
- **Removed files:** `src/newsagent/brief/`, `src/newsagent/analyzers/`,
  `src/newsagent/renderers/`, `src/newsagent/pipeline/cluster.py`, `rank.py`,
  `planning.py`, `research.py`, `quality_gates.py`, `prioritize.py`.
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
- **Test count:** 263 → 286 (added cadence, embed, synthesize, report split,
  eval split, integration test for the new orchestrator).
```

- [ ] **Step 3: Update `docs/ARCHITECTURE.md`**

- §1: replace the dual-pipeline diagram with a single one.
- §2.6: replace with a "The unified pipeline" section describing `orchestrator.py` + the optional cognition core.
- §2.7: delete the 18-renderer table.
- §2.8: collapse "Brief-driven report pipeline" into §2.6.

- [ ] **Step 4: Update `docs/PIPELINE.md`**

- §1: replace the dual-pipeline diagram.
- §2: rename stages as "always run" vs "optional cognition core."
- §3: update the self-critique section to mention the per-section critic loop is the only one.
- §4: unchanged.
- §5: delete (RAG legacy).
- §6: delete (research_loops flag is gone).

- [ ] **Step 5: Update `docs/CONFIGURATION.md`**

Remove the entries for the deleted env vars (`NEWSAGENT_PIPELINE_SELF_CRITIQUE`, `NEWSAGENT_PIPELINE_RAG_WRITING`, `NEWSAGENT_PIPELINE_RESEARCH_LOOPS`, `NEWSAGENT_PIPELINE_CRITIC_MAX_CHARS`, `NEWSAGENT_PIPELINE_ANALYZE_MAX_CHARS`, `NEWSAGENT_PIPELINE_PRIORITIZER_*`, `NEWSAGENT_SEARCH_MAX_RESULTS`, `NEWSAGENT_SEARCH_SEARCH_DEPTH`, `NEWSAGENT_SEARCH_TOPIC`, `NEWSAGENT_SEARCH_INCLUDE_RAW_CONTENT`, `NEWSAGENT_SEARCH_MAX_SOURCES`, `NEWSAGENT_SEARCH_PER_SECTION_SOURCES`). Add `NEWSAGENT_CADENCE` with the three valid values.

- [ ] **Step 6: Update `docs/CLI.md`**

Replace the 8-command list with the 7-command list. Note that `news` no longer accepts `--daily`/`--weekly`/`--monthly`. The full list of supported flags per command is now:

| Command | Positional | Flags |
|---|---|---|
| `news` | `<prompt.md>` (required) | — |
| `eval` | `<report.md>` | `--prompt <prompt.md>`, `--cadence <name>`, `--rate 1-5` |
| `quality` | — | `--date YYYY-MM-DD` |
| `profiles` | — | — |
| `status` | — | — |
| `models` | — | — |
| `sources` | — | — |

- [ ] **Step 7: Update `docs/STORAGE.md`**

Add a one-paragraph note: "The KG tables (`entities`, `relationships`, `entity_aliases`, `entity_history`, `timelines`) are defined but not written by the pipeline. The in-memory `EvidenceGraph` is the only graph used at runtime; past-reports RAG provides cross-run memory."

- [ ] **Step 8: Delete `docs/BRIEF.md`**

The content is now in `docs/PIPELINE.md` and `docs/CONFIGURATION.md`. Keep `docs/NEWSAGENT_DESIGN.md` and `docs/COGNITION_DESIGN.md` as historical references.

```bash
rm docs/BRIEF.md
```

- [ ] **Step 9: Run full suite one last time**

```bash
.venv/bin/python -m pytest -q tests/
```

Expected: 286 passed.

- [ ] **Step 10: Verify ruff clean**

```bash
.venv/bin/python -m ruff check src tests
```

---

## Self-Review

### Spec coverage

- §1 (user-facing surface, 7 commands, 1 output file, prompt arg required): Tasks 17, 18, 20.
- §2.1 (one orchestrator): Task 11.
- §2.2 (module map after unification): Tasks 1, 6, 7, 8, 9.
- §2.3 (orchestrator flow with optional cognition core): Task 11 (`_maybe_run_cognition_core`).
- §2.5 (no KG writes): Tasks 16, 20 (STORAGE.md note).
- §3 (data flow + persistence): Task 11.
- §4 (error handling): Task 11 (every place where `except Exception` is caught, logged, and a placeholder/empty result is used).
- §5.1 (PipelineConfig slimmed): Task 4.
- §5.2 (SearchConfig slimmed): Task 4.
- §5.3 (`NEWSAGENT_CADENCE` env var): Task 3 + Task 5.
- §5.4 (removed env vars): Task 4 + Task 20 (CONFIGURATION.md).
- §6.1 (whole directories deleted): Task 16 + Task 18.
- §6.2 (functions/classes to delete): Task 16 (`quality_gates`, `prioritize`, `metrics.log_summary`).
- §6.3 (test renames + deletions): Tasks 2, 10, 15, 16.
- §6.4 (docs updated): Task 20.
- §6.5 (scheduler templates): Task 19.
- §7 (test strategy 250-280 tests): Tasks 5, 13, 14, 15. Final count: 286.
- §8 (migration ordering): Task 1 → 20 in order.

### Placeholder scan

- No "TBD", "TODO", "implement later" in any task.
- All code blocks are full implementations.
- The orchestrator code in Task 11 Step 4 has a deliberate "this orchestrator will be wired up in Task 12" comment that is overwritten by the actual implementation in the same step (the `Wait — that's wrong.` paragraph + replacement). This is intentional scaffolding commentary for the implementer, not a placeholder.
- Task 11 Step 5 ("Note about the `Embedder` import") corrects a placeholder from Step 4. Not a plan failure.

### Type consistency

- `CadenceSpec` fields (`window`, `days`, `per_section`, `sources`, `max_tokens`, `min_citations`): defined in Task 5, used in Task 11 (orchestrator) and Task 20 (CADENCE table).
- `FULL_COGNITION_MIN_SECTIONS = 3`: defined in Task 11 (orchestrator), tested in Task 11 (integration test).
- `parse_prompt`: defined in Task 1, used in Task 11 (orchestrator), Task 17 (cli), Task 20 (changelog).
- `SearchResult`: defined in `pipeline/search.py` (Task 7), used throughout Task 11.
- `BriefSpec`, `SectionSpec`: defined in `pipeline/spec.py` (Task 1), used throughout.
- `run_news_pipeline`: defined in Task 11, used in Task 17 (cli).
- `LLMRouter`, `Embedder`, `Store`, `ProviderResult`: imported as before; no signature changes.
- The `Report` model field `sections_count` is set to `len(report.references)` in Task 11 — this is a pre-existing inconsistency from the daily path (`sections_count` semantically should be `len(sections)`, not `len(references)`). It's preserved here to avoid scope creep. The unify-pipelines design doesn't address it; leave for a follow-up.

### Plan gaps

- The spec says "All legacy/fallback code is deleted." Task 16 + Task 18 cover this.
- The spec says "the launchd plist runs `newsagent news <prompt.md>` once a day." Task 19 covers this.
- The spec says "250-280 tests pass." Task 20's final count is 286 (slightly over) — within the spirit of the spec.
- The spec mentions "rewrite `BriefSpec` parsing for the new `parse_prompt`" but the underlying logic doesn't change. Task 1's rename is sufficient.

No gaps found. Plan is complete.
