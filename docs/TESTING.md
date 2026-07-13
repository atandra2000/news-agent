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

**Current status: 227 tests, all passing, ~2.5s runtime.**

---

## 2. Test layout

```
tests/
├── conftest.py          # Autouse structlog isolation + fake_ctx fixture
├── helpers.py           # FakeRouter, _settings, _fake_items (shared)
├── unit/
│   ├── test_core.py             # dedup, embedder, collector registry
│   ├── test_llm.py              # catalog, roles, registry, router, providers (HTTP mocked)
│   ├── test_cli.py              # arg parsing, command dispatch, _parse_date
│   ├── test_quality.py          # quality stage: heuristic + LLM judge + run_quality
│   ├── test_sinks.py            # MarkdownFileSink + ObsidianSink + build_sinks
│   ├── test_brief_spec.py       # brief Markdown parser (uses example_prompt.md)
│   ├── test_brief_citations.py  # citation resolution + report assembly
│   └── test_brief_planner.py    # query planner
├── integration/
│   ├── test_brief_run.py        # brief pipeline: search + RAG + research loop + cadences
│   └── test_extended.py         # source breadth, profiles, sinks, planning, KG, pipeline
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

Builds isolated `HermesSettings` for offline tests:
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

### `test_brief_run.py` (4 tests)

- Brief pipeline with search: title, sections, citations, references.
- Brief pipeline no search.
- Research loop fills thin citations.
- Daily/weekly/monthly cadences.

### `test_brief_spec.py` (5 tests)

- Parses title, 18 sections, section bullets, prioritized sources,
  deliverables + quality. Uses `example_prompt.md`.

### `test_brief_citations.py` (5 tests)

- Citation reordering by first appearance, drops unknown sources, tolerates URL
  noise, appends references, no references when none.

### `test_brief_planner.py` (3 tests)

- Section + source queries, respects caps, year in query.

### `test_extended.py` (5 tests)

- New collectors registered, profiles exist, sinks (Obsidian), planning gates
  research, research partial-tolerant, KG query.

### `test_core.py` (5 tests)

- SimHash near-dup, Deduper, Embedder normalized, collector registry,
  run_collector skip-on-failure.

---

## 6. Adding a new test

### Unit test (no network, no LLM)

```python
# tests/unit/test_my_module.py
from hermes.my_module import my_function

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
.venv/bin/python -m ruff check --fix src/hermes/llm/catalog.py src/hermes/config.py

# Mypy (type check).
.venv/bin/python -m mypy src/hermes/
```

Both are configured in `pyproject.toml`. Ruff target: `py311`, line-length 100.