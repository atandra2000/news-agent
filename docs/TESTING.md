# Testing

> Test layout, fixtures, helpers, running the suite, and adding new tests.

---

## 1. Quickstart

```bash
# Run the full test suite (offline — no network, no LLM server).
.venv/bin/python -m pytest tests/ -q

# Run a subset.
.venv/bin/python -m pytest tests/unit/ -q
.venv/bin/python -m pytest tests/integration/ -q
.venv/bin/python -m pytest tests/unit/test_llm.py -q

# Verbose with short tracebacks.
.venv/bin/python -m pytest tests/ -v --tb=short

# Run a single test.
.venv/bin/python -m pytest tests/unit/test_llm.py::TestRouter::test_token_budget_guard -v
```

**Current status: 237 tests, all passing, ~3.8s runtime.**

---

## 2. Test layout

```
tests/
├── conftest.py          # Autouse structlog isolation + fake_ctx fixture
├── helpers.py           # FakeRouter, _settings, _fake_items (shared)
├── unit/
│   ├── test_cadence.py              # CadenceSpec + resolve_cadence + daily/weekly/monthly shape
│   ├── test_cli.py                  # arg parsing, command dispatch, _parse_date
│   ├── test_core.py                 # dedup, embedder, collector registry
│   ├── test_coverage.py             # OK/THIN/CRITICAL verdict (Scope 2)
│   ├── test_cross_post_dedup.py     # content_fingerprint + cross-post groups (Scope 4)
│   ├── test_embed.py                # hashing embedder shape/length/determinism
│   ├── test_llm.py                  # catalog, roles, registry, router, providers (HTTP mocked)
│   ├── test_new_collectors.py       # registry contract for new collectors
│   ├── test_orchestrator_observability.py  # sources_checked / sources_failed plumbed (Scope 7)
│   ├── test_planner.py              # query planner
│   ├── test_quality.py              # quality stage: heuristic + LLM judge + run_quality
│   ├── test_report.py               # assemble_report, citation audit, deliverables gate, thin banner
│   ├── test_sanitizer.py            # CoT scrub + synthesis-failure stub detection (Scope 3)
│   ├── test_sinks.py                # MarkdownFileSink + ObsidianSink + build_sinks
│   ├── test_spec.py                 # parse_prompt + cadence detection (Scope 1)
│   └── test_synthesize.py           # select_relevant + priority boost + diversity floor (Scope 8)
├── integration/
│   ├── test_extended.py             # source breadth, profiles, sinks, planning, KG, pipeline
│   └── test_news_run.py             # orchestrator end-to-end with a real prompt
```

---

## 3. Shared helpers (`tests/helpers.py`)

All test modules import from `tests/helpers.py` — **never** from another test
file.

### `FakeRouter`

A deterministic `LLMRouter` subclass that returns valid structured JSON for
every role the pipeline exercises:

- `complete()` → returns `"ok"` text.
- `json_complete()` → tailors the fake payload to the role/prompt keyword:
  - `verifier` → `{"verdicts": []}`
  - `critic` → `{"fixes": []}`
  - `self-evaluator` / `score` + `rubric` → quality scores
  - `label` → `{"label": "fake-cluster"}`
  - analyzer prompt → 10+ field analysis JSON with type detection

Never makes HTTP calls. Never returns heuristic fallback (unless all providers
fail in a specific test).

### `_settings(tmp_path)`

Builds isolated `NewsAgentSettings` for offline tests:
- `storage.dir = tmp_path` (in-memory SQLite)
- `embed.model = "hashing"` (zero-dep)
- `embed.dim = 256`
- `pipeline.top_k_analysis = 8` (small for speed)
- `pipeline.rag_writing = False`
- `pipeline.self_critique = False`
- `collectors.enabled = []` (no network)

### `_fake_items()`

Returns 5 deterministic `RawItem`s (arXiv, HuggingFace, GitHub Trending,
RSS×2) with varied source types and extras.

---

## 4. Conftest fixtures (`tests/conftest.py`)

### `_isolated_structlog` (autouse)

Resets structlog config before each test so the cached `PrintLoggerFactory`
doesn't hold a stale `sys.stderr` reference (which pytest's capsys may close).

```python
@pytest.fixture(autouse=True)
def _isolated_structlog():
    structlog.reset_defaults()
    structlog.configure(
        ...,
        logger_factory=structlog.PrintLoggerFactory(file=io.StringIO()),
        cache_logger_on_first_use=False,
    )
    yield
    structlog.reset_defaults()
```

### `fake_ctx`

A full `RunContext` with in-memory SQLite + FakeRouter + hashing embedder +
numpy vectorstore. Yields and closes the store.

```python
@pytest.fixture
def fake_ctx(tmp_path):
    settings = _settings(tmp_path)
    store = Store(settings.sqlite_url)
    asyncio.run(store.init())
    router = FakeRouter()
    ...
    yield ctx
    asyncio.run(store.close())
```

Used by `test_extended.py`, `test_quality.py`.

---

## 5. What each test file covers

### `test_llm.py` (40 tests)

- **Catalog:** tier presence, chain length, `tier_spec`, `all_catalog_models`,
  catalog-distinct-from-ollama, real-models-only, cheap-tier-avoids-starvation.
- **Roles:** all 13 roles present, `get_role` unknown raises, `get_role` returns
  chain + defaults, write/verify temperatures, per-provider resolution.
- **Registry:** default ollama, opencode_go requires key, openai requires
  base_url, provider_for prefix routing, model_name prefix stripping, catalog
  routing vs single-model.
- **Router:** success, fallback-to-next, raises-when-all-fail, empty-text-as-
  failure, token budget guard, accounting, json_complete (parse, fence-strip,
  plain-text→{}, heuristic→{}).
- **Providers (HTTP mocked via respx):** Ollama chat + generate fallback +
  list_models + available; OpenCodeGo chat + list + non-JSON-error + JSON
  format; OpenAI-compatible chat + JSON format + no-auth-header.

### `test_cli.py` (25 tests)

- `_parse_args`: run command, all 10 commands, dry-run/daily/weekly/monthly
  flags, prompt/cadence/rate/date/stage/profile/from/to opts, positionals,
  -h/--help aliases.
- `_parse_date`: ISO date, ISO datetime, invalid returns None.
- CLI commands: help prints usage, no-args prints help, status runs, models
  runs, profiles lists all, sources lists collectors.

### `test_quality.py` (15 tests)

- Heuristic scorer: all 6 dimensions, coverage/depth/synthesis/trust boosts,
  5-cap.
- LLM judge: uses LLM when available, falls back to heuristic on empty LLM.
- `run_quality`: writes markdown + JSON, persists lessons, handles missing
  report.
- Renderer: includes rubric + score.

### `test_sinks.py` (11 tests)

- MarkdownFileSink: writes file, creates parent dirs, default name, name attr.
- ObsidianSink: frontmatter, sinks meta, noop when vault=None, name attr.
- build_sinks: always markdown, obsidian when vault set, excluded when None.

### `test_spec.py` (10 tests)

- `parse_prompt` parses title, sections, bullets, deliverables, quality.
- **Cadence detection (Scope 1):** monthly / weekly / daily hints,
  no-hint returns None, longer/more specific cadences win when both
  are present.

### `test_synthesize.py` (18 tests)

- `select_relevant`: keyword ranking, domain cap.
- **Source-priority boost (Scope 8):** known values, arxiv outranks
  HN on the same paper.
- **Diversity floor:** swaps for unseen source types when
  `min_source_types=3` and the picked set is dominated by HN; no-op
  when already diverse.
- `clean_section_text`: drops planning lines, rejects no-heading /
  planning-only.
- `_content_word_count`: excludes headings and tables.
- `is_substantial_section`: true for real prose, false for stubs.
- `count_citations`: unique-URL count.
- `extract_prose` + sanitizer: CoT scratchpad dropped, no-op when no
  heading, leading scratchpad heading skipped, "heading-first
  dithering" collapsed to the last occurrence, legit repeated
  subheadings survive.

### `test_sanitizer.py` (23 tests)

- All banned phrases (planning markers + round-3 CoT class from
  Scope 3) are scrubbed.
- **Synthesis-failure stub detection (Scope 3):**
  `is_synthesis_failure_stub` returns True for the orchestrator's
  last-resort placeholder, False for real prose.

### `test_coverage.py` (8 tests)

- Source-type → category mapping (official / research / news /
  community).
- `_section_required_category`: title-hint matching.
- `evaluate_coverage`: OK when required category has ≥5 sources,
  CRITICAL when 0, THIN in between.
- Universal sections (Executive Summary, Month Timeline, Predictions)
  have `required_category=None` and pass on any source.
- Realistic monthly report scenario.

### `test_cross_post_dedup.py` (8 tests)

- URL-dedup still works.
- Cross-post detection: 3 HN reposts of the same story collapse to 1
  canonical + 1 cross-post group of 2 duplicates.
- Different stories with similar titles are kept separate.
- Cross-post only fires on the same host (different hosts = different
  stories).
- `content_fingerprint` normalizes whitespace / strips apostrophes.
- `duplication_collapse_rate`: 0.0 for no dedup, 1.0 for all dupes.
- `limit` caps the deduped output.

### `test_orchestrator_observability.py` (2 tests)

- `_gather_sources_fallback` returns `(results, checked, failed)` —
  even with no collectors, the 3-tuple shape holds.
- A successful collector is recorded in `checked`; a failing one
  is recorded in `failed`.

### `test_report.py` (35 tests)

- Citation resolution: reordering by first appearance, drops unknown
  sources, tolerates URL noise, appends references, no references
  when none.
- **Citation discipline (Scope 5):** `audit_citation_discipline`
  counts cited / unsourced / unmarked sentences.
- **Required Deliverables gate (Scope 6):** `check_required_deliverables`
  finds / misses each brief deliverable; `format_missing_deliverables_note`
  renders the Coverage Check tail.
- **Thin-corpus banner (Scope 9):** emits the `⚠️` banner when
  sources/section < 5 or any section is CRITICAL; suppresses when
  the corpus is healthy.
- Stub-renderer behavior: `is_synthesis_failure_stub` triggers the
  dropped-section marker, empty writer output triggers a
  different marker.
- `drop_empty_subheadings`: removes stub subheadings + placeholders.

### `test_cadence.py` (10 tests)

- `CadenceSpec` table has 3 entries (daily/weekly/monthly).
- Daily shape (`days=1`, `per_section=…`, `max_tokens=5000`).
- `max_tokens` and `sources` scale with the lookback window.
- `resolve_cadence`: valid strings map correctly; invalid / unknown
  / None falls back to daily.

### `test_planner.py` (3 tests)

- Section + source queries, respects caps, year in query.

### `test_extended.py` (3 tests)

- New collectors registered, profiles exist, sinks (Obsidian).

### `test_core.py` (5 tests)

- SimHash near-dup, Deduper, Embedder normalized, collector registry,
  run_collector skip-on-failure.

### `test_news_run.py` (1 test, integration)

- `run_news_pipeline` writes a report file for a simple prompt
  (uses `fake_ctx` + in-memory store; offline).

---

## 6. Adding a new test

### Unit test (no network, no LLM)

```python
# tests/unit/test_my_module.py
from newsagent.my_module import my_function

def test_my_function():
    assert my_function("input") == "expected"
```

### Integration test (with FakeRouter + in-memory store)

```python
# tests/integration/test_my_stage.py
import pytest
from tests.helpers import FakeRouter, _settings

@pytest.mark.asyncio
async def test_my_stage(tmp_path):
    settings = _settings(tmp_path)
    # ... build context, run stage, assert ...
```

### Test with HTTP mocking (respx)

```python
import httpx
import respx

@respx.mock
@pytest.mark.asyncio
async def test_http_call():
    respx.get("https://api.example.com/data").mock(
        return_value=httpx.Response(200, json={"key": "value"})
    )
    # ... call that makes the HTTP request ...
```

---

## 7. Lint + typecheck

```bash
# Ruff (lint + format).
.venv/bin/python -m ruff check src/ tests/
.venv/bin/python -m ruff check --fix src/newsagent/llm/catalog.py src/newsagent/config.py

# Mypy (type check).
.venv/bin/python -m mypy src/newsagent/
```

Both are configured in `pyproject.toml`. Ruff target: `py311`, line-length 100.