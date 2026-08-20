from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
)

from prompts.router import ROUTER_SYSTEM
from schemas.models import RouterDecision
from schemas.state import State
from services.llm import gemini_llm
from services.time import (
    current_date,
    current_year,
)


def router_node(
    state: State,
) -> dict:
    decider = gemini_llm.with_structured_output(RouterDecision)

    decision = decider.invoke(
        [
            SystemMessage(content=ROUTER_SYSTEM),
            HumanMessage(
                content=(
                    f"Current date: {current_date()}\n"
                    f"Current year: {current_year()}\n\n"
                    f"Topic:\n{state['topic']}"
                )
            ),
        ]
    )

    return {
        "needs_research": decision.needs_research,
        "mode": decision.mode,
        "research_focus": decision.research_focus,
        "queries": decision.queries,
    }


def route_next(
    state: State,
) -> str:
    if state["needs_research"]:
        return "research"

    return "orchestrator"
