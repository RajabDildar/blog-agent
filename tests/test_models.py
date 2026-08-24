from schemas.models import ResearchEvidence


def test_research_evidence_supports_quality_metadata():
    evidence = ResearchEvidence(
        id=1,
        claim="FastAPI provides async web APIs.",
        source_title="FastAPI Documentation",
        url="https://fastapi.tiangolo.com",
        source_type="official_documentation",
        authority_score=0.95,
        support_strength="direct",
        confidence_score=0.9,
    )

    assert evidence.source_type == "official_documentation"
    assert evidence.authority_score == 0.95
    assert evidence.support_strength == "direct"
    assert evidence.confidence_score == 0.9
