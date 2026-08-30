from urllib.parse import urlparse

from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
)
from langchain_google_genai import ChatGoogleGenerativeAI

from config.settings import EVAL_JUDGE_MODEL
from eval.models import EvaluationResult
from prompts.evaluator import EVALUATION_SYSTEM
from schemas.models import Plan

judge_llm = ChatGoogleGenerativeAI(
    model=EVAL_JUDGE_MODEL,
    temperature=0,
    max_retries=0,
)


def evaluate_article(
    *,
    topic: str,
    plan: Plan,
    article: str,
) -> EvaluationResult:
    judge = judge_llm.with_structured_output(
        EvaluationResult,
    )

    return judge.invoke(
        [
            SystemMessage(
                content=EVALUATION_SYSTEM,
            ),
            HumanMessage(
                content=(
                    f"Topic:\n{topic}\n\n"
                    f"Article plan:\n"
                    f"{plan.model_dump_json(indent=2)}\n\n"
                    f"Generated article:\n"
                    f"{article}"
                ),
            ),
        ]
    )


def extract_evidence_metrics(
    evidence: list,
) -> dict:
    if not evidence:
        return {
            "official_source_ratio": 0.0,
            "average_authority_score": 0.0,
            "average_quality_score": 0.0,
            "weak_source_ratio": 0.0,
            "unique_domain_count": 0,
            "source_type_distribution": {},
        }

    total = len(evidence)

    official_types = {
        "official_documentation",
        "official_company_announcement",
        "government_source",
        "academic_paper",
        "standards_document",
        "github_repository",
    }

    source_type_distribution: dict[str, int] = {}

    domains = set()

    weak_count = 0
    authority_total = 0.0
    quality_total = 0.0
    official_count = 0

    for item in evidence:
        source_type = item.source_type

        source_type_distribution[source_type] = (
            source_type_distribution.get(source_type, 0) + 1
        )

        if source_type in official_types:
            official_count += 1

        if item.support_strength == "weak":
            weak_count += 1

        authority_total += item.authority_score
        quality_total += item.quality_score

        domain = urlparse(item.url).netloc

        if domain:
            domains.add(domain)

    return {
        "official_source_ratio": round(
            official_count / total,
            3,
        ),
        "average_authority_score": round(
            authority_total / total,
            3,
        ),
        "average_quality_score": round(
            quality_total / total,
            3,
        ),
        "weak_source_ratio": round(
            weak_count / total,
            3,
        ),
        "unique_domain_count": len(domains),
        "source_type_distribution": source_type_distribution,
    }


def extract_metrics(
    diagnostics: dict,
    *,
    evidence: list | None = None,
) -> dict:
    provider_attempts = diagnostics.get(
        "provider_attempts",
        {},
    )

    metrics = {
        "llm_calls": sum(
            count
            for provider, count in provider_attempts.items()
            if provider != "tavily+gemini"
        ),
        "research_calls": provider_attempts.get(
            "tavily+gemini",
            0,
        ),
        "image_calls": diagnostics.get(
            "image_attempts",
            0,
        ),
        "revision_count": diagnostics.get(
            "editorial_revisions",
            0,
        ),
        "generation_time_seconds": diagnostics.get(
            "duration_seconds",
            0,
        ),
        "retries": diagnostics.get(
            "retry_count",
            0,
        ),
    }

    if evidence is not None:
        metrics.update(
            extract_evidence_metrics(
                evidence,
            )
        )

    return metrics
