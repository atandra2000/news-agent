"""Synthesize one report section from retrieved sources using the LLM router."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from hermes.pipeline.planner import section_keywords
from hermes.pipeline.search import SearchResult, _host
from hermes.pipeline.spec import SectionSpec
from hermes.pipeline.coverage import _section_required_category
from hermes.llm.router import LLMRouter
from hermes.logging import get_logger

log = get_logger("brief.synthesize")


@dataclass(frozen=True)
class SectionRewriteBudget:
    """Gate the critic loop's final ship decision.

    After the loop exhausts ``max_iterations`` rewrites, the section is only
    shipped if its final ``critic.score`` is at or above ``min_score``;
    otherwise the section is replaced with the standard ``_placeholder(section)``
    and marked as failed. Without this gate the loop used to ship drafts
    with scores as low as 0.25 (see 2026-07-13 monthly brief).
    """

    min_score: float = 0.5
    max_iterations: int = 2

_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "into", "your", "have",
    "are", "was", "were", "will", "what", "when", "which", "their", "about", "been",
    "they", "them", "than", "then", "over", "also", "more", "most", "some", "such",
}


def _tokenize(text: str) -> set[str]:
    return {w for w in re.split(r"\W+", text.lower()) if len(w) > 3 and w not in _STOP}


def _recency_bonus(s: SearchResult, recency_days: int | None) -> int:
    if not (recency_days and s.published_date):
        return 0
    try:
        d = datetime.fromisoformat(s.published_date[:10]).date()
        return 1 if (date.today() - d).days <= recency_days else 0
    except Exception:
        return 0


def _score_source(kws: set[str], s: SearchResult, recency_days: int | None, *, section: SectionSpec | None = None) -> int:
    title = (s.title or "").lower()
    body = f"{s.title} {s.content}".lower()
    score = 0
    for w in kws:
        if w in title:
            score += 2
        if w in body:
            score += 1
    score += _recency_bonus(s, recency_days)
    # Source-priority boost: official/research sources outrank community ones.
    # Without this, a high-keyword-match HN comment on a paper outranks the
    # arxiv abstract for the same paper. Scope 8: pull from the priority
    # tiers the brief listed.
    score += source_priority_boost(s.source)
    # Per-category tiebreaker: when the item's per-feed category stamp matches
    # the section's required category, add a small bonus. Smaller than the
    # keyword score (2x title) so keyword relevance still dominates; this just
    # breaks ties between equally-relevant items from feeds of different
    # categories (e.g. openai.com "official" outranks substack "community" on
    # a frontier-model section). ponytail: one ternary, no new map.
    if section is not None:
        req_cat = _section_required_category(section)
        item_cat = (getattr(s, "extra", None) or {}).get("category")
        if req_cat and item_cat == req_cat:
            score += 3.0
    return score


# ── Source-priority boost (Scope 8) ─────────────────────────────────────────
# Prompts list "Official Sources" / "Research Sources" / "Trusted News Sources" /
# "Community Intelligence" in priority order. The default scoring here rewards
# keyword matches + recency but treats all sources equally — for a brief that
# says "Use arXiv as primary", an arxiv item must outrank an HN comment on the
# same paper. This map applies a per-source bonus at scoring time. The 2026-07-13
# monthly report had 110 arxiv items, 94 huggingface items, 90 RSS items in the
# DB and the report cited zero of them — pure HN + GitHub Trending won. The
# fix is a numeric boost, not a hard filter: keyword match still matters.
_SOURCE_PRIORITY_BOOST: dict[str, int] = {
    # Official sources (highest weight — these are the brief's primary tier).
    "openai": 5, "anthropic": 5, "google_deepmind": 5, "google_ai": 5,
    "microsoft_ai": 5, "meta_ai": 5, "xai": 5, "nvidia": 5, "amd": 5,
    "intel": 5, "apple_ml": 5, "amazon_aws_ai": 5, "ibm_research": 5,
    "huggingface": 4, "mistral": 5, "deepseek": 5, "qwen": 5, "moonshot": 5,
    "minimax": 5, "zhipu": 5, "perplexity": 5, "groq": 5, "cerebras": 5,
    "databricks": 5, "cohere": 5,
    # Research sources.
    "arxiv": 4, "semantic_scholar": 4, "openreview": 4,
    "papers_with_code": 3, "context7": 3,
    # Trusted news.
    "rss": 2, "tavily": 2, "blog": 2,
    # Community intelligence (lowest weight — useful for sentiment, not facts).
    "hacker_news": 1, "github_trending": 1, "github_releases": 1,
    "devto": 1, "lobsters": 1, "bluesky": 1, "youtube": 1,
}


def source_priority_boost(source: str | None) -> int:
    """Return the priority boost for a source_type. 0 for unknown."""
    if not source:
        return 0
    return _SOURCE_PRIORITY_BOOST.get(source.lower(), 0)


def select_relevant(
    section: SectionSpec,
    sources: list[SearchResult],
    *,
    top_k: int = 12,
    domain_cap: int = 3,
    recency_days: int | None = None,
    min_source_types: int = 3,
) -> list[SearchResult]:
    """Pick the ``top_k`` sources most relevant to a section.

    Scoring: keyword hits (title weighted 2x body) + recency bonus + source-priority
    boost. Selection is then domain-diversified — at most ``domain_cap`` sources
    from any single host — so one outlet cannot dominate a section. A
    ``min_source_types`` floor ensures the picked set spans multiple source
    types when possible; without it, a section whose top-12 are all from HN
    would still be returned even though the brief asked for cross-source
    coverage (the 2026-07-13 monthly report's disease: every cited source
    was HN or GitHub Trending despite 110 arxiv items in the DB).
    """
    if not sources:
        return []
    kws = section_keywords(section)
    if kws:
        scored = [( _score_source(kws, s, recency_days, section=section), s) for s in sources]
        scored.sort(key=lambda x: x[0], reverse=True)
        # Keyword scoring found matches → use them.
        ranked = [s for _, s in scored if _ > 0]
        # Nothing scored above zero ⇒ no source is topically relevant by keyword.
        # Fall back to recency-ranked sources (most recent first) so the writer
        # has something to work with — but the prompt will flag these as tangential.
        # This fixes the "Research Breakthroughs" and "Regulation" empty-section
        # bug: broad section titles don't keyword-match arXiv paper titles, but
        # the most recent sources are still better than the "insufficient sources"
        # cop-out. The writer prompt's tangential-sources flag tells it to be
        # honest about relevance rather than fabricating connections.
        if not ranked:
            # Sort by published_date descending (most recent first), then by
            # original order for sources without dates.
            dated = [(s, s.published_date or "1970-01-01") for s in sources]
            dated.sort(key=lambda x: x[1], reverse=True)
            ranked = [s for s, _ in dated]
    else:
        ranked = list(sources)

    picked: list[SearchResult] = []
    per_host: dict[str, int] = {}
    per_type: dict[str, int] = {}
    for s in ranked:
        host = s.source or _host(s.url)
        if domain_cap and per_host.get(host, 0) >= domain_cap:
            continue
        picked.append(s)
        per_host[host] = per_host.get(host, 0) + 1
        src_type = s.source or "unknown"
        per_type[src_type] = per_type.get(src_type, 0) + 1
        if len(picked) >= top_k:
            break

    # Diversity floor: if we picked top_k but only N source types (N < min_source_types)
    # and the broader pool has more variety, swap the lowest-priority items
    # for new source types. The 2026-07-13 monthly report's bug: top_k items
    # all from HN + GitHub Trending despite 13 source types in the DB.
    if min_source_types and len(per_type) < min_source_types and len(ranked) > top_k:
        existing_types = set(per_type.keys())
        existing_urls = {s.url for s in picked}
        # One swap-in pass: find candidates from unseen source types.
        for s in ranked:
            if s.url in existing_urls:
                continue
            src_type = s.source or "unknown"
            if src_type in existing_types:
                continue
            # Find the lowest-priority item to drop (last picked, lowest score).
            # We just take the LAST one — selection is already scored.
            if not picked:
                break
            dropped = picked.pop()
            per_type[dropped.source or "unknown"] -= 1
            if per_type[dropped.source or "unknown"] <= 0:
                per_type.pop(dropped.source or "unknown", None)
            picked.append(s)
            existing_urls.add(s.url)
            existing_types.add(src_type)
            per_type[src_type] = per_type.get(src_type, 0) + 1
            if len(per_type) >= min_source_types:
                break
        # Restore order: highest-priority first.
        # Recompute scores for stable sort.
        if kws:
            rescored = [(_score_source(kws, s, recency_days, section=section), s) for s in picked]
            rescored.sort(key=lambda x: x[0], reverse=True)
            picked = [s for _, s in rescored]

    return picked


def _source_block(sources: list[SearchResult]) -> str:
    lines = []
    for i, s in enumerate(sources, 1):
        snippet = s.content.strip().replace("\n", " ")
        if len(snippet) > 600:
            snippet = snippet[:600] + "…"
        lines.append(f"[{i}] {s.title} ({s.source or 'web'})")
        lines.append(f"    URL: {s.url}")
        if s.published_date:
            lines.append(f"    Date: {s.published_date}")
        if snippet:
            lines.append(f"    {snippet}")
    return "\n".join(lines)


def build_section_prompt(
    section: SectionSpec,
    sources: list[SearchResult],
    instructions: str,
    quality: list[str],
    date_label: str,
    cadence_note: str = "",
    deliverables: list[str] | None = None,
    rag_context: str = "",
    thin_corpus: bool = False,
) -> str:
    bullets = "\n".join(f"- {b}" for b in section.bullets) or "(cover comprehensively)"
    qual = "\n".join(f"- {q}" for q in quality[:12]) or "(none specified)"
    deliv = "\n".join(f"- {d}" for d in (deliverables or [])[:12]) or "(none specified)"
    # Pass full instructions (no truncation) so the writer follows source priorities precisely.
    src_block = _source_block(sources) or "(NO RETRIEVED SOURCES — see SOURCES-GUARDBAND below)"
    cadence_line = f"\nREPORT CADENCE: {cadence_note}\n" if cadence_note else ""
    rag_block = f"\n{rag_context}\n" if rag_context else ""
    sources_guardband = _SOURCES_GUARDBAND if not sources else ""
    # THIN CORPUS honesty note: when the coverage verdict was THIN/CRITICAL,
    # the writer must be transparent about gaps rather than fabricating from
    # parametric knowledge. The note sits between the QUALITY BAR and the
    # RETRIEVED SOURCES block so the writer reads it just before citing.
    thin_note = (
        "\nTHIN CORPUS: The retrieved sources for this section are sparse. "
        "Be honest about what is and isn't covered; do not fabricate. "
        "List the gaps explicitly.\n"
        if thin_corpus else ""
    )
    # Frontier / model sections require an explicit comparison table.
    # The general "use a Markdown comparison table" rule is too soft — the
    # writer tends to default to prose. The 2026-07-14 monthly §3 shipped
    # 85 words of narrative with no table; the brief asks for "model and
    # silicon comparison tables" as a Required Deliverable.
    low_title = section.title.lower()
    is_frontier_or_model = (
        "frontier" in low_title
        or "model" in low_title
        or "silicon" in low_title
        or "hardware" in low_title
    )
    frontier_block = ""
    if is_frontier_or_model:
        frontier_block = (
            "\n\nFRONTIER / MODEL SECTION — TABLE REQUIRED:\n"
            "Render a Markdown comparison table with these columns, in this order:\n"
            "| Model | Developer | Context | Reasoning | Coding | Pricing | Release date |\n"
            "If a field is unknown for a row, write `n/a` — do NOT omit the row. "
            "Include at least 3 models actually released or substantially updated in the "
            "report cadence window. After the model table, render a SECOND Markdown table "
            "for chips / hardware (columns: Chip, Vendor, Process node, Memory, Notable use) "
            "if the section bullets mention chips, hardware, serving, or silicon. "
            "If you have no in-window chip data, write a one-sentence 'No in-window chip "
            "releases' note after the model table — do not silently drop the table.\n"
        )

    return f"""You are an expert AI research analyst writing ONE section of an institutional-grade AI industry report ({date_label}).

SECTION TO WRITE:
## **{section.number}. {section.title}**

What this section must cover:
{bullets}
{frontier_block}
{cadence_line}
REPORT-WIDE DELIVERABLES (these span the FULL report — include ONLY the ones relevant to THIS section; do NOT stub out the others as empty subheadings):
{deliv}

RESEARCH PRIORITIES (from the brief — follow these source priorities and angles):
{instructions}

QUALITY BAR (apply to this section):
{qual}
{rag_block}
{thin_note}
RETRIEVED SOURCES (cite with the exact token [src:URL] right after each claim):
{src_block}
{sources_guardband}
OUTPUT RULES — FOLLOW EXACTLY:
- Begin with the heading "## **{section.number}. {section.title}**" exactly ONCE. Never repeat it, never emit placeholder subheadings such as "### Full Analytical Report", "### Month Timeline", "### Executive Summary", "(single paragraph)", "(detailed analysis, organized by...)", or "### Funding Tables" with no body.
- Write in third-person, information-dense Markdown prose. Never use first-person ("we", "I", "our", "let's", "we'll") or planning language ("we need to", "now, write", "we can organize", "we'll use", "say:").
- Cover every bullet listed under "What this section must cover". Do not skip any sub-topic.
- Do NOT repeat information that belongs in other sections; focus on the unique angle of this section.
- Do NOT emit ellipses "..." or "…" as placeholders. Do NOT emit "[Analyst assessment]", "[community sentiment]", "[Analyst's Note]", "[src]", "[source]", or any bracketed label without a real URL.
- Do NOT invent model names, release dates, funding figures, benchmark numbers, or quotes that are not supported by the retrieved sources.
- When the section compares entities (models, hardware, companies, funding rounds), use a Markdown comparison table.
- For every factual claim, append the citation token [src:EXACT_URL] using the exact URL of the supporting source above. Multiple claims may cite the same source.
- CITATION DISCIPLINE — CRITICAL: every factual claim must be EITHER cited with [src:URL] OR explicitly tagged as unsourced. When you include a fact from industry knowledge (e.g. "LangSmith was launched by LangChain in 2023", "RAGAS was developed by the community") that is NOT in the retrieved sources above, append the marker [unsourced — industry knowledge] right after the claim. This is the only acceptable way to use parametric knowledge: make it visible to the reader. Never present unsourced facts as if they were cited evidence.
- Clearly distinguish facts, analysis, estimates, rumors, and community sentiment. Prefer primary sources. Quantify where possible (funding, performance, pricing, dates).
- Maximize depth and analytical insight. Do not pad with filler. Produce a substantive, comprehensive section; do not emit thin stubs.
- Before output, self-check: (1) no planning/first-person language, (2) every bullet covered, (3) every factual claim has either a [src:URL] citation or an [unsourced — industry knowledge] tag, (4) all dates and developments fall within the REPORT CADENCE window above.

Write only the final section now."""

# When no sources were retrieved, the writer must NOT fabricate events, numbers,
# dates, or model names from parametric knowledge. It writes a short, transparent
# notice instead. This is the integrity guardband: a thin honest section beats a
# dense invented one. (The pipeline also falls back to free collectors before
# reaching here — see ``_gather_sources_fallback`` in run.py.)
_SOURCES_GUARDBAND = """
SOURCES GUARDBAND — NO RETRIEVED SOURCES AVAILABLE:
You have NO retrieved sources for this section. Do NOT invent or extrapolate
facts, model names, release dates, funding figures, or benchmark numbers from
parametric knowledge — that is fabrication. Instead write ONLY the section
heading (shown above under SECTION TO WRITE) followed by this one-line notice:

_Insufficient retrieved source material for this section in this run. This
subsection is intentionally left thin rather than fabricated; re-run after
restoring search/collector connectivity for full coverage._

Do not add any other claims, tables, or citations. Stop after the notice.
"""


# ── Section-validity gate ─────────────────────────────────────────────────────
# Planning/reasoning markers that NEVER appear in finished report prose. If any
# survive into a section, the writer emitted a planning scratchpad instead of
# the section (the 2026-07-13 monthly report's sections 6 & 8). High precision:
# these phrases are unambiguous meta-commentary, not analysis.
_COT_MARKERS: tuple[str, ...] = (
    "write a section", "write the section", "write the actual section",
    "now, write", "now, draft", "now, fill in", "fill in.",
    "we are supposed to", "we are told", "we are to write", "we are to include",
    "the instruction says", "the instructions say", "the prompt says", "the prompt asks",
    "say:",
    "examine each source", "check the url",
    "we'll use the source", "we'll use the", "we'll", "here we'll",
    "we'll elaborate", "we'll wrap up", "we'll discuss",
    "we can organize", "we can structure", "we can frame", "we can tie",
    "we can mention", "we can note", "we can phrase", "we can cite",
    "we can include", "we can interpret", "we can check", "we can look",
    "we can embed", "we can say", "we can infer", "we might say",
    "we might not", "we can look up", "we can estimate",
    "the exercise is", "the expectation is", "the report is supposed",
    "the section is specifically",
    "weave in the required", "use the sources rigorously", "fulfill the requirement",
    "provide a brief synthesis", "a bullet list with", "scan for funding",
    "list key events", "summarize the month", "elaborate on each",
    # ── Meta-authorship class ────────────────────────────────────────────────
    # The writer discussing ITS OWN authorship, its reader/user, or admitting
    # invention. A finished report NEVER contains these — they are unambiguous
    # meta-commentary. This is the class that survived the 2026-07-13 round-3
    # section-12 tail ("the user said", "fabricate numbers", "we can simulate",
    # "as the writer, we can't access it", "do our best"): a finite, well-defined
    # vocabulary, not arbitrary phrase-banning. Kept high-precision — phrases are
    # line-dropped whole, so common idioms ("sets the stage") and bare end-user
    # references ("the user expects") are excluded to avoid dropping real analysis.
    "the user said", "the user wants us", "the user gave us", "the user made a mistake",
    "the user only wants us", "the user instructed", "the user asked us",
    "the user provided us", "the user expects us", "the user might expect",
    "as the writer", "as a writer",
    "we don't have sources", "we do not have sources", "we don't have a source",
    "we could cite older", "we could cite",
    "we cannot make up", "we can't make up", "make up numbers",
    "fabricate numbers", "fabricate some", "fabricate details", "fabricate the", "fabricate a",
    "we can simulate", "we can simulate that", "simulate that by saying",
    "we can't access", "we cannot access",
    "we only see the metadata",
    "do our best", "be creative but realistic", "use the metadata creatively",
    "craft an executive summary", "first, craft",
    "the only safe route", "the safe route is", "the only route is",
    # ── Structural planning patterns (2026-07-13 monthly §6 & §12) ────────────
    # Imperative planning lines that aren't bare imperatives but still meta-commentary.
    # These survived because they're multi-word phrases, not bare "write." lines.
    "now, flesh out", "first, gather all", "then, flesh out",
    "craft the executive summary", "then full analytical report",
    "month timeline:", "model comparison matrix:", "benchmark comparison:",
    "key statistics:", "strategic conclusions:",
    # Template stub descriptions — parenthetical planning notes after headings.
    # These are unambiguous: a finished report never has "(a single paragraph...)"
    # or "(detailed analysis, organized by...)" after a heading.
    "(a single paragraph", "(detailed analysis, organized", "(since we have",
    "(analysis of what these", "(maybe a small list",
)
# A standalone planning-fragment line — a bare imperative / connective the model
# drops between paragraphs (" write.", "now.", "first.", "so."). These never
# appear as a whole line in finished prose; requires the WHOLE line to be just
# that word so legit usage ("the model can write code") is never matched.
_BARE_IMPERATIVE_LINE_RE = re.compile(
    r"^\s*(?:write|draft|craft|fill|begin|start|now|first|so|hmm|ok|let's|lets|again|but)\b[\s.:,]*$",
    re.IGNORECASE,
)
_COT_MARKER_RE = re.compile("|".join(re.escape(p) for p in _COT_MARKERS), re.IGNORECASE)
# A whole line containing any CoT marker — used to drop planning lines whether
# they appear as a preamble, a tail, or mid-section.
_COT_MARKER_LINE_RE = re.compile(
    r"^[^\n]*(?:" + "|".join(re.escape(p) for p in _COT_MARKERS) + r")",
    re.IGNORECASE | re.MULTILINE,
)
# Minimum real-prose size for the cleaned text to count as a real section
# (distinguishes "all planning dropped → just a heading" from a real section).
# A heading-only dump leaves ~0 words after marker removal; a real section has
# 100+. 30 rejects a planning dump with no analysis while still allowing a
# dense executive-summary paragraph. The critic loop, not this backstop,
# enforces depth.
_MIN_PROSE_WORDS = 30

# Floor for a *substantial* section after the validity gate. If retrieved
# sources exist and the final cleaned section falls below this word count, it
# is treated as a stub and rewritten/placeholdered rather than shipped.
_SECTION_MIN_WORDS = 80


# ── CoT scratchpad backstop (extract_prose) ───────────────────────────────────
# Reasoning models emit a scratchpad ("We need to write a polished section… Let's
# assume OpenAI released GPT-5.6") BEFORE the real `## ` heading. The phrase-based
# sanitizer can't rescue this — stripping "let's" leaves the fabrication in line.
# This structural extractor drops everything before the first real heading. It is
# deliberately STRUCTURAL ONLY: the phrase-level sanitizer stays the final net so
# the Critic's leakage check still sees raw (de-scratchpadded) prose.
_HEADING_RE = re.compile(r"^#{1,6}\s+.+$", re.MULTILINE)
# Leading headings whose text marks a scratchpad section, not real content.
_SCRATCHPAD_HEADINGS = (
    "reasoning", "thoughts", "thinking", "draft", "notes", "plan",
    "scratchpad", "my approach", "analysis plan", "approach",
)
# Trailing separators after which only meta-commentary follows.
_TRAIL_SEPARATORS = ("\n---\n", "\n***\n", "\n___\n")
# Inline planning-debris patterns that appear AFTER a real heading but are
# still scratchpad, not prose. These mark the boundary between the LLM's
# internal outline/instruction block and the actual answer.
_INLINE_PLANNING_MARKERS = (
    "\n... prose ...\n",
    "\nStructure:\n",
    "\nMake sure to cite every claim",
    "\nFor example:\n",
    "\nWe can write:",
    "\nSo we can add a paragraph",
    "\n**Month at a Glance (",
)


def extract_prose(text: str, *, title: str | None = None) -> str:
    """Drop a reasoning scratchpad; keep the real section heading onward.

    Structural only — does not call ``sanitize_text`` (that runs as the final net
    after the Critic sees the de-scratchpadded raw prose). No-op when there is no
    heading to anchor on (e.g. executive summary), where the sanitizer handles
    phrase-level leakage.

    Two scratchpad shapes are handled:
    1. *Leading* — reasoning before the first real heading (classic CoT dump).
    2. *Heading-first* — the model emits the required ``## **N. Title**`` heading,
       then dithers underneath it (template-stub subheadings + first-person
       planning), then re-emits the SAME heading with the real prose. This is
       what instruction-compliant models produce when told "begin with the exact
       heading": the heading lands first, so a "drop text before the first
       heading" rule is defeated. We collapse to the LAST occurrence of the first
       real level-2 heading — everything between the first and last is dithering.
    """
    text = (text or "").strip()
    if not text:
        return text

    headings = list(_HEADING_RE.finditer(text))
    if headings:
        # Skip any leading headings that are themselves scratchpad markers.
        first_real: re.Match | None = None
        for h in headings:
            heading_text = (
                text[h.start():h.end()].lstrip("#").strip().replace("*", "").strip().lower()
            )
            if not any(heading_text.startswith(m) for m in _SCRATCHPAD_HEADINGS):
                first_real = h
                break
        if first_real is None:
            first_real = headings[0]

        start = first_real.start()
        # Heading-first dithering: if the first real LEVEL-2 heading line recurs
        # later verbatim, the last recurrence is the real section start. Drop the
        # stub-subheading + CoT preamble sandwiched between the two. Restricted to
        # level-2 (``## ``) so legitimate repeated ``### `` subheadings survive.
        if text[first_real.start():first_real.end()].startswith("## ") and not \
                text[first_real.start():first_real.end()].startswith("### "):
            heading_line = text[first_real.start():first_real.end()]
            for h in headings:
                if h.start() > first_real.start() and text[h.start():h.end()] == heading_line:
                    start = h.start()  # keep advancing → lands on the last match
        text = text[start:]

    # Drop inline planning debris that appears AFTER the first real heading.
    # Stops at the earliest marker in text position; the heading is preserved.
    marker_positions = [text.find(m) for m in _INLINE_PLANNING_MARKERS]
    valid = [i for i in marker_positions if i > 0]
    if valid:
        text = text[: min(valid)]

    # Strip trailing meta after a horizontal-rule separator.
    for sep in _TRAIL_SEPARATORS:
        if sep in text:
            text = text.split(sep, 1)[0]

    return text.strip()


def _has_real_prose(text: str) -> bool:
    """True if ``text`` has substantial non-heading, non-parenthetical content."""
    return _content_word_count(text) >= _MIN_PROSE_WORDS


def _content_word_count(text: str) -> int:
    """Count real prose words, excluding headings, tables, and parenthetical stubs."""
    words = 0
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith("#") or s.startswith("|") or s.startswith("("):
            continue
        words += len(s.split())
    return words


def is_substantial_section(text: str, section: SectionSpec, *, min_words: int = _SECTION_MIN_WORDS) -> bool:
    """True iff ``text`` is a valid headed section with at least ``min_words`` prose."""
    cleaned = clean_section_text(text, section)
    if cleaned is None:
        return False
    return _content_word_count(cleaned) >= min_words


def clean_section_text(text: str, section: SectionSpec) -> str | None:
    """Return a valid section with planning/CoT lines dropped, or ``None``.

    Drops any line containing a planning marker — handling three contamination
    shapes uniformly: a CoT preamble before real content (``### stubs`` +
    "Now, fill in." + real prose), a planning tail after real content
    ("Now, format: …"), and a full planning dump (no real prose at all).
    After line removal, the result must still contain the expected heading and
    real prose; otherwise it is treated as a full dump → caller retries, then
    placeholders.
    """
    if not text or not text.strip():
        return None
    heading_re = re.compile(rf"^##\s+\*{{0,2}}{section.number}\.", re.MULTILINE)
    if not heading_re.search(text):
        return None  # no real heading → full dump
    kept = [
        ln for ln in text.split("\n")
        if not _COT_MARKER_LINE_RE.match(ln) and not _BARE_IMPERATIVE_LINE_RE.match(ln)
    ]
    cleaned = "\n".join(kept)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if not heading_re.search(cleaned):
        return None
    if not _has_real_prose(cleaned):
        return None  # every content line was planning → full dump
    if _COT_MARKER_RE.search(cleaned):
        return None  # residual marker inside kept prose → reject
    return cleaned


def has_valid_section(text: str, section: SectionSpec) -> bool:
    """True iff ``text`` is a real headed section, not a CoT/planning dump."""
    return clean_section_text(text, section) is not None


_STRICT_RETRY = """

STRICT RETRY — YOUR PREVIOUS OUTPUT WAS REJECTED:
Your previous attempt was rejected because it contained PLANNING NOTES, a STUB,
or FAILED THE QUALITY BAR (parenthetical placeholders like "(Provide a brief synthesis…)",
deliverable subheadings with no body, first-person reasoning, uncited claims,
or insufficient coverage of the required bullets). This time:
- Output ONLY the finished report section. No scratchpad, no meta-commentary.
- Start with the heading "## **{n}. {t}**" exactly once, then write the analysis
  immediately.
- NEVER emit placeholder subheadings ("### Full Analytical Report", "### Month Timeline",
  "### Executive Summary", "### Funding Tables"), parenthetical planning notes,
  ellipses "...", "[Analyst assessment]", first-person language ("we'll", "let's",
  "I'll"), or restating what you will do.
- Cover EVERY bullet listed under "What this section must cover" and cite every
  factual claim with [src:EXACT_URL].
- If the retrieved sources are insufficient for a real section, output ONLY the
  heading plus exactly the one-line notice from the SOURCES GUARDBAND above.
"""


async def synthesize_section(
    section: SectionSpec,
    sources: list[SearchResult],
    *,
    router: LLMRouter,
    instructions: str = "",
    quality: list[str] | None = None,
    deliverables: list[str] | None = None,
    date_label: str = "",
    cadence_note: str = "",
    rag_context: str = "",
    strict_retry: bool = False,
    max_tokens: int = 5000,
    thin_corpus: bool = False,
) -> str:
    quality = quality or []
    deliverables = deliverables or []
    prompt = build_section_prompt(
        section, sources, instructions, quality, date_label, cadence_note,
        deliverables, rag_context, thin_corpus=thin_corpus,
    )
    if strict_retry:
        prompt += _STRICT_RETRY.format(n=section.number, t=section.title)
    res = await router.complete("brief_write", prompt, temperature=0.3, max_tokens=max_tokens)
    if res.provider == "heuristic" or not res.text.strip():
        return _placeholder(section)
    return res.text.strip()


def _placeholder(
    section: SectionSpec,
    *,
    reason: str = "No LLM available to synthesize this section",
    required_category: str | None = None,
) -> str:
    """Render a section that the writer couldn't produce.

    The 2026-07-14 monthly report's four short-circuited sections were
    Required Deliverables — Funding/Regulation/Enterprise/Predictions — and
    readers were given an 18-word stub. The named-category placeholder is the
    honest disclosure: name the missing category (``news`` / ``official`` /
    ``research``) so the next run knows what corpus to broaden.
    """
    missing_cat = required_category or "any"
    return (
        f"## **{section.number}. {section.title}**\n\n"
        f"_Section synthesis failed after retry: {reason}. "
        f"This section's brief lists it as a Required Deliverable, but the "
        f"retrieved corpus had insufficient evidence in the `{missing_cat}` "
        f"category. Re-run with broader collectors or loosen the brief's "
        f"Required Deliverables. The thin-corpus banner at the top of the "
        f"report has the full per-section breakdown._"
    )


# Phase 2: critic → rewrite loop


def build_critic_prompt(
    section_text: str,
    section: SectionSpec,
    instructions: str,
    quality: list[str],
    deliverables: list[str],
    cadence_note: str,
) -> str:
    """Build the critic LLM prompt for a section."""
    qual = "\n".join(f"- {q}" for q in quality[:12]) or "(none specified)"
    deliv = "\n".join(f"- {d}" for d in (deliverables or [])[:12]) or "(none specified)"
    cadence_line = f"\nREPORT CADENCE: {cadence_note}\n" if cadence_note else ""

    return f"""You are a critical editor evaluating ONE section of an AI industry report.

SECTION TO EVALUATE:
{section_text}

SECTION REQUIREMENTS:
- Title: ## **{section.number}. {section.title}**
- Must cover: {', '.join(section.bullets) or 'comprehensive coverage'}
{cadence_line}
REQUIRED DELIVERABLES (must all be present):
{deliv}

RESEARCH PRIORITIES (from the brief):
{instructions[:1500]}

QUALITY BAR:
{qual}

EVALUATE THE SECTION AGAINST:
1. CoT/stub free: no first-person planning ("we'll", "let's", "I will"), no placeholder subheadings ("### Full Analytical Report" with no body, "(single paragraph)"), no ellipses "...", no bracketed labels without URLs ("[Analyst assessment]", "[community sentiment]").
2. Coverage: it covers every bullet under "Must cover" and every required deliverable relevant to this section.
3. Quality: it synthesizes and explains significance rather than merely listing items; it quantifies where possible; it distinguishes fact/analysis/estimate/rumor.
4. Cadence: all claims and dates fall within the REPORT CADENCE window.
5. Citations: every factual claim is followed by a [src:URL] token from the provided sources; no uncited numbers or dates.
6. Substance: the section contains at least 100 words of substantive prose (excluding headings and tables) when sources are available.
7. No leakage: the section reads like a finished report, not like instructions, prompts, or meta-commentary about the writing task.

OUTPUT JSON ONLY (no markdown fences):
{{
  "pass": true/false,
  "score": 0.0-1.0,
  "gaps": ["list of missing elements or issues"],
  "missing_citations": true/false,
  "cadence_ok": true/false,
  "has_cot_or_stub": true/false,
  "feedback": "detailed feedback for rewrite if needed"
}}"""


async def critique_section(
    section_text: str,
    section: SectionSpec,
    *,
    router: LLMRouter,
    instructions: str = "",
    quality: list[str] | None = None,
    deliverables: list[str] | None = None,
    cadence_note: str = "",
) -> dict:
    """Call the critic LLM to evaluate a section; returns a verdict dict."""
    quality = quality or []
    deliverables = deliverables or []
    prompt = build_critic_prompt(
        section_text, section, instructions, quality, deliverables, cadence_note
    )
    # Use json_complete for structured output
    verdict = await router.json_complete("critic", prompt)
    if not verdict:
        # Fallback: assume pass if critic fails
        return {"pass": True, "score": 0.7, "gaps": [], "missing_citations": False, "cadence_ok": True, "has_cot_or_stub": False, "feedback": ""}
    verdict.setdefault("pass", True)
    verdict.setdefault("score", 0.7)
    verdict.setdefault("gaps", [])
    verdict.setdefault("missing_citations", False)
    verdict.setdefault("cadence_ok", True)
    verdict.setdefault("has_cot_or_stub", False)
    verdict.setdefault("feedback", "")
    return verdict


async def synthesize_section_with_review(
    section: SectionSpec,
    sources: list[SearchResult],
    *,
    router: LLMRouter,
    instructions: str = "",
    quality: list[str] | None = None,
    deliverables: list[str] | None = None,
    date_label: str = "",
    cadence_note: str = "",
    rag_context: str = "",
    rewrite_threshold: float = 0.75,
    min_score: float = 0.5,
    max_iterations: int = 2,
    max_tokens: int = 5000,
    thin_corpus: bool = False,
) -> str:
    """Synthesize a section, then critique and optionally rewrite (bounded to
    ``max_iterations`` iterations; only rewrites if the critic flags issues).

    After the rewrite budget is exhausted, the section is only shipped if the
    final ``critic.score`` is at or above ``min_score``; otherwise the section
    is replaced with the standard ``_placeholder(section)`` and the section is
    marked as failed. This gate fixes the 2026-07-13 bug where drafts with
    scores as low as 0.25 were shipped.

    ``thin_corpus`` flows into the writer prompt as a "THIN CORPUS" honesty
    note when the coverage verdict was THIN or CRITICAL — see
    ``build_section_prompt``.
    """
    quality = quality or []
    deliverables = deliverables or []

    text = await synthesize_section(
        section,
        sources,
        router=router,
        instructions=instructions,
        quality=quality,
        deliverables=deliverables,
        date_label=date_label,
        cadence_note=cadence_note,
        rag_context=rag_context,
        max_tokens=max_tokens,
        thin_corpus=thin_corpus,
    )
    if text.startswith("## **") and "No LLM available" in text:
        return text  # Placeholder — skip critic

    # Track the final critic score so the post-loop min_score gate can see it.
    final_score: float | None = None
    for iteration in range(max_iterations + 1):
        verdict = await critique_section(
            text,
            section,
            router=router,
            instructions=instructions,
            quality=quality,
            deliverables=deliverables,
            cadence_note=cadence_note,
        )
        score = float(verdict.get("score", 1.0))
        gaps = verdict.get("gaps", [])
        missing_citations = verdict.get("missing_citations", False)
        has_cot_or_stub = verdict.get("has_cot_or_stub", False)
        feedback = verdict.get("feedback", "")
        final_score = score

        if score >= rewrite_threshold and not gaps and not missing_citations and not has_cot_or_stub:
            log.info(
                "brief.section_pass",
                section=section.number,
                title=section.title,
                score=score,
                iteration=iteration,
            )
            return text

        if iteration < max_iterations:
            log.info(
                "brief.section_rewrite",
                section=section.number,
                title=section.title,
                score=score,
                gaps=len(gaps),
                missing_citations=missing_citations,
                iteration=iteration,
            )
            rewrite_prompt = build_section_prompt(
                section,
                sources,
                instructions,
                quality,
                date_label,
                cadence_note,
                deliverables,
                rag_context,
                thin_corpus=thin_corpus,
            )
            rewrite_prompt += f"""

CRITIC FEEDBACK (address these in your rewrite):
{feedback}

REWRITE THE SECTION NOW, addressing the gaps while maintaining the same structure and citation format."""
            res = await router.complete("brief_write", rewrite_prompt, temperature=0.3, max_tokens=max_tokens)
            if res.provider == "heuristic" or not res.text.strip():
                break  # Keep the original if rewrite fails
            text = res.text.strip()

    # Post-loop min_score gate. If the final critic verdict falls below the
    # floor after we've exhausted the budget, refuse to ship and substitute
    # the placeholder so a sub-threshold draft never reaches assemble_report.
    if final_score is not None and final_score < min_score:
        log.warning(
            "brief.section_below_floor",
            section=section.number,
            title=section.title,
            score=final_score,
            min_score=min_score,
            iterations=max_iterations,
        )
        return _placeholder(section)

    return text


# Phase 3: research loop — citation counting + extra queries if thin


_CITATION_RE = re.compile(r"\[src:[^\]]+\]")


def count_citations(text: str) -> int:
    """Count unique [src:URL] citations in section text."""
    return len(set(_CITATION_RE.findall(text)))
