from langchain_core.messages import HumanMessage, SystemMessage

from schemas.models import RouterDecision
from schemas.state import State
from services.llm import gemini_llm
from prompts.router import ROUTER_SYSTEM


def router_node(state: State) -> dict:
    try:
        decider = gemini_llm.with_structured_output(RouterDecision)

        decision = decider.invoke(
            [
                SystemMessage(content=ROUTER_SYSTEM),
                HumanMessage(content=f"Topic:\n{state['topic']}"),
            ]
        )

    except Exception as exc:
        raise RuntimeError(f"Router failed: {exc}") from exc

    return {
        "needs_research": decision.needs_research,
        "mode": decision.mode,
        "research_focus": decision.research_focus,
        "queries": decision.queries,
    }


def route_next(state: State) -> str:
    if state["needs_research"]:
        return "research"

    return "orchestrator"
