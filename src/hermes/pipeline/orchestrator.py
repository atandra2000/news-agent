"""The unified Hermes orchestrator: parse a brief, plan queries, search, and synthesize each section in parallel."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hermes.config import HermesSettings, load_settings
from hermes.llm.embed import Embedder
from hermes.llm.providers.registry import build_registry
from hermes.llm.router import LLMRouter
from hermes.logging import get_logger
from hermes.output import build_sinks
from hermes.pipeline.adapter import PromptAdapter
from hermes.pipeline.cadence import CadenceSpec, resolve_cadence
from hermes.pipeline.planner import plan_queries
from hermes.pipeline.report import assemble_report
from hermes.pipeline.retrieval import embed_chunks, format_rag_context, load_past_reports, retrieve_similar
from hermes.pipeline.search import (
    SearchProvider,
    SearchResult,
    build_search_provider,
    dedup_sources,
    dedup_sources_with_cross_posts,
    duplication_collapse_rate,
)
from hermes.pipeline.spec import BriefSpec
from hermes.pipeline.synthesize import (
    _SECTION_MIN_WORDS,
    _content_word_count,
    clean_section_text,
    count_citations,
    select_relevant,
    synthesize_section,
    synthesize_section_with_review,
)
from hermes.storage.db import Store

log = get_logger("orchestrator")


_FALLBACK_COLLECTORS = (
    "arxiv",
    "hacker_news",
    "github_trending",
    "huggingface",
    "semantic_scholar",
    "devto",
    "lobsters",
)


def _build_router(settings: HermesSettings) -> LLMRouter:
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
) -> tuple[list[SearchResult], list[str], list[str]]:
    """Pull from free collectors when Tavily returns nothing.

    Returns ``(results, sources_checked, sources_failed)`` so the orchestrator
    can persist real observability data into the run manifest. Previously
    fallback path always recorded ``[]`` for both fields, hiding which
    collectors actually ran.
    """
    from hermes.collectors.registry import run_collector

    out: list[SearchResult] = []
    sources_checked: list[str] = []
    sources_failed: list[str] = []
    for name in _FALLBACK_COLLECTORS:
        try:
            items = await run_collector(name, since=since, limit=20, timeout=20)
        except Exception as exc:  # noqa: BLE001
            log.warning("fallback_collector_failed", name=name, error=str(exc))
            sources_failed.append(name)
            continue
        sources_checked.append(name)
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
    return out, sources_checked, sources_failed


async def _synthesize_section_parallel(
    sec,
    sources,
    rag_chunks,
    embedder,
    router: LLMRouter,
    search: SearchProvider,
    spec: BriefSpec,
    settings: HermesSettings,
    cad: CadenceSpec,
    date_label: str,
    cadence_note: str,
    per_section_sources: int,
    extra_queries: int,
    year: str,
    search_enabled: bool,
    semaphore: asyncio.Semaphore,
    max_tokens: int = 5000,
    coverage_verdict: str | None = None,
) -> str:
    """Synthesize one section with RAG context + critic loop + CoT backstop.

    ``coverage_verdict`` is one of "OK" / "THIN" / "CRITICAL" / None (unknown).
    CRITICAL sections are short-circuited to a transparent "section omitted"
    marker — the writer cannot synthesize from nothing, and we don't want to
    burn an LLM call on a doomed attempt. THIN sections proceed but the writer
    is told the corpus is thin so it can be honest about gaps.
    """
    from hermes.pipeline.report import drop_empty_subheadings
    from hermes.pipeline.sanitizer import sanitize_text
    from hermes.pipeline.synthesize import extract_prose

    # Short-circuit CRITICAL: no useful evidence for this section. Drop it
    # transparently instead of forcing the writer to invent.
    if coverage_verdict == "CRITICAL":
        log.warning("section_critical_drop", section=sec.number, title=sec.title)
        return (
            f"## **{sec.number}. {sec.title}**\n\n"
            f"_Section omitted: source coverage verdict is CRITICAL "
            f"(insufficient retrieved evidence to write a real analysis for this section)._"
        )

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


async def run_news_pipeline(
    spec: BriefSpec,
    *,
    settings: HermesSettings | None = None,
    router: LLMRouter | None = None,
    search: SearchProvider | None = None,
    out_path: Path | None = None,
    brief_path: str | Path | None = None,
) -> Path:
    """The one Hermes production command. Run a parsed brief end to end."""
    settings = settings or load_settings()
    # Cadence precedence: prompt body > HERMES_CADENCE env > "daily".
    # parse_prompt already detected cadence from the brief; use that as the
    # authoritative source so a "monthly" brief gets a 30-day lookback even
    # if the env is set to "daily".
    effective_cadence = spec.cadence or settings.cadence
    cad = resolve_cadence(effective_cadence)
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
    year = str(run_date.year)
    queries = plan_queries(
        spec, per_section=cad.per_section, source_queries=cad.sources,
        year=year, cadence=effective_cadence,
    )
    log.info("planned", queries=len(queries), sections=len(spec.sections), cadence=effective_cadence)

    # Search.
    sources: list[SearchResult] = []
    sources_checked: list[str] = []
    sources_failed: list[str] = []
    raw_count = 0
    cross_post_groups: list[list[SearchResult]] = []
    try:
        raw = await _gather_sources(queries, search, max_sources=cad.sources * 5)
        raw_count = len(raw)
        # URL-dedup + cross-post-dedup. Cat's-grant-style HN reposts (3 IDs,
        # same story) collapse to one signal here; the cross_post_groups list
        # tells the writer to cite once and note "cross-posted N times".
        sources, cross_post_groups = dedup_sources_with_cross_posts(raw, limit=cad.sources * 5)
        sources_checked.append(search.__class__.__name__)
        collapse_rate = duplication_collapse_rate(raw_count, len(sources))
        log.info(
            "searched",
            raw=raw_count, deduped=len(sources), collapse_rate=round(collapse_rate, 3),
            cross_post_groups=len(cross_post_groups),
        )
    except Exception as exc:  # noqa: BLE001
        sources_failed.append(search.__class__.__name__)
        log.warning("search_failed", error=str(exc))

    if not sources:
        log.warning("search_empty_fallback_collectors")
        since = run_date - timedelta(days=cad.days)
        fb, fb_checked, fb_failed = await _gather_sources_fallback(since, max_sources=cad.sources * 5)
        # Apply the same cross-post dedup to fallback-collected items; the
        # Cat's-grant HN items would otherwise slip through the fallback path
        # un-collapsed.
        fb_deduped, fb_cross_posts = dedup_sources_with_cross_posts(fb, limit=cad.sources * 5)
        sources = fb_deduped
        cross_post_groups.extend(fb_cross_posts)
        sources_checked.extend(fb_checked)
        sources_failed.extend(fb_failed)
        collapse_rate = duplication_collapse_rate(len(fb), len(sources))
        log.info(
            "fallback_used",
            sources=len(sources), checked=len(fb_checked), failed=len(fb_failed),
            collapse_rate=round(collapse_rate, 3),
            cross_post_groups=len(fb_cross_posts),
        )

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

    # Coverage verdicts: per-section OK/THIN/CRITICAL classification based on
    # the retrieved corpus. Drives both writer-prompt honesty and CRITICAL
    # short-circuit (no LLM call when there's nothing to write about).
    from hermes.pipeline.coverage import evaluate_coverage
    verdicts = evaluate_coverage(spec, sources)
    verdict_by_num = {v.section_number: v for v in verdicts}
    log.info(
        "coverage_verdicts",
        ok=sum(1 for v in verdicts if v.verdict == "OK"),
        thin=sum(1 for v in verdicts if v.verdict == "THIN"),
        critical=sum(1 for v in verdicts if v.verdict == "CRITICAL"),
    )

    # Parallel synthesis.
    semaphore = asyncio.Semaphore(settings.pipeline.section_concurrency)
    max_tokens = cad.max_tokens
    tasks = [
        _synthesize_section_parallel(
            sec, sources, rag_chunks, embedder, router, search, spec, settings,
            cad, date_label, cadence_note, per_section_sources, extra_queries,
            year, True, semaphore, max_tokens=max_tokens,
            coverage_verdict=verdict_by_num.get(sec.number).verdict if sec.number in verdict_by_num else None,
        )
        for sec in spec.sections
    ]
    sections_md = await asyncio.gather(*tasks)

    report = assemble_report(spec, list(sections_md), sources, verdicts=verdicts)

    if out_path is None:
        from hermes.pipeline.spec import brief_slug

        out_path = settings.reports_dir / f"{brief_slug(spec)}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report.text, encoding="utf-8")

    meta = {"date": run_date.strftime("%Y-%m-%d"), "profile": "news", "path": str(out_path)}
    for sink in build_sinks(settings):
        try:
            await sink.deliver(report.text, meta)
        except Exception as exc:  # noqa: BLE001
            log.warning("sink.failed", sink=getattr(sink, "?", None), error=str(exc))

    # Persist a Report row.
    try:
        store = Store(settings.sqlite_url)
        await store.init()
        from hermes.storage.models import Report

        async with store.session() as session:
            await session.merge(
                Report(
                    run_date=run_date, path=str(out_path),
                    md_sha256=hashlib.sha256(report.text.encode("utf-8")).hexdigest(),
                    sections_count=len(spec.sections),
                    items_analyzed=len(sources),
                    # Plumb the actual collectors/queries that ran — was hardcoded
                    # to json.dumps([]) before, hiding observability gaps.
                    sources_checked_json=json.dumps(sorted(set(sources_checked))),
                    sources_failed_json=json.dumps(sorted(set(sources_failed))),
                    # Fraction of raw sources dropped as URL or cross-post dupes.
                    # 0.0 means no dedup, 1.0 means all raw results were dupes.
                    duplication_collapse_rate=duplication_collapse_rate(
                        raw_count + sum(len(g) for g in cross_post_groups),
                        len(sources),
                    ),
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
    from hermes.pipeline.planner import ResearchQuery

    queries = [ResearchQuery(f"{section.title} {year}", section.title, "section")]
    for bullet in section.bullets[:count]:
        queries.append(ResearchQuery(f"{section.title}: {bullet} {year} AI", section.title, "section"))
    return queries[:count]
