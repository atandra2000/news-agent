"""Unit tests for cross-post deduplication.

The 2026-07-13 monthly report cited the same Hacker News Cat's-grant
post 3× — once per repost ID (40491303, 40346743, 40346716) — and treated
them as 3 independent signals. The fix is in ``dedup_sources_with_cross_posts``:
URL-dedup + content-fingerprint-dedup, returning both the deduped list and
the cross-post groups so the writer prompt can cite once and note
"cross-posted N times".
"""

from __future__ import annotations

from hermes.pipeline.search import (
    SearchResult,
    content_fingerprint,
    dedup_sources_with_cross_posts,
    duplication_collapse_rate,
)


def _src(title: str, url: str, source: str = "hacker_news") -> SearchResult:
    return SearchResult(title=title, url=url, source=source)


def test_dedup_url_dedup_still_works():
    """URL-level dedup is preserved (the original dedup_sources behavior)."""
    results = [
        _src("A", "https://x/1"),
        _src("A duplicate by URL", "https://x/1"),  # same URL
        _src("B", "https://x/2"),
    ]
    deduped, groups = dedup_sources_with_cross_posts(results)
    assert len(deduped) == 2
    assert [r.url for r in deduped] == ["https://x/1", "https://x/2"]


def test_cross_post_detection_for_hn_reposts():
    """The Cat's-grant case: 3 HN items with different IDs but same title."""
    results = [
        _src("Get paid to do your own ML research (Cat's grant)",
             "https://news.ycombinator.com/item?id=40346716"),
        _src("Get paid to do your own ML research (Cat's grant)",
             "https://news.ycombinator.com/item?id=40346743"),
        _src("Get paid to do your own ML research (Cat's grant)",
             "https://news.ycombinator.com/item?id=40491303"),
    ]
    deduped, groups = dedup_sources_with_cross_posts(results)
    # Only 1 unique story after cross-post dedup.
    assert len(deduped) == 1
    assert deduped[0].url.endswith("id=40346716")  # first-seen wins
    # 1 cross-post group with 3 items.
    assert len(groups) == 1
    assert len(groups[0]) == 3
    assert all("Cat's grant" in r.title for r in groups[0])


def test_different_stories_with_similar_titles_kept_separate():
    """Titles that differ in non-whitespace characters are NOT cross-posts."""
    results = [
        _src("OpenAI releases GPT-5", "https://openai.com/blog/1"),
        _src("Anthropic releases Claude 4", "https://anthropic.com/blog/1"),
    ]
    deduped, groups = dedup_sources_with_cross_posts(results)
    assert len(deduped) == 2
    assert len(groups) == 0


def test_cross_post_on_same_host_only():
    """A story on HN and a story with the same title on Reddit are NOT cross-posts
    (different hosts = different community framings; treat as independent)."""
    results = [
        _src("Show HN: My new project", "https://news.ycombinator.com/item?id=1"),
        _src("Show HN: My new project", "https://reddit.com/r/ShowHackerNews/1"),
    ]
    deduped, groups = dedup_sources_with_cross_posts(results)
    # Different hosts → both survive, no cross-post group.
    assert len(deduped) == 2
    assert len(groups) == 0


def test_content_fingerprint_normalizes_whitespace():
    """Title whitespace differences should not prevent cross-post detection."""
    fp1 = content_fingerprint(_src("Cat's  grant", "https://hn/1"))
    fp2 = content_fingerprint(_src("Cat's grant", "https://hn/2"))
    assert fp1 == fp2


def test_content_fingerprint_strips_apostrophes():
    """Curly/straight apostrophes don't break fingerprint matching."""
    fp1 = content_fingerprint(_src("Cat's grant", "https://hn/1"))
    fp2 = content_fingerprint(_src("Cats grant", "https://hn/2"))
    # Different strings — not equal, but both normalize cleanly (no internal spaces).
    assert "  " not in fp1
    assert "  " not in fp2


def test_duplication_collapse_rate():
    assert duplication_collapse_rate(0, 0) == 0.0
    assert duplication_collapse_rate(10, 10) == 0.0
    assert duplication_collapse_rate(10, 7) == 0.3
    assert duplication_collapse_rate(10, 0) == 1.0
    # Clamp out-of-range inputs to [0, 1].
    assert duplication_collapse_rate(5, 10) == 0.0
    assert duplication_collapse_rate(10, -1) == 1.0


def test_limit_caps_deduped_output():
    """The ``limit`` param caps the deduped result, like the original ``dedup_sources``."""
    results = [_src(f"Story {i}", f"https://x/{i}") for i in range(20)]
    deduped, _ = dedup_sources_with_cross_posts(results, limit=5)
    assert len(deduped) == 5
