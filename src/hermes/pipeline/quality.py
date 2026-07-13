"""Self-assessment quality loop (internal, Ollama-Pro-only).

Self-scores the day's report on six dimensions via an LLM judge (lexical
heuristic fallback) and persists improvement notes to the ``lessons`` table.
No external baseline model — stays on Ollama Pro.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime

from hermes.logging import get_logger
from hermes.pipeline.context import RunContext
from hermes.storage.models import Lesson

log = get_logger("pipeline.quality")

RUBRIC = [
    "coverage",
    "accuracy_verification",
    "depth",
    "synthesis",
    "usefulness",
    "trust",
]


@dataclass
class QualityReport:
    run_date: str
    hermes_score: float = 0.0
    per_dimension: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    path: str = ""


def _heuristic_scores(text: str) -> dict:
    """Offline rubric scorer (1-5) from lexical signals. Used when the LLM judge
    is unavailable, and as a sanity baseline."""
    scores: dict[str, float] = {}
    links = len(re.findall(r"https?://", text))
    scores["coverage"] = min(5.0, 1.0 + links / 15.0)
    badges = len(re.findall(r"(corroborated|conflicting|single-source)", text, re.I))
    scores["accuracy_verification"] = min(5.0, 1.0 + badges / 4.0)
    scores["depth"] = min(5.0, 1.0 + len(text) / 4000.0)
    scores["synthesis"] = 4.0 if "Emerging Trends" in text or "Theme clusters" in text else 2.0
    scores["usefulness"] = 4.0 if ("Practical Takeaways" in text or "Engineering Insights" in text) else 2.0
    scores["trust"] = 4.0 if ("Coverage & Method" in text or "References" in text) else 2.0
    return scores


async def judge(ctx: RunContext, hermes_text: str) -> dict:
    """Self-assessment of Hermes' own report (no external baseline)."""
    prompt = (
        "You are a strict self-evaluator. Score THIS report on six dimensions (1-5, 5 best): "
        + ", ".join(RUBRIC)
        + ". Also give 3 concrete improvement notes. Return STRICT JSON: "
        '{"scores": {dim: score}, "notes": [str]}. Return ONLY JSON.\n\n'
        f"=== REPORT ===\n{hermes_text[:6000]}"
    )
    data = await ctx.router.json_complete("critic", prompt)
    if data and data.get("scores"):
        notes = data.get("notes", [])
        return {"scores": data["scores"], "notes": notes if isinstance(notes, list) else []}
    # Heuristic fallback.
    scores = _heuristic_scores(hermes_text)
    return {
        "scores": scores,
        "notes": ["LLM judge unavailable (rate-limited); used heuristic rubric."],
    }


async def run_quality(ctx: RunContext, run_date: datetime, settings) -> QualityReport:
    hermes_path = settings.reports_dir / f"{run_date.strftime('%Y-%m-%d')}.md"
    hermes_text = hermes_path.read_text(encoding="utf-8", errors="ignore") if hermes_path.exists() else None

    if not hermes_text:
        rep = QualityReport(run_date=run_date.strftime("%Y-%m-%d"), notes=["No report found for date."])
        rep.path = str(hermes_path)
        return rep

    verdict = await judge(ctx, hermes_text)
    scores = verdict.get("scores", {})
    total = sum(scores.values()) / max(len(scores), 1)

    rep = QualityReport(
        run_date=run_date.strftime("%Y-%m-%d"),
        hermes_score=round(total, 2),
        per_dimension=scores,
        notes=verdict.get("notes", []),
    )

    # Persist improvement notes into self-improving memory (batched).
    if rep.notes:
        async with ctx.store.session() as s:
            for note in rep.notes:
                s.add(Lesson(run_date=run_date, kind="quality", text=note))
            await s.commit()

    out = settings.storage.dir / "quality"
    out.mkdir(parents=True, exist_ok=True)
    qpath = out / f"{rep.run_date}.md"
    qpath.write_text(_render_quality(rep), encoding="utf-8")
    rep.path = str(qpath)

    (out / f"{rep.run_date}.json").write_text(json.dumps(rep.__dict__, indent=2), encoding="utf-8")
    log.info("quality.done", score=rep.hermes_score, notes=len(rep.notes))
    return rep


def _render_quality(rep: QualityReport) -> str:
    lines = [f"# Hermes Quality Report — {rep.run_date}", ""]
    lines.append(f"- **Self-score:** {rep.hermes_score}/5")
    lines.append("")
    lines.append("## Per-dimension")
    lines.append("| Dimension | Score |")
    lines.append("|---|---|")
    for dim in RUBRIC:
        lines.append(f"| {dim} | {rep.per_dimension.get(dim, '-')} |")
    lines.append("")
    lines.append("## Improvement notes (persisted to memory)")
    for n in rep.notes:
        lines.append(f"- {n}")
    return "\n".join(lines) + "\n"
