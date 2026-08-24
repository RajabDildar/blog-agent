from nodes.editor import build_editor_evidence_sheet
from schemas.models import ResearchEvidence


def test_editor_evidence_sheet_is_compact():
    evidence = [
        ResearchEvidence(
            id=1,
            claim="Cloudflare R2 provides S3 compatibility.",
            source_title="Cloudflare R2 documentation",
            url="https://developers.cloudflare.com/r2/",
            supporting_text="Large body of source text",
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
