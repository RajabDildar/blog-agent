from langchain_core.messages import HumanMessage, SystemMessage

from schemas.models import Plan
from schemas.state import State
from services.llm import planner_llm
from prompts.planner import ORCH_SYSTEM


def orchestrator_node(state: State) -> dict:
    planner = planner_llm.with_structured_output(Plan)

    evidence = state.get("evidence", [])

    plan = planner.invoke(
        [
            SystemMessage(content=ORCH_SYSTEM),
            HumanMessage(
                content=(
                    f"Topic: {state['topic']}\n"
                    f"Mode: {state['mode']}\n\n"
                    f"Research brief:\n"
                    f"{state.get('research_brief', '')}\n\n"
                    f"Evidence:\n"
                    f"{[e.model_dump() for e in evidence][:20]}"
                )
            ),
        ]
    )

    return {
        "plan": plan,
    }
