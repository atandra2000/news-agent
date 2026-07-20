# Security

newsagent runs locally, reads from public web sources, writes to a local
SQLite database, and ships Markdown reports to disk. The threat surface is
intentionally small. This document describes what is in scope, what is not,
and how to handle credentials responsibly.

---

## Threat model in one paragraph

newsagent is a **local-first, single-user** research agent. It executes
briefs you author and writes reports to a directory you choose. The
operator is the only principal; there is no multi-tenant isolation, no
remote control plane, no exposed HTTP API, and no automatic outbound
network calls except those you explicitly enable in `.env`. The
single-network-credential blast radius is the operator's own LLM API
quota, GitHub rate limit, and Tavily quota.

---

## What the agent does on the wire

| Direction | Endpoint | Trigger | Auth |
|-----------|----------|---------|------|
| Outbound | `https://api.tavily.com/search` (opt-in) | `NEWSAGENT_SEARCH_BACKEND=tavily` | `NEWSAGENT_SEARCH_TAVILY_API_KEY` |
| Outbound | `https://api.ollama.com/api/chat` (default LLM backend) | Every LLM call | `NEWSAGENT_LLM_OLLAMA_API_KEY` (or none for local server) |
| Outbound | `https://opencode.ai/zen/go/v1/chat/completions` | `NEWSAGENT_LLM_BACKEND=opencode_go` | `NEWSAGENT_LLM_OPENCODE_GO_API_KEY` |
| Outbound | `https://<host>/chat/completions` | `NEWSAGENT_LLM_BACKEND=openai` | `NEWSAGENT_LLM_OPENAI_API_KEY` |
| Outbound | `https://<collector host>/...` (15+ sources) | Every run | Optional `NEWSAGENT_COLLECTOR_GITHUB_TOKEN`, `NEWSAGENT_COLLECTOR_CONTEXT7_API_KEY` |
| Outbound | `https://api.x.com/...` (opt-in) | `x_twitter` collector enabled | `NEWSAGENT_X_BEARER_TOKEN` |
| Inbound | None | — | — |

**There is no inbound HTTP server in `newsagent`.** The optional
`api = ["fastapi", "uvicorn"]` extra in `pyproject.toml` is declared
but not used by any source file; do not expose it without adding
authentication and a reverse proxy in front.

---

## Credential handling

newsagent reads credentials from environment variables (prefixed
`NEWSAGENT_`) and `.env` (which is `.gitignore`d). The CLI never logs
secret values, never writes them to disk, and never includes them in
`storage/run_manifests/*.json` (only `sources_checked_json` and
`sources_failed_json` — collector *names*, not secrets).

**What you must do:**

1. Keep `.env` out of git. The repo's `.gitignore` already excludes it.
2. If you fork newsagent and publish your own fork, do not commit a
   real `.env`. Copy from `.env.example`.
3. When you switch LLM backends (e.g. from local Ollama to OpenCode
   Go), rotate or delete the credentials you no longer need.
4. Treat `storage/newsagent.db` as sensitive: the `lessons` table
   may contain excerpts from your previous reports. If you publish the
   repo, do not publish `storage/`.

**What newsagent will not do for you:**

- It will not refuse to run with an empty API key. A missing LLM key
  falls through to the heuristic fallback (`ProviderResult(text="")`)
  so a report is always produced. If you want the run to *fail* on
  missing credentials, set
  `NEWSAGENT_LLM_ALLOW_HEURISTIC_FALLBACK=false` in `.env`.
- It will not redact PII from sources. If a source contains a personal
  email or a private key (it happens in HN comments and Reddit posts),
  the report will quote it. If this matters to you, add a sanitizer
  pass to `pipeline/sanitizer.py` (the sanitization module already
  exists; extend it as needed).

---

## Output handling

Reports are written to `storage/reports/` (configurable via
`NEWSAGENT_STORAGE_DIR`). They are plain Markdown and contain:

- Quoted text from public web sources, with inline citations.
- Tables comparing models, papers, funding rounds, and chips.
- A "References" block of cited URLs.

The Obsidian sink (`MarkdownFileSink` + `ObsidianSink` in
`output.py`) copies the rendered report to a directory you choose
(`NEWSAGENT_STORAGE_OBSIDIAN_VAULT`). If you point it at a public
Obsidian vault, the report becomes public. Do not enable the
Obsidian sink for reports containing unpublished research, internal
funding figures, or unredacted executive names.

---

## What is **not** in scope

- **Multi-tenant isolation.** newsagent has one operator. Do not run
  it as a shared service.
- **Prompt-injection defense beyond heuristics.** Collector responses
  are passed to the LLM as raw text. The Critic LLM is asked to reject
  planning leaks, but it is not a guarantee. A malicious source page
  *can* try to influence the report. For high-stakes reports, eyeball
  the citations before shipping.
- **Rate-limit self-defense.** Each collector enforces its own
  retry-once + skip-on-failure; newsagent does not implement global
  back-pressure across sources. If you hit GitHub's 60 req/hr limit on
  unauthenticated calls, add a `NEWSAGENT_COLLECTOR_GITHUB_TOKEN` to
  lift it to 5,000 req/hr.
- **Output auditing.** The CLI does not sign reports. If you need an
  audit trail, add a hash to the run manifest and pin
  `storage/newsagent.db` in a write-once store.

---

## Reporting a vulnerability

newsagent is a portfolio project without a paid security team. If you
find a vulnerability, open a GitHub issue with the label `security`
or email the author (see `self.md` in the workspace root). Do not
file a public issue that includes a working exploit against a
production deployment.
