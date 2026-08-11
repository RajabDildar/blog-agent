from langchain_core.messages import HumanMessage, SystemMessage

from schemas.models import EditorialReview, Plan
from schemas.state import State
from services.llm import editor_llm
from prompts.editor import EDITOR_SYSTEM


def editor_node(state: State) -> dict:
    plan: Plan | None = state["plan"]

    if plan is None:
        raise ValueError("Plan is missing")

    reviewer = editor_llm.with_structured_output(EditorialReview)

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

    approved = review.overall_score >= 8 and not any(
        issue.severity == "high" for issue in review.issues
    )

    review.approved = approved

    return {
        "editorial_review": review,
    }
