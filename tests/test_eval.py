import json
import time
from types import SimpleNamespace

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
from eval.run_eval import (
    _wait_for_resume,
    load_topics,
    run_evaluation,
)
from eval.score import extract_evidence_metrics, extract_metrics
from services.rate_limits import (
    RateLimitInfo,
    RateLimitRetryExhausted,
)


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


def make_metrics() -> EvaluationMetrics:
    return EvaluationMetrics(
        llm_calls=0,
        research_calls=0,
        image_calls=0,
        revision_count=0,
        generation_time_seconds=0,
        retries=0,
    )


def test_wait_for_resume_rejects_wait_over_limit(
    monkeypatch,
):
    monkeypatch.setattr(
        "eval.run_eval.load_diagnostics",
        lambda run_id: {
            "resume_after": time.time() + 30,
        },
    )

    with pytest.raises(
        RuntimeError,
        match="configured evaluation maximum",
    ):
        _wait_for_resume(
            run_id="run-1",
            max_wait_seconds=1,
        )


def test_run_evaluation_resumes_same_run_id(
    monkeypatch,
    tmp_path,
):
    run_ids = iter(["run-1"])

    monkeypatch.setattr(
        "eval.run_eval.generate_run_id",
        lambda: next(run_ids),
    )

    resume_calls = []

    def fake_run(topic, *, run_id):
        raise RateLimitRetryExhausted(
            RateLimitInfo(
                provider="groq",
                status_code=429,
                retry_after_seconds=0,
                reset_tokens_seconds=None,
                remaining_tokens=0,
                limit_tokens=8000,
            )
        )

    def fake_resume(run_id):
        resume_calls.append(run_id)

        return {
            "plan": object(),
            "final": "Article",
            "saved_path": "article.md",
        }

    monkeypatch.setattr(
        "eval.run_eval.run",
        fake_run,
    )

    monkeypatch.setattr(
        "eval.run_eval.resume",
        fake_resume,
    )

    monkeypatch.setattr(
        "eval.run_eval.load_diagnostics",
        lambda run_id: {
            "resume_after": time.time(),
            "provider_attempts": {},
            "image_attempts": 0,
            "editorial_revisions": 0,
            "duration_seconds": 0,
            "retry_count": 0,
        },
    )

    monkeypatch.setattr(
        "eval.run_eval.evaluate_article",
        lambda **kwargs: (
            make_run(
                topic=kwargs["topic"],
                overall_quality=8,
            ).evaluation
        ),
    )

    runs = run_evaluation(
        topics=["AI agents"],
        output_dir=tmp_path,
        between_run_delay_seconds=0,
    )

    assert resume_calls == ["run-1"]
    assert runs[0].run_id == "run-1"
    assert runs[0].status == "success"
    assert runs[0].rate_limit_recoveries == 1


def test_terminal_failure_does_not_stop_next_topic(
    monkeypatch,
    tmp_path,
):
    run_ids = iter(
        [
            "run-1",
            "run-2",
        ]
    )

    monkeypatch.setattr(
        "eval.run_eval.generate_run_id",
        lambda: next(run_ids),
    )

    def fake_run(topic, *, run_id):
        if topic == "first":
            raise RuntimeError(
                "terminal failure",
            )

        return {
            "plan": object(),
            "final": "Article",
            "saved_path": "article.md",
        }

    monkeypatch.setattr(
        "eval.run_eval.run",
        fake_run,
    )

    monkeypatch.setattr(
        "eval.run_eval.load_diagnostics",
        lambda run_id: {
            "provider_attempts": {},
            "image_attempts": 0,
            "editorial_revisions": 0,
            "duration_seconds": 0,
            "retry_count": 0,
        },
    )

    monkeypatch.setattr(
        "eval.run_eval.evaluate_article",
        lambda **kwargs: (
            make_run(
                topic=kwargs["topic"],
                overall_quality=8,
            ).evaluation
        ),
    )

    runs = run_evaluation(
        topics=[
            "first",
            "second",
        ],
        output_dir=tmp_path,
        between_run_delay_seconds=0,
    )

    assert [run.status for run in runs] == [
        "failed",
        "success",
    ]


def test_completed_results_are_preserved_on_rerun(
    monkeypatch,
    tmp_path,
):
    existing = make_run(
        topic="completed",
        overall_quality=8,
    )

    from eval.report import write_report

    write_report(
        runs=[existing],
        output_dir=tmp_path,
    )

    generated_topics = []

    monkeypatch.setattr(
        "eval.run_eval.generate_run_id",
        lambda: "new-run",
    )

    def fake_run(topic, *, run_id):
        generated_topics.append(topic)

        return {
            "plan": object(),
            "final": "Article",
            "saved_path": "article.md",
        }

    monkeypatch.setattr(
        "eval.run_eval.run",
        fake_run,
    )

    monkeypatch.setattr(
        "eval.run_eval.load_diagnostics",
        lambda run_id: {
            "provider_attempts": {},
            "image_attempts": 0,
            "editorial_revisions": 0,
            "duration_seconds": 0,
            "retry_count": 0,
        },
    )

    monkeypatch.setattr(
        "eval.run_eval.evaluate_article",
        lambda **kwargs: (
            make_run(
                topic=kwargs["topic"],
                overall_quality=7,
            ).evaluation
        ),
    )

    runs = run_evaluation(
        topics=[
            "completed",
            "new",
        ],
        output_dir=tmp_path,
        between_run_delay_seconds=0,
    )

    assert generated_topics == ["new"]
    assert [run.topic for run in runs] == [
        "completed",
        "new",
    ]


def test_report_supports_mixed_recovery_results(
    tmp_path,
):
    recovered = make_run(
        topic="Recovered",
        overall_quality=8,
    ).model_copy(
        update={
            "rate_limit_recoveries": 2,
            "rate_limit_wait_seconds": 12.5,
        }
    )

    failed = EvaluationRun(
        topic="Failed",
        run_id="failed-run",
        status="failed",
        metrics=make_metrics(),
        failure="RuntimeError: failed",
        rate_limit_recoveries=1,
        rate_limit_wait_seconds=5,
    )

    report = build_report(
        [
            recovered,
            failed,
        ]
    )

    assert "Rate-limit recoveries: 2" in report
    assert "Rate-limit wait: 12.50s" in report
    assert "Rate-limit recoveries: 1" in report


def test_extract_evidence_metrics():
    evidence = [
        SimpleNamespace(
            source_type="official_documentation",
            authority_score=1.0,
            quality_score=0.9,
            support_strength="direct",
            url="https://docs.example.com/a",
        ),
        SimpleNamespace(
            source_type="vendor_blog",
            authority_score=0.5,
            quality_score=0.4,
            support_strength="weak",
            url="https://blog.example.com/b",
        ),
    ]

    metrics = extract_evidence_metrics(
        evidence,
    )

    assert metrics["official_source_ratio"] == 0.5
    assert metrics["average_authority_score"] == 0.75
    assert metrics["average_quality_score"] == 0.65
    assert metrics["weak_source_ratio"] == 0.5
    assert metrics["unique_domain_count"] == 2


def test_extract_metrics_includes_evidence_metrics_when_provided():
    from types import SimpleNamespace

    metrics = extract_metrics(
        {
            "provider_attempts": {},
            "image_attempts": 0,
            "editorial_revisions": 0,
            "duration_seconds": 1,
            "retry_count": 0,
        },
        evidence=[
            SimpleNamespace(
                source_type="official_documentation",
                authority_score=1.0,
                quality_score=0.9,
                support_strength="direct",
                url="https://docs.example.com",
            )
        ],
    )

    assert metrics["official_source_ratio"] == 1.0
    assert metrics["average_authority_score"] == 1.0
    assert metrics["average_quality_score"] == 0.9
    assert metrics["weak_source_ratio"] == 0.0
    assert metrics["unique_domain_count"] == 1
