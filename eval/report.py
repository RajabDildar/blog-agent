import json
from pathlib import Path

from eval.models import EvaluationManifest, EvaluationMetrics, EvaluationRun, EvaluationScores


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


def _average_metric(runs: list[EvaluationRun], field: str) -> float | None:
    """Return the average of a numeric metrics field across all runs, or None if empty."""
    if not runs:
        return None
    return round(sum(getattr(r.metrics, field) for r in runs) / len(runs), 3)


def _revision_rate(runs: list[EvaluationRun]) -> float | None:
    """Fraction of runs that triggered at least one revision, or None if empty."""
    if not runs:
        return None
    return round(sum(1 for r in runs if r.metrics.revision_count > 0) / len(runs), 3)


def _total_citation_issues(runs: list[EvaluationRun]) -> dict[str, int]:
    """Aggregate citation issue counts across all runs."""
    totals: dict[str, int] = {}
    for run in runs:
        for key, count in run.metrics.citation_issue_counts.items():
            totals[key] = totals.get(key, 0) + count
    return totals


def build_report(runs: list[EvaluationRun], manifest: EvaluationManifest | None = None) -> str:
    averages = calculate_average_scores(runs)

    lines = [
        "# Blog Evaluation Report",
        "",
        f"Total runs: {len(runs)}",
        (f"Successful evaluations: {sum(run.evaluation is not None for run in runs)}"),
        "",
    ]

    if manifest is not None:
        lines.extend([
            "## Experiment",
            "",
            f"- Name: `{manifest.experiment_name}`",
            f"- Purpose: {manifest.purpose}",
            f"- Pipeline commit: `{manifest.pipeline_commit}`",
            f"- Judge image input: {manifest.judge_image_input}",
            "",
        ])

    lines.extend([
        "## Average scores",
        "",
    ])

    if averages:
        for name, score in averages.items():
            lines.append(f"- {name}: {score:.2f}/10")
    else:
        lines.append(
            "No successful evaluations.",
        )

    # Operational summary across all runs
    all_revision_rate = _revision_rate(runs)
    lines.extend([
        "",
        "## Operational summary",
        "",
        f"- Revision rate: {all_revision_rate:.2f}" if all_revision_rate is not None else "- Revision rate: n/a",
        f"- Average LLM calls: {_average_metric(runs, 'llm_calls')}",
        f"- Average research calls: {_average_metric(runs, 'research_calls')}",
        f"- Average image calls: {_average_metric(runs, 'image_calls')}",
        f"- Average node attempts: {_average_metric(runs, 'node_attempts')}",
        f"- Average retries: {_average_metric(runs, 'retries')}",
        f"- Average generation time: {_average_metric(runs, 'generation_time_seconds'):.2f}s"
        if runs else "- Average generation time: n/a",
        "",
    ])

    lines.extend(
        [
            "## Runs",
            "",
        ]
    )

    for run in runs:
        rev_rate = (
            f"{run.metrics.revision_count / run.metrics.editorial_reviews:.2f}"
            if run.metrics.editorial_reviews > 0
            else "n/a (no reviews)"
        )
        lines.extend(
            [
                f"### {run.topic}",
                "",
                f"- Run ID: `{run.run_id}`",
                f"- Status: {run.status}",
                f"- LLM calls: {run.metrics.llm_calls}",
                (f"- Research calls: {run.metrics.research_calls}"),
                f"- Image calls: {run.metrics.image_calls}",
                f"- Node attempts: {run.metrics.node_attempts}",
                f"- Judge calls: {run.metrics.judge_calls}",
                (f"- Revision count: {run.metrics.revision_count}"),
                f"- Editorial reviews: {run.metrics.editorial_reviews}",
                f"- Revision rate: {rev_rate}",
                (f"- Generation time: {run.metrics.generation_time_seconds:.2f}s"),
                f"- Retries: {run.metrics.retries}",
                (f"- Official source ratio: {run.metrics.official_source_ratio:.2f}"),
                (f"- Unknown source ratio: {run.metrics.unknown_source_ratio:.2f}"),
                (
                    f"- Average authority score: "
                    f"{run.metrics.average_authority_score:.2f}"
                ),
                (f"- Average quality score: {run.metrics.average_quality_score:.2f}"),
                # weak_source_ratio = evidence with source_type in WEAK_SOURCE_CATEGORIES
                # (vendor_blog, unknown) OR authority_score < WEAK_SOURCE_AUTHORITY_THRESHOLD.
                # This is distinct from support_strength (claim-support strength).
                (f"- Weak source ratio: {run.metrics.weak_source_ratio:.2f}"),
                "- Weak source ratio definition: evidence in weak source categories "
                "(vendor_blog or unknown source_type) or authority_score below threshold "
                "(default 0.5). Separate from LLM claim-support strength.",
                (f"- Unique domains: {run.metrics.unique_domain_count}"),
                (f"- Source type distribution: {run.metrics.source_type_distribution}"),
                (f"- Authority distribution: {run.metrics.authority_distribution}"),
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


def _fmt_delta(baseline: float | None, candidate: float | None) -> tuple[str, str, str]:
    """Return (baseline_str, candidate_str, delta_str) for a table row."""
    b = f"{baseline:.3f}" if baseline is not None else "unavailable"
    c = f"{candidate:.3f}" if candidate is not None else "unavailable"
    if baseline is None or candidate is None:
        d = "unavailable"
    else:
        d = f"{candidate - baseline:+.3f}"
    return b, c, d


def build_comparison_report(
    *,
    baseline_runs: list[EvaluationRun],
    candidate_runs: list[EvaluationRun],
) -> str:
    baseline_scores = calculate_average_scores(baseline_runs)
    candidate_scores = calculate_average_scores(candidate_runs)

    lines = ["# Evaluation Comparison", "", "## Score deltas", "",
             "| Metric | Baseline | Candidate | Delta |",
             "| --- | ---: | ---: | ---: |"]

    for name in sorted(set(baseline_scores) | set(candidate_scores)):
        baseline = baseline_scores.get(name)
        candidate = candidate_scores.get(name)
        delta = (
            "unavailable"
            if baseline is None or candidate is None
            else f"{candidate - baseline:+.2f}"
        )
        b_str = f"{baseline}" if baseline is not None else "unavailable"
        c_str = f"{candidate}" if candidate is not None else "unavailable"
        lines.append(f"| {name} | {b_str} | {c_str} | {delta} |")

    # ---- Operational metric deltas ----
    op_metrics = [
        ("llm_calls", "Average LLM calls"),
        ("research_calls", "Average research calls"),
        ("image_calls", "Average image calls"),
        ("node_attempts", "Average node attempts"),
        ("retries", "Average retries"),
        ("revision_count", "Average revisions"),
        ("editorial_reviews", "Average editorial reviews"),
        ("generation_time_seconds", "Average generation time (s)"),
        ("rate_limit_recoveries", "Average rate-limit recoveries"),
        ("rate_limit_wait_seconds", "Average rate-limit wait (s)"),
    ]

    lines.extend(["", "## Operational metric deltas", "",
                  "| Metric | Baseline | Candidate | Delta |",
                  "| --- | ---: | ---: | ---: |"])

    def _run_avg(runs: list[EvaluationRun], field: str) -> float | None:
        if not runs:
            return None
        try:
            values = [
                getattr(r.metrics, field)
                if hasattr(r.metrics, field)
                else getattr(r, field, None)
                for r in runs
            ]
            if any(v is None for v in values):
                return None
            return round(sum(values) / len(values), 3)
        except AttributeError:
            return None

    # rate_limit_recoveries and rate_limit_wait_seconds are on EvaluationRun directly
    def _run_avg_any(runs: list[EvaluationRun], field: str) -> float | None:
        if not runs:
            return None
        vals = []
        for r in runs:
            v = getattr(r.metrics, field, None)
            if v is None:
                v = getattr(r, field, None)
            vals.append(v)
        if any(v is None for v in vals):
            return None
        return round(sum(vals) / len(vals), 3)

    for field, label in op_metrics:
        b_val = _run_avg_any(baseline_runs, field)
        c_val = _run_avg_any(candidate_runs, field)
        b_str, c_str, d_str = _fmt_delta(b_val, c_val)
        lines.append(f"| {label} | {b_str} | {c_str} | {d_str} |")

    # Revision rates
    b_rev_rate = _revision_rate(baseline_runs)
    c_rev_rate = _revision_rate(candidate_runs)
    b_str, c_str, d_str = _fmt_delta(b_rev_rate, c_rev_rate)
    lines.append(f"| Revision rate | {b_str} | {c_str} | {d_str} |")

    # ---- Citation issue deltas ----
    b_issues = _total_citation_issues(baseline_runs)
    c_issues = _total_citation_issues(candidate_runs)
    all_issue_keys = sorted(set(b_issues) | set(c_issues))
    if all_issue_keys:
        lines.extend(["", "## Citation issue deltas", "",
                      "| Issue key | Baseline total | Candidate total | Delta |",
                      "| --- | ---: | ---: | ---: |"])
        for key in all_issue_keys:
            b_cnt = b_issues.get(key, 0)
            c_cnt = c_issues.get(key, 0)
            lines.append(f"| {key} | {b_cnt} | {c_cnt} | {c_cnt - b_cnt:+d} |")

    # ---- Per-topic regressions (all score dimensions) ----
    lines.extend(["", "## Per-topic regressions", ""])
    baseline_by_topic = {run.topic: run for run in baseline_runs if run.evaluation is not None}
    score_names = list(EvaluationScores.model_fields.keys())

    regressions_found = False
    for candidate in candidate_runs:
        baseline = baseline_by_topic.get(candidate.topic)
        if baseline is None or candidate.evaluation is None:
            continue
        dims = []
        for dim in score_names:
            b_score = getattr(baseline.evaluation.scores, dim, None)
            c_score = getattr(candidate.evaluation.scores, dim, None)
            if b_score is not None and c_score is not None and c_score < b_score:
                dims.append(f"{dim}: {b_score} → {c_score}")
        if dims:
            lines.append(f"- **{candidate.topic}**: " + ", ".join(dims))
            regressions_found = True

    if not regressions_found:
        lines.append("No per-topic regressions detected.")

    return "\n".join(lines)


# Phase 8 acceptance guardrails
# These thresholds are the pre-agreed gates from the remediation plan.
GUARDRAIL_OVERALL_QUALITY_MIN = 9.00
GUARDRAIL_CITATIONS_MIN = 8.12
GUARDRAIL_RESEARCH_QUALITY_MIN = 8.62
GUARDRAIL_LLM_CALLS_MAX = 12.63  # rejected candidate's measured average


def check_acceptance_guardrails(
    candidate_runs: list[EvaluationRun],
) -> list[str]:
    """
    Evaluate Phase 8 acceptance guardrails against candidate evaluation runs.

    Returns a list of human-readable failure messages.  An empty list means all
    deterministic guardrails pass.  Probabilistic judge-score guardrails are
    included so callers can surface them, but they should be interpreted with
    the caveat that a single judge pass is noisy.

    Guardrails (from the remediation plan):
    - 8/8 generation and evaluation success.
    - Zero unresolved high-severity citation issues.
    - Overall judge average >= 9.00 (historical baseline).
    - Citations judge average > 8.12.
    - Research quality judge average >= 8.62.
    - Average pipeline LLM calls <= 12.63 (rejected candidate).
    """
    failures: list[str] = []

    total = len(candidate_runs)
    succeeded = sum(r.status == "success" and r.evaluation is not None for r in candidate_runs)
    if succeeded < total:
        failures.append(
            f"Generation/evaluation success: {succeeded}/{total} "
            f"(required: {total}/{total})"
        )

    # Deterministic citation gate: any high-severity unresolved citation issues.
    high_severity_topics = []
    for run in candidate_runs:
        for key, count in run.metrics.citation_issue_counts.items():
            if key.startswith("high:") and count > 0:
                high_severity_topics.append(f"{run.topic} ({key}: {count})")
    if high_severity_topics:
        failures.append(
            "Unresolved high-severity citation issues in: "
            + ", ".join(high_severity_topics)
        )

    scores = calculate_average_scores(candidate_runs)

    overall = scores.get("overall_quality")
    if overall is not None and overall < GUARDRAIL_OVERALL_QUALITY_MIN:
        failures.append(
            f"Overall quality average {overall:.2f} < required {GUARDRAIL_OVERALL_QUALITY_MIN:.2f}"
        )

    citations = scores.get("citations")
    if citations is not None and citations <= GUARDRAIL_CITATIONS_MIN:
        failures.append(
            f"Citations average {citations:.2f} <= required > {GUARDRAIL_CITATIONS_MIN:.2f}"
        )

    research = scores.get("research_quality")
    if research is not None and research < GUARDRAIL_RESEARCH_QUALITY_MIN:
        failures.append(
            f"Research quality average {research:.2f} < required {GUARDRAIL_RESEARCH_QUALITY_MIN:.2f}"
        )

    avg_llm = _average_metric(candidate_runs, "llm_calls")
    if avg_llm is not None and avg_llm > GUARDRAIL_LLM_CALLS_MAX:
        failures.append(
            f"Average LLM calls {avg_llm:.2f} > allowed {GUARDRAIL_LLM_CALLS_MAX:.2f}"
        )

    return failures


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Generate blog evaluation reports and guardrail checks.")
    parser.add_argument("--baseline", type=Path, help="Path to baseline experiment directory")
    parser.add_argument("--candidate", type=Path, help="Path to candidate experiment directory")
    parser.add_argument("--run", type=Path, help="Path to single experiment directory to check")

    args = parser.parse_args()

    if args.baseline and args.candidate:
        baseline_results = json.loads((args.baseline / "results.json").read_text(encoding="utf-8"))
        candidate_results = json.loads((args.candidate / "results.json").read_text(encoding="utf-8"))

        baseline_runs = [EvaluationRun.model_validate(r) for r in baseline_results]
        candidate_runs = [EvaluationRun.model_validate(r) for r in candidate_results]

        comparison = build_comparison_report(baseline_runs=baseline_runs, candidate_runs=candidate_runs)
        print(comparison)

        failures = check_acceptance_guardrails(candidate_runs)
        print("\n## Acceptance Guardrail Status")
        if not failures:
            print("PASSED: All acceptance guardrails met!")
        else:
            print("FAILED: The following guardrail checks failed:")
            for f in failures:
                print(f"  - {f}")

    elif args.run or args.baseline or args.candidate:
        run_dir = args.run or args.candidate or args.baseline
        results_file = run_dir / "results.json"
        if not results_file.exists():
            print(f"Error: {results_file} does not exist.")
            return

        results_data = json.loads(results_file.read_text(encoding="utf-8"))
        runs = [EvaluationRun.model_validate(r) for r in results_data]

        print(build_report(runs))

        failures = check_acceptance_guardrails(runs)
        print("\n## Acceptance Guardrail Status")
        if not failures:
            print("PASSED: All acceptance guardrails met!")
        else:
            print("FAILED: The following guardrail checks failed:")
            for f in failures:
                print(f"  - {f}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
