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
    build_comparison_report,
    build_report,
    calculate_average_scores,
    check_acceptance_guardrails,
)
from eval.run_eval import (
    _wait_for_resume,
    load_topics,
    run_evaluation,
)
from eval.score import extract_evidence_metrics, extract_metrics
from blog_agent.services.rate_limits import (
    RateLimitInfo,
    RateLimitRetryExhausted,
)


def test_extract_metrics_from_diagnostics():
    diagnostics = {
        "provider_calls": {
            "gemini": 3,
            "groq": 4,
            "tavily": 2,
            "cloudflare_image": 3,
        },
        "provider_attempts": {
            "gemini": 3,
            "groq": 4,
            "tavily+gemini": 2,
        },
        "image_attempts": 3,
        "editorial_revisions": 1,
        "editorial_reviews": 1,
        "duration_seconds": 42.5,
        "retry_count": 2,
    }

    metrics = extract_metrics(diagnostics)

    assert metrics == {
        "llm_calls": 7,
        "research_calls": 2,
        "image_calls": 3,
        "revision_count": 1,
        "editorial_reviews": 1,
        "generation_time_seconds": 42.5,
        "retries": 2,
        "node_attempts": 9,
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


# ---------------------------------------------------------------------------
# Step 5 — New tests
# ---------------------------------------------------------------------------


def make_run_with_metrics(
    *,
    topic: str,
    overall_quality: int,
    llm_calls: int = 5,
    revision_count: int = 0,
    editorial_reviews: int = 1,
    citation_issues: dict | None = None,
) -> EvaluationRun:
    return EvaluationRun(
        topic=topic,
        run_id=f"run-{topic[:4]}",
        status="success",
        evaluation=EvaluationResult(
            scores=EvaluationScores(
                overall_quality=overall_quality,
                structure=9,
                technical_accuracy=9,
                research_quality=9,
                coherence=9,
                usefulness=9,
                writing_quality=9,
                citations=9,
                images=8,
            ),
            strengths=[],
            weaknesses=[],
            summary="Good.",
        ),
        metrics=EvaluationMetrics(
            llm_calls=llm_calls,
            research_calls=1,
            image_calls=2,
            revision_count=revision_count,
            editorial_reviews=editorial_reviews,
            generation_time_seconds=10.0,
            retries=0,
            citation_issue_counts=citation_issues or {},
        ),
    )


def test_extract_metrics_actual_calls_vs_node_attempts():
    """
    Verify that extract_metrics reads actual call counts from provider_calls
    (outbound invocations at call boundaries) and node attempt counts from
    provider_attempts (infrastructure-level retries) as two separate values.
    """
    diagnostics = {
        # Actual provider invocations recorded by InstrumentedRunnable/tavily_search.
        "provider_calls": {
            "gemini": 5,
            "groq": 2,
            "tavily": 1,
            "cloudflare_image": 3,
        },
        # Node-level attempt counts: can differ from call counts due to retries.
        "provider_attempts": {
            "gemini": 3,  # 3 node attempts but 5 actual calls across those attempts
            "groq": 2,
        },
        "editorial_revisions": 1,
        "editorial_reviews": 1,
        "duration_seconds": 20.0,
        "retry_count": 1,
    }

    metrics = extract_metrics(diagnostics)

    # LLM calls = actual gemini + groq provider_calls (not node_attempts).
    assert metrics["llm_calls"] == 7  # 5 gemini + 2 groq
    assert metrics["research_calls"] == 1
    assert metrics["image_calls"] == 3
    # node_attempts is the infrastructure sum (separate from call counts).
    assert metrics["node_attempts"] == 5  # sum of provider_attempts values
    assert metrics["retries"] == 1
    # Confirm they diverge as expected.
    assert metrics["llm_calls"] != metrics["node_attempts"]


def test_build_report_includes_revision_rate_and_judge_calls():
    """
    build_report must show editorial_reviews, revision_count, and
    a computed revision rate for each run.
    """
    run = make_run_with_metrics(
        topic="Revision rate topic",
        overall_quality=9,
        revision_count=1,
        editorial_reviews=1,
    )
    run = run.model_copy(update={"metrics": run.metrics.model_copy(update={"judge_calls": 1})})
    report = build_report([run])

    assert "Editorial reviews: 1" in report
    assert "Revision count: 1" in report
    assert "Judge calls: 1" in report
    # Revision rate should appear (1/1 = 1.00)
    assert "Revision rate: 1.00" in report


def test_build_report_revision_rate_no_reviews():
    """When editorial_reviews is 0, revision rate should show as n/a."""
    run = make_run_with_metrics(
        topic="No review topic",
        overall_quality=9,
        revision_count=0,
        editorial_reviews=0,
    )
    report = build_report([run])
    assert "n/a" in report


def test_build_comparison_report_includes_operational_deltas():
    """
    build_comparison_report must include an operational deltas table covering
    LLM calls, revisions, retries, and generation time alongside score deltas.
    """
    baseline = [
        make_run_with_metrics(topic="AI", overall_quality=9, llm_calls=10, revision_count=0)
    ]
    candidate = [
        make_run_with_metrics(topic="AI", overall_quality=8, llm_calls=12, revision_count=1)
    ]
    report = build_comparison_report(baseline_runs=baseline, candidate_runs=candidate)

    assert "Score deltas" in report
    assert "Operational metric deltas" in report
    # Score regression visible.
    assert "overall_quality" in report
    # Operational regression visible.
    assert "Average LLM calls" in report
    assert "Average revisions" in report


def test_build_comparison_report_per_topic_all_score_dimensions():
    """
    Per-topic regressions section must cover all judge score dimensions,
    not just overall_quality.
    """
    baseline_scores = EvaluationScores(
        overall_quality=9,
        structure=10,
        technical_accuracy=9,
        research_quality=9,
        coherence=10,
        usefulness=9,
        writing_quality=9,
        citations=9,
        images=8,
    )
    candidate_scores = EvaluationScores(
        overall_quality=9,  # no overall regression
        structure=10,
        technical_accuracy=9,
        research_quality=9,
        coherence=10,
        usefulness=9,
        writing_quality=9,
        citations=7,  # citation regression
        images=8,
    )
    baseline_run = EvaluationRun(
        topic="Citations topic",
        run_id="b-run",
        status="success",
        evaluation=EvaluationResult(scores=baseline_scores, strengths=[], weaknesses=[], summary="ok"),
        metrics=EvaluationMetrics(
            llm_calls=5, research_calls=1, image_calls=2,
            revision_count=0, generation_time_seconds=10.0, retries=0,
        ),
    )
    candidate_run = EvaluationRun(
        topic="Citations topic",
        run_id="c-run",
        status="success",
        evaluation=EvaluationResult(scores=candidate_scores, strengths=[], weaknesses=[], summary="ok"),
        metrics=EvaluationMetrics(
            llm_calls=5, research_calls=1, image_calls=2,
            revision_count=0, generation_time_seconds=10.0, retries=0,
        ),
    )
    report = build_comparison_report(baseline_runs=[baseline_run], candidate_runs=[candidate_run])

    assert "Per-topic regressions" in report
    # The citation regression should appear (9 -> 7) even though overall_quality didn't drop.
    assert "citations" in report
    assert "Citations topic" in report


def test_build_comparison_report_citation_issue_deltas():
    """build_comparison_report must show citation issue count deltas when present."""
    baseline = [
        make_run_with_metrics(
            topic="Sources",
            overall_quality=9,
            citation_issues={"high:missing_citation": 2},
        )
    ]
    candidate = [
        make_run_with_metrics(
            topic="Sources",
            overall_quality=9,
            citation_issues={"high:missing_citation": 0},
        )
    ]
    report = build_comparison_report(baseline_runs=baseline, candidate_runs=candidate)

    assert "Citation issue deltas" in report
    assert "high:missing_citation" in report


def test_check_acceptance_guardrails_passes_on_good_run():
    """All guardrails should pass for a high-quality, low-cost run."""
    runs = [
        make_run_with_metrics(
            topic="T1", overall_quality=9, llm_calls=10, revision_count=0
        ),
        make_run_with_metrics(
            topic="T2", overall_quality=9, llm_calls=11, revision_count=0
        ),
    ]
    # Override scores to pass all guardrails.
    for run in runs:
        run.evaluation.scores.overall_quality = 9
        run.evaluation.scores.citations = 9
        run.evaluation.scores.research_quality = 9

    failures = check_acceptance_guardrails(runs)
    assert failures == [], f"Expected no failures, got: {failures}"


def test_check_acceptance_guardrails_fails_on_low_overall_quality():
    """Guardrail fails when overall quality average drops below 9.00."""
    runs = [
        make_run_with_metrics(topic="T1", overall_quality=8, llm_calls=10)
    ]
    # Force citations and research_quality to pass; only overall_quality is low.
    runs[0].evaluation.scores.citations = 9
    runs[0].evaluation.scores.research_quality = 9

    failures = check_acceptance_guardrails(runs)
    assert any("Overall quality" in f for f in failures), failures


def test_check_acceptance_guardrails_fails_on_high_severity_citation_issues():
    """Guardrail fails when any run has unresolved high-severity citation issues."""
    runs = [
        make_run_with_metrics(
            topic="Problematic",
            overall_quality=9,
            citation_issues={"high:missing_citation": 3},
        )
    ]
    runs[0].evaluation.scores.citations = 9
    runs[0].evaluation.scores.research_quality = 9

    failures = check_acceptance_guardrails(runs)
    assert any("high-severity citation" in f.lower() for f in failures), failures


def test_check_acceptance_guardrails_fails_on_excess_llm_calls():
    """Guardrail fails when average LLM calls exceed the rejected candidate's 12.63."""
    runs = [
        make_run_with_metrics(topic="T1", overall_quality=9, llm_calls=15)
    ]
    runs[0].evaluation.scores.citations = 9
    runs[0].evaluation.scores.research_quality = 9

    failures = check_acceptance_guardrails(runs)
    assert any("LLM calls" in f for f in failures), failures


def test_rerun_failed_skips_failed_topics_by_default(monkeypatch, tmp_path):
    """
    By default (rerun_failed=False), previously failed topics are skipped
    to prevent redundant reruns in the same session.
    """
    failed_run = EvaluationRun(
        topic="previously-failed",
        run_id="run-old",
        status="failed",
        metrics=EvaluationMetrics(
            llm_calls=0,
            research_calls=0,
            image_calls=0,
            revision_count=0,
            generation_time_seconds=0,
            retries=0,
        ),
        failure="RuntimeError: something went wrong",
    )

    from eval.report import write_report

    write_report(runs=[failed_run], output_dir=tmp_path)

    generated_topics = []

    def fake_run(topic, *, run_id):
        generated_topics.append(topic)
        return {"plan": object(), "final": "Article", "saved_path": "a.md"}

    monkeypatch.setattr("eval.run_eval.generate_run_id", lambda: "new-id")
    monkeypatch.setattr("eval.run_eval.run", fake_run)
    monkeypatch.setattr(
        "eval.run_eval.load_diagnostics",
        lambda run_id: {
            "provider_attempts": {},
            "editorial_revisions": 0,
            "editorial_reviews": 0,
            "duration_seconds": 0,
            "retry_count": 0,
        },
    )
    monkeypatch.setattr(
        "eval.run_eval.evaluate_article",
        lambda **kwargs: make_run(topic=kwargs["topic"], overall_quality=8).evaluation,
    )

    run_evaluation(
        topics=["previously-failed", "new-topic"],
        output_dir=tmp_path,
        between_run_delay_seconds=0,
        rerun_failed=False,
    )

    # With rerun_failed=False, previously-failed topic must be skipped.
    assert "previously-failed" not in generated_topics
    assert "new-topic" in generated_topics


def test_rerun_failed_retries_failed_topics_when_requested(monkeypatch, tmp_path):
    """
    When rerun_failed=True, previously failed topics are included in the run set.
    """
    failed_run = EvaluationRun(
        topic="retry-me",
        run_id="run-old",
        status="failed",
        metrics=EvaluationMetrics(
            llm_calls=0,
            research_calls=0,
            image_calls=0,
            revision_count=0,
            generation_time_seconds=0,
            retries=0,
        ),
        failure="RuntimeError: first attempt failed",
    )

    from eval.report import write_report

    write_report(runs=[failed_run], output_dir=tmp_path)

    generated_topics = []

    def fake_run(topic, *, run_id):
        generated_topics.append(topic)
        return {"plan": object(), "final": "Article", "saved_path": "a.md"}

    monkeypatch.setattr("eval.run_eval.generate_run_id", lambda: "new-id")
    monkeypatch.setattr("eval.run_eval.run", fake_run)
    monkeypatch.setattr(
        "eval.run_eval.load_diagnostics",
        lambda run_id: {
            "provider_attempts": {},
            "editorial_revisions": 0,
            "editorial_reviews": 0,
            "duration_seconds": 0,
            "retry_count": 0,
        },
    )
    monkeypatch.setattr(
        "eval.run_eval.evaluate_article",
        lambda **kwargs: make_run(topic=kwargs["topic"], overall_quality=8).evaluation,
    )

    run_evaluation(
        topics=["retry-me"],
        output_dir=tmp_path,
        between_run_delay_seconds=0,
        rerun_failed=True,
    )

    # With rerun_failed=True, previously-failed topic must be retried.
    assert "retry-me" in generated_topics
