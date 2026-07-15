"""Reasoning-leakage sanitizer — the single enforcement point.

The Writer is the only stage that emits prose, and LLMs leak reasoning
("we need to…", "to summarize", "the evaluator…").  This deterministic
post-processor strips banned phrases from the prose before it reaches the
Editor/Renderer.  Applied per-section after the Writer, and again in
``FinalReport.to_markdown()`` as defense-in-depth.
"""

from __future__ import annotations

import re

# ── Banned phrases ──
# Writer reasoning-leakage markers; must never appear in output.
# Case-insensitive, word-boundary matched; compiled as a single alternation.
_BANNED_PHRASES: tuple[str, ...] = (
    # First-person planning / meta-commentary.
    "we need to",
    "we should",
    "we must",
    "let's",
    "lets",
    "i should",
    "i will",
    "i need to",
    "we will",
    "we can see",
    "as we can see",
    "we have seen",
    "we will see",
    # First-person contractions — the expansion-safe phrases above miss the
    # contracted forms ("I'll just put", "I'm simulating", "Since I'm GPT-4")
    # that leak when a model reasons in-line under a heading. Banned in this
    # domain: a research report never uses first-person singular.
    "i'll",
    "i'm",
    "i've",
    "i'd",
    "i might",
    "i could",
    "i can",
    "i'll just",
    "i'll begin",
    "i'll assume",
    "i'll invent",
    "i'll fabricate",
    "i'll simulate",
    "i'll project",
    "i'll generate",
    "i'll create",
    "i'll write",
    "i'll put",
    "i'll treat",
    "i'll use",
    "i'll do",
    "i'll make",
    "i'll note",
    "i'll include",
    "i'll base",
    "i'll draw",
    "i'll select",
    "i'll structure",
    "i'll differentiate",
    "i'll stick",
    "since i'm",
    "i'm simulating",
    "i'm going",
    # References to the evaluation / prompting process.
    "the evaluator",
    "the prompt",
    "the instructions",
    "the planner",
    "the researcher",
    "the analyst",
    "the editor",
    "the renderer",
    # Self-referential report commentary.
    "this report will",
    "this section will",
    "in this section we",
    "in this report we",
    # Boilerplate transitions that a senior analyst would never write.
    "it is important to note",
    "it should be noted",
    "it is worth noting",
    "as mentioned earlier",
    "as previously mentioned",
    "as discussed earlier",
    "in conclusion",
    "to summarize",
    "to summarise",
    "in summary",
    "to wrap up",
    "wrapping up",
    # Meta-explanations.
    "the purpose of this",
    "the goal of this",
    "the aim of this",
    # Instruction-acknowledgement leakage.
    "based on the provided",
    "according to the provided",
    "per the instructions",
    "as instructed",
    "as per the",
    "here is the",
    "here's the",
    # Summary-instead-of-synthesis indicators.
    "this article discusses",
    "this paper presents",
    "the author argues",
    "according to the article",
    "the blog post explains",
    "the report states",
    "in this article",
    "this post describes",
    "the source says",
    "as mentioned in the source",
    # Vague language that indicates weak synthesis.
    "several developments",
    "multiple companies",
    "various papers",
    "there were many",
    "a number of",
    "some analysts",
    "it is believed",
    "it is expected",
    "experts say",
    "sources suggest",
    # Blueprint/instruction leakage.
    "the blueprint",
    "the story editor",
    "the story blueprint",
    "according to the blueprint",
    "as specified in",
    "the instructions say",
    "the prompt asks",
    # ── 2026-07-13 monthly §12 round-3 CoT class ─────────────────────────────
    # These survived because they don't reference the user/evaluator directly
    # and don't match "we need to" / "let's" patterns. Each is a planning
    # fragment the writer emitted while reasoning about the task itself.
    "now, for each factual claim",
    "now, for each",
    "it's a bit of a trap",
    "it is a bit of a trap",
    "hope the user overlooks",
    "hope the user",
    "ignore that rule",
    "ignore the rule",
    "so we can weave",
    "so be creative",
    "so we won't",
    "so we will",  # planning-followup
    "we could avoid making",
    "for this draft",
    "is it acceptable to",
    "is acceptable to not",
    "the user demanded",
    "the user said cite",
    "we need to add citations",
    "we need citations",
    "the critic feedback emphasized",
    "we need to ensure citations",
    # ── Self-aware/instruction-leakage ("the writer discusses the writing") ──
    "as a meta point",
    "to fulfill the requirement",
    "we can be more creative",
    "can be more creative",
    "let's go ahead and",
    "let us go ahead",
)

# Pre-compile a single alternation pattern for efficiency.
_BANNED_RE: re.Pattern[str] = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in _BANNED_PHRASES) + r")\b",
    flags=re.IGNORECASE,
)

# Clean up artifacts (dangling punctuation/spaces) left after phrase removal.
_COLLAPSE_LEADING_PUNCT = re.compile(r"^\s*[,;:]\s+")
_COLLAPSE_DOUBLE_SPACE = re.compile(r"[ \t]{2,}")
_COLLAPSE_BLANK_LINES = re.compile(r"\n{3,}")

# Strip the writer's `[unsourced - ...]` / `[unsourced — ...]` markers from
# rendered prose. The critic counts them in `report.audit_citation_discipline`
# (a separate regex over raw output), but the reader should never see the
# tag — and the unsourced claim that couldn't be cited is dropped along
# with its tag. The dash is non-greedy and may be em/en/ASCII. The pattern
# consumes the surrounding sentence so the unsourced claim disappears with
# its tag (not a stranded "GPT-5 was released in 2026. Other claim.").
_UNSOURCED_SENTENCE_RE = re.compile(
    r"[^.!?\n]*\[unsourced\s*[—–-][^\]]*\][^.!?\n]*[.!?]?\s*",
    re.IGNORECASE,
)


def sanitize_text(text: str) -> str:
    """Remove banned phrases and clean up artifacts from a prose string.

    Returns the cleaned text.  Never raises.
    """
    if not text:
        return text

    # Drop entire sentences that carry an unsourced-claim tag — the tag is
    # internal bookkeeping for the critic, and the claim itself is what
    # couldn't be cited. The regex consumes the sentence + trailing
    # punctuation; the blank-line collapse below cleans up the gap.
    cleaned = _UNSOURCED_SENTENCE_RE.sub("", text)

    # Strip banned phrases (replace with empty string, not a placeholder).
    cleaned = _BANNED_RE.sub("", cleaned)

    # Clean up artifacts left by phrase removal.
    lines = cleaned.split("\n")
    fixed_lines: list[str] = []
    for line in lines:
        line = _COLLAPSE_LEADING_PUNCT.sub("", line)
        line = _COLLAPSE_DOUBLE_SPACE.sub(" ", line)
        fixed_lines.append(line)
    cleaned = "\n".join(fixed_lines)

    # Collapse 3+ blank lines to 2.
    cleaned = _COLLAPSE_BLANK_LINES.sub("\n\n", cleaned)

    # Strip trailing whitespace per line (common after phrase removal).
    cleaned = "\n".join(line.rstrip() for line in cleaned.split("\n"))

    return cleaned.strip()


def has_leakage(text: str) -> bool:
    """Check if text contains any banned phrase (for tests / quality gates)."""
    return bool(_BANNED_RE.search(text))


# The orchestrator's last-resort stub when both the writer and its retry fail.
# It is intentionally a single-line marker so the renderer can detect and
# replace it. The 2026-07-13 monthly report had this exact phrase render in
# sections 6 and 7 — a transparent gap, not actual prose.
_SYNTHESIS_FAILURE_MARKERS: tuple[str, ...] = (
    "synthesis for this section did not produce valid, substantial prose",
    "no content synthesized for this section in this run",
)


def is_synthesis_failure_stub(text: str) -> bool:
    """True if ``text`` is the orchestrator's last-resort stub, not real prose.

    The renderer should suppress these entirely (or replace with a short
    dropped-section marker) rather than ship them as if they were analysis.
    """
    low = (text or "").lower()
    return any(marker in low for marker in _SYNTHESIS_FAILURE_MARKERS)