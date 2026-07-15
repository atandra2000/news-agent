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
    # Build RunContext inline for the quality self-check.
    from newsagent.llm.embed import Embedder
    from newsagent.llm.providers.registry import build_registry
    from newsagent.llm.router import LLMRouter
    from newsagent.pipeline.context import RunContext
    from newsagent.pipeline.quality import run_quality
    from newsagent.storage.db import Store
    from newsagent.storage.vectorstore import build_vector_store

    date_str = args["opts"].get("date")
    run_date = _parse_date(date_str) if date_str else datetime.now(timezone.utc)
    store = Store(settings.sqlite_url)
    asyncio.run(store.init())
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
    embedder = Embedder(
        model=settings.embed.model, dim=settings.embed.dim, normalize=settings.embed.normalize,
    )
    vectorstore = build_vector_store(
        settings.storage.vector_backend,
        store.session_factory,
        qdrant_path=str(settings.qdrant_path),
        collection=settings.storage.qdrant_collection,
        dim=settings.embed.dim,
    )
    ctx = RunContext(
        settings=settings, store=store, router=router,
        embedder=embedder, vectorstore=vectorstore, run_date=run_date,
    )
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
