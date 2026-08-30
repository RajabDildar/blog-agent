from datetime import (
    UTC,
    datetime,
)

from nodes.research import (
    apply_post_extraction_evidence_gate,
    apply_research_quality_gate,
)
from schemas.models import ResearchEvidence
from services.source_quality import (
    classify_source,
)

NOW = datetime(
    2026,
    8,
    22,
    tzinfo=UTC,
)


def make_result(
    *,
    url: str,
    score: float,
    published_at: str | None = None,
) -> dict:
    return {
        "title": f"Source for {url}",
        "url": url,
        "score": score,
        "content": "Supporting content.",
        "raw_content": "Raw supporting content.",
        "published_at": published_at,
    }


def test_relevance_threshold_filters_low_score_results() -> None:
    results = [
        make_result(
            url="https://example.com/low",
            score=0.29,
        ),
        make_result(
            url="https://example.com/accepted",
            score=0.30,
        ),
        make_result(
            url="https://example.com/high",
            score=0.91,
        ),
    ]

    quality_results = apply_research_quality_gate(
        results,
        research_focus=[],
        min_relevance_score=0.30,
        max_results_per_domain=10,
        now=NOW,
    )

    assert [result["url"] for result in quality_results] == [
        "https://example.com/high",
        "https://example.com/accepted",
    ]


def test_duplicate_urls_keep_highest_scoring_result() -> None:
    results = [
        make_result(
            url="https://example.com/article",
            score=0.40,
        ),
        make_result(
            url="https://example.com/article",
            score=0.90,
        ),
        make_result(
            url="https://example.com/other",
            score=0.80,
        ),
    ]

    quality_results = apply_research_quality_gate(
        results,
        research_focus=[],
        min_relevance_score=0.0,
        max_results_per_domain=10,
        now=NOW,
    )

    assert [result["url"] for result in quality_results] == [
        "https://example.com/article",
        "https://example.com/other",
    ]

    assert quality_results[0]["score"] == 0.90


def test_results_are_ranked_by_descending_score() -> None:
    results = [
        make_result(
            url="https://a.example.com/first",
            score=0.50,
        ),
        make_result(
            url="https://b.example.com/second",
            score=0.95,
        ),
        make_result(
            url="https://c.example.com/third",
            score=0.75,
        ),
    ]

    quality_results = apply_research_quality_gate(
        results,
        research_focus=[],
        min_relevance_score=0.0,
        max_results_per_domain=10,
        now=NOW,
    )

    assert [result["score"] for result in quality_results] == [
        0.95,
        0.75,
        0.50,
    ]


def test_equal_scores_use_url_as_deterministic_tie_breaker() -> None:
    results = [
        make_result(
            url="https://example.com/z",
            score=0.80,
        ),
        make_result(
            url="https://example.com/a",
            score=0.80,
        ),
        make_result(
            url="https://example.com/m",
            score=0.80,
        ),
    ]

    quality_results = apply_research_quality_gate(
        results,
        research_focus=[],
        min_relevance_score=0.0,
        max_results_per_domain=10,
        now=NOW,
    )

    assert [result["url"] for result in quality_results] == [
        "https://example.com/a",
        "https://example.com/m",
        "https://example.com/z",
    ]


def test_domain_cap_limits_results_per_domain() -> None:
    results = [
        make_result(
            url="https://example.com/one",
            score=0.95,
        ),
        make_result(
            url="https://example.com/two",
            score=0.90,
        ),
        make_result(
            url="https://example.com/three",
            score=0.85,
        ),
        make_result(
            url="https://other.example/article",
            score=0.80,
        ),
    ]

    quality_results = apply_research_quality_gate(
        results,
        research_focus=[],
        min_relevance_score=0.0,
        max_results_per_domain=2,
        now=NOW,
    )

    assert [result["url"] for result in quality_results] == [
        "https://example.com/one",
        "https://example.com/two",
        "https://other.example/article",
    ]


def test_publication_date_is_preserved() -> None:
    results = [
        make_result(
            url="https://example.com/article",
            score=0.90,
            published_at="2025-12-01T10:30:00Z",
        ),
    ]

    quality_results = apply_research_quality_gate(
        results,
        research_focus=[],
        min_relevance_score=0.0,
        max_results_per_domain=10,
        now=NOW,
    )

    assert quality_results[0]["published_at"] == "2025-12-01T10:30:00Z"


def test_old_authoritative_evidence_remains_allowed() -> None:
    results = [
        make_result(
            url="https://docs.example.com/specification",
            score=0.90,
            published_at="2020-01-01T00:00:00Z",
        ),
    ]

    quality_results = apply_research_quality_gate(
        results,
        research_focus=[
            "Explain the architecture and design.",
        ],
        min_relevance_score=0.0,
        max_results_per_domain=10,
        now=NOW,
    )

    assert len(quality_results) == 1

    assert quality_results[0]["freshness_status"] == "fresh"

    assert quality_results[0]["freshness_warning"] == ""


def test_stale_time_sensitive_evidence_gets_warning() -> None:
    results = [
        make_result(
            url="https://news.example.com/release",
            score=0.90,
            published_at="2024-01-01T00:00:00Z",
        ),
    ]

    quality_results = apply_research_quality_gate(
        results,
        research_focus=[
            "Latest release announcement and current updates.",
        ],
        min_relevance_score=0.0,
        max_results_per_domain=10,
        now=NOW,
    )

    assert quality_results[0]["freshness_status"] == "stale_warning"

    assert (
        "Verify that the claim is still current."
        in quality_results[0]["freshness_warning"]
    )


def test_research_results_receive_authority_metadata():
    result = {
        "url": "https://fastapi.tiangolo.com/",
        "score": 0.9,
    }

    quality = classify_source(
        result["url"],
    )

    assert quality.source_type == "official_documentation"
    assert quality.authority_score >= 0.9


def test_authoritative_source_can_rank_above_equal_relevance_source():
    results = [
        {
            "url": "https://random-example.com/article",
            "score": 0.9,
            "title": "Random article",
        },
        {
            "url": "https://fastapi.tiangolo.com/",
            "score": 0.9,
            "title": "Official docs",
        },
    ]

    ranked = apply_research_quality_gate(
        results,
        research_focus=[],
    )

    assert ranked[0]["title"] == "Official docs"


def test_research_evidence_accepts_grounding_metadata():
    evidence = ResearchEvidence(
        id=1,
        claim="FastAPI supports async endpoints.",
        source_title="FastAPI docs",
        url="https://fastapi.tiangolo.com",
        source_type="official_documentation",
        authority_score=0.95,
        support_strength="direct",
        confidence_score=0.9,
    )

    assert evidence.support_strength == "direct"
    assert evidence.confidence_score == 0.9


def test_research_evidence_accepts_quality_score():
    evidence = ResearchEvidence(
        id=1,
        claim="Example claim",
        source_title="Example source",
        url="https://example.com",
        quality_score=0.8,
    )

    assert evidence.quality_score == 0.8


def test_post_extraction_gate_removes_weak_evidence():
    evidence = [
        ResearchEvidence(
            id=1,
            claim="weak claim",
            source_title="weak source",
            url="https://example.com",
            quality_score=0.2,
        ),
        ResearchEvidence(
            id=2,
            claim="strong claim",
            source_title="strong source",
            url="https://example.org",
            quality_score=0.8,
        ),
    ]

    result = apply_post_extraction_evidence_gate(
        evidence,
    )

    assert [item.id for item in result] == [2]


def test_post_extraction_gate_keeps_moderate_quality_evidence():
    evidence = [
        ResearchEvidence(
            id=1,
            claim="moderate claim",
            source_title="moderate source",
            url="https://example.com",
            quality_score=0.55,
            relevance="supports claim",
        ),
    ]

    result = apply_post_extraction_evidence_gate(
        evidence,
    )

    assert len(result) == 1
    assert result[0].id == 1
