"""Assemble the final report Markdown and resolve ``[src:URL]`` citations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from hermes.pipeline.sanitizer import is_synthesis_failure_stub
from hermes.pipeline.search import SearchResult
from hermes.pipeline.spec import BriefSpec

_SRC_RE = re.compile(r"\[src:(.*?)\]")
_URL_CLEAN = re.compile(r"[)\]\.,;>\s]+$")


def _clean_url(u: str) -> str:
    return _URL_CLEAN.sub("", u.strip().strip("`"))


def resolve_citations(
    body: str,
    sources: list[SearchResult],
) -> tuple[str, list[SearchResult]]:
    """Rewrite ``[src:URL]`` tokens into ``[n]`` refs, numbered by first appearance.

    Returns ``(resolved_text, ordered_references)``.
    """
    known = {_clean_url(r.url): r for r in sources}
    order: list[SearchResult] = []
    index: dict[str, int] = {}

    def _repl(m: re.Match) -> str:
        url = _clean_url(m.group(1))
        ref = known.get(url)
        if ref is None:
            return ""
        if url not in index:
            order.append(ref)
            index[url] = len(order)
        return f"[{index[url]}]"

    resolved = _SRC_RE.sub(_repl, body)
    return resolved, order


def _references_markdown(refs: list[SearchResult]) -> str:
    if not refs:
        return ""
    lines = ["## **References**", ""]
    for i, r in enumerate(refs, 1):
        date = f" ({r.published_date})" if r.published_date else ""
        host = f" — {r.source}" if r.source else ""
        lines.append(f"[{i}] {r.title}{host}{date}: {r.url}")
    return "\n".join(lines)


@dataclass
class AssembledReport:
    title: str
    body: str
    references: list[SearchResult]
    text: str


# Fig-leaf citation labels the model emits when it has no real URLs: bare
# brackets with NO URL inside — "[Analyst assessment]", "[Analyst assessment,
# community sentiment]", "[community sentiment]", "[Analyst's Note]", and
# empty "[src]" / "[source]". ``resolve_citations`` only matches ``[src:URL]``,
# so these survive as literal prose unless we strip them first. The ``src`` /
# ``source`` branches require ``]`` immediately after (no colon), so a real
# ``[src:https://…]`` token is never matched here.
_LABEL_BRACKET_RE = re.compile(
    r"\s*\[(?:"
    r"analyst assessment[^\]]*"
    r"|community sentiment[^\]]*"
    r"|community opinion[^\]]*"
    r"|analyst'?s?\s*note[^\]]*"
    r"|analyst projection[^\]]*"
    r"|src\s*"
    r"|source\s*"
    r")\]",
    re.IGNORECASE,
)


# Unsourced-claim marker the writer is instructed to append when using
# parametric knowledge that isn't in the retrieved sources. Visible to
# readers so they can tell cited evidence from contextual filler.
_UNSOURCED_MARKER_RE = re.compile(
    r"\[unsourced\s*[—–-]\s*industry\s*knowledge\]",
    re.IGNORECASE,
)


def audit_citation_discipline(body: str) -> dict[str, int]:
    """Count cited vs unsourced-vs-unmarked sentences.

    Heuristic: split body into sentences, count how many contain a [src:URL]
    token vs an [unsourced — industry knowledge] marker vs neither. Sentences
    with NEITHER a citation NOR an unsourced marker are potential fabrications.

    Returns a small dict so callers (eval, reporter) can surface this in the
    manifest. The function is cheap; do not over-engineer.
    """
    # Strip citation/unsourced tokens before splitting to count them per sentence.
    # We split on `.!?` followed by whitespace, but ignore dots inside URLs/numbers.
    sentences = re.split(r"(?<=[.!?])\s+", body)
    cited = unsourced = unmarked = 0
    src_re = re.compile(r"\[src:[^\]]+\]")
    for s in sentences:
        if not s.strip():
            continue
        has_src = bool(src_re.search(s))
        has_unsourced = bool(_UNSOURCED_MARKER_RE.search(s))
        if has_src:
            cited += 1
        elif has_unsourced:
            unsourced += 1
        else:
            unmarked += 1
    return {"cited": cited, "unsourced": unsourced, "unmarked": unmarked, "total": cited + unsourced + unmarked}


# Maps deliverable keywords (lowercased) to required presence of a
# corresponding content element in the report. The 2026-07-13 monthly prompt
# listed "Model comparison matrix" / "Funding tables" / "Benchmark comparison
# tables" / "Key statistics" as required — but the report had only a
# competitor-comparison table inside §3 and a funding table inside §8, with
# no gate to surface the missing ones. The gate below is a soft check: if
# a deliverable is required, the report must contain at least one table OR
# a subheading whose text mentions the deliverable's keyword.
_DELIVERABLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "executive summary": ("## **1. executive", "## **1.", "## **executive"),
    "model comparison": ("model comparison", "| model", "| developer"),
    "funding table": ("funding", "| entity", "| amount"),
    "benchmark comparison": ("benchmark", "| benchmark"),
    "key statistics": ("key statistics",),
    "strategic conclusion": ("strategic conclusion",),
    "month timeline": ("timeline", "## **2.", "## **month"),
    "full analytical report": ("analytical", "## **"),
    "comparison matrix": ("comparison", "|"),
}


@dataclass
class DeliverableCheck:
    deliverable: str
    found: bool
    matched_keyword: str | None


def check_required_deliverables(
    deliverables: list[str],
    report_text: str,
) -> list[DeliverableCheck]:
    """Soft check: which deliverables have a matching element in the report?

    Returns a list with one entry per deliverable. The orchestrator's
    pre-write gate (see ``gate_required_deliverables``) consumes this and
    raises when any item is missing. The previous "render a tail block" use
    was removed in Task 4: a missing deliverable is a hard refusal, not a
    disclosure in a footer.
    """
    low = report_text.lower()
    checks: list[DeliverableCheck] = []
    for d in deliverables:
        d_low = d.lower().strip()
        # Find the best-matching keyword group for this deliverable.
        matched = None
        for keyword_group_key, candidates in _DELIVERABLE_KEYWORDS.items():
            if keyword_group_key in d_low:
                for c in candidates:
                    if c.lower() in low:
                        matched = c
                        break
                break
        # If no keyword group matched, do a direct substring search.
        if matched is None and d_low and d_low in low:
            matched = d_low
        checks.append(DeliverableCheck(deliverable=d, found=matched is not None, matched_keyword=matched))
    return checks


def gate_required_deliverables(
    deliverables: list[str] | None,
    report_text: str,
) -> None:
    """Pre-write gate. Raises PipelineRefusedError when any required deliverable
    is missing from the assembled report.

    The 2026-07-13 monthly report wrote a 'Required Deliverables' footer
    naming the missing items AFTER the file was already on disk — readers
    got a partial report with the gap disclosed only in a tail block. The
    gate now runs *before* ``out_path.write_text``: the contract is that
    shipping a report that omits a brief-mandated deliverable is a hard
    refusal, not a footnote.
    """
    if not deliverables:
        return
    from hermes.errors import PipelineRefusedError

    checks = check_required_deliverables(deliverables, report_text)
    missing = [c for c in checks if not c.found]
    if not missing:
        return
    names = ", ".join(c.deliverable for c in missing)
    raise PipelineRefusedError(
        f"refusing to write report: {len(missing)} required deliverable(s) "
        f"missing ({names}). Re-run with broader search/collectors or "
        f"loosen the brief's Required Deliverables."
    )


def thin_corpus_banner(
    *,
    total_sources: int,
    section_count: int,
    critical_sections: int,
    thin_threshold: int = 5,
) -> str:
    """Emit a thin-corpus banner at the top of a report when evidence is sparse.

    The 2026-07-13 monthly report had 20 sources for 13 sections → ~1.5/section,
    well below the bar for a real monthly industry brief. A banner at the top
    makes the limitation visible to readers, distinguishing it from a normal
    report where the absence of mention simply means nothing happened.

    Returns "" when the corpus is healthy; a short banner string otherwise.
    """
    if total_sources >= thin_threshold * section_count and critical_sections == 0:
        return ""
    per_section = total_sources / max(1, section_count)
    if total_sources < thin_threshold * section_count or critical_sections > 0:
        return (
            f"> ⚠️ **Thin-corpus run**: {total_sources} sources for {section_count} sections "
            f"(≈{per_section:.1f}/section); {critical_sections} section(s) omitted due to "
            f"insufficient evidence. Re-run with broader search/collectors for fuller coverage."
        )
    return ""


def format_coverage_summary(verdicts: list[tuple[str, str]]) -> str:
    """Render a one-line-per-section coverage table for the report footer.

    The orchestrator already computes per-section OK/THIN/CRITICAL verdicts
    and logs them as ``coverage_verdicts critical=N ok=N thin=N``. The 2026-07-13
    monthly report shipped without surfacing those verdicts in the rendered
    text — readers could not tell which sections were healthy and which were
    CRITICAL without re-running. This footer makes the verdict visible at the
    end of the report so the corpus quality is transparent at a glance.

    Returns "" when no verdicts are supplied (silent no-op).
    """
    if not verdicts:
        return ""
    lines = ["## Coverage Verdicts (per section)", ""]
    lines.append("| Section | Verdict |")
    lines.append("|---|---|")
    for title, verdict in verdicts:
        lines.append(f"| {title} | {verdict} |")
    return "\n".join(lines) + "\n"


def _strip_label_brackets(body: str) -> str:
    """Remove non-URL citation fig-leaves before citation resolution."""
    return _LABEL_BRACKET_RE.sub("", body)


_HEADING_LINE_RE = re.compile(r"^(#{1,6})\s+(.*)$")


_PLACEHOLDER_BODY_RE = re.compile(r"^[.\s…]*$")


def _is_placeholder_line(s: str) -> bool:
    """True for blank/ellipsis placeholder lines ('...', '…', '....')."""
    s = s.strip()
    return bool(s) and _PLACEHOLDER_BODY_RE.match(s) is not None


def drop_empty_subheadings(text: str) -> str:
    """Remove stub/malformed subheadings that carry no real body.

    Dropped:
    - Malformed headings with an empty title (``## **`` — bare asterisks).
    - Subheadings (level ≥ 3) whose first non-blank body line is another heading,
      EOF, or a placeholder (``...``/``…``) — i.e. a deliverable echoed as an
      empty stub. When a stub's body starts with placeholder lines, those
      placeholder lines are dropped too. Level-2 section headings are never
      dropped for "no body" (they legitimately precede subheadings); only for an
      empty title.

    Iterates to a fixpoint so a run of consecutive stub headings all clears.
    """
    if not text:
        return text
    while True:
        lines = text.split("\n")
        keep = [True] * len(lines)
        changed = False
        for i, ln in enumerate(lines):
            m = _HEADING_LINE_RE.match(ln)
            if not m:
                continue
            level = len(m.group(1))
            title = m.group(2).strip().strip("*").strip()
            if not title:  # malformed heading, no title
                keep[i] = False
                changed = True
                continue
            if level < 3:
                continue
            # First non-blank body line after this subheading.
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j >= len(lines) or _HEADING_LINE_RE.match(lines[j]) or _is_placeholder_line(lines[j]):
                keep[i] = False
                changed = True
                # Drop the trailing placeholder body lines belonging to this stub.
                p = i + 1
                while p < len(lines) and (not lines[p].strip() or _is_placeholder_line(lines[p])):
                    if _is_placeholder_line(lines[p]):
                        keep[p] = False
                    p += 1
        if not changed:
            break
        lines = [ln for k, ln in zip(keep, lines) if k]
        text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def assemble_report(
    spec: BriefSpec,
    sections_markdown: Iterable[str],
    sources: list[SearchResult],
    verdicts: list | None = None,
) -> AssembledReport:
    """Combine the title, synthesized sections, and a references section.

    Empty/missing sections get a transparent placeholder heading instead of
    being silently dropped (the cause of the 2026-07-13 report's missing
    section 12): a visible gap is honest; vanishing is not.
    """
    body_parts: list[str] = [f"## **{spec.title}**", ""]
    md_list = list(sections_markdown)
    for i, section in enumerate(spec.sections):
        md = (md_list[i] if i < len(md_list) else "").strip()
        if not md:
            md = (
                f"## **{section.number}. {section.title}**\n\n"
                f"_No content synthesized for this section in this run "
                f"(empty writer output). Re-run to fill the gap._"
            )
        elif is_synthesis_failure_stub(md):
            # The orchestrator's last-resort stub renders as if it were real
            # prose. Replace with a single-line "section omitted" marker so
            # the gap is transparent to readers (the 2026-07-13 monthly
            # report had this exact phrase render in §6 and §7).
            md = (
                f"## **{section.number}. {section.title}**\n\n"
                f"_Section omitted: synthesis failed after retry in this run._"
            )
        else:
            md = drop_empty_subheadings(md)
        body_parts.append(md)
        body_parts.append("")
    # Any extra sections beyond spec.sections (shouldn't happen) — append as-is.
    for md in md_list[len(spec.sections):]:
        md = (md or "").strip()
        if md:
            body_parts.append(md)
            body_parts.append("")
    body = "\n".join(body_parts).rstrip() + "\n"

    body = _strip_label_brackets(body)
    resolved_body, refs = resolve_citations(body, sources)
    ref_block = _references_markdown(refs)
    full = resolved_body
    if ref_block:
        full = full.rstrip() + "\n\n" + ref_block + "\n"

    # Pre-write deliverable gate is the orchestrator's responsibility — see
    # gate_required_deliverables in orchestrator.py:run_news_pipeline. It
    # runs *after* assemble_report returns and *before* out_path.write_text,
    # so a missing deliverable refuses the write rather than appending a
    # 'Coverage Check' footer to a file already on disk.

    # Thin-corpus banner: a top-of-report callout when sources-per-section is
    # too low to support real analysis. Distinguishes "nothing happened" from
    # "we didn't see anything" — the 2026-07-13 report had 20 sources for 13
    # sections and a thin banner makes that visible.
    critical_count = sum(1 for v in (verdicts or []) if v.verdict == "CRITICAL")
    banner = thin_corpus_banner(
        total_sources=len(sources),
        section_count=len(spec.sections),
        critical_sections=critical_count,
    )
    if banner:
        # Insert just after the title heading.
        title_line = f"## **{spec.title}**"
        if title_line in full:
            full = full.replace(title_line, f"{title_line}\n\n{banner}", 1)
        else:
            full = banner + "\n" + full

    # Per-section coverage verdict table (Task 7). The orchestrator computes
    # OK/THIN/CRITICAL per section and passes them via ``verdicts``; we render
    # them as a small markdown table appended to the report so readers can see
    # corpus quality at a glance without re-running.
    if verdicts:
        verdict_pairs = [(v.section_title, v.verdict) for v in verdicts]
        coverage_footer = format_coverage_summary(verdict_pairs)
        if coverage_footer:
            full = full.rstrip() + "\n\n" + coverage_footer

    return AssembledReport(
        title=spec.title,
        body=resolved_body,
        references=refs,
        text=full,
    )
