# Configuration

> Every environment variable, settings group, profile, and `.env` reference
> for Hermes.

All settings use the `HERMES_` env prefix and are loaded from a `.env` file in
the project root (gitignored). Settings are validated by Pydantic
(`hermes/config.py`). Unknown env vars are ignored.

---

## 1. Quick reference

```bash
# .env — copy from .env.example and fill in.
HERMES_LLM_BACKEND=opencode_go
HERMES_LLM_OPENCODE_GO_BASE_URL=https://opencode.ai/zen/go/v1
HERMES_LLM_OPENCODE_GO_API_KEY=<your-key>
# Leave blank for per-tier catalog routing:
HERMES_LLM_OPENCODE_GO_MODEL=

HERMES_SEARCH_BACKEND=none
HERMES_SEARCH_TAVILY_API_KEY=
```

---

## 2. LLM settings (`HERMES_LLM_`)

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `https://api.ollama.com` | Ollama API endpoint (local or Pro) |
| `OLLAMA_API_KEY` | _(none)_ | Ollama Pro API key (Bearer auth) |
| `BACKEND` | `ollama` | Backend selector: `ollama` · `opencode_go` · `openai` |
| `OPENCODE_GO_BASE_URL` | `https://opencode.ai/zen/go/v1` | OpenCode Go endpoint |
| `OPENCODE_GO_API_KEY` | _(none)_ | OpenCode Go API key |
| `OPENCODE_GO_MODEL` | _(none)_ | Single model for all roles, or blank for per-tier catalog routing |
| `OPENAI_BASE_URL` | _(none)_ | OpenAI-compatible `/chat/completions` base URL |
| `OPENAI_API_KEY` | _(none)_ | OpenAI-compatible API key |
| `OPENAI_MODEL` | _(none)_ | OpenAI-compatible model id |
| `TOKEN_BUDGET` | `2000000` | Hard cap: abort generation if cumulative tokens exceed this |
| `ALLOW_HEURISTIC_FALLBACK` | `True` | If `False`, fail loudly when the API is down; if `True`, produce a heuristic report |
| `TIMEOUT_SECONDS` | `180.0` | Per-LLM-call timeout |
| `COST_PER_1K_TOKENS` | `0.0` | USD per 1k tokens for cost accounting (0 disables) |

### Backend selectors

| Backend | When to use | Auth | Catalog |
|---------|-------------|------|---------|
| `ollama` | Default; local Ollama or Ollama Pro | Bearer key (optional) | `OLLAMA_CATALOG` |
| `opencode_go` | OpenCode Zen free models | Bearer key (required) | `OPENCODE_GO_CATALOG` |
| `openai` | Any OpenAI-compatible endpoint | Bearer key (optional) | Single `OPENAI_MODEL` |

### Per-tier catalog routing (opencode_go)

When `HERMES_LLM_OPENCODE_GO_MODEL` is blank, each role routes to its tier's
chain in `OPENCODE_GO_CATALOG`:

| Tier | Primary model | Used by roles |
|------|---------------|---------------|
| `writer` | `deepseek-v4-pro` | research, write, brief_write |
| `critic` | `kimi-k2.6` | reason, compare, verify, critic |
| `plan` | `kimi-k2.6` | plan, brief_plan |
| `cheap` | `deepseek-v4-flash` | label, summarize, markdown, proofread |

This avoids the **reasoning-token starvation** pitfall: models like `glm-5.2`
need ≥200 tokens for their `reasoning_content` before `content` appears. Cheap
roles use `max_tokens=64`, so they must use a model that returns content at low
token budgets. See [LLM_PROVIDERS.md](./LLM_PROVIDERS.md) for the full catalog.

---

## 3. Collector settings (`HERMES_COLLECTOR_`)

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLED` | `arxiv,rss,github_trending,github_releases,huggingface,blog,hacker_news,semantic_scholar,openreview,devto,lobsters,tavily,context7,bluesky,youtube` | Comma-separated collector names (15 registered; all enabled by default) |
| `LOOKBACK_HOURS` | `168` (7 days) | Per-source lookback window |
| `PER_SOURCE_LIMIT` | `60` | Max items pulled per source per run |
| `CONCURRENCY` | `12` | Concurrent collector fan-out |
| `TIMEOUT_SECONDS` | `30.0` | Per-source HTTP timeout |
| `RETRY_ONCE` | `True` | Retry a failed source once before skipping |

---

## 4. Embedder settings (`HERMES_EMBED_`)

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL` | `hashing` | `hashing` (zero-dep) or a sentence-transformers model id |
| `DIM` | `768` | Dimension for the hashing embedder |
| `NORMALIZE` | `True` | Normalize vectors to unit length (required for cosine) |
| `BATCH_SIZE` | `32` | Batch size for embedding |

---

## 5. Pipeline settings (`HERMES_PIPELINE_`)

| Variable | Default | Description |
|----------|---------|-------------|
| `TOP_K_ANALYSIS` | `25` | How many top items get deep evidence/claim extraction |
| `REPORT_TOP_K` | `25` | Top items that make the report body |
| `SECTION_CONCURRENCY` | `3` | Bounded concurrency for parallel section synthesis |
| `GRAPH_CONTEXT_MAX_CHARS` | `4000` | Max chars of the cross-document graph context injected into synthesis/chief-analyst prompts |

---

## 6. Storage settings (`HERMES_STORAGE_`)

| Variable | Default | Description |
|----------|---------|-------------|
| `DIR` | `storage` | Root storage directory |
| `SQLITE_FILE` | `hermes.db` | SQLite filename inside storage dir |
| `VECTOR_BACKEND` | `numpy` | `numpy` (default, zero-dep) or `qdrant` (embedded local mode) |
| `QDRANT_DIR` | `vectors` | Qdrant local on-disk path inside storage dir |
| `QDRANT_COLLECTION` | `hermes` | Qdrant collection name |
| `OBSIDIAN_VAULT` | _(none)_ | Obsidian vault directory to mirror reports into |

---

## 7. Search settings (`HERMES_SEARCH_`)

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKEND` | `none` | `tavily` (requires API key) or `none` (parametric knowledge only) |
| `TAVILY_API_KEY` | _(none)_ | Tavily API key |
| `TAVILY_BASE_URL` | `https://api.tavily.com` | Tavily endpoint |
| `DOMAIN_CAP` | `3` | At most this many sources from any single host |
| `TIMEOUT_SECONDS` | `30.0` | Per-source HTTP timeout |
| `MIN_CITATIONS` | `3` | Research loop trigger: if a section has fewer citations, spawn extra queries |
| `EXTRA_QUERIES` | `2` | Max extra queries per section if citations are thin |

---

## 8. RAG settings (`HERMES_RAG_`)

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLED` | `True` | Enable RAG retrieval from past reports |
| `MAX_REPORTS` | `20` | Max past reports to load (most recent first) |
| `TOP_K` | `3` | Top-k similar past sections to retrieve per section |
| `THRESHOLD` | `0.3` | Cosine similarity threshold for retrieval |
| `MAX_CONTEXT_CHARS` | `2000` | Max chars of RAG context to inject into writer prompt |

> **Scope:** the RAG config group is consumed by the per-section synthesizer
> (`pipeline/synthesize.py`), which loads past reports for
> style/consistency anchoring. The in-run `EvidenceGraph` provides the
> primary cross-document context.

---

## 9. Report profiles

Profiles are defined in [`hermes/profiles.py`](../src/hermes/profiles.py).
Cadence is set via `HERMES_CADENCE` in `.env` (not via profile); the profile
selects the structural parameters of the report.

| Profile | top_k_analysis | report_top_k | depth | sections (legacy 18-renderer subset) |
|---------|----------------|--------------|-------|----------------------------------------|
| `daily` | 25 | 25 | standard | all 18 |
| `weekly` | 60 | 60 | deep | all 18 |
| `minimal` | 10 | 10 | standard | `executive_summary`, `major_news` |
| `deep_dive` | 10 | 10 | exhaustive | 7 focused |
| `trend_report` | 40 | 40 | standard | 6 trend-focused |

> The `sections` column selects a subset of the legacy 18 `hermes.renderers`
> (used only by the fallback path). The unified pipeline builds a
> **dynamic** report (synthesized per prompt + References & Provenance)
> via `stages/renderer.py`, so this column does not constrain the output.

Profiles override `settings.pipeline.*`. No new pipeline code is needed for a
new profile — just add an entry to `PROFILES` in
[`hermes/profiles.py`](../src/hermes/profiles.py).

---

## 10. Global settings (`HERMES_`)

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Logging level |
| `JSON_LOGS` | `False` | If `True`, emit JSON-formatted logs |
| `CADENCE` | `daily` | Lookback window + per-section source budget. One of: `daily` (last 24h), `weekly` (last 7 days), `monthly` (last 30 days). Invalid values fall back to `daily` at the orchestrator boundary. Loaded by `pipeline/cadence.py` into a `CadenceSpec(window, days, per_section, sources, max_tokens, min_citations)`. **Overridden by the brief's own cadence hint** when `parse_prompt` detects `"monthly"` / `"weekly"` / `"daily"` in the title or first 800 chars of the body — `spec.cadence` takes precedence over `HERMES_CADENCE` so the lookback window always matches the prompt body. |

---

## 11. `.env` example

```bash
# LLM backend
HERMES_LLM_OLLAMA_BASE_URL=https://api.ollama.com
HERMES_LLM_OLLAMA_API_KEY=
HERMES_LLM_BACKEND=opencode_go
HERMES_LLM_OPENCODE_GO_BASE_URL=https://opencode.ai/zen/go/v1
HERMES_LLM_OPENCODE_GO_API_KEY=<your-key>
HERMES_LLM_OPENCODE_GO_MODEL=

# Cadence (drives the lookback window + per-section source budget)
HERMES_CADENCE=daily

# Search (optional, for web-grounded synthesis)
HERMES_SEARCH_BACKEND=none
HERMES_SEARCH_TAVILY_API_KEY=

# Storage (optional)
HERMES_STORAGE_OBSIDIAN_VAULT=~/Documents/obsidian

# Logging
HERMES_LOG_LEVEL=INFO
HERMES_JSON_LOGS=False
```