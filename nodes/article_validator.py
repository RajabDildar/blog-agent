from schemas.state import State
from services.markdown_validation import (
    validate_article_markdown,
)


def article_validator_node(
    state: State,
) -> dict:
    plan = state["plan"]

    if plan is None:
        raise ValueError("Article validator: plan is missing.")

    expected_sections = [task.title for task in plan.tasks]

    errors = validate_article_markdown(
        state["merged_md"],
        expected_sections=expected_sections,
    )

    return {
        "article_validation_errors": errors,
        "article_validation_passed": not errors,
    }
