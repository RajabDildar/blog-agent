from unittest.mock import MagicMock, patch

import pytest

from blog_agent.nodes.editor import build_editor_evidence_sheet, editor_node
from blog_agent.schemas.models import EditorialReview, Plan, ResearchEvidence, Task
from blog_agent.services.citation_verification import verify_evidence_quality


def test_editor_evidence_sheet_is_compact():
    evidence = [
        ResearchEvidence(
            id=1,
            claim="Cloudflare R2 provides S3 compatibility.",
            source_title="Cloudflare R2 documentation",
            url="https://developers.cloudflare.com/r2/",
            supporting_text="Large body of source text",
            published_at="2025-01-01",
            freshness_status="stale_warning",
            freshness_warning="Source published over 6 months ago",
        )
    ]

    result = build_editor_evidence_sheet(
        evidence,
    )

    assert result == [
        {
            "id": 1,
            "claim": "Cloudflare R2 provides S3 compatibility.",
            "source_title": "Cloudflare R2 documentation",
            "url": "https://developers.cloudflare.com/r2/",
            "source_type": "unknown",
            "authority_score": 0.0,
            "support_strength": "weak",
            "confidence_score": 0.0,
            "published_at": "2025-01-01",
            "freshness_status": "stale_warning",
            "freshness_warning": "Source published over 6 months ago",
        }
    ]


def test_editor_evidence_sheet_preserves_multiple_ids():
    evidence = [
        ResearchEvidence(
            id=1,
            claim="Claim one",
            source_title="Source one",
            url="https://example.com/1",
        ),
        ResearchEvidence(
            id=2,
            claim="Claim two",
            source_title="Source two",
            url="https://example.com/2",
        ),
    ]

    result = build_editor_evidence_sheet(
        evidence,
    )

    assert [item["id"] for item in result] == [1, 2]


def test_verify_evidence_quality_emits_issue_for_freshness_warning():
    task = Task(
        id=1,
        title="Task 1",
        goal="Goal 1",
        bullets=["b1", "b2", "b3"],
        target_words=200,
        requires_research=True,
        evidence_refs=[10],
    )
    evidence = ResearchEvidence(
        id=10,
        claim="Old announcement",
        source_title="Tech News",
        url="https://technews.com/old",
        authority_score=0.8,
        support_strength="direct",
        freshness_warning="Verify claim is still current",
    )

    issues = verify_evidence_quality(tasks=[task], evidence=[evidence])

    assert len(issues) == 1
    assert issues[0].category == "citation"
    assert issues[0].severity == "medium"
    assert "freshness warning" in issues[0].problem.lower()


def test_editor_node_rejects_unapproved_review_without_actionable_task_issues():
    task = Task(
        id=1,
        title="Task 1",
        goal="Goal 1",
        bullets=["b1", "b2", "b3"],
        target_words=200,
    )
    plan = Plan(
        blog_title="Test Title",
        thesis="Test thesis",
        opening_angle="Angle",
        reader_promise="Promise",
        audience="Audience",
        tone="Tone",
        tasks=[task],
    )
    state = {
        "plan": plan,
        "topic": "Test Topic",
        "evidence": [],
        "citation_issues": [],
        "merged_md": "# Test Title\n\n## Task 1\n\nBody",
    }

    mock_review = EditorialReview(
        approved=False,
        overall_score=6,
        issues=[],
        sections_to_revise=[],
    )

    with patch("blog_agent.nodes.editor.gemini_llm") as mock_llm:
        mock_llm.with_structured_output.return_value.invoke.return_value = mock_review
        with pytest.raises(
            ValueError,
            match="approved=False but provided no valid task-scoped actionable issues",
        ):
            editor_node(state)
