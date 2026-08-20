import argparse

from graph.main_graph import (
    generate_run_id,
    resume,
    run,
)
from services.run_diagnostics import (
    format_cli_summary,
    load_diagnostics,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate or resume a blog run.",
    )

    parser.add_argument(
        "--resume",
        metavar="RUN_ID",
        help="Resume a previously failed run.",
    )

    return parser.parse_args()


def print_success_summary(
    result,
    run_id: str,
):
    print("\nBlog generated successfully.")

    print(f"Title: {result['plan'].blog_title}")

    print(f"Revisions: {result['revision_count']}")

    print(f"Image plans: {len(result['image_specs'])}")

    print(f"Images inserted: {len(result['image_results'])}")

    print(f"Saved to: {result['saved_path']}")

    print(f"Diagnostics: runs/{run_id}/diagnostics.json")


def report_failure(
    exc: Exception,
    run_id: str,
):
    print("\nBlog generation failed.")
    print(f"Error: {exc}")

    diagnostics = load_diagnostics(run_id)

    if diagnostics:
        print()
        print(format_cli_summary(diagnostics))
    else:
        print("\nDiagnostics were not written.")


def main():
    args = parse_args()

    if args.resume:
        run_id = args.resume

        print(f"\nResuming run: {run_id}")

        try:
            result = resume(run_id)

        except Exception as exc:
            report_failure(
                exc,
                run_id,
            )

            raise SystemExit(1)

        print_success_summary(
            result,
            run_id,
        )

        return

    topic = input("Enter blog topic: ").strip()

    if not topic:
        raise SystemExit("Topic cannot be empty.")

    run_id = generate_run_id()

    print(f"\nRun ID: {run_id}")

    try:
        result = run(
            topic,
            run_id=run_id,
        )

    except Exception as exc:
        report_failure(
            exc,
            run_id,
        )

        raise SystemExit(1)

    print_success_summary(
        result,
        run_id,
    )


if __name__ == "__main__":
    main()
