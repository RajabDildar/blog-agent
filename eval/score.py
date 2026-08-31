import base64
import mimetypes
from pathlib import Path
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
    image_paths: list[Path],
) -> EvaluationResult:
    judge = judge_llm.with_structured_output(
        EvaluationResult,
    )

    content: list[dict[str, str]] = [
        {
            "type": "text",
            "text": (
                f"Topic:\n{topic}\n\n"
                f"Article plan:\n{plan.model_dump_json(indent=2)}\n\n"
                f"Generated article:\n{article}"
            ),
        }
    ]
    for image_path in image_paths:
        mime_type, _ = mimetypes.guess_type(image_path.name)
        if mime_type is None or not mime_type.startswith("image/"):
            raise ValueError(f"Unsupported evaluation image type: {image_path}")
        content.append(
            {
                "type": "image",
                "base64": base64.b64encode(image_path.read_bytes()).decode("ascii"),
                "mime_type": mime_type,
            }
        )

    return judge.invoke(
        [
            SystemMessage(
                content=EVALUATION_SYSTEM,
            ),
            HumanMessage(content=content),
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
            "unknown_source_ratio": 0.0,
            "unique_domain_count": 0,
            "source_type_distribution": {},
            "authority_distribution": {},
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
    unknown_count = 0
    authority_distribution: dict[str, int] = {}

    for item in evidence:
        source_type = item.source_type

        source_type_distribution[source_type] = (
            source_type_distribution.get(source_type, 0) + 1
        )

        if source_type in official_types:
            official_count += 1

        if source_type == "unknown":
            unknown_count += 1

        authority_bucket = f"{item.authority_score:.1f}"
        authority_distribution[authority_bucket] = authority_distribution.get(authority_bucket, 0) + 1

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
        "unknown_source_ratio": round(unknown_count / total, 3),
        "unique_domain_count": len(domains),
        "source_type_distribution": source_type_distribution,
        "authority_distribution": authority_distribution,
    }


def extract_metrics(
    diagnostics: dict,
    *,
    evidence: list | None = None,
) -> dict:
    provider_calls = diagnostics.get(
        "provider_calls",
        {},
    )
    provider_attempts = diagnostics.get(
        "provider_attempts",
        {},
    )

    metrics = {
        "llm_calls": provider_calls.get("groq", 0) + provider_calls.get("gemini", 0),
        "research_calls": provider_calls.get("tavily", 0),
        "image_calls": provider_calls.get("cloudflare_image", 0),
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
        "node_attempts": sum(provider_attempts.values()),
    }

    if evidence is not None:
        metrics.update(
            extract_evidence_metrics(
                evidence,
            )
        )

    return metrics
