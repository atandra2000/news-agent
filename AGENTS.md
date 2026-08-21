# AGENTS.md — news-agent

> Read root `AGENTS.md` and `self.md` first. Workspace rules are
> authoritative; this file adds project-specific rules only.

> **Project:** `news-agent/` · **Type:** autonomous research-intel agent ·
> **Stats:** 291 tests (all collecting green) · **Stack:** Python 3.12,
> pydantic v2, structlog, Qdrant (`qdrant-client`), pytest.
> Deep dives live in `docs/` (ARCHITECTURE, COLLECTORS, CONFIGURATION,
> COST, LLM_PROVIDERS, PERFORMANCE, PIPELINE, SECURITY, STORAGE,
> TESTING); day-to-day rules live here.

## Quick checks (run before claiming work is done)

```bash
cd news-agent
.venv/bin/python -m pytest tests/ -q        # 291 tests
```

> **Environment note:** bare `python3 -m pytest` uses the system Python and
> fails on `structlog`; the project `.venv` is the only supported runner.
> Prefix with `env -u PYTHONPATH` inside Hermes GUI shells (venv-ABI quirk).

## Layout

- `src/newsagent/` — package source; `src/newsagent/collectors/` holds the
  source collectors (one module per feed/source family).
- `tests/` — unit + orchestrator tests (`tests/helpers.py` has shared fakes).
- `docs/` — canonical documentation tree; `README.md`, `CONTRIBUTING.md`,
  `CHANGELOG.md` at root. Runtime dumps land in `prompts/` and
  `storage/reports/` — never commit those, never mirror them to the vault.

## Hard rules

1. **Raw Python + pydantic v2 contracts.** No framework web servers; the
   agent is a pipeline, not a service.
2. **Collectors stay isolated:** one collector per source, no cross-imports;
   new sources follow `tests/unit/test_new_collectors.py` patterns.
3. **Never reduce below 291 passing tests**; add a test for every new
   collector or config key.
4. **Secrets live in env/config only** — never hardcode API keys in
   collectors (see `docs/SECURITY.md`).
5. **Vault whitelist:** only `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`,
   and direct children of `docs/*.md` mirror to Obsidian
   (`Agentic/NewsAgent/…`). Everything else is excluded by
   `scripts/sync_to_vault.sh`.
