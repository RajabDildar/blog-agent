from nodes.orchestrator import _sort_planner_evidence
from schemas.models import ResearchEvidence


def test_planner_evidence_is_sorted_by_quality_then_authority():
    evidence = [
        ResearchEvidence(
            id=1,
            claim="weak evidence",
            source_title="weak",
            url="https://example.com",
            quality_score=0.4,
            authority_score=0.4,
            confidence_score=0.4,
        ),
        ResearchEvidence(
            id=2,
            claim="strong evidence",
            source_title="strong",
            url="https://docs.python.org",
            quality_score=0.9,
            authority_score=0.95,
            confidence_score=0.9,
        ),
    ]

    sorted_evidence = _sort_planner_evidence(
        evidence,
    )

    assert sorted_evidence[0].id == 2
    assert sorted_evidence[1].id == 1
