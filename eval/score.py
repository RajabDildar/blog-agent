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


def extract_metrics(
    diagnostics: dict,
) -> dict:
    provider_attempts = diagnostics.get(
        "provider_attempts",
        {},
    )

    return {
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
