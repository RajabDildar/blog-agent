from schemas.state import State
from services.citation_verification import (
    verify_citations,
)


def citation_verifier_node(
    state: State,
) -> dict:
    plan = state["plan"]

    if plan is None:
        raise ValueError("Citation verifier: plan is missing.")

    issues = verify_citations(
        markdown=state["merged_md"],
        tasks=plan.tasks,
        evidence=state["evidence"],
    )

    return {
        "citation_issues": issues,
    }
