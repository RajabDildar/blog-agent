from blog_agent.schemas.state import State
from blog_agent.services.article_structure import get_expected_sections
from blog_agent.services.final_validation import (
    validate_final_images,
)
from blog_agent.services.markdown_quality import (
    run_markdown_quality_gate,
)
from blog_agent.services.run_diagnostics import (
    get_current_diagnostics,
)


def validator_node(
    state: State,
) -> dict:
    plan = state["plan"]

    if plan is None:
        raise ValueError("Final validator: plan is missing.")

    expected_sections = get_expected_sections(plan)

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

    if errors:
        diagnostics = get_current_diagnostics()

        if diagnostics is not None:
            diagnostics.record_final_validation(errors)

    return {
        "final": gate.markdown,
        "final_validation_errors": errors,
        "final_validation_passed": not errors,
    }
