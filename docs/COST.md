# Cost

newsagent's bill is dominated by LLM tokens. The pipeline emits a
`RouterStats` object after every run that counts tokens per role, per
provider, and a `cost_per_1k_tokens`-based USD estimate. This document
explains what costs what, how to set a budget, and how to drive the
estimate down.

---

## What costs what (per run)

| Stage | Role(s) | Calls/run (daily) | Notes |
|-------|---------|--------------------|-------|
| Plan | `plan` | 1-2 | Cheap tier; tiny budget. |
| Coverage | `cheap` heuristics | 0 LLM | Free — pure Python in `pipeline/coverage.py`. |
| Per-section synthesis | `brief_write` (writer) + `critic` + optional retry | N (one per section) | **Largest cost.** Daily briefs are 6-8 sections, monthly 10-18. |
| RAG retrieval | `embed` | 0 LLM | Hashing embedder is free; sentence-transformers is local CPU. |
| Report editor | `edit` (cheap) | 1 | Consistency pass. |
| Report critic | `report_critic` (critic) | 1 | Verdict. |
| Critique/rewrite loop | `brief_write` × retry | 0-2N | Capped at `NEWSAGENT_REPORT_MAX_REWRITE_ITERATIONS=2`. |
| Sinks | — | 0 LLM | File + Obsidian copy. |

A representative **weekly brief** with 8 sections, no critic rewrites, on
a paid API at $1/M tokens (input + output blended) lands at
**~200-400k tokens ≈ $0.20-0.40**. A **monthly brief** with 18 sections
and one rewrite per section can climb to **~1.5-2.5M tokens ≈ $1.50-2.50**.

The local-Ollama path costs $0 in API fees but burns CPU/GPU time; the
non-monetary cost there is wall-clock, not money.

---

## How cost is estimated

`LLMRouter.stats.estimated_cost_usd` multiplies cumulative
`prompt_tokens + completion_tokens` by a single
`cost_per_1k_tokens` value (set in `.env`):

```python
# src/newsagent/llm/router.py
@property
def estimated_cost_usd(self) -> float:
    return (self.total_tokens / 1000.0) * self.cost_per_1k_tokens
```

The number is **reported** in the `Report` row
(`token_usage=router.stats.total_tokens`) and in structlog events, but
is not surfaced in the rendered Markdown. To get the figure, run
`newsagent status` (DB-only inspection) or grep `storage/hermes.log`.

The estimate is intentionally coarse:

- It treats input and output at the same price. Real APIs price them
  differently (output is usually 2-4× input). If your provider charges
  split rates, set `cost_per_1k_tokens` to a weighted average.
- It does not include Tavily, GitHub, X, or other third-party API
  quotas. Those are flat-fee (or free-tier) and tracked separately.
- It does not subtract KV-cache hits. The Ollama provider enables
  `cache_prompt` (when `keep_alive` is set), which can cut repeated
  prefix tokens by 30-70%; the router never sees the cached portion.

---

## Hard safety caps

| Cap | Env var | Default | Effect |
|-----|---------|---------|--------|
| Token budget | `NEWSAGENT_LLM_TOKEN_BUDGET` | 2,000,000 | Router raises `LLMError` once `stats.total_tokens` exceeds it. The current run aborts; no partial report is written. |
| Per-section max_tokens | (per role in `llm/roles.py`) | 1,200-8,000 | The LLM is told it cannot emit more than this per call. |
| Section concurrency | `NEWSAGENT_PIPELINE_SECTION_CONCURRENCY` | 3 | Hard cap on parallel section synthesis. |
| Per-collector timeout | `NEWSAGENT_COLLECTOR_TIMEOUT_SECONDS` | 30 | Source is skipped on timeout (not retried forever). |
| Per-collector retries | hardcoded | 1 | `retry_once=True`; after 1 retry the source is skipped. |

The token budget is a **process-wide abort**, not a per-run cap. If
you set it to 500k, a 600k-token mid-monthly run dies; reduce the brief
or split the run.

---

## Driving cost down

Five levers, ranked by impact:

1. **Use the cheap tier for non-prose roles.** Roles like `summarize`,
   `markdown`, `label`, `proofread`, `edit` are already on the cheap
   tier in `llm/roles.py`. Do not promote them to writer-tier unless
   you have a measured quality regression.
2. **Enable prompt caching.** Set `NEWSAGENT_LLM_PROMPT_CACHE=true` and
   make sure each role's `keep_alive` is non-None (Ollama-side).
   Identical-prefix calls (the writer's `## Section` boilerplate, the
   critic's `Respond in JSON` system prompt) reuse the KV cache and
   cost ~0 input tokens on subsequent calls.
3. **Lower max_tokens per role.** If your reports look fine at
   2,500-token sections, edit `llm/roles.py` and reduce
   `brief_write.max_tokens` from 5,000 to 2,500. The LLM cannot
   overspend.
4. **Cap section count in the brief.** A 6-section daily brief is
   ~3× cheaper than an 18-section monthly at the same per-section
   quality. Trim `## N. ...` lines in the prompt if the report is
   too dense.
5. **Skip the rewrite loop.** Set
   `NEWSAGENT_REPORT_MAX_REWRITE_ITERATIONS=0` to disable the
   critic→writer loop. Quality will drop on thin-corpus runs but the
   cost drops by ~30-40%.

---

## Cost observability

The pipeline emits the following per-run signals:

- `LLMRouter.stats.total_tokens` (cumulative prompt + completion).
- `LLMRouter.stats.calls` and `.failures`.
- `LLMRouter.stats.by_provider` (calls per provider).
- `LLMRouter.stats.by_role` (per-role token breakdown).
- `LLMRouter.stats.estimated_cost_usd` (when `cost_per_1k_tokens > 0`).
- `Report.token_usage` in the `reports` table (SQLite).
- structlog events: `orchestrator.done` carries `tokens=…` in the log.

To add a per-run cost line to the rendered report, edit
`pipeline/report.py:assemble_report` and inject
`router.stats.estimated_cost_usd` into the metadata block. (Not
shipped by default — keeps the report body free of operational
metadata.)

---

## Free-tier limits of upstream APIs

| API | Free tier | Cost when exceeded |
|-----|-----------|--------------------|
| Tavily | 1,000 searches/month | $0.001-0.005 per search |
| GitHub (unauthenticated) | 60 req/hour | Set `NEWSAGENT_COLLECTOR_GITHUB_TOKEN` for 5,000 req/hour |
| GitHub (authenticated) | 5,000 req/hour | Above that: per-request billing |
| Ollama Pro (default LLM backend) | Per account | Per-token, varies by model |
| OpenCode Go | Per account | Per-token, varies by model |
| X / Twitter | 100 tweets/month (v1.1) | Pro: $5,000/month |

When you see `collector.skipped` events in `storage/hermes.log` with
rate-limit 403/429 errors, the source has been silently dropped for
the rest of the run. Re-enable on the next run when the window resets.
