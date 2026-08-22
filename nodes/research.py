from collections import defaultdict
from datetime import (
    UTC,
    datetime,
)
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
    ResearchEvidence,
    ResearchPack,
)
from schemas.state import State
from services.llm import gemini_llm
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


def _parse_published_at(
    published_at: str | None,
) -> datetime | None:
    if not published_at:
        return None

    normalized = published_at.replace(
        "Z",
        "+00:00",
    )

    try:
        parsed = datetime.fromisoformat(
            normalized,
        )
    except ValueError:
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

    classification = {
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

    if _is_time_sensitive(research_focus) and age_days > STALE_TIME_SENSITIVE_DAYS:
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
    filtered = [
        result for result in results if _result_score(result) >= min_relevance_score
    ]

    unique_by_url: dict[str, dict] = {}

    for result in filtered:
        url = result.get("url") or ""

        if not url:
            continue

        existing = unique_by_url.get(url)

        if existing is None or _result_score(result) > _result_score(existing):
            unique_by_url[url] = result

    ranked = sorted(
        unique_by_url.values(),
        key=lambda result: (
            -_result_score(result),
            result.get("url") or "",
        ),
    )

    domain_counts: dict[str, int] = defaultdict(int)
    selected: list[dict] = []

    for result in ranked:
        domain = _result_domain(result)

        if domain and domain_counts[domain] >= max_results_per_domain:
            continue

        if domain:
            domain_counts[domain] += 1

        selected.append(
            classify_result_freshness(
                result,
                research_focus=research_focus,
                now=now,
            )
        )

    return selected


def research_node(
    state: State,
) -> dict:
    queries = state.get(
        "queries",
        [],
    )

    raw_results: list[dict] = []

    for query in queries[:5]:
        raw_results.extend(
            tavily_search(
                query,
                max_results=3,
            )
        )

    quality_results = apply_research_quality_gate(
        raw_results,
        research_focus=state.get(
            "research_focus",
            [],
        ),
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
                "content": result["content"][:2000],
                "raw_content": (result["raw_content"][:2500]),
                "published_at": (result.get("published_at")),
                "freshness_status": (result["freshness_status"]),
                "freshness_warning": (result["freshness_warning"]),
            }
        )

    extractor = gemini_llm.with_structured_output(
        ResearchPack,
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
                    f"{state.get('research_focus', [])}\n\n"
                    f"Search results:\n"
                    f"{compact_results}"
                )
            ),
        ]
    )

    evidence = [
        ResearchEvidence(
            id=index,
            **item.model_dump(
                exclude={"id"},
            ),
        )
        for index, item in enumerate(
            pack.evidence,
            start=1,
        )
    ]

    return {
        "evidence": evidence,
        "research_brief": pack.research_brief,
    }
