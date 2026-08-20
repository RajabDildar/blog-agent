import argparse
import json
from pathlib import Path

from eval.models import (
    EvaluationMetrics,
    EvaluationRun,
)
from eval.report import write_report
from eval.score import (
    evaluate_article,
    extract_metrics,
)
from graph.main_graph import (
    generate_run_id,
    run,
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


def run_evaluation(
    *,
    topics: list[str],
    output_dir: Path,
) -> list[EvaluationRun]:
    runs: list[EvaluationRun] = []

    for topic in topics:
        run_id = generate_run_id()

        try:
            result = run(
                topic,
                run_id=run_id,
            )

            diagnostics = load_diagnostics(
                run_id,
            )

            metrics = EvaluationMetrics(
                **extract_metrics(
                    diagnostics,
                )
            )

            evaluation = evaluate_article(
                topic=topic,
                plan=result["plan"],
                article=result["final"],
            )

            runs.append(
                EvaluationRun(
                    topic=topic,
                    run_id=run_id,
                    status="success",
                    article_path=result.get(
                        "saved_path",
                    ),
                    evaluation=evaluation,
                    metrics=metrics,
                )
            )

        except Exception as exc:
            diagnostics = load_diagnostics(
                run_id,
            )

            metrics = EvaluationMetrics(
                **extract_metrics(
                    diagnostics,
                )
            )

            runs.append(
                EvaluationRun(
                    topic=topic,
                    run_id=run_id,
                    status="failed",
                    metrics=metrics,
                    failure=(f"{type(exc).__name__}: {exc}"),
                )
            )

    write_report(
        runs=runs,
        output_dir=output_dir,
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

    return parser.parse_args()


def main():
    args = parse_args()

    topics = load_topics(
        args.topics,
    )

    runs = run_evaluation(
        topics=topics,
        output_dir=args.output_dir,
    )

    successful = sum(run.status == "success" for run in runs)

    print(f"Evaluation complete: {successful}/{len(runs)} runs succeeded.")

    print(f"Results: {args.output_dir / 'results.json'}")

    print(f"Report: {args.output_dir / 'report.md'}")


if __name__ == "__main__":
    main()
