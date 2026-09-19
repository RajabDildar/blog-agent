from blog_agent.schemas.state import State
from blog_agent.services.article_structure import get_expected_sections
from blog_agent.services.llm import revision_llm
from blog_agent.services.markdown_llm_repair import (
    repair_markdown_with_llm,
)
from blog_agent.services.markdown_quality import (
    run_markdown_quality_gate,
)
from blog_agent.services.run_diagnostics import (
    get_current_diagnostics,
)


def repair_node(
    state: State,
) -> dict:
    plan = state["plan"]

    if plan is None:
        raise ValueError("Repair: plan is missing.")

    blog_title = plan.blog_title
    expected_sections = get_expected_sections(plan)

    diagnostics = get_current_diagnostics()

    gate = run_markdown_quality_gate(
        state["merged_md"],
        profile="article",
        expected_title=blog_title,
        expected_sections=expected_sections,
        llm_repair=lambda current, errors: repair_markdown_with_llm(
            llm=revision_llm,
            markdown=current,
            errors=errors,
            scope="article",
            expected_title=blog_title,
            expected_sections=expected_sections,
        ),
        diagnostics=diagnostics,
    )

    return {
        "merged_md": gate.markdown,
        "article_validation_errors": gate.errors,
        "article_validation_passed": not gate.errors,
        "article_repair_count": state["article_repair_count"] + 1,
    }
