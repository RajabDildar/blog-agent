from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
)

from prompts.editor import EDITOR_SYSTEM
from schemas.models import (
    EditorialIssue,
    EditorialReview,
    Plan,
)
from schemas.state import State
from services.llm import gemini_llm
from services.run_diagnostics import (
    get_current_diagnostics,
)


def _merge_editorial_issues(
    *,
    citation_issues: list[EditorialIssue],
    editor_issues: list[EditorialIssue],
) -> list[EditorialIssue]:
    seen: set[
        tuple[
            int | None,
            str,
            str,
        ]
    ] = set()

    merged: list[EditorialIssue] = []

    for issue in [
        *citation_issues,
        *editor_issues,
    ]:
        key = (
            issue.task_id,
            issue.category,
            issue.problem,
        )

        if key in seen:
            continue

        seen.add(key)
        merged.append(issue)

    return merged


def editor_node(
    state: State,
) -> dict:
    plan: Plan | None = state["plan"]

    if plan is None:
        raise ValueError("Plan is missing")

    citation_issues = state.get(
        "citation_issues",
        [],
    )

    reviewer = gemini_llm.with_structured_output(
        EditorialReview,
    )

    review = reviewer.invoke(
        [
            SystemMessage(content=EDITOR_SYSTEM),
            HumanMessage(
                content=(
                    f"Topic: {state['topic']}\n\n"
                    f"Plan:\n"
                    f"{plan.model_dump()}\n\n"
                    f"Deterministic citation issues:\n"
                    f"{[issue.model_dump() for issue in citation_issues]}\n\n"
                    f"Article:\n"
                    f"{state['merged_md']}"
                )
            ),
        ]
    )

    planned_ids = {task.id for task in plan.tasks}

    invalid_section_ids = [
        task_id for task_id in review.sections_to_revise if task_id not in planned_ids
    ]

    if invalid_section_ids:
        raise ValueError(f"Editor returned invalid section IDs: {invalid_section_ids}")

    review.issues = _merge_editorial_issues(
        citation_issues=citation_issues,
        editor_issues=review.issues,
    )

    deterministic_task_ids = {
        issue.task_id for issue in citation_issues if issue.task_id is not None
    }

    review.sections_to_revise = sorted(
        {
            *review.sections_to_revise,
            *deterministic_task_ids,
        }
    )

    approved = review.overall_score >= 8 and not any(
        issue.severity == "high" for issue in review.issues
    )

    review.approved = approved

    diagnostics = get_current_diagnostics()

    if diagnostics is not None:
        diagnostics.record_editorial_review()

    return {
        "editorial_review": review,
    }
