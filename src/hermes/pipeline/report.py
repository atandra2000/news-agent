"""Assemble the final report Markdown and resolve ``[src:URL]`` citations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

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

    return AssembledReport(
        title=spec.title,
        body=resolved_body,
        references=refs,
        text=full,
    )
