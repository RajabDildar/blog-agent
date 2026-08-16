from graph.main_graph import (
    generate_run_id,
    run,
)
from services.run_diagnostics import (
    format_cli_summary,
    load_diagnostics,
)


def main():
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
        print("\nBlog generation failed.")
        print(f"Error: {exc}")

        diagnostics = load_diagnostics(run_id)

        if diagnostics:
            print()
            print(format_cli_summary(diagnostics))
        else:
            print("\nDiagnostics were not written.")

        raise SystemExit(1)

    print("\nBlog generated successfully.")

    print(f"Title: {result['plan'].blog_title}")

    print(f"Revisions: {result['revision_count']}")

    print(f"Image plans: {len(result['image_specs'])}")

    print(f"Images inserted: {len(result['image_results'])}")

    print(f"Saved to: {result['saved_path']}")

    print(f"Diagnostics: runs/{run_id}/diagnostics.json")


if __name__ == "__main__":
    main()
