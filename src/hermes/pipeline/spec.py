"""Parse a Markdown research brief (see ``example_prompt.md``) into a
:class:`BriefSpec`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class SectionSpec:
    number: int
    title: str
    bullets: list[str] = field(default_factory=list)


@dataclass
class BriefSpec:
    title: str
    instructions: str = ""
    source_names: list[str] = field(default_factory=list)
    sections: list[SectionSpec] = field(default_factory=list)
    deliverables: list[str] = field(default_factory=list)
    quality: list[str] = field(default_factory=list)
    raw: str = ""
    # Cadence parsed from the brief body (e.g. "monthly" in the title or
    # "the past 30 days" in instructions). Orchestrator uses this in preference
    # to HERMES_CADENCE so the lookback window matches the prompt.
    cadence: str | None = None


_H1 = re.compile(r"^#\s+(.*)$")
_H2 = re.compile(r"^##\s+(.*)$")
_SECTION = re.compile(r"^##\s+(\d+)\.\s+(.*)$")
_BULLET = re.compile(r"^[-*]\s+(.*)$")
_NUM = re.compile(r"\d+")

# Cadence detection: scan the title + the first 800 chars of the body for
# the strongest cadence hint. The prompt body is the authoritative source;
# HERMES_CADENCE env is a fallback.
_CADENCE_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("monthly", ("monthly", "month in review", "the past 30 days", "30-day", "30 day")),
    ("weekly", ("weekly", "week in review", "the past 7 days", "7-day", "7 day")),
    ("daily", ("daily", "today", "the last 24 hours", "24-hour", "24 hour")),
)


def _blocks(md: str) -> list[tuple[str, int, int]]:
    """Return ``(title, start_line, end_line)`` per top-level ``#`` heading."""
    lines = md.splitlines()
    heads: list[tuple[str, int]] = []
    for i, ln in enumerate(lines):
        m = _H1.match(ln)
        if m:
            heads.append((m.group(1).strip().rstrip("#").strip(), i))
    blocks: list[tuple[str, int, int]] = []
    for idx, (title, start) in enumerate(heads):
        end = heads[idx + 1][1] if idx + 1 < len(heads) else len(lines)
        blocks.append((title, start, end))
    return blocks


def _bullets(lines: list[str], start: int, end: int) -> list[str]:
    out: list[str] = []
    for ln in lines[start:end]:
        m = _BULLET.match(ln.strip())
        if m:
            out.append(m.group(1).strip())
    return out


def _source_lines(lines: list[str], start: int, end: int) -> list[str]:
    """Collect prioritized sources from the Research Instructions block.

    Sources appear two ways in a brief: as ``- ` bullets AND as bare lines
    (e.g. the ``## Official Sources`` list in ``example_prompt.md`` lists
    each lab on its own line with no bullet). We capture both, but skip
    prose (lines ending in ``.``/``:``) and headings.
    """
    out: list[str] = []
    for ln in lines[start:end]:
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        m = _BULLET.match(s)
        if m:
            out.append(m.group(1).strip())
            continue
        if s.endswith((".", ":")):
            continue
        if len(s) > 60:
            continue
        out.append(s)
    # Dedupe (keep order).
    seen: set[str] = set()
    dedup: list[str] = []
    for x in out:
        if x not in seen:
            seen.add(x)
            dedup.append(x)
    return dedup


def _slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s or "brief"


def _detect_cadence(text: str) -> str | None:
    """Best-effort cadence detection from prompt body.

    Returns one of ``"daily" | "weekly" | "monthly"`` or ``None`` if no hint
    matches. The first hint that appears in the text wins (longer/more
    specific cadences are checked first so "the past 30 days" beats "the
    past 7 days" if both are present).
    """
    low = text.lower()
    for cadence, hints in _CADENCE_HINTS:
        for hint in hints:
            if hint in low:
                return cadence
    return None


def parse_prompt(md: str) -> BriefSpec:
    lines = md.splitlines()
    blocks = _blocks(md)
    if not blocks:
        raise ValueError("Brief has no '# ' title heading.")

    title = blocks[0][0]
    spec = BriefSpec(title=title, raw=md, cadence=_detect_cadence(md))

    by_title = {t.lower(): (s, e) for (t, s, e) in blocks}

    # Research instructions + prioritized source list.
    inst = by_title.get("research instructions")
    if inst:
        s, e = inst
        spec.instructions = "\n".join(lines[s + 1 : e]).strip()
        spec.source_names = _source_lines(lines, s + 1, e)

    # Report structure sections.
    struct = by_title.get("report structure")
    if struct:
        s, e = struct
        cur: SectionSpec | None = None
        for ln in lines[s + 1 : e]:
            m = _SECTION.match(ln.strip())
            if m:
                if cur:
                    spec.sections.append(cur)
                cur = SectionSpec(number=int(m.group(1)), title=m.group(2).strip())
                continue
            if cur is None:
                continue
            b = _BULLET.match(ln.strip())
            if b:
                cur.bullets.append(b.group(1).strip())
            elif ln.strip() and not ln.strip().startswith("#"):
                # Plain lead-in / sub-point lines also become coverage bullets.
                cur.bullets.append(ln.strip())
        if cur:
            spec.sections.append(cur)

    # Deliverables + quality requirements.
    deliv = by_title.get("required deliverables")
    if deliv:
        spec.deliverables = _bullets(lines, deliv[0] + 1, deliv[1])
    qual = by_title.get("output quality requirements")
    if qual:
        spec.quality = _bullets(lines, qual[0] + 1, qual[1])

    return spec


def brief_slug(spec: BriefSpec) -> str:
    return _slug(spec.title)
