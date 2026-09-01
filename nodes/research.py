from collections import defaultdict
from dataclasses import dataclass
from datetime import (
    UTC,
    datetime,
)
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
)

from config.settings import (
    TAVILY_MAX_RESULTS_PER_DOMAIN,
    TAVILY_MIN_RELEVANCE_SCORE,
)
from prompts.research import RESEARCH_SYSTEM
from schemas.models import (
    EXEMPT_AUTHORITATIVE_SOURCE_TYPES,
    ExtractedResearchPack,
    ResearchEvidence,
)
from schemas.state import State
from services.citation_verification import normalize_url
from services.llm import gemini_llm
from services.source_quality import (
    classify_source,
    is_official_primary_source,
)
from services.tavily import tavily_search

TIME_SENSITIVE_KEYWORDS = {
    "announcement",
    "current",
    "latest",
    "news",
    "recent",
    "release",
    "today",
    "trend",
    "update",
}

STALE_TIME_SENSITIVE_DAYS = 365

TIME_SENSITIVE_NEWS_TIME_RANGE = "year"

SOURCE_TYPE_LIMITS = {
    "vendor_blog": 2,
}


def _result_score(
    result: dict,
) -> float:
    return float(
        result.get("score") or 0,
    )


def _result_domain(
    result: dict,
) -> str:
    return urlparse(
        result.get("url") or "",
    ).netloc.lower()


def _apply_source_quality(
    result: dict,
) -> dict:
    quality = classify_source(
        result.get("url") or "",
    )

    return {
        **result,
        "source_type": quality.source_type,
        "authority_score": quality.authority_score,
    }


def _research_ranking_sort_key(
    result: dict,
) -> tuple:
    """
    Deterministic ranking: relevance first, authority as tie-breaker, URL last.

    Roadmap policy: relevance descending; authority only as deterministic
    tie-breaker or informational field; not an unexplained weighted combo.
    """
    relevance_score = _result_score(result)
    authority_score = float(
        result.get(
            "authority_score",
            0.0,
        )
    )
    return (
        -relevance_score,
        -authority_score,
        result.get("url") or "",
    )


def _parse_published_at(
    published_at: str | None,
) -> datetime | None:
    """
    Parse publication date using standard library only.

    Tavily docs: published_date is available with topic="news" and can be
    RFC-style, e.g. "Tue, 11 Mar 2025 17:00:00 GMT", or ISO format.

    Attempts:
    1. ISO 8601 via fromisoformat
    2. RFC 2822 via email.utils.parsedate_to_datetime
    """
    if not published_at:
        return None

    normalized = published_at.replace(
        "Z",
        "+00:00",
    )

    parsed: datetime | None = None

    try:
        parsed = datetime.fromisoformat(
            normalized,
        )
    except ValueError:
        parsed = None

    if parsed is None:
        try:
            parsed = parsedate_to_datetime(published_at)
        except (ValueError, TypeError, IndexError, OverflowError):
            parsed = None

    if parsed is None:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(
            tzinfo=UTC,
        )

    return parsed.astimezone(
        UTC,
    )


def _is_time_sensitive(
    research_focus: list[str],
) -> bool:
    text = " ".join(
        research_focus,
    ).lower()

    return any(keyword in text for keyword in TIME_SENSITIVE_KEYWORDS)


def classify_result_freshness(
    result: dict,
    *,
    research_focus: list[str],
    now: datetime | None = None,
) -> dict:
    published_at = result.get("published_at")
    source_type = result.get("source_type", "unknown")

    classification: dict[str, str] = {
        "freshness_status": "unknown",
        "freshness_warning": "",
    }

    if not published_at:
        return {
            **result,
            **classification,
        }

    published = _parse_published_at(
        published_at,
    )

    if published is None:
        return {
            **result,
            **classification,
        }

    current_time = now or datetime.now(
        UTC,
    )

    age_days = (current_time - published).days

    if source_type in EXEMPT_AUTHORITATIVE_SOURCE_TYPES:
        if _is_time_sensitive(research_focus) and age_days > STALE_TIME_SENSITIVE_DAYS:
            classification = {
                "freshness_status": "exempt_authoritative_spec",
                "freshness_warning": (
                    "This authoritative source is more than "
                    f"{STALE_TIME_SENSITIVE_DAYS} days old "
                    "for a time-sensitive research focus. "
                    "It is retained as stable foundational/specification "
                    "material, but verify separately that any current "
                    "announcements, pricing, release details, or "
                    "time-sensitive claims are still accurate."
                ),
            }
        else:
            classification = {
                "freshness_status": "exempt_authoritative_spec",
                "freshness_warning": "",
            }
    elif _is_time_sensitive(research_focus) and age_days > STALE_TIME_SENSITIVE_DAYS:
        classification = {
            "freshness_status": "stale_warning",
            "freshness_warning": (
                "This source is more than "
                f"{STALE_TIME_SENSITIVE_DAYS} days old "
                "for a time-sensitive research focus. "
                "Verify that the claim is still current."
            ),
        }
    else:
        classification = {
            "freshness_status": "fresh",
            "freshness_warning": "",
        }

    return {
        **result,
        **classification,
    }


def apply_research_quality_gate(
    results: list[dict],
    *,
    research_focus: list[str],
    min_relevance_score: float = (TAVILY_MIN_RELEVANCE_SCORE),
    max_results_per_domain: int = (TAVILY_MAX_RESULTS_PER_DOMAIN),
    now: datetime | None = None,
) -> list[dict]:
    """
    Deterministic pre-extraction quality gate.

    Order of operations (roadmap 8.2 + Step 1):
    1. Relevance floor (drop below min_relevance_score)
    2. Normalized-URL dedupe (keep highest-scoring copy)
    3. Sort: relevance DESC, authority DESC tiebreak, URL ASC tiebreak
    4. Per-domain cap + source-type cap
    5. Freshness classification
    """
    filtered = [
        _apply_source_quality(result)
        for result in results
        if _result_score(result) >= min_relevance_score
    ]

    unique_by_normalized_url: dict[str, dict] = {}

    for result in filtered:
        raw_url = result.get("url") or ""
        if not raw_url:
            continue
        normalized = normalize_url(raw_url)

        existing = unique_by_normalized_url.get(normalized)

        if existing is None or _result_score(result) > _result_score(existing):
            unique_by_normalized_url[normalized] = result

    ranked = sorted(
        unique_by_normalized_url.values(),
        key=_research_ranking_sort_key,
    )

    domain_counts: dict[str, int] = defaultdict(int)
    source_type_counts: dict[str, int] = defaultdict(int)

    selected: list[dict] = []

    for result in ranked:
        domain = _result_domain(result)

        source_type = result.get(
            "source_type",
            "unknown",
        )

        if domain and domain_counts[domain] >= max_results_per_domain:
            continue

        source_limit = SOURCE_TYPE_LIMITS.get(
            source_type,
        )

        if source_limit is not None and source_type_counts[source_type] >= source_limit:
            continue

        if domain:
            domain_counts[domain] += 1

        source_type_counts[source_type] += 1

        selected.append(
            classify_result_freshness(
                result,
                research_focus=research_focus,
                now=now,
            )
        )

    return selected


@dataclass(frozen=True)
class GroundingDiagnostics:
    accepted_count: int
    rejected_count: int
    rejection_reasons: list[str]
    no_official_primary_source: bool


def ground_extracted_evidence(
    extracted_pack: ExtractedResearchPack,
    accepted_search_results: list[dict],
) -> tuple[list[ResearchEvidence], GroundingDiagnostics]:
    """
    Deterministically ground every extracted evidence item in an accepted search result.

    Policy (Step 1 P0):
    - Every extracted evidence item must map to exactly one accepted search result URL.
    - No match -> reject the item and record a deterministic reason.
    - Canonical URL, title, source_type, authority, published_at, freshness,
      and Tavily score come from the matched accepted search result,
      NOT from the LLM extraction.
    - LLM-owned fields (claim, supporting_text, relevance, support_strength,
      confidence_score, quality_score) are preserved from the extraction.
    """

    normalized_lookup: dict[str, dict] = {}
    for result in accepted_search_results:
        raw_url = result.get("url") or ""
        if not raw_url:
            continue
        normalized_lookup[normalize_url(raw_url)] = result

    accepted: list[ResearchEvidence] = []
    rejection_reasons: list[str] = []

    for index, item in enumerate(extracted_pack.evidence):
        extracted_url = item.url
        normalized = normalize_url(extracted_url) if extracted_url else ""

        matched = normalized_lookup.get(normalized) if normalized else None

        if matched is None:
            rejection_reasons.append(
                f"Extraction item {index + 1}: URL does not match any "
                f"accepted search result: {extracted_url!r}"
            )
            continue

        canonical = matched
        accepted.append(
            ResearchEvidence(
                id=0,
                claim=item.claim,
                source_title=canonical.get("title") or item.source_title,
                url=canonical.get("url") or extracted_url,
                supporting_text=item.supporting_text,
                relevance=item.relevance,
                published_at=canonical.get("published_at"),
                freshness_status=canonical.get(
                    "freshness_status",
                    "unknown",
                ),
                freshness_warning=canonical.get(
                    "freshness_warning",
                    "",
                ),
                tavily_score=float(canonical.get("score") or 0),
                source_type=canonical.get("source_type", "unknown"),
                authority_score=float(
                    canonical.get(
                        "authority_score",
                        0.0,
                    )
                ),
                support_strength=item.support_strength,
                confidence_score=item.confidence_score,
                quality_score=0.0,
            )
        )

    any_official = any(
        is_official_primary_source(
            source_type=item.source_type,
            url=item.url,
        )
        for item in accepted
    )

    diagnostics = GroundingDiagnostics(
        accepted_count=len(accepted),
        rejected_count=len(extracted_pack.evidence) - len(accepted),
        rejection_reasons=rejection_reasons,
        no_official_primary_source=(not any_official),
    )

    return accepted, diagnostics


def assign_final_evidence_ids(
    grounded: list[ResearchEvidence],
) -> list[ResearchEvidence]:
    """
    Assign final sequential IDs 1..N only after all deterministic filtering.

    Roadmap 8.1 + Step 1 requirement: no gaps after post-extraction rejection.
    """
    return [
        ResearchEvidence(
            **{
                **item.model_dump(),
                "id": new_id,
            }
        )
        for new_id, item in enumerate(grounded, start=1)
    ]


def apply_post_extraction_evidence_gate(
    evidence: list[ResearchEvidence],
) -> list[ResearchEvidence]:
    """
    Post-grounding validation without unexplained LLM hard gates.

    The old quality_score hard rejection is removed. quality_score is now
    informational only. Retain the evidence list as-is after grounding.
    """
    return list(evidence)


def research_node(
    state: State,
) -> dict:
    queries = state.get(
        "queries",
        [],
    )

    research_focus = state.get(
        "research_focus",
        [],
    )

    time_sensitive = _is_time_sensitive(research_focus)

    search_topic = "news" if time_sensitive else "general"
    search_time_range: str | None = (
        TIME_SENSITIVE_NEWS_TIME_RANGE if time_sensitive else None
    )

    raw_results: list[dict] = []

    for query in queries[:5]:
        raw_results.extend(
            tavily_search(
                query,
                max_results=3,
                topic=search_topic,
                time_range=search_time_range,
            )
        )

    quality_results = apply_research_quality_gate(
        raw_results,
        research_focus=research_focus,
    )

    if not quality_results:
        return {
            "evidence": [],
            "research_brief": "",
        }

    compact_results = []

    for result in quality_results:
        compact_results.append(
            {
                "title": result["title"],
                "url": result["url"],
                "score": result["score"],
                "published_at": result.get("published_at"),
                "freshness_status": result.get("freshness_status", "unknown"),
                "freshness_warning": result.get("freshness_warning", ""),
                "source_type": result.get(
                    "source_type",
                    "unknown",
                ),
                "authority_score": result.get(
                    "authority_score",
                    0.0,
                ),
                "source_quality_note": (
                    f"Authority score: "
                    f"{result.get('authority_score', 0.0)}, "
                    f"Type: "
                    f"{result.get('source_type', 'unknown')}, "
                    f"Freshness: "
                    f"{result.get('freshness_status', 'unknown')}"
                ),
                "content": result["content"][:2000],
            }
        )

    extractor = gemini_llm.with_structured_output(
        ExtractedResearchPack,
    )

    pack = extractor.invoke(
        [
            SystemMessage(
                content=RESEARCH_SYSTEM,
            ),
            HumanMessage(
                content=(
                    f"Topic: {state['topic']}\n\n"
                    f"Research focus:\n"
                    f"{research_focus}\n\n"
                    f"Search results:\n"
                    f"{compact_results}"
                )
            ),
        ]
    )

    grounded_evidence, grounding_diag = ground_extracted_evidence(
        pack,
        quality_results,
    )

    grounded_evidence = apply_post_extraction_evidence_gate(
        grounded_evidence,
    )

    final_evidence = assign_final_evidence_ids(grounded_evidence)

    return {
        "evidence": final_evidence,
        "research_brief": pack.research_brief,
    }
