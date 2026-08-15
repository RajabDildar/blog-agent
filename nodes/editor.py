from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
)

from schemas.models import (
    EditorialReview,
    Plan,
)
from schemas.state import State
from services.llm import gemini_llm
from prompts.editor import EDITOR_SYSTEM


def editor_node(
    state: State,
) -> dict:
    plan: Plan | None = state["plan"]

    if plan is None:
        raise ValueError("Plan is missing")

    reviewer = gemini_llm.with_structured_output(EditorialReview)

    review = reviewer.invoke(
        [
            SystemMessage(content=EDITOR_SYSTEM),
            HumanMessage(
                content=(
                    f"Topic: {state['topic']}\n\n"
                    f"Plan:\n"
                    f"{plan.model_dump()}\n\n"
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

    approved = review.overall_score >= 8 and not any(
        issue.severity == "high" for issue in review.issues
    )

    review.approved = approved

    return {
        "editorial_review": review,
    }
