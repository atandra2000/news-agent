"""Per-section synthesis helpers: source selection, CoT backstop, validity gate."""

from __future__ import annotations

from newsagent.pipeline.search import SearchResult
from newsagent.pipeline.spec import SectionSpec
from newsagent.pipeline.sanitizer import sanitize_text
from newsagent.pipeline.synthesize import (
    _content_word_count,
    build_section_prompt,
    clean_section_text,
    count_citations,
    extract_prose,
    is_substantial_section,
    select_relevant,
)


def _sec() -> SectionSpec:
    return SectionSpec(number=1, title="Pulse", bullets=["alpha", "beta"])


def _src(title: str, url: str, content: str = "x", date: str | None = None) -> SearchResult:
    return SearchResult(title=title, url=url, content=content, published_date=date, source="example.com")


def test_select_relevant_ranks_by_keyword():
    sources = [
        _src("Other news", "https://other.com/1", "irrelevant"),
        _src("Alpha release", "https://example.com/a", "alpha is mentioned here"),
        _src("Beta beta beta", "https://example.com/b", "more beta here"),
    ]
    picked = select_relevant(_sec(), sources, top_k=2)
    urls = [s.url for s in picked]
    # example.com/ hosts (alpha + beta) should rank above other.com
    assert "https://other.com/1" not in urls


def test_select_relevant_respects_domain_cap():
    sources = [
        _src("a1", "https://a.com/1"),
        _src("a2", "https://a.com/2"),
        _src("a3", "https://a.com/3"),
        _src("a4", "https://a.com/4"),
        _src("b1", "https://b.com/1"),
    ]
    picked = select_relevant(_sec(), sources, top_k=4, domain_cap=2)
    hosts = [s.url.split("/")[2] for s in picked]
    assert hosts.count("a.com") <= 2


def test_source_priority_boost_official_beats_community():
    """An arxiv item must outrank an HN item on the same paper (Scope 8).

    Without source-priority boost, a high-keyword-match HN comment on a paper
    can outrank the arxiv abstract for the same paper. With the boost, arxiv
    wins because the brief lists research sources above community.
    """
    sources = [
        # HN comment with strong keyword match (would win on raw keyword score).
        SearchResult(
            title="Discussion of alpha on Hacker News",
            url="https://news.ycombinator.com/item?id=1",
            content="alpha alpha alpha beta beta",
            source="hacker_news",
        ),
        # arxiv abstract with the same content but lower raw keyword density.
        SearchResult(
            title="Alpha: a new method",
            url="https://arxiv.org/abs/0001",
            content="We present alpha. A short abstract.",
            source="arxiv",
        ),
    ]
    picked = select_relevant(_sec(), sources, top_k=2)
    # arxiv must come first despite the HN comment having more keyword matches.
    assert picked[0].url == "https://arxiv.org/abs/0001"
    assert picked[1].url.startswith("https://news.ycombinator.com")


def test_diversity_floor_swaps_for_unseen_source_types():
    """When top_k would otherwise return one source type, swap for variety.

    Mirrors the 2026-07-13 bug: 12 HN items would win over 12 items spread
    across 4 source types. With min_source_types=3, the result must include
    at least 3 distinct source types.
    """
    sources = (
        [SearchResult(title=f"hn{i}", url=f"https://hn/{i}",
                      content="alpha beat beat beat", source="hacker_news")
         for i in range(6)]
        + [SearchResult(title=f"arxiv{i}", url=f"https://arxiv/{i}",
                        content="alpha study", source="arxiv")
           for i in range(3)]
        + [SearchResult(title=f"hf{i}", url=f"https://hf/{i}",
                        content="alpha model", source="huggingface")
           for i in range(2)]
        + [SearchResult(title=f"rss{i}", url=f"https://rss/{i}",
                        content="alpha news", source="rss")
           for i in range(2)]
    )
    picked = select_relevant(_sec(), sources, top_k=8, min_source_types=3)
    types = {s.source for s in picked}
    assert len(types) >= 3, f"Expected ≥3 source types in picked set, got {types}"


def test_diversity_floor_no_swap_when_already_diverse():
    """If top_k already covers min_source_types, no swap is needed."""
    sources = (
        [SearchResult(title=f"a{i}", url=f"https://arxiv/{i}",
                      content="alpha study", source="arxiv")
         for i in range(3)]
        + [SearchResult(title=f"h{i}", url=f"https://hn/{i}",
                        content="alpha news", source="hacker_news")
           for i in range(3)]
        + [SearchResult(title=f"r{i}", url=f"https://rss/{i}",
                        content="alpha news", source="rss")
           for i in range(3)]
    )
    picked = select_relevant(_sec(), sources, top_k=6, min_source_types=3)
    types = {s.source for s in picked}
    # Already diverse, picked set should be untouched in composition.
    assert types == {"arxiv", "hacker_news", "rss"}


def test_source_priority_boost_known_values():
    from newsagent.pipeline.synthesize import source_priority_boost
    assert source_priority_boost("arxiv") >= 4
    assert source_priority_boost("openai") >= 5
    assert source_priority_boost("hacker_news") == 1
    assert source_priority_boost("unknown_source") == 0
    assert source_priority_boost(None) == 0


def test_clean_section_text_drops_planning_lines():
    text = (
        "## **1. Pulse**\n\n"
        "Now, write a section about this.\n\n"
        + ("Real analysis paragraph with enough words to pass the validity gate. " * 6) + "\n"
    )
    out = clean_section_text(text, _sec())
    assert out is not None
    assert "Now, write" not in out
    assert "Real analysis" in out


def test_clean_section_text_rejects_no_heading():
    text = "Random prose with no section heading at all."
    assert clean_section_text(text, _sec()) is None


def test_clean_section_text_rejects_planning_only_dump():
    text = "## **1. Pulse**\n\nNow, write.\nFirst, gather all.\nThen, flesh out.\n"
    assert clean_section_text(text, _sec()) is None


def test_content_word_count_excludes_headings_and_tables():
    text = "## **1. Pulse**\n\n| col1 | col2 |\n| --- | --- |\n| a | b |\n\nA real paragraph with five words here.\n"
    assert _content_word_count(text) == 7  # "A real paragraph with five words here" = 7 tokens


def test_is_substantial_section_true_for_real_section():
    text = "## **1. Pulse**\n\n" + ("meaningful prose " * 50)
    assert is_substantial_section(text, _sec())


def test_is_substantial_section_false_for_stub():
    text = "## **1. Pulse**\n\nshort"
    assert not is_substantial_section(text, _sec())


def test_count_citations_unique():
    text = "alpha [src:https://a.com/1] beta [src:https://a.com/1] gamma [src:https://b.com/1]"
    assert count_citations(text) == 2


# ── extract_prose: CoT scratchpad backstop ─────────────────────────────────────
# Moved here from test_cognition_refactor.py after the stages/ directory was
# deleted. extract_prose now lives in pipeline/synthesize.py alongside the
# related CoT-marker sanitizer logic.


_BROKEN_SECTION = (
    "We need to write a polished, institutional-grade report section. "
    "We don't have exact numbers, we have to be creative but realistic. "
    "Let's assume OpenAI released GPT-5.6 in this period. "
    "We might need to fabricate some details to fill the comparison table.\n\n"
    "## **1. Executive Summary**\n\n"
    "July 2026 saw frontier-model competition intensify [src:https://example.com/1]. "
    "Governance became operational [src:https://example.com/3]."
)


def test_extract_prose_scratchpad_dropped_heading_preserved():
    cleaned = sanitize_text(extract_prose(_BROKEN_SECTION))
    assert "We need to write a polished" not in cleaned
    assert "Let's assume" not in cleaned
    assert "fabricate" not in cleaned
    assert "be creative but realistic" not in cleaned
    assert "## **1. Executive Summary**" in cleaned
    assert "[src:https://example.com/1]" in cleaned
    assert "[src:https://example.com/3]" in cleaned


def test_extract_prose_noop_when_no_heading():
    text = "We need to summarize the month. July was busy."
    cleaned = sanitize_text(extract_prose(text))
    assert "We need to" not in cleaned
    assert "July was busy." in cleaned


def test_extract_prose_leading_scratchpad_heading_skipped():
    text = (
        "## Reasoning\n\nLet's think about this. We should cover X.\n\n"
        "## **2. Frontier Models**\n\nReal content [src:https://x/1]."
    )
    cleaned = sanitize_text(extract_prose(text))
    assert "## Reasoning" not in cleaned
    assert "We should cover" not in cleaned
    assert "## **2. Frontier Models**" in cleaned


def test_extract_prose_heading_first_dithering_collapsed_to_last():
    # Model emits heading FIRST, then stub subheadings + CoT, then re-emits
    # the SAME heading with real prose. Must collapse to the last occurrence.
    text = (
        "## **1. Executive Summary**\n\n"
        "### Full Analytical Report\n\n... detailed analysis ...\n\n"
        "### Month Timeline\n\n... dates ...\n\n"
        "I'll just put analyst assessment as the src. Since I'm simulating, "
        "I'll invent plausible content for June 2026. I'll begin:\n\n"
        "## **1. Executive Summary**\n\n"
        "July 2026 saw frontier-model competition intensify [src:https://x/1]. "
        "Governance became operational [src:https://x/3]."
    )
    cleaned = sanitize_text(extract_prose(text))
    assert "Full Analytical Report" not in cleaned
    assert "... detailed analysis ..." not in cleaned
    assert "... dates ..." not in cleaned
    assert "I'll" not in cleaned
    assert "simulating" not in cleaned
    assert "invent plausible" not in cleaned
    assert cleaned.count("## **1. Executive Summary**") == 1
    assert "frontier-model competition" in cleaned
    assert "[src:https://x/1]" in cleaned


def test_extract_prose_legit_repeated_subheading_survives():
    # Repeated level-3 subheadings (two funding tables) must NOT be collapsed —
    # only level-2 duplicates trigger the collapse.
    text = (
        "## **8. Funding**\n\n"
        "### Funding Tables\n\ntable one [src:https://x/1]\n\n"
        "### Funding Tables\n\ntable two [src:https://x/2]"
    )
    cleaned = sanitize_text(extract_prose(text))
    assert cleaned.count("### Funding Tables") == 2
    assert "table one" in cleaned
    assert "table two" in cleaned


def test_extract_prose_strips_inline_planning_debris_after_heading():
    raw = """## **3. Frontier & Infrastructure**

... prose ...

**Month at a Glance (Frontier & Infrastructure)**
- [date] ...
...

**Infrastructure Comparison Table**
| ... |

**Key Statistics**
- ...

**Strategic Conclusions**
...

Similarly, OpenScience might be an AI workbench...

Structure:

- Intro: ...
- Serving Frameworks: ...
- Make sure to cite every claim.
- The vLLM release had 558 commits: need citation for that.

## **4. Research Breakthroughs**"""
    out = extract_prose(raw, title="Frontier & Infrastructure")
    assert "... prose ..." not in out
    assert "Structure:" not in out
    assert "Make sure to cite every claim" not in out
    assert "**4. Research Breakthroughs**" not in out
    # Real heading is preserved:
    assert out.startswith("## **3. Frontier & Infrastructure**")


# ── section-rewrite gate: pin the floor so 0.25/0.35 can never ship ──────────
# 2026-07-13 monthly brief: Research & Breakthroughs shipped with score=0.35
# and Benchmarks shipped with score=0.25 because the loop returned the
# final text unconditionally after exhausting rewrites.


def test_section_rewrite_budget_defaults():
    from newsagent.pipeline.synthesize import SectionRewriteBudget

    b = SectionRewriteBudget()
    assert b.min_score == 0.5
    assert b.max_iterations == 2


def test_section_rewrite_budget_explicit_values():
    from newsagent.pipeline.synthesize import SectionRewriteBudget

    b = SectionRewriteBudget(min_score=0.6, max_iterations=3)
    assert b == SectionRewriteBudget(min_score=0.6, max_iterations=3)


async def test_section_rewrite_loop_placeholder_when_below_floor(monkeypatch):
    """The 2026-07-13 bug: a section whose final critic score is 0.25 must NOT
    be shipped. The loop must substitute the existing _placeholder(section)
    after exhausting its iteration budget.
    """
    from newsagent.pipeline import synthesize as synth
    from newsagent.pipeline.synthesize import (
        SectionRewriteBudget,
        synthesize_section_with_review,
    )
    from tests.helpers import FakeRouter

    section = SectionSpec(number=6, title="Benchmarks & Capability Moves", bullets=["MMLU", "GPQA"])

    # Force the writer to always emit a real-looking (but critic-rejected) draft.
    real_text = (
        "## **6. Benchmarks & Capability Moves**\n\n"
        "July saw MMLU climb to 92% [src:https://example.com/b]."
    )

    async def fake_synthesize(*_args, **_kwargs):
        return real_text

    # Critic verdict: score=0.25, 8 gaps, citations missing. Mirrors the bad log.
    bad_verdict = {
        "pass": False,
        "score": 0.25,
        "gaps": ["g"] * 8,
        "missing_citations": True,
        "cadence_ok": True,
        "has_cot_or_stub": False,
        "feedback": "rewrite harder",
    }

    async def fake_critique(*_args, **_kwargs):
        return bad_verdict

    monkeypatch.setattr(synth, "synthesize_section", fake_synthesize)
    monkeypatch.setattr(synth, "critique_section", fake_critique)

    budget = SectionRewriteBudget(min_score=0.5, max_iterations=2)
    out = await synthesize_section_with_review(
        section, [], router=FakeRouter(),
        rewrite_threshold=0.75,
        min_score=budget.min_score,
        max_iterations=budget.max_iterations,
    )

    # The score-0.25 draft must NOT be the shipped text.
    assert "MMLU climb to 92%" not in out
    # The placeholder from synthesize.py must be the returned text.
    assert out.startswith("## **6. Benchmarks & Capability Moves**")
    assert "No LLM available to synthesize this section" in out


async def test_section_rewrite_loop_passes_above_floor(monkeypatch):
    """A section whose final score meets the floor must ship the real prose."""
    from newsagent.pipeline import synthesize as synth
    from newsagent.pipeline.synthesize import (
        SectionRewriteBudget,
        synthesize_section_with_review,
    )
    from tests.helpers import FakeRouter

    section = SectionSpec(number=1, title="Executive Summary", bullets=["frontier models"])

    real_text = (
        "## **1. Executive Summary**\n\n"
        "Frontier models advanced significantly this month [src:https://example.com/a]."
    )

    async def fake_synthesize(*_args, **_kwargs):
        return real_text

    good_verdict = {
        "pass": True,
        "score": 0.85,
        "gaps": [],
        "missing_citations": False,
        "cadence_ok": True,
        "has_cot_or_stub": False,
        "feedback": "",
    }

    async def fake_critique(*_args, **_kwargs):
        return good_verdict

    monkeypatch.setattr(synth, "synthesize_section", fake_synthesize)
    monkeypatch.setattr(synth, "critique_section", fake_critique)

    budget = SectionRewriteBudget(min_score=0.5, max_iterations=2)
    out = await synthesize_section_with_review(
        section, [], router=FakeRouter(),
        rewrite_threshold=0.75,
        min_score=budget.min_score,
        max_iterations=budget.max_iterations,
    )

    # Real prose ships when critic accepts.
    assert "Frontier models advanced significantly" in out
    assert "No LLM available" not in out


# ── _placeholder: named missing category ────────────────────────────────────
# Task 2: when synthesis fails after retry, the placeholder must name the
# missing category so the reader knows what corpus to broaden next run.
# The 2026-07-14 monthly report's four short-circuited sections were Required
# Deliverables — Funding/Regulation/Enterprise/Predictions. The named-category
# placeholder is the new "honest disclosure" the gate can't deliver.


def test_placeholder_names_missing_category():
    from newsagent.pipeline.synthesize import _placeholder

    sec = SectionSpec(number=6, title="Funding, M&A & Business")
    out = _placeholder(sec, reason="writer emitted planning notes after retry",
                       required_category="news")
    assert "Required Deliverable" in out
    assert "`news`" in out
    assert "Funding, M&A & Business" in out


def test_placeholder_default_reason_for_heuristic_provider():
    from newsagent.pipeline.synthesize import _placeholder

    sec = SectionSpec(number=1, title="Pulse")
    out = _placeholder(sec)  # no reason → default "no LLM available"
    assert "No LLM available" in out
    # No required_category → falls back to "any".
    assert "`any`" in out


# Task 3 (corpus-coverage-fixes): frontier/model sections must carry an
# explicit Markdown-comparison-table requirement. The 2026-07-14 monthly
# report's §3 "Frontier & Infrastructure" shipped as 85 words of prose with
# no table; the general "use a Markdown comparison table" rule in the writer
# prompt was too soft. These tests pin the section-title-conditional block.


def test_frontier_section_prompt_requires_comparison_table():
    sec = SectionSpec(number=3, title="Frontier & Infrastructure",
                      bullets=["model releases", "chips", "serving frameworks"])
    prompt = build_section_prompt(sec, [], "instructions", ["quality"], "July 2026")
    lowered = prompt.lower()
    # Explicit table requirement must be in the prompt
    assert "comparison table" in lowered
    assert "model" in lowered and "developer" in lowered and "context" in lowered
    # Must mention silicon or hardware (so the writer includes chips)
    assert "silicon" in lowered or "hardware" in lowered or "chip" in lowered


def test_non_frontier_section_prompt_does_not_force_table():
    sec = SectionSpec(number=6, title="Funding, M&A & Business", bullets=["rounds"])
    prompt = build_section_prompt(sec, [], "instructions", ["quality"], "July 2026")
    # The general "use a Markdown comparison table" rule is fine; the
    # FRONTIER-SPECIFIC block must not appear.
    assert "model, developer, context" not in prompt.lower()


# Task 4 (corpus-coverage-fixes): for sections that need a specific category
# (e.g. "official" for frontier-model sections, "news" for funding), the writer
# should get the category-matched RSS feed at the top when keyword scores are
# equal. Without the per-category tiebreaker, all RSS items are tied at boost=2
# and the writer gets a shuffled list regardless of category stamp.


def test_select_relevant_prefers_official_for_frontier_section():
    # Three items: one official (openai), one community (substack), one news.
    # All share the keyword so all score 1.0 on the base metric; the only
    # differentiator is the per-category tiebreaker. Title "Frontier Model
    # Releases" maps to required_category="official" via _SECTION_CATEGORY_HINTS,
    # so the openai.com item must rank above the substack community item.
    sec = SectionSpec(number=3, title="Frontier Model Releases",
                      bullets=["Qwen3 model release"])
    items = [
        SearchResult(title="Qwen3 release", url="https://substack.example/x",
                     content="Qwen3 release", source="rss",
                     extra={"category": "community"},
                     published_date="2026-07-14"),
        SearchResult(title="Qwen3 release", url="https://openai.com/x",
                     content="Qwen3 release", source="rss",
                     extra={"category": "official"},
                     published_date="2026-07-14"),
        SearchResult(title="Qwen3 release", url="https://venturebeat.com/x",
                     content="Qwen3 release", source="rss",
                     extra={"category": "news"},
                     published_date="2026-07-14"),
    ]
    out = select_relevant(sec, items, top_k=3, domain_cap=3, min_source_types=1)
    urls = [s.url for s in out]
    assert urls.index("https://openai.com/x") < urls.index("https://substack.example/x")


def test_select_relevant_prefers_news_for_funding_section():
    # Mirror of the frontier test: funding section needs category="news" via
    # _SECTION_CATEGORY_HINTS, so the venturebeat news item must outrank the
    # openai.com official item on equal keyword scores.
    sec = SectionSpec(number=8, title="Funding, M&A & Business",
                      bullets=["funding rounds"])
    items = [
        SearchResult(title="Funding round", url="https://openai.com/x",
                     content="Funding round", source="rss",
                     extra={"category": "official"},
                     published_date="2026-07-14"),
        SearchResult(title="Funding round", url="https://venturebeat.com/x",
                     content="Funding round", source="rss",
                     extra={"category": "news"},
                     published_date="2026-07-14"),
        SearchResult(title="Funding round", url="https://substack.example/x",
                     content="Funding round", source="rss",
                     extra={"category": "community"},
                     published_date="2026-07-14"),
    ]
    out = select_relevant(sec, items, top_k=3, domain_cap=3, min_source_types=1)
    urls = [s.url for s in out]
    assert urls.index("https://venturebeat.com/x") < urls.index("https://openai.com/x")

