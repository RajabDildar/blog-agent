from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
)

from prompts.planner import PLANNER_SYSTEM
from schemas.models import (
    Plan,
    ResearchEvidence,
)
from schemas.state import State
from services.llm import gemini_llm


def validate_plan_evidence_refs(
    plan: Plan,
    evidence: list[ResearchEvidence],
) -> None:
    available_evidence_ids = {item.id for item in evidence}

    for task in plan.tasks:
        if not task.requires_research:
            if task.evidence_refs:
                raise ValueError(
                    "Task "
                    f"{task.id} does not require research but "
                    f"has evidence_refs: {task.evidence_refs}"
                )

            continue

        seen_refs: set[int] = set()

        for evidence_id in task.evidence_refs:
            if evidence_id in seen_refs:
                raise ValueError(
                    f"Task {task.id} has duplicate evidence reference: {evidence_id}"
                )

            seen_refs.add(evidence_id)

            if evidence_id not in available_evidence_ids:
                raise ValueError(
                    f"Task {task.id} references unknown evidence ID: {evidence_id}"
                )


def _sort_planner_evidence(
    evidence: list[ResearchEvidence],
) -> list[ResearchEvidence]:
    return sorted(
        evidence,
        key=lambda item: (
            -item.quality_score,
            -item.authority_score,
            -item.confidence_score,
            item.id,
        ),
    )


def orchestrator_node(
    state: State,
) -> dict:
    planner = gemini_llm.with_structured_output(Plan)

    evidence = state.get(
        "evidence",
        [],
    )

    sorted_evidence = _sort_planner_evidence(
        evidence,
    )

    planner_evidence = [
        {
            "id": item.id,
            "claim": item.claim,
            "source_type": item.source_type,
            "authority_score": item.authority_score,
            "quality_score": item.quality_score,
            "confidence_score": item.confidence_score,
        }
        for item in sorted_evidence
    ]

    plan = planner.invoke(
        [
            SystemMessage(
                content=PLANNER_SYSTEM,
            ),
            HumanMessage(
                content=(
                    f"Topic: {state['topic']}\n\n"
                    f"Research brief:\n"
                    f"{state.get('research_brief', '')}\n\n"
                    f"Research evidence:\n"
                    f"{planner_evidence}"
                )
            ),
        ]
    )

    validate_plan_evidence_refs(
        plan,
        evidence,
    )

    return {
        "plan": plan,
    }
