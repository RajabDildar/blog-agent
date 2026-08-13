from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
)

from prompts.repair import REPAIR_SYSTEM
from schemas.models import MarkdownRepairOutput, Plan
from schemas.state import State
from services.llm import revision_llm
from services.markdown_repair import (
    repair_heading_structure,
)


def repair_node(state: State) -> dict:
    plan: Plan | None = state["plan"]

    if plan is None:
        raise ValueError("Repair: plan is missing.")

    errors = state.get(
        "validation_errors",
        [],
    )

    if not errors:
        return {
            "repair_count": state["repair_count"],
        }

    markdown = state["final"]

    # ---------------------------------------------------------
    # 1. Deterministic repairs first
    # ---------------------------------------------------------

    if any(
        "exactly one H1" in error or "Invalid heading level" in error
        for error in errors
    ):
        markdown = repair_heading_structure(markdown)

    # Recalculate the remaining structural problems later
    # through the validator.
    #
    # If heading repair fixed the known problem, we return
    # immediately instead of spending an LLM call.
    heading_errors = [
        error
        for error in errors
        if ("exactly one H1" in error or "Invalid heading level" in error)
    ]

    if heading_errors and markdown != state["final"]:
        return {
            "final": markdown,
            "repair_count": (state["repair_count"] + 1),
        }

    # ---------------------------------------------------------
    # 2. LLM repair for problems that actually need it
    # ---------------------------------------------------------

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

    return {
        "final": result.markdown,
        "repair_count": (state["repair_count"] + 1),
    }
