import argparse
import json
import time
from pathlib import Path

from config.settings import (
    EVAL_BETWEEN_RUN_DELAY_SECONDS,
    EVAL_MAX_RATE_LIMIT_WAIT_SECONDS,
    EVAL_RESUME_ATTEMPT_LIMIT,
)
from eval.models import (
    EvaluationMetrics,
    EvaluationRun,
)
from eval.report import (
    load_results,
    write_report,
)
from eval.score import (
    evaluate_article,
    extract_metrics,
)
from graph.main_graph import (
    generate_run_id,
    resume,
    run,
)
from services.rate_limits import (
    RateLimitRetryExhausted,
)
from services.run_diagnostics import (
    load_diagnostics,
)

DEFAULT_TOPICS_PATH = Path(__file__).parent / "topics.json"

DEFAULT_OUTPUT_ROOT = Path(__file__).parent / "runs"


def load_topics(
    path: Path,
) -> list[str]:
    data = json.loads(
        path.read_text(
            encoding="utf-8",
        )
    )

    if not isinstance(data, list):
        raise ValueError(
            "Evaluation topics must be a JSON list.",
        )

    topics = [
        topic.strip() for topic in data if isinstance(topic, str) and topic.strip()
    ]

    if not topics:
        raise ValueError(
            "Evaluation topics cannot be empty.",
        )

    return topics


def _build_metrics(
    run_id: str,
    evidence: list | None = None,
) -> EvaluationMetrics:
    diagnostics = load_diagnostics(
        run_id,
    )

    return EvaluationMetrics(
        **extract_metrics(
            diagnostics,
            evidence=evidence,
        )
    )


def _build_success_run(
    *,
    topic: str,
    run_id: str,
    result: dict,
    rate_limit_recoveries: int,
    rate_limit_wait_seconds: float,
) -> EvaluationRun:
    metrics = _build_metrics(
        run_id,
        evidence=result.get(
            "evidence",
            [],
        ),
    )

    evaluation = evaluate_article(
        topic=topic,
        plan=result["plan"],
        article=result["final"],
    )

    return EvaluationRun(
        topic=topic,
        run_id=run_id,
        status="success",
        article_path=result.get(
            "saved_path",
        ),
        evaluation=evaluation,
        metrics=metrics,
        rate_limit_recoveries=rate_limit_recoveries,
        rate_limit_wait_seconds=rate_limit_wait_seconds,
    )


def _build_failure_run(
    *,
    topic: str,
    run_id: str,
    exc: Exception,
    rate_limit_recoveries: int,
    rate_limit_wait_seconds: float,
) -> EvaluationRun:
    return EvaluationRun(
        topic=topic,
        run_id=run_id,
        status="failed",
        metrics=_build_metrics(
            run_id,
        ),
        failure=f"{type(exc).__name__}: {exc}",
        rate_limit_recoveries=rate_limit_recoveries,
        rate_limit_wait_seconds=rate_limit_wait_seconds,
    )


def _replace_run(
    *,
    runs: list[EvaluationRun],
    evaluation_run: EvaluationRun,
) -> None:
    for index, existing in enumerate(runs):
        if existing.topic == evaluation_run.topic:
            runs[index] = evaluation_run
            return

    runs.append(
        evaluation_run,
    )


def _wait_for_resume(
    *,
    run_id: str,
    max_wait_seconds: float,
) -> float:
    diagnostics = load_diagnostics(
        run_id,
    )

    resume_after = diagnostics.get(
        "resume_after",
    )

    if resume_after is None:
        raise RuntimeError("Rate-limited run has no resume_after timestamp.")

    wait_seconds = max(
        0.0,
        float(resume_after) - time.time(),
    )

    if wait_seconds > max_wait_seconds:
        raise RuntimeError(
            "Rate-limit wait exceeds the configured evaluation "
            f"maximum of {max_wait_seconds:.2f} seconds."
        )

    if wait_seconds > 0:
        time.sleep(
            wait_seconds,
        )

    return wait_seconds


def _run_topic(
    *,
    topic: str,
    run_id: str,
    max_rate_limit_wait_seconds: float,
    resume_attempt_limit: int,
) -> EvaluationRun:
    rate_limit_recoveries = 0
    rate_limit_wait_seconds = 0.0
    resume_attempts = 0

    try:
        result = run(
            topic,
            run_id=run_id,
        )

    except RateLimitRetryExhausted:
        while True:
            if resume_attempts >= resume_attempt_limit:
                return _build_failure_run(
                    topic=topic,
                    run_id=run_id,
                    exc=RuntimeError(
                        "Rate-limit recovery exceeded the configured "
                        f"resume attempt limit of {resume_attempt_limit}."
                    ),
                    rate_limit_recoveries=rate_limit_recoveries,
                    rate_limit_wait_seconds=rate_limit_wait_seconds,
                )

            try:
                waited = _wait_for_resume(
                    run_id=run_id,
                    max_wait_seconds=max_rate_limit_wait_seconds,
                )

            except Exception as wait_exc:
                return _build_failure_run(
                    topic=topic,
                    run_id=run_id,
                    exc=wait_exc,
                    rate_limit_recoveries=rate_limit_recoveries,
                    rate_limit_wait_seconds=rate_limit_wait_seconds,
                )

            rate_limit_wait_seconds += waited
            rate_limit_recoveries += 1
            resume_attempts += 1

            try:
                result = resume(
                    run_id,
                )
                break

            except RateLimitRetryExhausted:
                continue

            except Exception as resume_exc:
                return _build_failure_run(
                    topic=topic,
                    run_id=run_id,
                    exc=resume_exc,
                    rate_limit_recoveries=rate_limit_recoveries,
                    rate_limit_wait_seconds=rate_limit_wait_seconds,
                )

    except Exception as exc:
        return _build_failure_run(
            topic=topic,
            run_id=run_id,
            exc=exc,
            rate_limit_recoveries=rate_limit_recoveries,
            rate_limit_wait_seconds=rate_limit_wait_seconds,
        )

    return _build_success_run(
        topic=topic,
        run_id=run_id,
        result=result,
        rate_limit_recoveries=rate_limit_recoveries,
        rate_limit_wait_seconds=rate_limit_wait_seconds,
    )


def run_evaluation(
    *,
    topics: list[str],
    output_dir: Path,
    max_rate_limit_wait_seconds: float = (EVAL_MAX_RATE_LIMIT_WAIT_SECONDS),
    between_run_delay_seconds: float = (EVAL_BETWEEN_RUN_DELAY_SECONDS),
    resume_attempt_limit: int = (EVAL_RESUME_ATTEMPT_LIMIT),
) -> list[EvaluationRun]:
    runs = load_results(
        output_dir,
    )

    completed_topics = {evaluation_run.topic for evaluation_run in runs}

    topics_to_run = [topic for topic in topics if topic not in completed_topics]

    for index, topic in enumerate(topics_to_run):
        run_id = generate_run_id()

        evaluation_run = _run_topic(
            topic=topic,
            run_id=run_id,
            max_rate_limit_wait_seconds=(max_rate_limit_wait_seconds),
            resume_attempt_limit=resume_attempt_limit,
        )

        _replace_run(
            runs=runs,
            evaluation_run=evaluation_run,
        )

        write_report(
            runs=runs,
            output_dir=output_dir,
        )

        if index < len(topics_to_run) - 1 and between_run_delay_seconds > 0:
            time.sleep(
                between_run_delay_seconds,
            )

    return runs


def parse_args():
    parser = argparse.ArgumentParser(
        description=("Run the blog evaluation baseline."),
    )

    parser.add_argument(
        "--topics",
        type=Path,
        default=DEFAULT_TOPICS_PATH,
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
    )

    parser.add_argument(
        "--max-rate-limit-wait-seconds",
        type=float,
        default=EVAL_MAX_RATE_LIMIT_WAIT_SECONDS,
    )

    parser.add_argument(
        "--between-run-delay-seconds",
        type=float,
        default=EVAL_BETWEEN_RUN_DELAY_SECONDS,
    )

    parser.add_argument(
        "--resume-attempt-limit",
        type=int,
        default=EVAL_RESUME_ATTEMPT_LIMIT,
    )

    return parser.parse_args()


def main():
    args = parse_args()

    topics = load_topics(
        args.topics,
    )

    runs = run_evaluation(
        topics=topics,
        output_dir=args.output_dir,
        max_rate_limit_wait_seconds=(args.max_rate_limit_wait_seconds),
        between_run_delay_seconds=(args.between_run_delay_seconds),
        resume_attempt_limit=args.resume_attempt_limit,
    )

    successful = sum(evaluation_run.status == "success" for evaluation_run in runs)

    print(f"Evaluation complete: {successful}/{len(runs)} runs succeeded.")

    print(f"Results: {args.output_dir / 'results.json'}")

    print(f"Report: {args.output_dir / 'report.md'}")


if __name__ == "__main__":
    main()
