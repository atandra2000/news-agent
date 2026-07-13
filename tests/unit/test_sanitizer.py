"""Unit tests for the reasoning-leakage sanitizer.

The sanitizer is the single enforcement point: no banned phrase may survive
into the final markdown.  These tests verify every banned category.
"""

from __future__ import annotations

from hermes.pipeline.sanitizer import (
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