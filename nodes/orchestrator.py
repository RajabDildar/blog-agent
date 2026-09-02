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


RESEARCH_MODES: frozenset[str] = frozenset({
    "hybrid",
    "open_book",
})

# The application owns the final `## Sources` section, so no planned task may
# claim that title (roadmap Step 2 / Step 3 reserved-title invariant).
RESERVED_TASK_TITLES: frozenset[str] = frozenset({
    "Sources",
})

RESERVED_TASK_TITLE_NORMALIZED: frozenset[str] = frozenset(
    title.casefold() for title in RESERVED_TASK_TITLES
)


class EvidenceInsufficiencyError(ValueError):
    """A research-required run produced zero accepted evidence."""


def research_is_required(
    mode: str,
    needs_research: bool,
) -> bool:
    return needs_research or mode in RESEARCH_MODES


def validate_plan_contract(
    plan: Plan,
    evidence: list[ResearchEvidence],
) -> None:
    """
    Enforce the complete plan and task evidence ownership contract.

    Phase 8 remediation Step 2. Checks run in a deterministic order and raise
    on the first violation so failures are stable and reproducible:

    1. plan has at least one task;
    2. task IDs are unique;
    3. task titles are unique after trimming/case normalization;
    4. no task claims the reserved application-owned `Sources` title;
    5. citations imply research;
    6. a research/citation task references at least one evidence ID;
    7. a non-research task references no evidence;
    8. evidence references are unique within a task and exist in the run evidence.
    """
    if not plan.tasks:
        raise ValueError("Plan must contain at least one task.")

    seen_task_ids: set[int] = set()
    seen_task_titles: set[str] = set()

    for task in plan.tasks:
        if task.id in seen_task_ids:
            raise ValueError(
                f"Plan contains duplicate task ID: {task.id}"
            )

        seen_task_ids.add(task.id)

        normalized_title = task.title.strip().casefold()

        if normalized_title in seen_task_titles:
            raise ValueError(
                f"Plan contains duplicate task title: {normalized_title!r}"
            )

        seen_task_titles.add(normalized_title)

        if normalized_title in RESERVED_TASK_TITLE_NORMALIZED:
            raise ValueError(
                f"Task title {task.title!r} is reserved for the "
                "application-owned Sources section."
            )

    available_evidence_ids = {item.id for item in evidence}

    for task in plan.tasks:
        if task.requires_citations and not task.requires_research:
            raise ValueError(
                f"Task {task.id} requires citations but not research."
            )

        if task.requires_research and not task.evidence_refs:
            raise ValueError(
                f"Task {task.id} requires research but has no evidence references."
            )

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
    evidence = state.get(
        "evidence",
        [],
    )

    if (
        research_is_required(
            mode=state.get(
                "mode",
                "",
            ),
            needs_research=state.get(
                "needs_research",
                False,
            ),
        )
        and not evidence
    ):
        raise EvidenceInsufficiencyError(
            "Research is required for this topic but zero evidence items "
            "were accepted; refusing to generate claims without evidence."
        )

    planner = gemini_llm.with_structured_output(Plan)

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

    validate_plan_contract(
        plan,
        evidence,
    )

    return {
        "plan": plan,
    }
