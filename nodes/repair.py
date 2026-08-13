from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
)

from prompts.repair import REPAIR_SYSTEM
from schemas.models import (
    MarkdownRepairOutput,
    Plan,
)
from schemas.state import State
from services.llm import revision_llm
from services.markdown_repair import (
    repair_heading_structure,
)


def repair_node(
    state: State,
) -> dict:
    plan: Plan | None = state["plan"]

    if plan is None:
        raise ValueError("Repair: plan is missing.")

    errors = state.get(
        "article_validation_errors",
        [],
    )

    if not errors:
        return {"article_repair_count": (state["article_repair_count"])}

    markdown = state["merged_md"]

    # 1. Deterministic repair

    has_heading_error = any(
        (
            "exactly one H1" in error
            or "Invalid heading level" in error
            or "Section" in error
        )
        for error in errors
    )

    if has_heading_error:
        repaired_markdown = repair_heading_structure(markdown)

        if repaired_markdown != markdown:
            return {
                "merged_md": repaired_markdown,
                "article_repair_count": (state["article_repair_count"] + 1),
            }

    # 2. LLM repair for remaining problems

    try:
        repairer = revision_llm.with_structured_output(MarkdownRepairOutput)

        result = repairer.invoke(
            [
                SystemMessage(content=REPAIR_SYSTEM),
                HumanMessage(
                    content=(
                        f"Article plan:\n"
                        f"{plan.model_dump()}\n\n"
                        f"Validation errors:\n"
                        f"{errors}\n\n"
                        f"Current Markdown:\n"
                        f"{markdown}"
                    )
                ),
            ]
        )

    except Exception as exc:
        raise RuntimeError(f"Markdown repair failed: {exc}") from exc

    if not result.markdown.strip():
        raise ValueError("Repair returned empty Markdown.")

    return {
        "merged_md": result.markdown,
        "article_repair_count": (state["article_repair_count"] + 1),
    }
