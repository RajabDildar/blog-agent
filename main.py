import argparse
from datetime import UTC, datetime
import uuid

from blog_agent import resume, run
from blog_agent.graph.main_graph import app, _thread_config
from blog_agent.schemas.models import IntentHumanResponse
from blog_agent.services.rate_limits import RateLimitRetryExhausted
from blog_agent.services.run_diagnostics import (
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
        help="Resume a previously failed or interrupted run.",
    )

    return parser.parse_args()


def print_success_summary(
    result,
    run_id: str,
):
    print("\nBlog generated successfully.")
    print(f"Title: {result['plan'].blog_title}")
    print(f"Topic: {result.get('topic', '')}")
    print(f"Revisions: {result['revision_count']}")
    print(f"Image plans: {len(result['image_specs'])}")
    print(f"Images inserted: {len(result['image_results'])}")
    print(f"Saved to: {result['saved_path']}")
    print(f"Diagnostics: runs/{run_id}/diagnostics.json")


def report_failure(
    exc: Exception,
    run_id: str,
):
    if isinstance(exc, RateLimitRetryExhausted):
        print("\nBlog generation paused by provider rate limit.")
        print(f"Run ID: {exc.run_id or run_id}")

        if exc.resume_after is not None:
            resume_at = datetime.fromtimestamp(
                exc.resume_after,
                tz=UTC,
            ).isoformat()
            print(f"Resume after (UTC): {resume_at}")
        else:
            print(
                "The provider did not supply a retry/reset time. "
                "Check diagnostics before resuming."
            )

    else:
        print("\nBlog generation failed.")
        print(f"Error: {exc}")

    diagnostics = load_diagnostics(run_id)

    if diagnostics:
        print()
        print(format_cli_summary(diagnostics))
    else:
        print("\nDiagnostics were not written.")


def get_pending_interrupt_payload(run_id: str) -> dict | None:
    """Check if thread is currently halted on a LangGraph interrupt."""
    state = app.get_state(_thread_config(run_id))
    if state.tasks and state.tasks[0].interrupts:
        return state.tasks[0].interrupts[0].value
    return None


def handle_interaction_and_finish(result: dict, run_id: str) -> None:
    """Handle clarification/confirmation interrupts and terminal intent states."""
    while True:
        payload = get_pending_interrupt_payload(run_id)
        if not payload:
            break

        payload_type = payload.get("type")

        if payload_type == "clarification_required":
            print(f"\nClarification Needed: {payload['question']}\n")
            options = payload.get("options", [])
            for i, opt in enumerate(options, 1):
                print(f"  [{i}] {opt}")
            print(f"  [4] Enter custom response")
            print(f"  [5] Cancel")

            human_response: IntentHumanResponse | None = None
            while human_response is None:
                choice = input("\nChoose an option (1-5): ").strip()
                if choice in ("1", "2", "3") and int(choice) <= len(options):
                    idx = int(choice) - 1
                    human_response = IntentHumanResponse(
                        action="select_option",
                        value=options[idx],
                    )
                elif choice == "4":
                    custom_text = input("Enter custom topic: ").strip()
                    if not custom_text:
                        print("Custom topic cannot be empty.")
                        continue
                    human_response = IntentHumanResponse(
                        action="custom_input",
                        value=custom_text,
                    )
                elif choice == "5":
                    human_response = IntentHumanResponse(action="cancel")
                else:
                    print("Please enter a valid option number (1-5).")

            try:
                result = resume(run_id, human_response=human_response)
            except Exception as exc:
                report_failure(exc, run_id)
                raise SystemExit(1)

        elif payload_type == "topic_confirmation_required":
            print(f"\n{payload.get('message', 'Your request is still broad.')}")
            print(f"Proposed Topic: {payload.get('proposed_topic', '')}\n")
            print("  [1] Proceed with proposed topic")
            print("  [2] Cancel")

            human_response = None
            while human_response is None:
                choice = input("\nChoose an option (1-2): ").strip()
                if choice == "1":
                    human_response = IntentHumanResponse(action="proceed")
                elif choice == "2":
                    human_response = IntentHumanResponse(action="cancel")
                else:
                    print("Please enter 1 or 2.")

            try:
                result = resume(run_id, human_response=human_response)
            except Exception as exc:
                report_failure(exc, run_id)
                raise SystemExit(1)

        else:
            break

    # Check terminal intent statuses
    intent_status = result.get("intent_status")
    intent_message = result.get("intent_message", "")

    if intent_status == "blocked":
        print(f"\n[Request Blocked]\n{intent_message}")
        print(f"Diagnostics: runs/{run_id}/diagnostics.json")
        return

    if intent_status == "invalid":
        print(f"\n[Invalid Request]\n{intent_message}")
        print(f"Diagnostics: runs/{run_id}/diagnostics.json")
        return

    if intent_status == "cancelled":
        print(f"\n[Generation Cancelled]\n{intent_message or 'Cancelled by user.'}")
        print(f"Diagnostics: runs/{run_id}/diagnostics.json")
        return

    if result.get("plan") is not None:
        print_success_summary(result, run_id)


def main():
    args = parse_args()

    if args.resume:
        run_id = args.resume
        print(f"\nResuming run: {run_id}")

        # Check if there is an existing pending interrupt
        pending_payload = get_pending_interrupt_payload(run_id)
        if pending_payload:
            # Re-enter the interaction loop
            handle_interaction_and_finish({}, run_id)
            return

        try:
            result = resume(run_id)
        except Exception as exc:
            report_failure(
                exc,
                run_id,
            )
            raise SystemExit(1)

        handle_interaction_and_finish(result, run_id)
        return

    topic = input("Enter blog topic: ").strip()

    if not topic:
        raise SystemExit("Topic cannot be empty.")

    run_id = str(uuid.uuid4())
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

    handle_interaction_and_finish(result, run_id)


if __name__ == "__main__":
    main()
