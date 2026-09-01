from datetime import (
    UTC,
    datetime,
)

import pytest

from nodes.research import (
    GroundingDiagnostics,
    _parse_published_at,
    assign_final_evidence_ids,
    apply_post_extraction_evidence_gate,
    apply_research_quality_gate,
    ground_extracted_evidence,
)
from schemas.models import (
    ExtractedResearchEvidence,
    ExtractedResearchPack,
    ResearchEvidence,
)
from services.source_quality import (
    classify_source,
    compute_source_ratios,
    is_official_primary_source,
)
from services.tavily import tavily_search

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
    title: str | None = None,
) -> dict:
    return {
        "title": title or f"Source for {url}",
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


def test_tracking_and_fragments_do_not_defeat_dedupe() -> None:
    results = [
        make_result(
            url="https://example.com/article?utm_source=twitter#section",
            score=0.90,
        ),
        make_result(
            url="https://example.com/article/",
            score=0.40,
        ),
        make_result(
            url="https://example.com/article?fbclid=abc",
            score=0.60,
        ),
    ]

    quality_results = apply_research_quality_gate(
        results,
        research_focus=[],
        min_relevance_score=0.0,
        max_results_per_domain=10,
        now=NOW,
    )

    assert len(quality_results) == 1
    assert quality_results[0]["score"] == 0.90


def test_results_are_ranked_by_relevance_then_authority_then_url() -> None:
    results = [
        {
            **make_result(
                url="https://z.example.com/low-relevance-high-authority",
                score=0.50,
            ),
            "source_type": "official_documentation",
            "authority_score": 0.95,
        },
        {
            **make_result(
                url="https://a.example.com/high-relevance-low-authority",
                score=0.95,
            ),
            "source_type": "unknown",
            "authority_score": 0.3,
        },
        {
            **make_result(
                url="https://m.example.com/mid-relevance",
                score=0.75,
            ),
            "source_type": "vendor_blog",
            "authority_score": 0.5,
        },
    ]

    quality_results = apply_research_quality_gate(
        results,
        research_focus=[],
        min_relevance_score=0.0,
        max_results_per_domain=10,
        now=NOW,
    )

    assert [result["url"] for result in quality_results] == [
        "https://a.example.com/high-relevance-low-authority",
        "https://m.example.com/mid-relevance",
        "https://z.example.com/low-relevance-high-authority",
    ]


def test_equal_relevance_scores_use_authority_as_tie_breaker() -> None:
    results = [
        {
            **make_result(
                url="https://example.com/z",
                score=0.80,
            ),
            "source_type": "unknown",
            "authority_score": 0.2,
        },
        {
            **make_result(
                url="https://example.com/a",
                score=0.80,
            ),
            "source_type": "official_documentation",
            "authority_score": 0.95,
        },
        {
            **make_result(
                url="https://example.com/m",
                score=0.80,
            ),
            "source_type": "vendor_blog",
            "authority_score": 0.5,
        },
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


def test_equal_relevance_and_authority_use_url_as_deterministic_tie_breaker() -> None:
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


def test_domain_cap_applies_after_ranking_not_before() -> None:
    results = [
        make_result(
            url="https://example.com/one",
            score=0.95,
        ),
        make_result(
            url="https://other.example/article",
            score=0.90,
        ),
        make_result(
            url="https://example.com/two",
            score=0.85,
        ),
        make_result(
            url="https://example.com/three",
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
        "https://other.example/article",
        "https://example.com/two",
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
    assert quality_results[0]["freshness_status"] == "fresh"
    assert quality_results[0]["freshness_warning"] == ""


def test_iso_date_parses() -> None:
    parsed = _parse_published_at("2025-12-01T10:30:00Z")
    assert parsed is not None
    assert parsed.year == 2025
    assert parsed.month == 12
    assert parsed.day == 1
    assert parsed.hour == 10
    assert parsed.tzinfo is not None


def test_rfc_date_parses() -> None:
    parsed = _parse_published_at("Tue, 11 Mar 2025 17:00:00 GMT")
    assert parsed is not None
    assert parsed.year == 2025
    assert parsed.month == 3
    assert parsed.day == 11
    assert parsed.hour == 17
    assert parsed.tzinfo is not None


def test_old_authoritative_standards_remain_allowed_in_time_sensitive_topic() -> None:
    results = [
        {
            **make_result(
                url="https://ietf.org/rfc/rfc9110.html",
                score=0.90,
                published_at="2020-01-01T00:00:00Z",
            ),
            "source_type": "standards_document",
            "authority_score": 0.95,
        }
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

    assert len(quality_results) == 1
    assert quality_results[0]["freshness_status"] == "exempt_authoritative_spec"
    assert "verify separately that any current" in quality_results[0]["freshness_warning"]


def test_stale_news_produces_explicit_stale_warning() -> None:
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


def test_authoritative_source_is_official_primary() -> None:
    q = classify_source("https://fastapi.tiangolo.com/features")
    assert is_official_primary_source(
        source_type=q.source_type,
        url="https://fastapi.tiangolo.com/features",
    )


def test_official_github_organization_is_primary() -> None:
    url = "https://github.com/langchain-ai/langgraph"
    q = classify_source(url)
    assert q.source_type == "github_repository"
    assert is_official_primary_source(
        source_type=q.source_type,
        url=url,
    )


def test_unknown_domain_remains_explicitly_unknown() -> None:
    url = "https://random-random-12345.example/not-a-real-thing"
    q = classify_source(url)
    assert q.source_type == "unknown"
    assert q.authority_score < 0.5
    assert not is_official_primary_source(
        source_type=q.source_type,
        url=url,
    )


def test_medium_is_vendor_blog_not_unknown() -> None:
    url = "https://medium.com/@someuser/ai-trends"
    q = classify_source(url)
    assert q.source_type == "vendor_blog"
    assert q.authority_score == 0.25


def test_support_strength_cannot_make_low_authority_official() -> None:
    low_auth_url = "https://medium.com/@user/post"
    q = classify_source(low_auth_url)
    evidence = ResearchEvidence(
        id=1,
        claim="Some claim.",
        source_title="Medium post",
        url=low_auth_url,
        source_type=q.source_type,
        authority_score=q.authority_score,
        support_strength="direct",
        confidence_score=1.0,
    )
    assert not is_official_primary_source(
        source_type=evidence.source_type,
        url=evidence.url,
    )


def test_official_unknown_and_weak_source_ratio_definitions_are_distinct() -> None:
    evidence_list = [
        ResearchEvidence(
            id=1,
            claim="Good claim",
            source_title="FastAPI docs",
            url="https://fastapi.tiangolo.com/features",
            source_type="official_documentation",
            authority_score=0.95,
        ),
        ResearchEvidence(
            id=2,
            claim="Unknown claim",
            source_title="Unknown blog",
            url="https://random.example/post",
            source_type="unknown",
            authority_score=0.3,
        ),
        ResearchEvidence(
            id=3,
            claim="Vendor claim",
            source_title="Vendor Blog",
            url="https://company.com/blog/post",
            source_type="vendor_blog",
            authority_score=0.5,
        ),
        ResearchEvidence(
            id=4,
            claim="Another unknown",
            source_title="Random 2",
            url="https://another-unknown.example/page",
            source_type="unknown",
            authority_score=0.3,
        ),
    ]

    ratios = compute_source_ratios(evidence_list)

    assert ratios.official_count == 1
    assert ratios.official_source_ratio == pytest.approx(0.25)

    assert ratios.unknown_count == 2
    assert ratios.unknown_source_ratio == pytest.approx(0.5)

    assert ratios.weak_count == 3
    assert ratios.weak_source_ratio == pytest.approx(0.75)


def test_source_ratios_zero_for_empty_evidence() -> None:
    ratios = compute_source_ratios([])
    assert ratios.total_count == 0
    assert ratios.official_source_ratio == 0.0
    assert ratios.weak_source_ratio == 0.0
    assert ratios.unknown_source_ratio == 0.0


def test_extractor_invented_url_is_rejected() -> None:
    accepted = [
        make_result(
            url="https://fastapi.tiangolo.com/features",
            score=0.95,
            title="FastAPI Features",
        ),
        make_result(
            url="https://docs.pydantic.dev/latest/",
            score=0.90,
            title="Pydantic Docs",
        ),
    ]
    accepted[0] = {
        **accepted[0],
        "source_type": "official_documentation",
        "authority_score": 0.95,
        "freshness_status": "fresh",
        "freshness_warning": "",
    }
    accepted[1] = {
        **accepted[1],
        "source_type": "official_documentation",
        "authority_score": 0.95,
        "freshness_status": "fresh",
        "freshness_warning": "",
    }

    pack = ExtractedResearchPack(
        evidence=[
            ExtractedResearchEvidence(
                claim="FastAPI has async.",
                source_title="FastAPI Features",
                url="https://fastapi.tiangolo.com/features",
                supporting_text="...async endpoints...",
                relevance="Core feature",
                support_strength="direct",
                confidence_score=0.9,
            ),
            ExtractedResearchEvidence(
                claim="Made up fact.",
                source_title="Totally Invented",
                url="https://this-url-was-never-searched.example/xyz",
                supporting_text="...content...",
                relevance="irrelevant",
                support_strength="weak",
                confidence_score=0.2,
            ),
        ],
        research_brief="Sample brief.",
    )

    grounded, diag = ground_extracted_evidence(pack, accepted)

    assert diag.rejected_count == 1
    assert diag.accepted_count == 1
    assert len(diag.rejection_reasons) == 1
    assert "does not match any accepted search result" in diag.rejection_reasons[0]
    assert len(grounded) == 1
    assert grounded[0].url == "https://fastapi.tiangolo.com/features"


def test_canonical_metadata_comes_from_matched_search_result() -> None:
    accepted = [
        {
            **make_result(
                url="https://docs.pydantic.dev/latest/",
                score=0.90,
                title="Pydantic Official Documentation",
                published_at="2025-06-01T00:00:00Z",
            ),
            "source_type": "official_documentation",
            "authority_score": 0.95,
            "freshness_status": "fresh",
            "freshness_warning": "",
        }
    ]

    pack = ExtractedResearchPack(
        evidence=[
            ExtractedResearchEvidence(
                claim="Pydantic validates data.",
                source_title="User-invented title",
                url="https://docs.pydantic.dev/latest/#validation",
                supporting_text="...Pydantic validates...",
                relevance="Core capability",
                support_strength="direct",
                confidence_score=0.8,
            )
        ],
        research_brief="Test grounding metadata.",
    )

    grounded, diag = ground_extracted_evidence(pack, accepted)

    assert diag.accepted_count == 1
    assert diag.rejected_count == 0
    assert len(grounded) == 1

    evidence = grounded[0]
    assert evidence.source_title == "Pydantic Official Documentation"
    assert evidence.url == "https://docs.pydantic.dev/latest/"
    assert evidence.source_type == "official_documentation"
    assert evidence.authority_score == pytest.approx(0.95)
    assert evidence.published_at == "2025-06-01T00:00:00Z"
    assert evidence.freshness_status == "fresh"
    assert evidence.freshness_warning == ""
    assert evidence.tavily_score == pytest.approx(0.90)

    assert evidence.claim == "Pydantic validates data."
    assert evidence.support_strength == "direct"
    assert evidence.confidence_score == pytest.approx(0.8)
    assert evidence.supporting_text == "...Pydantic validates..."


def test_ids_remain_sequential_after_rejection() -> None:
    accepted = [
        {
            **make_result(url=f"https://ok-{i}.example/article", score=0.90 - i * 0.01),
            "source_type": "official_documentation",
            "authority_score": 0.95,
            "freshness_status": "fresh",
            "freshness_warning": "",
        }
        for i in range(5)
    ]

    pack = ExtractedResearchPack(
        evidence=[
            ExtractedResearchEvidence(
                claim=f"Claim {i}",
                source_title=f"Source {i}",
                url=(
                    f"https://ok-{i}.example/article"
                    if i != 2
                    else "https://invented.example/fake"
                ),
                support_strength="direct",
                confidence_score=0.9,
            )
            for i in range(5)
        ],
        research_brief="Test ID assignment.",
    )

    grounded, diag = ground_extracted_evidence(pack, accepted)
    assert diag.accepted_count == 4
    assert diag.rejected_count == 1

    final = assign_final_evidence_ids(grounded)
    assert [item.id for item in final] == [1, 2, 3, 4]


def test_post_extraction_gate_no_longer_uses_quality_score_hard_gate() -> None:
    evidence = [
        ResearchEvidence(
            id=1,
            claim="LLM low-quality informational score.",
            source_title="canonical",
            url="https://canonical.example/1",
            quality_score=0.05,
            source_type="official_documentation",
            authority_score=0.95,
            support_strength="direct",
            confidence_score=0.9,
            tavily_score=0.95,
        ),
        ResearchEvidence(
            id=2,
            claim="Strong claim.",
            source_title="canonical 2",
            url="https://canonical.example/2",
            quality_score=0.8,
        ),
    ]

    result = apply_post_extraction_evidence_gate(evidence)
    assert [item.id for item in result] == [1, 2]


def test_research_quality_gate_limits_low_quality_source_types():
    results = [
        {
            "title": "Vendor blog 1",
            "url": "https://example.com/blog/a",
            "score": 0.9,
            "content": "content",
        },
        {
            "title": "Vendor blog 2",
            "url": "https://example.com/blog/b",
            "score": 0.85,
            "content": "content",
        },
        {
            "title": "Vendor blog 3",
            "url": "https://example.com/blog/c",
            "score": 0.8,
            "content": "content",
        },
    ]

    result = apply_research_quality_gate(
        results,
        research_focus=[],
        max_results_per_domain=10,
    )

    vendor_blogs = [item for item in result if item["source_type"] == "vendor_blog"]

    assert len(vendor_blogs) <= 2


def test_vendor_blog_source_type_is_limited():
    results = [
        make_result(
            url="https://vendor.com/blog/one",
            score=0.95,
        ),
        make_result(
            url="https://vendor.com/blog/two",
            score=0.90,
        ),
        make_result(
            url="https://vendor.com/blog/three",
            score=0.85,
        ),
    ]

    quality_results = apply_research_quality_gate(
        results,
        research_focus=[],
        max_results_per_domain=10,
    )

    vendor_results = [
        result for result in quality_results if result["source_type"] == "vendor_blog"
    ]

    assert len(vendor_results) <= 2
