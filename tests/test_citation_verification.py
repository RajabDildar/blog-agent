from schemas.models import (
    ResearchEvidence,
    Task,
)
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
) -> ResearchEvidence:
    return ResearchEvidence(
        id=evidence_id,
        claim="Example claim.",
        source_title="Example source",
        url=url,
    )


def make_article(
    body: str,
) -> str:
    return f"# Article\n\n## Section One\n\n{body}\n"


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

    assert len(issues) == 1
    assert issues[0].category == "citation"
    assert issues[0].task_id == 1
    assert "not backed by evidence" in issues[0].problem


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

    assert len(issues) == 1
    assert issues[0].task_id == 1
    assert "requires citations" in issues[0].problem


def test_sources_section_url_must_be_evidence_backed() -> None:
    issues = verify_citations(
        markdown=make_article(
            "Main content "
            "[source](https://example.com/source).\n\n"
            "### Sources\n\n"
            "- [Unsupported](https://unsupported.example/source)"
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

    assert len(issues) == 1
    assert "unsupported.example" in issues[0].problem


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
        markdown=make_article(
            "This is an introductory section that does not require citations."
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
