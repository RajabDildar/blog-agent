from schemas.state import State
from services.markdown_quality import (
    run_markdown_quality_gate,
)


def article_validator_node(
    state: State,
) -> dict:
    plan = state["plan"]

    if plan is None:
        raise ValueError("Article validator: plan is missing.")

    expected_sections = [task.title for task in plan.tasks]

    gate = run_markdown_quality_gate(
        state["merged_md"],
        profile="article",
        expected_title=plan.blog_title,
        expected_sections=expected_sections,
    )

    return {
        "merged_md": gate.markdown,
        "article_validation_errors": gate.errors,
        "article_validation_passed": not gate.errors,
    }
