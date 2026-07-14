"""Per-section synthesis helpers: source selection, CoT backstop, validity gate."""

from __future__ import annotations

from hermes.pipeline.search import SearchResult
from hermes.pipeline.spec import SectionSpec
from hermes.pipeline.sanitizer import sanitize_text
from hermes.pipeline.synthesize import (
    _content_word_count,
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
    from hermes.pipeline.synthesize import source_priority_boost
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
