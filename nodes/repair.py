from schemas.models import Plan
from schemas.state import State
from services.llm import revision_llm
from services.markdown_llm_repair import (
    repair_markdown_with_llm,
)
from services.markdown_quality import (
    run_markdown_quality_gate,
)
from services.run_diagnostics import (
    get_current_diagnostics,
)


def repair_node(
    state: State,
) -> dict:
    plan: Plan | None = state["plan"]

    if plan is None:
        raise ValueError("Repair: plan is missing.")

    expected_sections = [task.title for task in plan.tasks]

    diagnostics = get_current_diagnostics()

    gate = run_markdown_quality_gate(
        state["merged_md"],
        profile="article",
        expected_title=plan.blog_title,
        expected_sections=expected_sections,
        llm_repair=lambda current, errors: repair_markdown_with_llm(
            llm=revision_llm,
            markdown=current,
            errors=errors,
            scope="article",
            expected_title=(plan.blog_title),
            expected_sections=(expected_sections),
            diagnostics=diagnostics,
        ),
    )

    return {
        "merged_md": gate.markdown,
        "article_validation_errors": gate.errors,
        "article_validation_passed": not gate.errors,
        "article_repair_count": state["article_repair_count"] + 1,
    }
