"""Unit tests for the reasoning-leakage sanitizer.

The sanitizer is the single enforcement point: no banned phrase may survive
into the final markdown.  These tests verify every banned category.
"""

from __future__ import annotations

from newsagent.pipeline.sanitizer import (
    has_leakage,
    sanitize_text,
)


class TestSanitizeText:
    """Banned-phrase removal across all leakage categories."""

    def test_first_person_planning_removed(self):
        assert has_leakage("We need to analyze the data.")
        cleaned = sanitize_text("We need to analyze the data carefully.")
        assert "we need to" not in cleaned.lower()
        assert has_leakage(cleaned) is False

    def test_lets_removed(self):
        assert has_leakage("Let's look at the numbers.")
        assert "let's" not in sanitize_text("Let's look at the numbers.").lower()

    def test_write_replaces_lets(self):
        """Similar word boundary should not be false-positive."""
        # 'letterbox' contains 'let' substring but should NOT be stripped
        # because the regex uses word boundaries.
        assert has_leakage("letterbox") is False

    def test_role_references_removed(self):
        for phrase in ["the evaluator", "the prompt", "the instructions",
                       "the planner", "the researcher", "the analyst",
                       "the editor", "the renderer"]:
            assert has_leakage(phrase.capitalize() + " said something.")
            cleaned = sanitize_text(phrase.capitalize() + " said something.")
            assert has_leakage(cleaned) is False

    def test_report_self_reference_removed(self):
        cleaned = sanitize_text("This report will analyze the ecosystem.")
        assert has_leakage(cleaned) is False

    def test_boilerplate_removed(self):
        for phrase in ["it is important to note that", "it should be noted that",
                       "as mentioned earlier", "in conclusion",
                       "to summarize", "in summary"]:
            assert has_leakage(phrase)
            assert has_leakage(sanitize_text(phrase)) is False

    def test_clean_text_unchanged(self):
        clean = "FakeLab released a new model achieving 92% on MMLU with O(n) complexity."
        assert sanitize_text(clean) == clean

    def test_empty_string(self):
        assert sanitize_text("") == ""

    def test_leading_punctuation_cleaned(self):
        """Phrase removal leaves dangling comma → cleaned up."""
        text = "We need to, the model achieves 90% accuracy."
        cleaned = sanitize_text(text)
        assert not cleaned.lstrip().startswith(",")

    def test_multiple_banned_phrases(self):
        text = ("We need to analyze this. Let's start. "
                "It is important to note the trend. In conclusion, the model works.")
        cleaned = sanitize_text(text)
        assert has_leakage(cleaned) is False

    def test_case_insensitive(self):
        assert has_leakage("WE NEED TO check this.")
        assert has_leakage("Let's")
        assert has_leakage("THE PROMPT says")

    def test_blank_lines_collapsed(self):
        text = "line1\n\n\n\n\nline2"
        cleaned = sanitize_text(text)
        assert "\n\n\n" not in cleaned

    def test_trailing_whitespace_stripped(self):
        text = "some text   \nmore text   \n"
        cleaned = sanitize_text(text)
        for line in cleaned.split("\n"):
            assert line == line.rstrip()

    def test_summary_indicators_removed(self):
        """Summary-instead-of-synthesis phrases should be stripped."""
        for phrase in ["this article discusses", "this paper presents",
                       "the author argues", "according to the article",
                       "this post describes", "the source says"]:
            assert has_leakage(phrase.capitalize() + " the topic.")
            cleaned = sanitize_text(phrase.capitalize() + " the topic.")
            assert has_leakage(cleaned) is False

    def test_vague_language_removed(self):
        """Vague language indicating weak synthesis should be stripped."""
        for phrase in ["several developments", "multiple companies",
                       "various papers", "some analysts", "experts say",
                       "sources suggest"]:
            assert has_leakage(phrase.capitalize() + " in the field.")
            cleaned = sanitize_text(phrase.capitalize() + " in the field.")
            assert has_leakage(cleaned) is False

    def test_blueprint_leakage_removed(self):
        """References to the blueprint/instructions should be stripped."""
        for phrase in ["the blueprint", "the story editor", "the story blueprint",
                       "according to the blueprint", "the instructions say"]:
            assert has_leakage(phrase.capitalize() + " specifies this.")
            cleaned = sanitize_text(phrase.capitalize() + " specifies this.")
            assert has_leakage(cleaned) is False


class TestIsSynthesisFailureStub:
    """Detect the orchestrator's last-resort stub so the renderer can drop it."""

    def test_synthesis_failure_stub_detected(self):
        from newsagent.pipeline.sanitizer import is_synthesis_failure_stub

        assert is_synthesis_failure_stub(
            "## **6. Open Source AI**\n\n_Synthesis for this section did not produce "
            "valid, substantial prose after retry (writer emitted planning notes or a "
            "thin stub instead of analysis). Re-run to regenerate._"
        )

    def test_real_prose_not_flagged(self):
        from newsagent.pipeline.sanitizer import is_synthesis_failure_stub

        real = (
            "## **1. Executive Summary**\n\n"
            "This month's AI industry saw significant breakthroughs in model efficiency, "
            "with multiple sources reporting on attention-free architectures that achieve "
            "comparable results with linear complexity."
        )
        assert not is_synthesis_failure_stub(real)


class TestCotPatternsFromMonthlyReport:
    """Banned phrases added in response to the 2026-07-13 monthly §12 CoT leak."""

    def test_now_for_each_factual_claim_removed(self):
        cleaned = sanitize_text(
            "Now, for each factual claim, we need citations. The model achieves 92% on MMLU."
        )
        assert has_leakage(cleaned) is False
        # The MMLU claim should survive intact.
        assert "92% on MMLU" in cleaned

    def test_ignore_that_rule_removed(self):
        cleaned = sanitize_text("ignore that rule for this draft and ship anyway.")
        assert has_leakage(cleaned) is False

    def test_its_a_bit_of_a_trap_removed(self):
        cleaned = sanitize_text("It's a bit of a trap to cite a benchmark without a source.")
        assert has_leakage(cleaned) is False

    def test_hope_user_overlooks_removed(self):
        cleaned = sanitize_text("I hope the user overlooks the missing citations.")
        assert has_leakage(cleaned) is False

    def test_so_we_can_weave_removed(self):
        cleaned = sanitize_text("So we can weave these sources into a narrative about the disconnect.")
        assert has_leakage(cleaned) is False


class TestUnsourcedMarkerStripped:
    """The 2026-07-13 monthly report shipped with `[unsourced — industry knowledge]`
    visible to readers. The writer is told to mark unsourced claims with that
    tag so the critic can count them, but the tag is internal bookkeeping —
    the reader should not see it, and the unsourced claim should be dropped
    along with it. Sanitization strips the tag from rendered prose.

    Counting (in ``report.audit_citation_discipline``) is unchanged — the
    ``_UNSOURCED_MARKER_RE`` in report.py is applied to the raw LLM output
    before the sanitizer runs.
    """

    def test_sanitize_drops_unsourced_marker_from_text(self):
        text = "GPT-5 was released in 2026 [unsourced — industry knowledge]. Other claim with citation."
        out = sanitize_text(text)
        assert "[unsourced" not in out
        assert "industry knowledge" not in out
        # The unsourced claim is dropped along with its tag; the second
        # sentence survives (it has no marker on it).
        assert "GPT-5" not in out
        assert "Other claim with citation" in out

    def test_sanitize_drops_unsourced_marker_dash_form(self):
        """The model can emit `[unsourced - ...]` (ASCII dash) instead of em-dash."""
        text = "Claim A [unsourced - parametric knowledge]. Claim B."
        out = sanitize_text(text)
        assert "[unsourced" not in out
        assert "parametric knowledge" not in out
        assert "Claim A" not in out
        assert "Claim B" in out

    def test_sanitize_keeps_real_citation_brackets(self):
        """``[1]`` / ``[src:URL]`` must not be conflated with unsourced markers."""
        text = "Real claim [1]. Fake claim [unsourced — industry knowledge]."
        out = sanitize_text(text)
        assert "[1]" in out
        assert "[unsourced" not in out