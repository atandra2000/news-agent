"""Score reports against prompts on four dimensions (coverage, citation
integrity, quality adherence, cadence) via the critic LLM; persist to SQLite.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from hermes.pipeline.spec import BriefSpec, parse_prompt
from hermes.llm.router import LLMRouter
from hermes.logging import get_logger
from hermes.storage.db import Store
from hermes.storage.models import ReportEval

log = get_logger("pipeline.eval")

_CITATION_RE = re.compile(r"\[src:[^\]]+\]")
_SECTION_RE = re.compile(r"^##\s+\*?\*?(\d+\.\s+.+?)\*?\*?\s*$", re.MULTILINE)


@dataclass
class EvalVerdict:
    """Evaluation result for a report."""

    report_path: str
    prompt_path: str
    cadence: str
    coverage_score: float  # 0.0-1.0
    citation_score: float  # 0.0-1.0
    quality_score: float  # 0.0-1.0
    cadence_score: float  # 0.0-1.0
    overall_score: float  # 0.0-1.0
    feedback: str
    run_date: datetime
    token_usage: int


def _build_eval_prompt(
    report_text: str,
    spec: BriefSpec,
    cadence: str,
) -> str:
    """Build the critic LLM eval prompt."""
    deliverables = "\n".join(f"- {d}" for d in spec.deliverables) if spec.deliverables else "(none specified)"
    quality = "\n".join(f"- {q}" for q in spec.quality) if spec.quality else "(none specified)"
    cadence_window = {
        "daily": "the last 24 hours",
        "weekly": "the past 7 days",
        "monthly": "the past 30 days",
    }.get(cadence, "the last 24 hours")

    return f"""You are a critical editor evaluating an AI industry report.

REPORT:
{report_text}

PROMPT REQUIREMENTS:
Title: {spec.title}

Required Deliverables (must all be present):
{deliverables}

Quality Bar:
{quality}

Cadence: Focus EXCLUSIVELY on developments from {cadence_window}.

EVALUATE ON FOUR DIMENSIONS (0.0-1.0 each):

1. COVERAGE: Does the report cover all required deliverables? Are all sections present and comprehensive?
2. CITATION INTEGRITY: Are factual claims properly cited with [src:URL] tokens? Are there uncited claims? Is the citation density sufficient?
3. QUALITY ADHERENCE: Does the report meet the quality bar (synthesize vs summarize, quantify where possible, distinguish fact/analysis, information-dense)?
4. CADENCE: Does the report respect the time window? Are there claims outside the cadence? Is the focus appropriate?

OUTPUT JSON ONLY (no markdown fences):
{{
  "coverage_score": 0.0-1.0,
  "citation_score": 0.0-1.0,
  "quality_score": 0.0-1.0,
  "cadence_score": 0.0-1.0,
  "overall_score": 0.0-1.0,
  "feedback": "detailed feedback on strengths and weaknesses"
}}"""


def _count_citations(text: str) -> int:
    """Count unique [src:URL] citations."""
    return len(set(_CITATION_RE.findall(text)))


def _count_sections(text: str) -> int:
    """Count ## sections in text."""
    return len(_SECTION_RE.findall(text))


async def evaluate_text(
    report_text: str,
    spec: BriefSpec,
    *,
    router: LLMRouter,
    cadence: str = "daily",
    report_path: str = "",
    prompt_path: str = "",
) -> EvalVerdict:
    """Score report text against a parsed spec — pure, no file I/O or persistence.

    Split out from ``evaluate_report`` so the cognition core (and tests) can score
    an in-memory report without reading files or opening a store. The shim below
    handles file reading + persistence.
    """
    eval_prompt = _build_eval_prompt(report_text, spec, cadence)
    verdict_json = await router.json_complete("critic", eval_prompt)

    coverage = float(verdict_json.get("coverage_score", 0.5))
    citation = float(verdict_json.get("citation_score", 0.5))
    quality = float(verdict_json.get("quality_score", 0.5))
    cadence_score = float(verdict_json.get("cadence_score", 0.5))
    overall = float(verdict_json.get("overall_score", 0.5))
    feedback = verdict_json.get("feedback", "")

    return EvalVerdict(
        report_path=report_path,
        prompt_path=prompt_path,
        cadence=cadence,
        coverage_score=coverage,
        citation_score=citation,
        quality_score=quality,
        cadence_score=cadence_score,
        overall_score=overall,
        feedback=feedback,
        run_date=datetime.now(timezone.utc),
        token_usage=router.stats.total_tokens,
    )


async def evaluate_report(
    report_path: str | Path,
    prompt_path: str | Path,
    *,
    router: LLMRouter,
    store: Store,
    cadence: str = "daily",
) -> EvalVerdict:
    """Evaluate a report against a prompt and store the verdict (file-reading shim)."""
    report_path = Path(report_path)
    prompt_path = Path(prompt_path)

    if not report_path.exists():
        raise FileNotFoundError(f"Report not found: {report_path}")
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt not found: {prompt_path}")

    report_text = report_path.read_text(encoding="utf-8")
    spec = parse_prompt(prompt_path.read_text(encoding="utf-8"))

    verdict = await evaluate_text(
        report_text,
        spec,
        router=router,
        cadence=cadence,
        report_path=str(report_path),
        prompt_path=str(prompt_path),
    )

    await _store_eval(store, verdict)

    log.info(
        "pipeline.eval_done",
        report=str(report_path),
        coverage=verdict.coverage_score,
        citation=verdict.citation_score,
        quality=verdict.quality_score,
        cadence=verdict.cadence_score,
        overall=verdict.overall_score,
    )

    return verdict


async def _store_eval(store: Store, verdict: EvalVerdict) -> None:
    """Store an eval verdict in the report_evals table."""
    async with store.session() as session:
        eval_row = ReportEval(
            report_path=verdict.report_path,
            prompt_path=verdict.prompt_path,
            cadence=verdict.cadence,
            coverage_score=verdict.coverage_score,
            citation_score=verdict.citation_score,
            quality_score=verdict.quality_score,
            cadence_score=verdict.cadence_score,
            overall_score=verdict.overall_score,
            feedback=verdict.feedback,
            token_usage=verdict.token_usage,
            run_date=verdict.run_date,
        )
        session.add(eval_row)
        await session.commit()


async def get_rolling_scores(
    store: Store,
    prompt_path: str,
    *,
    limit: int = 5,
) -> dict[str, float]:
    """Get rolling average scores for a prompt over the last N evals."""
    from sqlalchemy import select

    async with store.session() as session:
        stmt = (
            select(ReportEval)
            .where(ReportEval.prompt_path == prompt_path)
            .order_by(ReportEval.run_date.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        evals = result.scalars().all()

    if not evals:
        return {}

    n = len(evals)
    return {
        "coverage": sum(e.coverage_score for e in evals) / n,
        "citation": sum(e.citation_score for e in evals) / n,
        "quality": sum(e.quality_score for e in evals) / n,
        "cadence": sum(e.cadence_score for e in evals) / n,
        "overall": sum(e.overall_score for e in evals) / n,
    }
