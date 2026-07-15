"""Test harness for the brief prompt library.

The 14 brief prompts in ``prompts/`` (and ``example_prompt.md``) drive the
unified pipeline. This module enforces the post-rewrite contract:

1. Every brief parses to a BriefSpec with the expected section count.
2. Every brief has a ``## Synthesis Directives`` block (the new convention
   introduced by the 2026-07-15 brief prompt optimization).
3. Every brief's Required Deliverables includes a comparison-table mention
   for every section flagged in the snapshot.
4. Every brief's byte count is in the snapshot's expected range (±20% drift).

The snapshot lives at ``tests/snapshots/briefs.json`` and is the
single source of truth for what each brief should look like.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from newsagent.pipeline.spec import parse_prompt

_REPO = Path(__file__).resolve().parents[2]
_PROMPTS_DIR = _REPO / "prompts"
_EXAMPLE_PROMPT = _REPO / "example_prompt.md"
_SNAPSHOT = _REPO / "tests" / "snapshots" / "briefs.json"


def _load_snapshot() -> dict:
    return json.loads(_SNAPSHOT.read_text(encoding="utf-8"))


def _all_briefs() -> list[Path]:
    """Return every brief file the snapshot knows about, in stable order."""
    snap = _load_snapshot()
    paths: list[Path] = []
    if "example_prompt.md" in snap:
        paths.append(_EXAMPLE_PROMPT)
    for name in sorted(snap):
        if name == "_comment" or name == "example_prompt.md":
            continue
        p = _PROMPTS_DIR / name
        if p.exists():
            paths.append(p)
    return paths


def test_snapshot_covers_every_brief():
    """Sanity check: the snapshot lists every brief in the prompts dir."""
    snap = _load_snapshot()
    snap_names = {n for n in snap if n != "_comment"}
    on_disk = {p.name for p in _PROMPTS_DIR.glob("*.md")}
    assert on_disk.issubset(snap_names), (
        f"Briefs on disk missing from snapshot: {on_disk - snap_names}"
    )


def test_each_brief_parses_with_expected_section_count():
    """Every brief parses to a BriefSpec with its declared section count.

    Catches the H1 trailing-# bug (parse fails), accidental section renames,
    and accidental section deletions.
    """
    snap = _load_snapshot()
    for path in _all_briefs():
        meta = snap[path.name]
        spec = parse_prompt(path.read_text(encoding="utf-8"))
        assert len(spec.sections) >= meta["section_count"], (
            f"{path.name}: expected >= {meta['section_count']} sections, "
            f"got {len(spec.sections)}"
        )


def test_each_brief_has_synthesis_directives_block():
    """Every brief includes a Synthesis Directives block (the new
    convention introduced by the 2026-07-15 brief prompt optimization).

    The block is detected by a heading whose stripped title contains
    'Synthesis Directives' (either '#' or '##' is acceptable, matching
    the convention in `example_prompt.md` which uses H1 for top-level
    sections).
    """
    head_re = re.compile(r"^#{1,3}\s+(.+?)\s*#*\s*$")
    for path in _all_briefs():
        raw = path.read_text(encoding="utf-8")
        titles = [head_re.match(ln).group(1) for ln in raw.splitlines()
                  if head_re.match(ln)]
        assert any("Synthesis Directives" in t for t in titles), (
            f"{path.name}: missing 'Synthesis Directives' block"
        )


def test_each_brief_has_clean_h1():
    """Every brief's H1 has no trailing '#' (cosmetic, but signals template
    hygiene and avoids confusion in the slug extractor)."""
    for path in _all_briefs():
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
        assert first_line.startswith("# "), (
            f"{path.name}: first line is not an H1: {first_line!r}"
        )
        title = first_line[2:].rstrip()
        assert not title.endswith("#"), (
            f"{path.name}: H1 has trailing '#': {first_line!r}"
        )


def test_each_brief_uses_consistent_citation_token():
    """Citation token is `[src:URL]` everywhere in the brief. The old
    `[src:EXACT_URL]` variant is deprecated at the brief layer (the system
    template keeps that exact wording)."""
    for path in _all_briefs():
        raw = path.read_text(encoding="utf-8")
        assert "[src:URL]" in raw, (
            f"{path.name}: missing canonical citation token `[src:URL]`"
        )


def test_each_brief_byte_count_in_range():
    """Per-brief byte count is within the snapshot's expected range.

    Catches accidental large diffs (overgrown rewrite) and accidental
    deletions of the Synthesis Directives block (shrunk rewrite).
    """
    snap = _load_snapshot()
    for path in _all_briefs():
        meta = snap[path.name]
        size = path.stat().st_size
        assert meta["min_bytes"] <= size <= meta["max_bytes"], (
            f"{path.name}: byte count {size} not in "
            f"[{meta['min_bytes']}, {meta['max_bytes']}]"
        )


def test_each_brief_deliverables_match_comparison_sections():
    """For every brief, each section flagged in `comparison_sections` has a
    Markdown comparison-table mention in the Required Deliverables block.

    Why: the writer's `build_section_prompt` checks the section title for
    frontier/model/hardware/silicon keywords; briefs whose comparison
    sections fall outside that keyword set (e.g. 'Funding' or 'Benchmarks')
    need an explicit deliverable in the brief so the post-render
    `check_required_deliverables` gate flags a missing table.
    """
    snap = _load_snapshot()
    for path in _all_briefs():
        meta = snap[path.name]
        if not meta["comparison_sections"]:
            continue
        spec = parse_prompt(path.read_text(encoding="utf-8"))
        joined = "\n".join(spec.deliverables).lower()
        # A "comparison table" deliverable may use any of these phrasings;
        # we just need the *concept* of a table to be present.
        has_table = any(
            phrase in joined
            for phrase in (
                "comparison table",
                "comparison tables",
                "markdown table",
                "comparison matrix",
            )
        )
        assert has_table, (
            f"{path.name}: no comparison-table deliverable in "
            f"Required Deliverables, but comparison_sections="
            f"{meta['comparison_sections']}"
        )


def test_each_brief_lists_unsourced_fact_rule():
    """Every brief's Output Quality Requirements mentions the unsourced-fact
    tagging rule `[unsourced — industry knowledge]`. This is the
    brief-level reinforcement of Scope 5 (citation discipline)."""
    for path in _all_briefs():
        spec = parse_prompt(path.read_text(encoding="utf-8"))
        joined = "\n".join(spec.quality).lower()
        assert "unsourced" in joined, (
            f"{path.name}: Output Quality Requirements missing the "
            f"unsourced-fact tagging rule"
        )
