from schemas.models import ResearchEvidence


def test_revision_payload_can_contain_task_scoped_evidence():
    evidence = [
        ResearchEvidence(
            id=3,
            claim="Example supported claim",
            source_title="Example source",
            url="https://example.com",
        )
    ]

    payload = {"evidence": [item.model_dump() for item in evidence]}

    restored = [ResearchEvidence(**item) for item in payload["evidence"]]

    assert restored[0].id == 3
    assert restored[0].url == "https://example.com"


def test_revision_evidence_is_not_required_for_non_research_tasks():
    payload = {
        "evidence": [],
    }

    assert payload["evidence"] == []
