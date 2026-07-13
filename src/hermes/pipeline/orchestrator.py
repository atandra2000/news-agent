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
from hermes.pipeline.search import SearchProvider, SearchResult, build_search_provider, dedup_sources
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
) -> list[SearchResult]:
    """Pull from free collectors when Tavily returns nothing."""
    from hermes.collectors.registry import run_collector

    out: list[SearchResult] = []
    for name in _FALLBACK_COLLECTORS:
        try:
            items = await run_collector(name, since=since, limit=20, timeout=20)
        except Exception as exc:  # noqa: BLE001
            log.warning("fallback_collector_failed", name=name, error=str(exc))
            continue
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
    return out


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
) -> str:
    """Synthesize one section with RAG context + critic loop + CoT backstop."""
    from hermes.pipeline.report import drop_empty_subheadings
    from hermes.pipeline.sanitizer import sanitize_text
    from hermes.pipeline.synthesize import extract_prose

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
    cad = resolve_cadence(settings.cadence)
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
        year=year, cadence=settings.cadence,
    )
    log.info("planned", queries=len(queries), sections=len(spec.sections), cadence=settings.cadence)

    # Search.
    sources: list[SearchResult] = await _gather_sources(queries, search, max_sources=cad.sources * 5)
    log.info("searched", sources=len(sources))

    if not sources:
        log.warning("search_empty_fallback_collectors")
        since = run_date - timedelta(days=cad.days)
        fb = await _gather_sources_fallback(since, max_sources=cad.sources * 5)
        sources = dedup_sources(fb, limit=cad.sources * 5)
        log.info("fallback_used", sources=len(sources))

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

    # Parallel synthesis.
    semaphore = asyncio.Semaphore(settings.pipeline.section_concurrency)
    max_tokens = cad.max_tokens
    tasks = [
        _synthesize_section_parallel(
            sec, sources, rag_chunks, embedder, router, search, spec, settings,
            cad, date_label, cadence_note, per_section_sources, extra_queries,
            year, True, semaphore, max_tokens=max_tokens,
        )
        for sec in spec.sections
    ]
    sections_md = await asyncio.gather(*tasks)

    report = assemble_report(spec, list(sections_md), sources)

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
                    sources_checked_json=json.dumps([]),
                    sources_failed_json=json.dumps([]),
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
