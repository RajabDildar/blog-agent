from langchain_core.messages import HumanMessage, SystemMessage

from prompts.repair import REPAIR_SYSTEM
from schemas.models import MarkdownRepairOutput, Plan
from schemas.state import State
from services.llm import revision_llm


def repair_node(state: State) -> dict:
    try:
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
                            f"{state['final']}"
                        )
                    ),
                ]
            )
        except Exception as exc:
            raise RuntimeError(f"Markdown repair failed: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"Repair failed: {exc}") from exc

    return {
        "final": result.markdown,
        "repair_count": (state["repair_count"] + 1),
    }
