# Contributing to newsagent

newsagent is an autonomous AI research-intelligence agent: it collects from
multiple sources, plans per-section research, runs an LLM-driven
synthesize→critic→rewrite loop, and renders a citation-backed report from a
prompt. This guide covers how to set up the environment, run the checks, and
extend the system.

---

## 1. Development environment

newsagent uses a `src/` layout and is installed as an editable package. A local
virtualenv (`.venv`) is required — the base system `python`/`python3` on this
machine does **not** have `structlog` and will fail at import time.

```bash
cd newsagent
python -m venv .venv
.venv/bin/pip install -e ".[dev,embed,api]"
```

- `dev` — pytest, pytest-asyncio, respx, ruff, mypy
- `embed` — `sentence-transformers` (semantic embeddings; falls back to hashing
  if absent)
- `api` — FastAPI/uvicorn (only needed for the optional `newsagent serve` API)

Verify the install:

```bash
.venv/bin/python -c "import newsagent; print('ok')"
```

---

## 2. Running the checks

All checks run inside `.venv`. **Do not** use bare `python`/`python3`.

```bash
# Tests (191 passing, async mode auto)
.venv/bin/python -m pytest

# Single test file
.venv/bin/python -m pytest tests/unit/test_llm.py

# Lint
.venv/bin/ruff check src tests

# Type check
.venv/bin/mypy src
```

> **Shell glob note:** `ruff --include=*.py` does not expand correctly under
> zsh. Pass paths explicitly (`ruff check src tests`) rather than a glob.

Tests are offline by default — collectors and LLM calls are mocked with
`respx`/`unittest.mock`. A run that hits the network is a test bug.

---

## 3. Project layout

```
src/newsagent/
  cli.py                 # entrypoint (newsagent news / sources / quality)
  config.py              # pydantic-settings; env vars NEWSAGENT_*
  profiles.py            # 5 report profiles
  collectors/            # source adapters + registry
  storage/               # db.py, models.py, vectorstore.py
  llm/                   # router, providers, roles, embed, prompts/
  pipeline/
    orchestrator.py      # SOLE production entrypoint: run_news_pipeline
    spec.py              # parse_prompt(md) -> BriefSpec
    planner.py           # section / source query planning
    search.py            # SearchProvider (Tavily / 7 free collectors fallback)
    retrieve.py          # evidence retrieval
    synthesize.py        # synthesize_section_with_review (synth → critic → rewrite)
    report.py            # resolve_citations + assemble_report
    eval.py              # evaluate_report (coverage · citation · quality · cadence)
    cadence.py           # cadence-scaled token budgeting
    sanitizer.py         # line-level cleanup (CoT / fabrication / empty sections)
    context.py           # PipelineContext (in-memory artifacts)
tests/                   # mirrors src/; offline
docs/                    # architecture / config / pipeline / collectors / storage
```

Notes on the recent unification: the prior `brief/`, `analyzers/`, and
`renderers/` packages were collapsed into the single `pipeline/` package; the
dual `newsagent run` + `newsagent news` commands were unified onto
`newsagent news <prompt.md>`. See `docs/ARCHITECTURE.md` for the current map and
the rationale.

---

## 4. Architecture conventions

- **Stages are pure-ish functions** that take `PipelineContext` and return a
  value (or mutate the context). Keep them side-effect-light and testable.
- **Intermediate artifacts are in-memory.** Evidence, claims, and
  intermediate synthesis results live in `PipelineContext` and are **not**
  persisted. Only a handful of tables are written by the pipeline: `items`,
  `item_aliases`, `vectors`, `trend_snapshots`, `reports`, `lessons`. (See
  `docs/STORAGE.md`.)
- **Review ≠ writing.** The critic stage is review-only; the synthesizer
  stage is the only prose producer. Do not merge these roles.
- **Bounded loops.** Any critic/rewrite loop must have a hard cap
  (`max_iterations`, `_MAX_CRITIC_RETRIES`). Never introduce an unbounded
  LLM loop.
- **Type hints everywhere.** Every function is fully typed. `mypy` must pass.

---

## 5. Adding a collector

1. Create `src/newsagent/collectors/<name>.py` subclassing `CollectorAdapter`.
2. Register it in `src/newsagent/collectors/registry.py` (`REGISTRY` dict).
3. Add it to the `CollectorConfig.enabled` default in `config.py` **only if** it
   has a stable, authenticated endpoint. (`reddit` and `papers_with_code` are
   intentionally excluded — their public web APIs are unreliable.)
4. Add an offline test under `tests/collectors/` using `respx`.
5. Document it in `docs/COLLECTORS.md`.

See `docs/COLLECTORS.md` §5 for a worked example.

---

## 6. Adding a profile

Add an entry to `PROFILES` in `src/newsagent/profiles.py`. Profiles override
`settings.pipeline.*` and select a subset of the legacy 18-renderer `sections`.
No pipeline code changes are needed. Document new profiles in
`docs/CONFIGURATION.md` §9.

---

## 7. Documentation

- Source-of-truth docs live in `docs/` (README, ARCHITECTURE, CONFIGURATION,
  PIPELINE, COLLECTORS, STORAGE).
- Keep docs in sync with code. If you change a stage, collector count, profile,
  or persisted table, update the corresponding doc.
- The root `README.md` is the GitHub landing page — keep it accurate and
  recruiter-friendly.

---

## 8. Commit & PR conventions

- Small, focused commits. One logical change per commit.
- Keep `ruff` and `pytest` green before pushing.
- PRs should describe the *why* (root-cause / design decision), not just the
  *what*.
- Reference the relevant `docs/` section when changing behavior.
