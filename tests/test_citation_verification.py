from schemas.models import (
    Plan,
    ResearchEvidence,
    SectionOutput,
    Task,
)
from nodes.merger import merge_content
from services.citation_verification import (
    normalize_url,
    verify_citations,
)


def make_task(
    *,
    task_id: int = 1,
    title: str = "Section One",
    requires_research: bool = True,
    requires_citations: bool = True,
    evidence_refs: list[int] | None = None,
) -> Task:
    return Task(
        id=task_id,
        title=title,
        goal="Explain the topic clearly.",
        bullets=[
            "Explain the first point.",
            "Explain the second point.",
            "Explain the third point.",
        ],
        target_words=300,
        requires_research=requires_research,
        requires_citations=requires_citations,
        evidence_refs=([] if evidence_refs is None else evidence_refs),
    )


def make_evidence(
    *,
    evidence_id: int = 1,
    url: str = "https://example.com/source",
    source_title: str = "Example source",
) -> ResearchEvidence:
    return ResearchEvidence(
        id=evidence_id,
        claim="Example claim.",
        source_title=source_title,
        url=url,
    )


def make_article(
    body: str,
    sources: str | None = "- [Example source](https://example.com/source)",
) -> str:
    md = f"# Article\n\n## Section One\n\n{body}\n"
    if sources is not None:
        md += f"\n## Sources\n\n{sources}\n"
    return md


def test_evidence_backed_inline_citation_passes() -> None:
    issues = verify_citations(
        markdown=make_article(
            "Evidence supports this [claim](https://example.com/source)."
        ),
        tasks=[
            make_task(
                evidence_refs=[1],
            )
        ],
        evidence=[
            make_evidence(),
        ],
    )

    assert issues == []


def test_unsupported_url_creates_issue() -> None:
    issues = verify_citations(
        markdown=make_article(
            "Unsupported [claim](https://unsupported.example/source)."
        ),
        tasks=[
            make_task(
                evidence_refs=[1],
            )
        ],
        evidence=[
            make_evidence(),
        ],
    )

    assert any(
        issue.task_id == 1 and "not backed by evidence" in issue.problem
        for issue in issues
    )


def test_required_citation_missing_creates_issue() -> None:
    issues = verify_citations(
        markdown=make_article("This section makes a factual claim without a citation."),
        tasks=[
            make_task(
                requires_citations=True,
                evidence_refs=[1],
            )
        ],
        evidence=[
            make_evidence(),
        ],
    )

    assert any(
        issue.task_id == 1 and "requires citations" in issue.problem
        for issue in issues
    )


def test_sources_section_url_must_be_evidence_backed() -> None:
    issues = verify_citations(
        markdown=(
            "# Article\n\n"
            "## Section One\n\n"
            "Main content [source](https://example.com/source).\n\n"
            "## Sources\n\n"
            "- [Unsupported](https://unsupported.example/source)\n"
        ),
        tasks=[
            make_task(
                evidence_refs=[1],
            )
        ],
        evidence=[
            make_evidence(),
        ],
    )

    assert any(
        issue.task_id is None
        and "Sources section contains a URL not backed" in issue.problem
        for issue in issues
    )


def test_sources_section_missing_when_research_used_creates_issue() -> None:
    issues = verify_citations(
        markdown=make_article(
            "Main content [source](https://example.com/source).",
            sources=None,
        ),
        tasks=[
            make_task(
                evidence_refs=[1],
            )
        ],
        evidence=[
            make_evidence(),
        ],
    )

    assert any(
        issue.task_id is None
        and "missing a final ## Sources section" in issue.problem
        for issue in issues
    )


def test_sources_section_not_final_h2_creates_issue() -> None:
    issues = verify_citations(
        markdown=(
            "# Article\n\n"
            "## Section One\n\n"
            "Content [link](https://example.com/source).\n\n"
            "## Sources\n\n"
            "- [Source](https://example.com/source)\n\n"
            "## Section Two\n\n"
            "After sources body.\n"
        ),
        tasks=[
            make_task(task_id=1, title="Section One", evidence_refs=[1]),
            make_task(task_id=2, title="Section Two", evidence_refs=[]),
        ],
        evidence=[
            make_evidence(),
        ],
    )

    assert any(
        issue.task_id is None
        and "must be the final H2 section" in issue.problem
        for issue in issues
    )


def test_sources_section_in_closed_book_creates_issue() -> None:
    issues = verify_citations(
        markdown=(
            "# Article\n\n"
            "## Section One\n\n"
            "Closed book prose.\n\n"
            "## Sources\n\n"
            "- [Source](https://example.com/source)\n"
        ),
        tasks=[
            make_task(
                requires_research=False,
                requires_citations=False,
                evidence_refs=[],
            )
        ],
        evidence=[],
    )

    assert any(
        issue.task_id is None
        and "not allowed in a closed-book article" in issue.problem
        for issue in issues
    )


def test_url_fragments_are_ignored() -> None:
    assert (
        normalize_url("https://example.com/source#section")
        == "https://example.com/source"
    )


def test_trailing_slash_variants_are_equivalent() -> None:
    assert normalize_url("https://example.com/source/") == normalize_url(
        "https://example.com/source"
    )


def test_scheme_and_host_casing_are_normalized() -> None:
    assert normalize_url("HTTPS://EXAMPLE.COM/Source") == "https://example.com/Source"


def test_tracking_parameters_are_removed_consistently() -> None:
    assert (
        normalize_url(
            "https://example.com/source"
            "?utm_source=newsletter"
            "&utm_campaign=test"
            "&keep=value"
            "&fbclid=abc"
        )
        == "https://example.com/source?keep=value"
    )


def test_section_without_research_requirements_has_no_missing_citation_issue() -> None:
    issues = verify_citations(
        markdown=(
            "# Article\n\n"
            "## Section One\n\n"
            "This is an introductory section that does not require citations.\n"
        ),
        tasks=[
            make_task(
                requires_research=False,
                requires_citations=False,
                evidence_refs=[],
            )
        ],
        evidence=[],
    )

    assert issues == []


def test_low_authority_evidence_creates_quality_issue():
    from services.citation_verification import (
        verify_evidence_quality,
    )

    evidence = [
        ResearchEvidence(
            id=1,
            claim="Example claim",
            source_title="Unknown Blog",
            url="https://example.com/blog/article",
            authority_score=0.3,
            support_strength="weak",
        )
    ]

    task = Task(
        id=1,
        title="Test Section",
        goal="Explain topic",
        bullets=[
            "point one",
            "point two",
            "point three",
        ],
        target_words=200,
        requires_citations=True,
        evidence_refs=[1],
    )

    issues = verify_evidence_quality(
        tasks=[task],
        evidence=evidence,
    )

    assert any(issue.category == "citation" for issue in issues)


def test_merger_generates_sources_section_in_first_reference_order():
    plan = Plan(
        blog_title="Test Blog",
        thesis="Thesis",
        opening_angle="Angle",
        reader_promise="Promise",
        audience="Audience",
        tone="Tone",
        tasks=[
            make_task(task_id=1, title="Section 1", evidence_refs=[2, 1]),
            make_task(task_id=2, title="Section 2", evidence_refs=[1, 2]),
        ],
    )
    evidence = [
        make_evidence(evidence_id=1, url="https://example.com/source1", source_title="Source 1"),
        make_evidence(evidence_id=2, url="https://example.com/source2", source_title="Source 2"),
        make_evidence(evidence_id=3, url="https://example.com/source3", source_title="Unused Source 3"),
    ]
    sections = {
        1: SectionOutput(body_markdown="Section 1 content [source2](https://example.com/source2)."),
        2: SectionOutput(body_markdown="Section 2 content [source1](https://example.com/source1)."),
    }

    state = {
        "plan": plan,
        "sections": sections,
        "evidence": evidence,
    }

    result = merge_content(state)
    merged_md = result["merged_md"]

    assert "## Sources" in merged_md
    pos_source2 = merged_md.find("https://example.com/source2")
    pos_source1 = merged_md.find("https://example.com/source1")
    assert pos_source2 < pos_source1
    assert "https://example.com/source3" not in merged_md


def test_merger_closed_book_does_not_generate_sources_section():
    plan = Plan(
        blog_title="Closed Book Blog",
        thesis="Thesis",
        opening_angle="Angle",
        reader_promise="Promise",
        audience="Audience",
        tone="Tone",
        tasks=[
            make_task(task_id=1, title="Section 1", requires_research=False, requires_citations=False, evidence_refs=[]),
        ],
    )
    sections = {
        1: SectionOutput(body_markdown="Closed book content."),
    }
    state = {
        "plan": plan,
        "sections": sections,
        "evidence": [],
    }

    result = merge_content(state)
    assert "## Sources" not in result["merged_md"]
