"""Unit tests for the query planner."""

from __future__ import annotations

from newsagent.pipeline.planner import plan_queries
from newsagent.pipeline.spec import BriefSpec, SectionSpec


def _spec(n_sections=3):
    return BriefSpec(
        title="T",
        source_names=["OpenAI", "Anthropic", "Google", "xAI"],
        sections=[
            SectionSpec(number=i + 1, title=f"Section {i + 1}", bullets=[f"point {i}-a", f"point {i}-b"])
            for i in range(n_sections)
        ],
    )


def test_plan_has_section_and_source_queries():
    spec = _spec(3)
    q = plan_queries(spec, per_section=2, source_queries=2)
    section_q = [x for x in q if x.kind == "section"]
    source_q = [x for x in q if x.kind == "source"]
    # 3 sections * (1 section-level + 1 bullet) = 6
    assert len(section_q) == 6
    assert len(source_q) == 2
    assert source_q[0].text.startswith("OpenAI")


def test_plan_respects_caps():
    spec = _spec(5)
    q = plan_queries(spec, per_section=1, source_queries=0)
    assert all(x.kind != "source" for x in q)
    # 5 sections * 1 query each
    assert len([x for x in q if x.kind == "section"]) == 5


def test_plan_year_in_query():
    spec = _spec(1)
    q = plan_queries(spec, year="2027")
    assert "2027" in q[0].text
