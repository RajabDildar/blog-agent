import json

import pytest

from eval.models import (
    EvaluationMetrics,
    EvaluationResult,
    EvaluationRun,
    EvaluationScores,
)
from eval.report import (
    build_report,
    calculate_average_scores,
)
from eval.run_eval import load_topics
from eval.score import extract_metrics


def test_extract_metrics_from_diagnostics():
    diagnostics = {
        "provider_attempts": {
            "gemini": 3,
            "groq": 4,
            "tavily+gemini": 2,
        },
        "image_attempts": 3,
        "editorial_revisions": 1,
        "duration_seconds": 42.5,
        "retry_count": 2,
    }

    metrics = extract_metrics(diagnostics)

    assert metrics == {
        "llm_calls": 7,
        "research_calls": 2,
        "image_calls": 3,
        "revision_count": 1,
        "generation_time_seconds": 42.5,
        "retries": 2,
    }


def test_evaluation_metrics_reject_negative_values():
    try:
        EvaluationMetrics(
            llm_calls=-1,
            research_calls=0,
            image_calls=0,
            revision_count=0,
            generation_time_seconds=0,
            retries=0,
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Expected EvaluationMetrics validation to fail.",
        )


def make_run(
    *,
    topic: str,
    overall_quality: int,
) -> EvaluationRun:
    return EvaluationRun(
        topic=topic,
        run_id=f"run-{overall_quality}",
        status="success",
        evaluation=EvaluationResult(
            scores=EvaluationScores(
                overall_quality=overall_quality,
                structure=8,
                technical_accuracy=7,
                research_quality=6,
                coherence=8,
                usefulness=7,
                writing_quality=8,
                citations=6,
                images=7,
            ),
            strengths=["Clear structure"],
            weaknesses=["More citations needed"],
            summary="Good article.",
        ),
        metrics=EvaluationMetrics(
            llm_calls=5,
            research_calls=1,
            image_calls=2,
            revision_count=1,
            generation_time_seconds=10,
            retries=0,
        ),
    )


def test_calculate_average_scores():
    averages = calculate_average_scores(
        [
            make_run(
                topic="First",
                overall_quality=8,
            ),
            make_run(
                topic="Second",
                overall_quality=6,
            ),
        ]
    )

    assert averages["overall_quality"] == 7.0
    assert averages["structure"] == 8.0


def test_build_report_includes_metrics_and_scores():
    report = build_report(
        [
            make_run(
                topic="AI agents",
                overall_quality=8,
            )
        ]
    )

    assert "# Blog Evaluation Report" in report
    assert "AI agents" in report
    assert "Overall quality: 8/10" in report
    assert "LLM calls: 5" in report


def test_load_topics_reads_non_empty_strings(
    tmp_path,
):
    path = tmp_path / "topics.json"

    path.write_text(
        json.dumps(
            [
                "AI agents",
                "",
                "  RAG  ",
                123,
            ]
        ),
        encoding="utf-8",
    )

    assert load_topics(path) == [
        "AI agents",
        "RAG",
    ]


def test_load_topics_rejects_non_list(
    tmp_path,
):
    path = tmp_path / "topics.json"

    path.write_text(
        json.dumps(
            {
                "topic": "AI agents",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="JSON list",
    ):
        load_topics(path)


def test_load_topics_rejects_empty_result(
    tmp_path,
):
    path = tmp_path / "topics.json"

    path.write_text(
        json.dumps(
            [
                "",
                123,
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="cannot be empty",
    ):
        load_topics(path)
