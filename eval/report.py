import json
from pathlib import Path

from eval.models import EvaluationManifest, EvaluationRun


def calculate_average_scores(
    runs: list[EvaluationRun],
) -> dict[str, float]:
    successful = [run for run in runs if run.evaluation is not None]

    if not successful:
        return {}

    score_names = type(successful[0].evaluation.scores).model_fields.keys()

    return {
        name: round(
            sum(
                getattr(
                    run.evaluation.scores,
                    name,
                )
                for run in successful
            )
            / len(successful),
            2,
        )
        for name in score_names
    }


def build_report(runs: list[EvaluationRun], manifest: EvaluationManifest | None = None) -> str:
    averages = calculate_average_scores(runs)

    lines = [
        "# Blog Evaluation Report",
        "",
        f"Total runs: {len(runs)}",
        (f"Successful evaluations: {sum(run.evaluation is not None for run in runs)}"),
        "",
        "## Average scores",
        "",
    ]
    if manifest is not None:
        lines.extend(["## Experiment", "", f"- Name: `{manifest.experiment_name}`", f"- Purpose: {manifest.purpose}", f"- Pipeline commit: `{manifest.pipeline_commit}`", f"- Judge image input: {manifest.judge_image_input}", ""])

    if averages:
        for name, score in averages.items():
            lines.append(f"- {name}: {score:.2f}/10")
    else:
        lines.append(
            "No successful evaluations.",
        )

    lines.extend(
        [
            "",
            "## Runs",
            "",
        ]
    )

    for run in runs:
        lines.extend(
            [
                f"### {run.topic}",
                "",
                f"- Run ID: `{run.run_id}`",
                f"- Status: {run.status}",
                f"- LLM calls: {run.metrics.llm_calls}",
                (f"- Research calls: {run.metrics.research_calls}"),
                f"- Image calls: {run.metrics.image_calls}",
                (f"- Revision count: {run.metrics.revision_count}"),
                (f"- Generation time: {run.metrics.generation_time_seconds:.2f}s"),
                f"- Retries: {run.metrics.retries}",
                (f"- Official source ratio: {run.metrics.official_source_ratio:.2f}"),
                (f"- Unknown source ratio: {run.metrics.unknown_source_ratio:.2f}"),
                (
                    f"- Average authority score: "
                    f"{run.metrics.average_authority_score:.2f}"
                ),
                (f"- Average quality score: {run.metrics.average_quality_score:.2f}"),
                (f"- Weak source ratio: {run.metrics.weak_source_ratio:.2f}"),
                (f"- Unique domains: {run.metrics.unique_domain_count}"),
                (f"- Source type distribution: {run.metrics.source_type_distribution}"),
                (f"- Authority distribution: {run.metrics.authority_distribution}"),
                "- Weak source ratio definition: evidence whose LLM claim-support strength is `weak` (not source authority).",
                f"- Citation issues: {run.metrics.citation_issue_counts}",
                f"- Rate-limit recoveries: {run.rate_limit_recoveries}",
                (f"- Rate-limit wait: {run.rate_limit_wait_seconds:.2f}s"),
            ]
        )

        if run.evaluation is not None:
            lines.append(
                f"- Overall quality: {run.evaluation.scores.overall_quality}/10"
            )
            lines.append(f"- Summary: {run.evaluation.summary}")

        if run.failure:
            lines.append(f"- Failure: {run.failure}")

        lines.append("")

    return "\n".join(lines)


def load_results(
    output_dir: Path,
) -> list[EvaluationRun]:
    json_path = output_dir / "results.json"

    if not json_path.is_file():
        return []

    data = json.loads(
        json_path.read_text(
            encoding="utf-8",
        )
    )

    if not isinstance(data, list):
        raise ValueError(
            "Evaluation results must be a JSON list.",
        )

    return [
        EvaluationRun.model_validate(
            item,
        )
        for item in data
    ]


def write_report(
    *,
    runs: list[EvaluationRun],
    output_dir: Path,
    manifest: EvaluationManifest | None = None,
) -> tuple[Path, Path]:
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    json_path = output_dir / "results.json"
    markdown_path = output_dir / "report.md"

    json_path.write_text(
        json.dumps(
            [
                run.model_dump(
                    mode="json",
                )
                for run in runs
            ],
            indent=2,
        ),
        encoding="utf-8",
    )

    markdown_path.write_text(
        build_report(runs, manifest),
        encoding="utf-8",
    )

    return json_path, markdown_path


def build_comparison_report(
    *,
    baseline_runs: list[EvaluationRun],
    candidate_runs: list[EvaluationRun],
) -> str:
    baseline_scores = calculate_average_scores(baseline_runs)
    candidate_scores = calculate_average_scores(candidate_runs)
    lines = ["# Evaluation Comparison", "", "## Score deltas", "", "| Metric | Baseline | Candidate | Delta |", "| --- | ---: | ---: | ---: |"]
    for name in sorted(set(baseline_scores) | set(candidate_scores)):
        baseline = baseline_scores.get(name)
        candidate = candidate_scores.get(name)
        delta = "unavailable" if baseline is None or candidate is None else f"{candidate - baseline:+.2f}"
        lines.append(f"| {name} | {baseline if baseline is not None else 'unavailable'} | {candidate if candidate is not None else 'unavailable'} | {delta} |")
    lines.extend(["", "## Per-topic regressions", ""])
    baseline_by_topic = {run.topic: run for run in baseline_runs if run.evaluation is not None}
    for candidate in candidate_runs:
        baseline = baseline_by_topic.get(candidate.topic)
        if baseline and candidate.evaluation and candidate.evaluation.scores.overall_quality < baseline.evaluation.scores.overall_quality:
            lines.append(f"- {candidate.topic}: overall quality {baseline.evaluation.scores.overall_quality} -> {candidate.evaluation.scores.overall_quality}")
    return "\n".join(lines)
