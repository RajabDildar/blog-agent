from schemas.state import State
from services.final_validation import (
    validate_final_artifact,
)


def validator_node(
    state: State,
) -> dict:
    plan = state["plan"]

    if plan is None:
        raise ValueError("Final validator: plan is missing.")

    expected_sections = [task.title for task in plan.tasks]

    errors = validate_final_artifact(
        state["final"],
        expected_sections=expected_sections,
        expected_title=plan.blog_title,
        image_results=state.get(
            "image_results",
            [],
        ),
    )

    return {
        "final_validation_errors": errors,
        "final_validation_passed": not errors,
    }
