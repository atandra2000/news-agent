"""Unit tests for citation resolution + report assembly."""

from __future__ import annotations

from hermes.pipeline.report import assemble_report, drop_empty_subheadings, resolve_citations
from hermes.pipeline.search import SearchResult
from hermes.pipeline.spec import BriefSpec, SectionSpec


def _sources():
    return [
        SearchResult(title="A", url="https://example.com/a", source="ex.com", published_date="2026-03-01"),
        SearchResult(title="B", url="https://example.com/b", source="ex.com"),
        SearchResult(title="C", url="https://example.com/c", source="ex.com"),
    ]


def test_resolve_reorders_by_first_appearance():
    text = "Claim two [src:https://example.com/b] and one [src:https://example.com/a]."
    resolved, refs = resolve_citations(text, _sources())
    assert "[1]" in resolved and "[2]" in resolved
    assert refs[0].url == "https://example.com/b"
    assert refs[1].url == "https://example.com/a"


def test_resolve_drops_unknown_source():
    text = "Known [src:https://example.com/a] and unknown [src:https://nope.com/x]."
    resolved, refs = resolve_citations(text, _sources())
    assert "[1]" in resolved
    assert "nope.com" not in resolved
    assert len(refs) == 1


def test_resolve_tolerates_url_noise():
    text = "Note [src:https://example.com/c).] end."
    resolved, refs = resolve_citations(text, _sources())
    assert "[1]" in resolved
    assert refs[0].url == "https://example.com/c"


def test_assemble_appends_references():
    spec = BriefSpec(
        title="T",
        sections=[SectionSpec(number=1, title="Exec", bullets=["x"])],
    )
    sections_md = ["## **1. Exec**\nFinding [src:https://example.com/a]."]
    rep = assemble_report(spec, sections_md, _sources())
    assert "## **T**" in rep.text
    assert "## **References**" in rep.text
    assert "[1] A" in rep.text
    assert "https://example.com/a" in rep.text
    assert rep.references[0].url == "https://example.com/a"


def test_assemble_no_references_when_none():
    spec = BriefSpec(title="T", sections=[SectionSpec(number=1, title="Exec")])
    rep = assemble_report(spec, ["## **1. Exec**\nNo citations here."], [])
    assert "References" not in rep.text


def test_assemble_fills_missing_section_with_placeholder():
    # Empty/short sections must get a transparent placeholder, not be silently
    # dropped (the 2026-07-13 report lost section 12 this way).
    spec = BriefSpec(
        title="T",
        sections=[
            SectionSpec(number=1, title="Exec", bullets=["x"]),
            SectionSpec(number=2, title="Timeline"),
            SectionSpec(number=3, title="Models"),
        ],
    )
    rep = assemble_report(spec, ["## **1. Exec**\nBody.", "", "   "], [])
    assert "## **1. Exec**" in rep.text
    assert "## **2. Timeline**" in rep.text
    assert "## **3. Models**" in rep.text
    assert "No content synthesized" in rep.text  # section 2 placeholder
    # Section 3 (whitespace-only) also gets a placeholder, not dropped.
    assert rep.text.count("No content synthesized") == 2


def test_assemble_fills_when_fewer_sections_than_spec():
    # sections_markdown shorter than spec.sections → trailing sections placeholdered.
    spec = BriefSpec(
        title="T",
        sections=[SectionSpec(number=1, title="A"), SectionSpec(number=2, title="B")],
    )
    rep = assemble_report(spec, ["## **1. A**\nBody."], [])
    assert "## **2. B**" in rep.text
    assert "No content synthesized" in rep.text


def test_assemble_strips_analyst_assessment_figleaf():
    # The fabrication fig-leaf "[Analyst assessment]" / "[Analyst assessment,
    # community sentiment]" is not a [src:URL] token, so resolve_citations
    # leaves it as literal prose. assemble must strip it.
    spec = BriefSpec(title="T", sections=[SectionSpec(number=1, title="Exec")])
    md = "## **1. Exec**\nClaim [Analyst assessment]. Sentiment [community sentiment]. Real [src:https://example.com/a]."
    rep = assemble_report(spec, [md], _sources())
    assert "Analyst assessment" not in rep.text
    assert "community sentiment" not in rep.text
    # Real [src:URL] citation survives and resolves.
    assert "[1]" in rep.text
    assert "https://example.com/a" in rep.text


def test_assemble_does_not_strip_real_src_tokens():
    # Guard: the label-bracket stripper must not eat [src:URL] tokens.
    spec = BriefSpec(title="T", sections=[SectionSpec(number=1, title="Exec")])
    md = "## **1. Exec**\nTwo [src:https://example.com/a] and [src:https://example.com/b]."
    rep = assemble_report(spec, [md], _sources())
    assert "[1]" in rep.text and "[2]" in rep.text
    assert len(rep.references) == 2


def test_assemble_replaces_synthesis_failure_stub():
    # The orchestrator emits this exact phrase when the writer + retry both fail.
    # The 2026-07-13 monthly report shipped it as if it were real prose in §6 and
    # §7. The renderer must replace it with a transparent "section omitted" marker
    # rather than ship the phrase as analysis.
    spec = BriefSpec(
        title="T",
        sections=[
            SectionSpec(number=6, title="Open Source AI"),
            SectionSpec(number=7, title="Hardware & Infrastructure"),
        ],
    )
    fail_stub = (
        "## **6. Open Source AI**\n\n"
        "_Synthesis for this section did not produce valid, substantial prose "
        "after retry (writer emitted planning notes or a thin stub instead of "
        "analysis). Re-run to regenerate._"
    )
    rep = assemble_report(spec, [fail_stub, ""], [])
    # The fail-stub phrase must NOT appear in the final report.
    assert "synthesis for this section did not produce" not in rep.text.lower()
    # A short "section omitted" marker replaces it.
    assert "section omitted" in rep.text.lower()
    # Section 7 still gets its normal empty placeholder (different code path).
    assert rep.text.count("No content synthesized") == 1


class TestCitationDiscipline:
    """Distinguish cited evidence from parametric-knowledge filler.

    The 2026-07-13 monthly §3 rendered a LangSmith/RAGAS/OpenAI Evals
    comparison table with the inline disclaimer that it was 'industry
    knowledge as of mid-2026' — visible to a careful reader, but not
    separated from cited claims. Scope 5: writer prompt instructs the
    model to mark unsourced claims with [unsourced — industry knowledge];
    audit_citation_discipline reports how many sentences have citations,
    how many are tagged, and how many are NEITHER (potential fabrications).
    """

    def test_audit_counts_cited_sentences(self):
        from hermes.pipeline.report import audit_citation_discipline
        body = (
            "OpenAI released a new model [src:https://x/1]. "
            "The model achieves 92% on MMLU [src:https://x/2]. "
            "The benchmark suite is widely used in industry."
        )
        out = audit_citation_discipline(body)
        assert out["cited"] == 2
        assert out["unsourced"] == 0
        assert out["unmarked"] == 1

    def test_audit_counts_unsourced_tagged_sentences(self):
        from hermes.pipeline.report import audit_citation_discipline
        body = (
            "LangSmith was launched by LangChain in 2023 [unsourced — industry knowledge]. "
            "RAGAS is an open-source RAG evaluation framework [unsourced — industry knowledge]."
        )
        out = audit_citation_discipline(body)
        assert out["cited"] == 0
        assert out["unsourced"] == 2
        assert out["unmarked"] == 0

    def test_audit_handles_mixed(self):
        from hermes.pipeline.report import audit_citation_discipline
        body = (
            "OpenAI released a new model [src:https://x/1]. "
            "LangSmith is a paid product [unsourced — industry knowledge]. "
            "The framework supports custom evaluators."  # unmarked — flagged
        )
        out = audit_citation_discipline(body)
        assert out["cited"] == 1
        assert out["unsourced"] == 1
        assert out["unmarked"] == 1
        assert out["total"] == 3

    def test_writer_prompt_instructs_unsourced_marker(self):
        """The writer prompt must explicitly tell the model to mark unsourced
        claims so the audit pass can count them. Otherwise audit_citation_discipline
        returns 0 unsourced for everything (false reassurance)."""
        from hermes.pipeline.synthesize import build_section_prompt
        from hermes.pipeline.spec import SectionSpec
        sec = SectionSpec(number=3, title="Frontier Models", bullets=["release dates"])
        prompt = build_section_prompt(sec, [], "instructions", ["quality"], "July 2026")
        assert "unsourced" in prompt.lower()
        assert "industry knowledge" in prompt.lower()


class TestRequiredDeliverablesGate:
    """The Required Deliverables list is parsed from the prompt but was never
    enforced. The 2026-07-13 monthly report's deliverables ('Model comparison
    matrix', 'Funding tables', 'Benchmark comparison tables', 'Key statistics')
    were largely missing, with no surface area telling the reader. This gate
    appends a 'Coverage Check' section listing any missing deliverable."""

    def test_missing_deliverable_surfaced(self):
        from hermes.pipeline.spec import BriefSpec, SectionSpec
        spec = BriefSpec(
            title="T",
            sections=[SectionSpec(number=1, title="Exec")],
            deliverables=["Model comparison matrix", "Funding tables", "Benchmark comparison tables"],
        )
        # The report has no tables, no model comparison, no funding, no benchmark
        # table — all three are missing.
        md = "## **1. Exec**\nThis report has no tables at all. [src:https://x/1]"
        rep = assemble_report(spec, [md], _sources())
        assert "Required Deliverables" in rep.text
        assert "Coverage Check" in rep.text
        assert "Model comparison matrix" in rep.text
        assert "Funding tables" in rep.text
        assert "Benchmark comparison tables" in rep.text

    def test_present_deliverable_not_listed_as_missing(self):
        from hermes.pipeline.spec import BriefSpec, SectionSpec
        spec = BriefSpec(
            title="T",
            sections=[SectionSpec(number=1, title="Exec")],
            deliverables=["Model comparison matrix", "Funding tables"],
        )
        # The report has a model comparison table; funding is missing.
        md = (
            "## **1. Exec**\n\n"
            "## **Model comparison matrix**\n\n"
            "| Model | Org | Score |\n|---|---|---|\n| A | X | 90 |\n"
        )
        rep = assemble_report(spec, [md], _sources())
        # Funding tables is missing → listed in coverage check.
        assert "Funding tables" in rep.text
        # Model comparison matrix is present → NOT in the missing list.
        # The text appears in the report body, so we look at the *missing* list
        # specifically (it should not appear under the "missing" bullet).
        assert "Required Deliverables" in rep.text
        assert "- Model comparison matrix" not in rep.text

    def test_no_coverage_check_when_all_deliverables_present(self):
        from hermes.pipeline.spec import BriefSpec, SectionSpec
        spec = BriefSpec(
            title="T",
            sections=[SectionSpec(number=1, title="Exec")],
            deliverables=["Executive summary"],
        )
        md = "## **1. Exec**\nSome prose. [src:https://x/1]"
        rep = assemble_report(spec, [md], _sources())
        # All deliverables present → no coverage check tail.
        assert "Coverage Check" not in rep.text

    def test_check_required_deliverables_returns_structured(self):
        from hermes.pipeline.report import check_required_deliverables
        checks = check_required_deliverables(
            ["Model comparison matrix", "Nonexistent thing"],
            "## **1. Exec**\nThis has a model comparison matrix.\n\n| Model | Score |\n|---|---|\n",
        )
        assert checks[0].found is True
        assert checks[0].deliverable == "Model comparison matrix"
        assert checks[1].found is False
        assert checks[1].deliverable == "Nonexistent thing"


class TestThinCorpusBanner:
    """The 2026-07-13 monthly report had 20 sources for 13 sections (≈1.5/section)
    with no banner telling the reader the corpus was thin. The thin-corpus
    banner distinguishes 'nothing happened' from 'we didn't see anything'."""

    def test_thin_corpus_banner_emitted_when_few_sources(self):
        from hermes.pipeline.coverage import CoverageVerdict
        from hermes.pipeline.report import assemble_report
        from hermes.pipeline.spec import BriefSpec, SectionSpec
        spec = BriefSpec(
            title="T",
            sections=[SectionSpec(number=i, title=f"Sec {i}") for i in range(1, 14)],
        )
        # 20 sources for 13 sections → thin. (5*13 = 65 threshold.)
        sources = [_sources()[0]] * 2  # actually use a single distinct source repeated
        # Use distinct URLs to avoid the URL-dedup that assemble_report doesn't
        # do but the runner does. assemble_report only dedups via resolve_citations.
        sources = [
            SearchResult(title=f"src{i}", url=f"https://x/{i}", source="ex.com")
            for i in range(20)
        ]
        # 5 CRITICAL verdicts → thin banner fires.
        verdicts = [
            CoverageVerdict(
                section_number=i, section_title=f"Sec {i}",
                verdict="CRITICAL" if i <= 5 else "OK",
                sources_in_section=0 if i <= 5 else 5,
                categories_present=("community",),
                required_category=None,
            )
            for i in range(1, 14)
        ]
        sections = [f"## **{i}. Sec {i}**\nBody for section {i}. [src:https://x/{i % 20}]"
                    for i in range(1, 14)]
        rep = assemble_report(spec, sections, sources, verdicts=verdicts)
        assert "Thin-corpus run" in rep.text
        assert "20 sources for 13 sections" in rep.text
        # 5 critical sections are mentioned in the banner.
        assert "5 section" in rep.text

    def test_thin_corpus_banner_absent_on_healthy_run(self):
        from hermes.pipeline.coverage import CoverageVerdict
        from hermes.pipeline.report import assemble_report
        from hermes.pipeline.spec import BriefSpec, SectionSpec
        spec = BriefSpec(
            title="T",
            sections=[SectionSpec(number=i, title=f"Sec {i}") for i in range(1, 4)],
        )
        sources = [
            SearchResult(title=f"src{i}", url=f"https://x/{i}", source="ex.com")
            for i in range(30)  # 30 sources for 3 sections = 10/section → healthy
        ]
        verdicts = [
            CoverageVerdict(
                section_number=i, section_title=f"Sec {i}",
                verdict="OK", sources_in_section=10,
                categories_present=("official", "research", "news"),
                required_category=None,
            )
            for i in range(1, 4)
        ]
        sections = [f"## **{i}. Sec {i}**\nBody for section {i}." for i in range(1, 4)]
        rep = assemble_report(spec, sections, sources, verdicts=verdicts)
        assert "Thin-corpus run" not in rep.text

    def test_thin_corpus_banner_helper_thresholds(self):
        from hermes.pipeline.report import thin_corpus_banner
        # 5 sections × 5 threshold = 25 sources needed for "healthy" → 20 is thin.
        banner = thin_corpus_banner(total_sources=20, section_count=5, critical_sections=0)
        assert "Thin-corpus run" in banner
        # 5 sections × 5 = 25 → exactly at threshold, still emits because <
        # (the condition is `total_sources < thin_threshold * section_count`).
        banner_at = thin_corpus_banner(total_sources=25, section_count=5, critical_sections=0)
        assert "Thin-corpus run" not in banner_at
        # Any CRITICAL also triggers the banner even if total is high.
        banner_crit = thin_corpus_banner(total_sources=50, section_count=5, critical_sections=2)
        assert "Thin-corpus run" in banner_crit


# ── drop_empty_subheadings + validity gate (round-2 fixes) ─────────────────────


def test_drop_empty_subheadings_removes_malformed_heading():
    # The 2026-07-13 section-8 failure: a bare "## **" heading (no title).
    text = "## **\n\nwrite a section for an AI report.\nMore CoT."
    out = drop_empty_subheadings(text)
    assert "## **\n" not in out
    # The CoT prose below survives drop_empty_subheadings (it's not a heading);
    # the validity gate in the pipeline is what replaces it.
    assert "More CoT." in out


def test_drop_empty_subheadings_removes_stub_subheadings_keeps_section_heading():
    # Stub subheadings that chain to another heading (or EOF) are dropped; the
    # section heading is kept; a trailing stub immediately before real body is a
    # structural ambiguity (could be a legit subheading) so it is kept — the
    # parenthetical-stub case from the real report is caught by the validity
    # gate, not here.
    text = (
        "## **6. Open Source AI**\n\n"
        "### Full Analytical Report\n\n"
        "### Month Timeline\n\n"
        "### Funding Tables\n\n"
        "Real body paragraph about Qwen. [src:https://x/1]"
    )
    out = drop_empty_subheadings(text)
    assert "## **6. Open Source AI**" in out  # section heading kept
    assert "### Full Analytical Report" not in out  # chains to a heading → stub
    assert "### Month Timeline" not in out       # chains to a heading → stub
    assert "Real body paragraph" in out


def test_drop_empty_subheadings_keeps_subheading_with_body():
    text = "## **3. Frontier Models**\n\n### Comparison\n\n| a | b |\nReal prose."
    out = drop_empty_subheadings(text)
    assert "### Comparison" in out  # has a table body → kept


def test_validity_gate_rejects_cot_and_missing_heading():
    from hermes.pipeline.synthesize import has_valid_section
    from hermes.pipeline.spec import SectionSpec
    sec8 = SectionSpec(number=8, title="Funding, M&A & Business")
    # CoT dump with no real heading → invalid.
    assert has_valid_section("write a section for an AI report. we are told to...", sec8) is False
    # Malformed heading only → invalid.
    assert has_valid_section("## **\n\nbody", sec8) is False
    # Empty → invalid.
    assert has_valid_section("", sec8) is False
    # Real headed section with real prose → valid.
    real = "## **8. Funding, M&A & Business**\n\n" + (
        "No major funding rounds were publicly disclosed this month, but the continued "
        "cadence of model releases from Zhipu and Tencent suggests that capital is still "
        "flowing into Chinese AI labs. The absence of headline M&A deals stands in contrast "
        "to earlier quarters, when consolidation among foundation-model startups dominated "
        "the business press. [src:https://x/1]"
    )
    assert has_valid_section(real, sec8) is True
    # Real heading but only planning prose (all marker lines) → invalid.
    assert has_valid_section(
        "## **8. Funding**\n\nNow, write the actual section. we'll use the source. "
        "we can organize by topic. we'll wrap up.",
        sec8,
    ) is False


def test_clean_section_text_trims_cot_tail_keeps_real_prose():
    # Section-10 pattern: real headed prose followed by a planning tail.
    from hermes.pipeline.synthesize import clean_section_text
    from hermes.pipeline.spec import SectionSpec
    sec10 = SectionSpec(number=10, title="Enterprise & Industry Adoption")
    body = "## **10. Enterprise & Industry Adoption**\n\n" + ("Real analysis sentence about adoption. " * 12) + "[src:https://x/1]\n\n"
    tail = "Now, format: The section must begin exactly. we'll use the source. say: foo."
    out = clean_section_text(body + tail, sec10)
    assert out is not None
    assert "Real analysis sentence" in out
    assert "Now, format" not in out
    assert "we'll use the source" not in out
    assert out.rstrip().endswith("[src:https://x/1]")


def test_clean_section_text_rejects_full_cot_dump():
    from hermes.pipeline.synthesize import clean_section_text
    from hermes.pipeline.spec import SectionSpec
    sec8 = SectionSpec(number=8, title="Funding, M&A & Business")
    # Marker appears before any real prose → full dump → None.
    dump = "## **8. Funding**\n\nNow, write the actual section. we are supposed to synthesize."
    assert clean_section_text(dump, sec8) is None


def test_drop_empty_subheadings_treats_ellipsis_as_placeholder():
    # Section-12 pattern: "### Executive Summary" followed by a literal "..."
    # placeholder, then the next stub heading. The ellipsis is NOT a body.
    text = (
        "## **12. Benchmarks**\n\n"
        "### Executive Summary\n...\n\n"
        "### Full Analytical Report\n...\n\n"
        "### Strategic Conclusions\n...\n\n"
        "Real benchmark prose about GPQA and AIME. [src:https://x/1]"
    )
    out = drop_empty_subheadings(text)
    assert "## **12. Benchmarks**" in out
    assert "### Executive Summary" not in out
    assert "### Full Analytical Report" not in out
    assert "### Strategic Conclusions" not in out
    assert "..." not in out
    assert "Real benchmark prose" in out


def test_clean_section_text_keeps_real_content_after_preamble():
    # Section-12 shape: stub subheadings + "Now, fill in." + REAL content. The
    # pipeline runs drop_empty_subheadings then clean_section_text; together they
    # drop the stubs+placeholder bodies and the "Now, fill in." line, keeping the
    # real content.
    from hermes.pipeline.synthesize import clean_section_text
    from hermes.pipeline.spec import SectionSpec
    sec12 = SectionSpec(number=12, title="Benchmarks & Capability")
    text = (
        "## **12. Benchmarks & Capability**\n\n"
        "### Executive Summary\n...\n\n### Full Analytical Report\n...\n\n"
        "Now, fill in.\n\n"
        "In the 30 days ending mid-July 2026, the industry saw several model "
        "releases but none accompanied by verified benchmark scores on GPQA, "
        "AIME, SWE-Bench, MMLU, or MMMU. This data drought underscores a growing "
        "trend of evaluation transparency lagging behind releases. Independent "
        "auditors have noted that labs increasingly publish marketing claims "
        "without reproducible evaluation artifacts, which complicates comparison "
        "and weakens the empirical basis for procurement decisions. [src:https://x/1]"
    )
    out = clean_section_text(drop_empty_subheadings(text), sec12)
    assert out is not None
    assert "Now, fill in" not in out
    assert "### Executive Summary" not in out
    assert "..." not in out
    assert "evaluation transparency" in out
    assert "[src:https://x/1]" in out


def test_clean_section_text_rejects_full_planning_section():
    # Section-5 shape: heading + only planning lines ("we'll", "we can organize",
    # "list key events") — no real analysis. After line-removal, no prose → None.
    from hermes.pipeline.synthesize import clean_section_text
    from hermes.pipeline.spec import SectionSpec
    sec5 = SectionSpec(number=5, title="AI Agents & Coding")
    text = (
        "## 5. AI Agents & Coding\n\n"
        "**Executive Summary.** ( summarize the month's key developments. "
        "We'll wrap up the executive summary with implications.)\n\n"
        "**Full Analytical Report.** Here we'll elaborate on each development. "
        "we can organize by topic: Coding Agents, MCP, Research Agents.\n\n"
        "**Month Timeline.** List key events with dates: e.g., June 13 - agents trending."
    )
    assert clean_section_text(text, sec5) is None


def test_clean_section_text_kills_meta_authorship_tail():
    # The 2026-07-13 round-3 section-12 failure: real headed prose + tables,
    # then a free-form meta-authorship tail where the writer reasons about its
    # own sourcing ("the user said", "fabricate numbers", "we can simulate",
    # "as the writer, we can't access it", "do our best") and drops a bare
    # " write." fragment + a "First, craft an executive summary..." planning line.
    # Line-level marker removal drops the meta lines + bare-imperative fragment;
    # the real tables survive.
    from hermes.pipeline.synthesize import clean_section_text
    from hermes.pipeline.spec import SectionSpec
    sec12 = SectionSpec(number=12, title="Benchmarks & Capability")
    text = (
        "## **12. Benchmarks & Capability**\n\n"
        "**Executive Summary:** In July 2026 the AI industry reached an inflection "
        "point regarding benchmarks, as the top models from several labs converged "
        "on MMLU and GPQA while remaining far apart on harder reasoning and multimodal "
        "suites such as SWE-Bench and MMMU. This convergence on well-known academic "
        "benchmarks masks a deeper transparency gap around evaluation methodology "
        "and reproducibility. [src:https://x/10]\n\n"
        "| Benchmark | Top Model | Score |\n"
        "| MMLU | GLM-5.2 | 89.1 (community est.) |\n\n"
        "But we don't have sources for these scores. We could cite older sources? "
        "The user only wants us to use the provided sources. We could instead make "
        "the table about new models.\n\n"
        "| Model | Org | MMLU |\n"
        "| GLM-5.2 | Zhipu | 89 (community est.) |\n\n"
        "Again, fabricate numbers. The user said to cite every claim. We can simulate "
        "that by saying the model card contains the score. As the writer, we can't "
        "access it. The user gave us a list of URLs. Do our best.\n\n"
        " write.\n\n"
        "First, craft an executive summary that sets the stage: July 2026 saw no "
        "official benchmark breakthroughs from major labs."
    )
    out = clean_section_text(text, sec12)
    assert out is not None
    # Real headed prose + tables survive.
    assert "## **12. Benchmarks & Capability**" in out
    assert "In July 2026 the AI industry" in out
    assert "GLM-5.2" in out
    assert "[src:https://x/10]" in out
    # Meta-authorship tail + bare-imperative fragment + planning line are gone.
    assert "we don't have sources" not in out
    assert "The user only wants us" not in out
    assert "fabricate numbers" not in out
    assert "we can simulate" not in out
    assert "as the writer" not in out
    assert "Do our best" not in out
    assert "craft an executive summary" not in out
    # The bare " write." fragment line is dropped.
    assert "\n write." not in out
    assert "\nwrite.\n" not in out


def test_clean_section_text_keeps_legit_fabricated_information_term():
    # Guard against false positive: "fabricated information" is a legit definitional
    # term (e.g. a hallucination table), NOT the meta "fabricate numbers" CoT.
    # The precise marker "fabricate numbers" must not match "fabricated information".
    from hermes.pipeline.synthesize import clean_section_text
    from hermes.pipeline.spec import SectionSpec
    sec6 = SectionSpec(number=6, title="Open Source AI")
    text = (
        "## **6. Open Source AI**\n\n"
        "| Risk | Definition | Present |\n"
        "| Hallucination | Degree of fabricated information | Yes [src:https://x/3] |\n\n"
        "Open-source releases this month included Qwen3, which continues the trend of "
        "large multilingual models being released under permissive licenses for both "
        "research and commercial use. The release was accompanied by technical "
        "documentation that explicitly discusses hallucination risks and evaluation "
        "protocols. [src:https://x/1]"
    )
    out = clean_section_text(text, sec6)
    assert out is not None
    assert "fabricated information" in out  # legit term survives
    assert "Hallucination" in out
    assert "[src:https://x/3]" in out


def test_clean_section_text_keeps_legit_end_user_prose():
    # Guard: bare end-user references in enterprise analysis ("the user expects a
    # model to...") must NOT be line-dropped — only the meta "the user expects us"
    # form is banned. Prevents over-broad meta-authorship matching.
    from hermes.pipeline.synthesize import clean_section_text
    from hermes.pipeline.spec import SectionSpec
    sec10 = SectionSpec(number=10, title="Enterprise & Industry Adoption")
    text = (
        "## **10. Enterprise & Industry Adoption**\n\n"
        "In enterprise settings, the user expects a model to follow instructions "
        "reliably before deployment. The user might prefer smaller open models that "
        "can be audited and fine-tuned on proprietary data rather than relying solely "
        "on closed API endpoints. These preferences are reshaping procurement criteria "
        "and pushing vendors to offer both cloud and on-premise deployment options. "
        "[src:https://x/1]"
    )
    out = clean_section_text(text, sec10)
    assert out is not None
    assert "the user expects a model" in out  # legit end-user prose survives
    assert "The user might prefer" in out


def test_is_substantial_section_rejects_thin_but_valid_section():
    # A headed section with only ~20 words of real prose should be considered a stub
    # and rejected by the substantial gate, even if it passes the CoT validity gate.
    from hermes.pipeline.synthesize import is_substantial_section
    from hermes.pipeline.spec import SectionSpec
    sec = SectionSpec(number=3, title="Frontier Models")
    thin = "## **3. Frontier Models**\n\nSome models released. [src:https://x/1]"
    assert is_substantial_section(thin, sec) is False
    substantial = (
        "## **3. Frontier Models**\n\n"
        "The past thirty days saw multiple frontier model releases from both closed "
        "and open-weight labs, with each camp emphasizing different trade-offs between "
        "capability, cost, and access. Closed labs pushed API-only updates and "
        "enterprise partnerships, while open-weight releases focused on long context, "
        "multilingual performance, and local deployment. These releases intensify "
        "competition and force buyers to re-evaluate their procurement strategies. "
        "Benchmarks remain scarce at launch, so comparisons rely heavily on community "
        "replication and inferred architectural details rather than official model "
        "cards. The resulting uncertainty makes it harder for enterprises to commit "
        "to a single vendor and increases the value of interoperable tooling. "
        "[src:https://x/1]"
    )
    assert is_substantial_section(substantial, sec) is True


def test_build_section_prompt_forbids_cot_and_stubs():
    # The writer prompt must explicitly instruct the model to avoid the failure modes
    # observed in the 2026-07-13 monthly report: planning language, placeholder
    # subheadings, ellipses, bracketed fig-leaf labels, and thin stubs.
    from hermes.pipeline.synthesize import build_section_prompt
    from hermes.pipeline.spec import SectionSpec
    sec = SectionSpec(number=6, title="Open Source AI", bullets=["licenses", "adoption"])
    prompt = build_section_prompt(sec, [], "instructions", ["quality"], "July 2026")
    lowered = prompt.lower()
    assert "placeholder subheadings" in lowered
    assert "ellipses" in lowered
    assert "analyst assessment" in lowered
    assert "first-person" in lowered or "first person" in lowered
    assert "planning language" in lowered
    assert "cover every bullet" in lowered
    assert "do not repeat information" in lowered
    assert "do not invent model names" in lowered
    assert "src:url" in lowered
