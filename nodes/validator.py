from schemas.state import State
from services.final_validation import (
    validate_final_images,
)
from services.markdown_quality import (
    run_markdown_quality_gate,
)


def validator_node(
    state: State,
) -> dict:
    plan = state["plan"]

    if plan is None:
        raise ValueError("Final validator: plan is missing.")

    expected_sections = [task.title for task in plan.tasks]

    # No LLM repair here.
    gate = run_markdown_quality_gate(
        state["final"],
        profile="article",
        expected_title=plan.blog_title,
        expected_sections=expected_sections,
    )

    errors = list(gate.errors)

    if not errors:
        errors.extend(
            validate_final_images(
                gate.markdown,
                image_results=state.get(
                    "image_results",
                    [],
                ),
            )
        )

    return {
        "final": gate.markdown,
        "final_validation_errors": errors,
        "final_validation_passed": not errors,
    }
