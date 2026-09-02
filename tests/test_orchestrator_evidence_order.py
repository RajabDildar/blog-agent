from graph.main_graph import fanout
from nodes.orchestrator import _sort_planner_evidence
from schemas.models import (
    Plan,
    ResearchEvidence,
    Task,
)


def make_task(
    *,
    task_id: int,
    requires_research: bool,
    evidence_refs: list[int],
) -> Task:
    return Task(
        id=task_id,
        title=f"Task {task_id}",
        goal="Explain the topic clearly.",
        bullets=[
            "Explain the first point.",
            "Explain the second point.",
            "Explain the third point.",
        ],
        target_words=300,
        requires_research=requires_research,
        evidence_refs=evidence_refs,
    )


def make_evidence(
    evidence_id: int,
) -> ResearchEvidence:
    return ResearchEvidence(
        id=evidence_id,
        claim=f"Claim {evidence_id}.",
        source_title=f"Source {evidence_id}",
        url=f"https://example.com/{evidence_id}",
    )


def make_plan(
    *tasks: Task,
) -> Plan:
    return Plan(
        blog_title="Evidence order test",
        thesis="Test deterministic task and evidence order.",
        opening_angle="Start with the problem.",
        reader_promise="Explain how order is preserved.",
        audience="Technical readers",
        tone="Clear",
        tasks=list(tasks),
    )


def make_state(
    *,
    plan: Plan,
    evidence: list[ResearchEvidence],
) -> dict:
    return {
        "plan": plan,
        "topic": "Evidence order",
        "mode": "hybrid",
        "evidence": evidence,
    }


def test_planner_evidence_is_sorted_by_quality_then_authority():
    evidence = [
        ResearchEvidence(
            id=1,
            claim="weak evidence",
            source_title="weak",
            url="https://example.com",
            quality_score=0.4,
            authority_score=0.4,
            confidence_score=0.4,
        ),
        ResearchEvidence(
            id=2,
            claim="strong evidence",
            source_title="strong",
            url="https://docs.python.org",
            quality_score=0.9,
            authority_score=0.95,
            confidence_score=0.9,
        ),
    ]

    sorted_evidence = _sort_planner_evidence(
        evidence,
    )

    assert sorted_evidence[0].id == 2
    assert sorted_evidence[1].id == 1


def test_fanout_emits_sends_in_plan_task_order() -> None:
    plan = make_plan(
        make_task(
            task_id=3,
            requires_research=True,
            evidence_refs=[1],
        ),
        make_task(
            task_id=1,
            requires_research=True,
            evidence_refs=[2],
        ),
    )

    sends = fanout(
        make_state(
            plan=plan,
            evidence=[
                make_evidence(1),
                make_evidence(2),
            ],
        )
    )

    assert [payload["task"]["id"] for payload in (send.arg for send in sends)] == [
        3,
        1,
    ]


def test_fanout_preserves_evidence_ref_order_per_task() -> None:
    plan = make_plan(
        make_task(
            task_id=3,
            requires_research=True,
            evidence_refs=[7, 2, 4],
        ),
        make_task(
            task_id=1,
            requires_research=True,
            evidence_refs=[4],
        ),
    )

    sends = fanout(
        make_state(
            plan=plan,
            evidence=[
                make_evidence(2),
                make_evidence(4),
                make_evidence(7),
            ],
        )
    )

    first_payload = sends[0].arg
    second_payload = sends[1].arg

    assert [item["id"] for item in first_payload["evidence"]] == [7, 2, 4]
    assert [item["id"] for item in second_payload["evidence"]] == [4]
