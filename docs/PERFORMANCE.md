# Performance Optimization Guide

**Last updated:** July 2026
**Status:** All 270 tests passing (241 unit + 29 integration). Backward-compatible.

---

## Token-Consumption Optimizations (LLM cost, not just wall-clock)

The speed-optimization pass optimized *speed* (parallelism, batching, caching of analyses). The token-optimization pass
optimizes *token spend* — the dominant recurring cost of an LLM-agent pipeline
that runs daily. These changes cut prompt tokens substantially with no quality
regression on the final report.

| # | Optimization | Stage | Impact | Mechanism |
|---|---|---|---|---|
| 1 | **Prompt caching (KV-cache reuse)** | all LLM calls | **HIGH** | `cache_prompt` (Ollama) / `cache_control` (OpenAI-compatible, best-effort) reuses the KV cache for identical prompt prefixes across the many repeated-prefix calls (same instruction headers, report scaffolding, lessons, graph context). Router-wide default `HERMES_LLM_PROMPT_CACHE=true`; requires `keep_alive` so the model + cache stay resident. |
| 2 | **Role tier rebalance** | analyze, synthesize | **HIGH** | `research` (per-item analysis, 25–60 calls/run) and `cluster_synth` (~10–20 calls/run) demoted from `writer` (deepseek-v4-pro) to `critic` (kimi-k2.6). Structured extraction/synthesis don't need the biggest model — ~3–5× cheaper per token. `chief_analyst`/`write` stay on `writer`. |
| 3 | **Right-sized `num_ctx`** | analyze, synthesize | **MEDIUM** | `research`/`cluster_synth` use `num_ctx=8192` instead of the `writer` tier default 16384 — smaller KV cache, better throughput for small prompts. `get_role_for_provider` now preserves per-role `num_ctx`/`keep_alive` overrides. |
| 4 | **Removed redundant double call** | synthesize | **MEDIUM** | `synthesize_stories._synthesize_batch` no longer re-issues a full `complete()` call on a JSON parse miss — `json_complete` already strips fences/extracts the first `{…}` span, so the second call was a pure duplicate burn. Goes straight to heuristic fallback. |
| 5 | **Condensed self-critique input** | render (critic) | **MEDIUM** | The critic now receives headings + the opening 500 chars of each section (capped at `HERMES_PIPELINE_CRITIC_MAX_CHARS=3500`) instead of `body[:6000]`. ~75% smaller critic prompt in testing, same critique quality. Rewrite still gets the full body so no section is dropped. |
| 6 | **Analyze content truncation** | analyze | **MEDIUM** | Per-item content truncated to `HERMES_PIPELINE_ANALYZE_MAX_CHARS=2500` (was hardcoded 4000). 100k–240k fewer prompt chars/run at no extraction-quality cost. |
| 7 | **Graph-context cap** | synthesize, chief | **MEDIUM** | Cross-document graph context capped at 4000 chars before injection into each synthesis batch + the Chief Analyst call (it is shared across all calls, so an unbounded graph would bloat every one). |
| 8 | **Per-role token accounting** | all | **NEW** | `RouterStats.by_role` + `PipelineMetrics.llm_by_role` break down prompt/completion tokens per role, surfaced in the run manifest `metrics.llm.by_role`. Makes future cost tuning data-driven. |

### Expected token savings (per daily run, cold)

| Call class | Before (writer tier) | After (critic tier + caching) | Δ |
|---|---|---|---|
| analyze (25 items × 1 call) | 25 × writer | 25 × critic + cached prefix | ~60–70% cheaper/token |
| cluster synth (10 clusters) | 10 × writer | 10 × critic + cached prefix | ~60–70% cheaper/token |
| self-critique | 6000 + 8000 chars | ~1070 + full chars | ~75% on critic call |
| (caching compounds across all repeated-prefix calls) | — | — | additional 10–30% prompt-token cut |

> Quality guard: `chief_analyst` and `write` (the two calls that produce the
> readable report) are intentionally **untouched** — only the high-frequency
> extraction/synthesis/critique calls were demoted or trimmed.

---

## Speed Optimizations (summary)

| # | Optimization | Stage | Impact | Before | After |
|---|---|---|---|---|---|
| 1 | Parallel collectors | collect | **HIGH** | Sequential: 15 × 30s = 7.5 min worst case | Parallel (semaphore=12): ~30s worst case |
| 2 | Batched ingest DB | ingest | **HIGH** | 2N DB sessions (check + insert per item) | 3 bulk queries (load + batch insert + batch alias) |
| 3 | Parallel LLM analysis | analyze | **HIGH** | 2N sequential LLM calls (analyze + verify per item) | Parallel (semaphore=6): ~4× faster |
| 4 | Batched analyze DB | analyze | **MEDIUM** | N individual existence checks + N persist sessions | 1 bulk check + 1 batch persist |
| 5 | Persistent analysis cache | analyze | **HIGH** | Re-analyze all items every run | Skip items with existing `Analysis` rows |
| 6 | Parallel cluster labels | cluster | **MEDIUM** | Sequential LLM calls per cluster | `asyncio.gather` all labels concurrently |
| 7 | Parallel research loops | research | **MEDIUM** | Sequential LLM calls per research item | Parallel (semaphore=4) |
| 8 | Batched trend DB | trend | **LOW** | N individual insert sessions | 1 batch insert session |
| 9 | Batched quality lessons | quality | **LOW** | N individual insert sessions | 1 batch insert session |
| 10 | Performance metrics | all | **NEW** | No instrumentation | Per-stage timing, LLM/DB/cache counters |

---

## Expected Performance Gains

### LLM Calls (>70% reduction on repeat runs)

**First run (cold):**
- Analyze: 25 items × 2 calls = 50 LLM calls (same as before, but now parallel)
- Clusters: ~10 labels = 10 LLM calls (same, but now parallel)
- Self-critique: 2 LLM calls (unchanged)
- Total: ~62 calls (same count, but ~4× faster wall-clock)

**Second run (warm, same items):**
- Analyze: 0 LLM calls (all skipped by persistent cache) → **100% saved**
- Clusters: ~10 labels (always re-computed)
- Self-critique: 2 LLM calls
- Total: ~12 calls → **~80% reduction**

### Execution Speed (>5× faster)

The critical path before:
```
collect: 15 × 30s = 450s (sequential)
analyze: 50 × 5s = 250s (sequential LLM)
clusters: 10 × 3s = 30s (sequential LLM)
research: 5 × 8s = 40s (sequential LLM)
Total LLM-bound: ~770s
```

After:
```
collect: 30s (parallel, 12 concurrent)
analyze: 50 calls / 6 concurrency × 5s ≈ 42s (parallel LLM)
clusters: 10 calls / all concurrent × 3s ≈ 3s (parallel LLM)
research: 5 calls / 4 concurrency × 8s ≈ 10s (parallel LLM)
Total LLM-bound: ~85s → ~9× faster
```

On warm runs (cached analyses): ~15s total → **>50× faster**.

### DB Sessions

| Stage | Before | After | Savings |
|---|---|---|---|
| ingest (300 items) | 600+ sessions | 3 sessions | 99.5% |
| analyze (25 items) | 100+ sessions | 3 sessions | 97% |
| trend (40 topics) | 40 sessions | 2 sessions | 95% |
| quality (3 notes) | 3 sessions | 1 session | 67% |

---

## Architecture

### Metrics System (`pipeline/metrics.py`)

```
PipelineMetrics
├── stages: dict[str, StageTiming]     # wall-clock per stage
├── llm_calls / llm_calls_saved        # API call counters
├── db_sessions / db_sessions_saved     # DB round-trip counters
├── cache_hits / cache_misses           # analysis cache effectiveness
├── items_collected / items_analyzed    # item flow counters
└── collectors_succeeded/failed/parallel # collector health
```

Metrics are attached to `RunContext.metrics` and logged at end of run.
The manifest JSON includes a full `metrics` section for debugging.

### PerfTimer Context Manager

```python
async with PerfTimer(ctx, "stage_name"):
    await do_work()
# Records start/end monotonic timestamps on ctx.metrics.stages["stage_name"]
```

### Parallel Execution Pattern

All parallel stages use the same pattern:

```python
sem = asyncio.Semaphore(concurrency)

async def _bounded(task):
    async with sem:
        return await task

results = await asyncio.gather(*[_bounded(t) for t in tasks])
```

Concurrency limits:
- Collectors: `settings.collectors.concurrency` (default: 12)
- Analysis LLM: `_ANALYZE_CONCURRENCY = 6`
- Research LLM: `_RESEARCH_CONCURRENCY = 4`
- Cluster labels: unbounded (typically <20 clusters)

### Batched DB Pattern

Instead of N individual sessions:
```python
# Before: N sessions
for item in items:
    async with ctx.store.session() as s:
        s.add(item)
        await s.commit()
```

We use a single session:
```python
# After: 1 session
async with ctx.store.session() as s:
    s.add_all(items)
    await s.commit()
```

### Persistent Analysis Cache

The analyze stage pre-fetches all existing `Analysis.item_uid` values for the
current `ANALYZER_VERSION` in a single query. Items with existing analyses are
skipped entirely — no LLM call, no vector search, no DB write. This makes
repeat runs nearly free.

---

## Configuration

All optimizations are backward-compatible. No new config keys are required.
Existing keys that affect performance:

| Key | Default | Effect |
|---|---|---|
| `HERMES_COLLECTOR_CONCURRENCY` | 12 | Max parallel collectors |
| `HERMES_PIPELINE_SECTION_CONCURRENCY` | 3 | Brief pipeline section parallelism |
| `HERMES_LLM_TIMEOUT_SECONDS` | 180 | Per-call timeout |

Internal concurrency limits (hardcoded, tunable):
- `_ANALYZE_CONCURRENCY = 6` in `pipeline/analyze.py`
- `_RESEARCH_CONCURRENCY = 4` in `pipeline/research.py`

---

## Metrics Output

The manifest JSON now includes a `metrics` section:

```json
{
  "metrics": {
    "total_elapsed_s": 42.5,
    "stages": {
      "collect": 28.3,
      "ingest": 1.2,
      "analyze": 8.7,
      "cluster": 2.1,
      "trend": 0.3,
      "rank": 0.1,
      "render": 1.8
    },
    "llm": {
      "calls": 15,
      "calls_saved": 50,
      "calls_total": 65,
      "prompt_tokens": 45000,
      "completion_tokens": 12000
    },
    "db": {
      "sessions": 12,
      "sessions_saved": 700,
      "sessions_total": 712
    },
    "cache": {
      "hits": 25,
      "misses": 0,
      "hit_rate": 1.0
    },
    "items": {
      "collected": 350,
      "ingested": 280,
      "analyzed": 0,
      "skipped_existing": 25
    },
    "collectors": {
      "succeeded": 13,
      "failed": 2,
      "max_parallel": 12
    }
  }
}
```

---

## Files Changed

| File | Change |
|---|---|
| `pipeline/metrics.py` | **NEW** — PerfTimer + PipelineMetrics |
| `pipeline/context.py` | Added `metrics: PipelineMetrics | None` field |
| `pipeline/run.py` | Parallel collectors, PerfTimer wrappers, metrics wiring |
| `pipeline/ingest.py` | Batched DB: 3 bulk queries instead of 2N |
| `pipeline/analyze.py` | Parallel LLM (semaphore=6), batched DB, persistent cache |
| `pipeline/cluster.py` | Parallel labeling via asyncio.gather |
| `pipeline/research.py` | Parallel research (semaphore=4) |
| `pipeline/trend.py` | Batched DB: 1 transaction instead of N |
| `pipeline/quality.py` | Batched lesson persistence |
| `tests/conftest.py` | Added PipelineMetrics to fake_ctx fixture |

### Files Changed (token optimizations)

| File | Change |
|---|---|
| `llm/providers/base.py` | `complete()` gains `cache: bool = False` |
| `llm/providers/ollama.py` | Sets `options.cache_prompt=True` when `cache` + `keep_alive` |
| `llm/providers/openai_compatible.py` | Attaches `cache_control` to system msg when `cache` (best-effort) |
| `llm/providers/opencode_go.py` | Attaches `cache_control` to system msg when `cache` (best-effort) |
| `llm/router.py` | `prompt_cache` flag; threads `cache` through; per-role `by_role` accounting |
| `llm/roles.py` | `research`/`cluster_synth` → `critic` tier, `num_ctx=8192`; `_spec` honors overrides; `get_role_for_provider` preserves `num_ctx`/`keep_alive` |
| `config.py` | `LLMConfig.prompt_cache`, `PipelineConfig.{critic_max_chars,analyze_max_chars,graph_context_max_chars}` |
| `pipeline/run.py` | Wires `prompt_cache`; condensed self-critique (`_condense_for_critic`); surfaces `llm_by_role` |
| `pipeline/analyze.py` | Uses `analyze_max_chars`; enables `cache=True` on analysis calls |
| `pipeline/synthesizer.py` | Removed redundant double call; caps graph context at 4000 chars |
| `pipeline/chief_analyst.py` | Caps graph context at 4000 chars |
| `pipeline/metrics.py` | Added `llm_by_role` to `PipelineMetrics` + manifest report |
| `tests/unit/test_llm.py`, `tests/helpers.py` | Provider/router signatures accept `cache` |

---

## Backward Compatibility

- All existing tests pass (270/270: 241 unit + 29 integration).
- New config keys are opt-out with safe defaults (`prompt_cache=true`,
  `critic_max_chars=3500`, `analyze_max_chars=2500`, `graph_context_max_chars=4000`).
- No database schema changes.
- No API changes to public interfaces (the `cache` param defaults to `False`).
- Metrics are optional (`ctx.metrics` can be `None`).
- The manifest format is extended (new `metrics.llm.by_role` key) but not broken.
