import pytest

from graph.main_graph import fanout
from nodes.orchestrator import (
    validate_plan_evidence_refs,
)
from schemas.models import (
    Plan,
    ResearchEvidence,
    ResearchPack,
    Task,
)


def make_task(
    *,
    task_id: int = 1,
    requires_research: bool = False,
    evidence_refs: list[int] | None = None,
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
        evidence_refs=([] if evidence_refs is None else evidence_refs),
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
        blog_title="Evidence mapping test",
        thesis="Test explicit evidence ownership.",
        opening_angle="Start with the problem.",
        reader_promise="Explain how evidence is assigned.",
        audience="Technical readers",
        tone="Clear",
        tasks=list(tasks),
    )


def test_task_evidence_refs_default_to_empty_list() -> None:
    task = Task(
        id=1,
        title="Introduction",
        goal="Introduce the topic.",
        bullets=[
            "Explain the problem.",
            "Define the scope.",
            "Set reader expectations.",
        ],
        target_words=200,
    )

    assert task.evidence_refs == []


def test_task_preserves_valid_evidence_refs() -> None:
    task = make_task(
        requires_research=True,
        evidence_refs=[3, 1, 7],
    )

    assert task.evidence_refs == [3, 1, 7]


def test_research_evidence_has_stable_integer_id() -> None:
    evidence = ResearchEvidence(
        id=1,
        claim="Example claim.",
        source_title="Example source",
        url="https://example.com",
    )

    assert evidence.id == 1


def test_research_pack_preserves_sequential_evidence_ids() -> None:
    pack = ResearchPack(
        evidence=[
            make_evidence(1),
            make_evidence(2),
            make_evidence(3),
        ]
    )

    assert [item.id for item in pack.evidence] == [1, 2, 3]


def test_valid_evidence_refs_pass_validation() -> None:
    plan = make_plan(
        make_task(
            requires_research=True,
            evidence_refs=[2, 1],
        )
    )

    evidence = [
        make_evidence(1),
        make_evidence(2),
    ]

    validate_plan_evidence_refs(
        plan,
        evidence,
    )


def test_unknown_evidence_id_fails_deterministically() -> None:
    plan = make_plan(
        make_task(
            task_id=4,
            requires_research=True,
            evidence_refs=[99],
        )
    )

    with pytest.raises(
        ValueError,
        match=("Task 4 references unknown evidence ID: 99"),
    ):
        validate_plan_evidence_refs(
            plan,
            [make_evidence(1)],
        )


def test_duplicate_evidence_id_fails_deterministically() -> None:
    plan = make_plan(
        make_task(
            task_id=5,
            requires_research=True,
            evidence_refs=[2, 2],
        )
    )

    with pytest.raises(
        ValueError,
        match=("Task 5 has duplicate evidence reference: 2"),
    ):
        validate_plan_evidence_refs(
            plan,
            [
                make_evidence(1),
                make_evidence(2),
            ],
        )


def test_non_research_task_with_evidence_refs_fails() -> None:
    plan = make_plan(
        make_task(
            task_id=6,
            requires_research=False,
            evidence_refs=[1],
        )
    )

    with pytest.raises(
        ValueError,
        match=("Task 6 does not require research but has evidence_refs: \\[1\\]"),
    ):
        validate_plan_evidence_refs(
            plan,
            [make_evidence(1)],
        )


def test_non_research_task_with_empty_refs_passes() -> None:
    plan = make_plan(
        make_task(
            requires_research=False,
            evidence_refs=[],
        )
    )

    validate_plan_evidence_refs(
        plan,
        [make_evidence(1)],
    )


def test_overlapping_evidence_refs_are_valid_across_tasks() -> None:
    plan = make_plan(
        make_task(
            task_id=1,
            requires_research=True,
            evidence_refs=[1, 2],
        ),
        make_task(
            task_id=2,
            requires_research=True,
            evidence_refs=[2, 3],
        ),
    )

    validate_plan_evidence_refs(
        plan,
        [
            make_evidence(1),
            make_evidence(2),
            make_evidence(3),
        ],
    )


def make_state(
    *,
    plan: Plan,
    evidence: list[ResearchEvidence],
) -> dict:
    return {
        "plan": plan,
        "topic": "Evidence mapping",
        "mode": "hybrid",
        "evidence": evidence,
    }


def send_payload(send) -> dict:
    return send.arg


def test_fanout_sends_only_task_a_evidence() -> None:
    plan = make_plan(
        make_task(
            task_id=1,
            requires_research=True,
            evidence_refs=[1, 3],
        ),
        make_task(
            task_id=2,
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
                make_evidence(3),
            ],
        )
    )

    first_payload = send_payload(
        sends[0],
    )

    assert [item["id"] for item in first_payload["evidence"]] == [1, 3]


def test_fanout_sends_only_task_b_evidence() -> None:
    plan = make_plan(
        make_task(
            task_id=1,
            requires_research=True,
            evidence_refs=[1, 3],
        ),
        make_task(
            task_id=2,
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
                make_evidence(3),
            ],
        )
    )

    second_payload = send_payload(
        sends[1],
    )

    assert [item["id"] for item in second_payload["evidence"]] == [2]


def test_fanout_allows_evidence_to_overlap_between_tasks() -> None:
    plan = make_plan(
        make_task(
            task_id=1,
            requires_research=True,
            evidence_refs=[1, 2],
        ),
        make_task(
            task_id=2,
            requires_research=True,
            evidence_refs=[2, 3],
        ),
    )

    sends = fanout(
        make_state(
            plan=plan,
            evidence=[
                make_evidence(1),
                make_evidence(2),
                make_evidence(3),
            ],
        )
    )

    first_payload = send_payload(
        sends[0],
    )

    second_payload = send_payload(
        sends[1],
    )

    assert [item["id"] for item in first_payload["evidence"]] == [1, 2]

    assert [item["id"] for item in second_payload["evidence"]] == [2, 3]


def test_fanout_sends_empty_evidence_to_non_research_task() -> None:
    plan = make_plan(
        make_task(
            task_id=1,
            requires_research=False,
            evidence_refs=[],
        )
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

    payload = send_payload(
        sends[0],
    )

    assert payload["evidence"] == []


def test_fanout_preserves_task_evidence_ref_order() -> None:
    plan = make_plan(
        make_task(
            task_id=1,
            requires_research=True,
            evidence_refs=[3, 1, 2],
        )
    )

    sends = fanout(
        make_state(
            plan=plan,
            evidence=[
                make_evidence(1),
                make_evidence(2),
                make_evidence(3),
            ],
        )
    )

    payload = send_payload(
        sends[0],
    )

    assert [item["id"] for item in payload["evidence"]] == [3, 1, 2]


def test_fanout_rejects_unknown_evidence_id() -> None:
    plan = make_plan(
        make_task(
            task_id=7,
            requires_research=True,
            evidence_refs=[99],
        )
    )

    with pytest.raises(
        ValueError,
        match=("Task 7 references unknown evidence ID: 99"),
    ):
        fanout(
            make_state(
                plan=plan,
                evidence=[
                    make_evidence(1),
                ],
            )
        )


def test_fanout_rejects_duplicate_evidence_id() -> None:
    plan = make_plan(
        make_task(
            task_id=8,
            requires_research=True,
            evidence_refs=[1, 1],
        )
    )

    with pytest.raises(
        ValueError,
        match=("Task 8 has duplicate evidence reference: 1"),
    ):
        fanout(
            make_state(
                plan=plan,
                evidence=[
                    make_evidence(1),
                ],
            )
        )


def test_fanout_rejects_evidence_for_non_research_task() -> None:
    plan = make_plan(
        make_task(
            task_id=9,
            requires_research=False,
            evidence_refs=[1],
        )
    )

    with pytest.raises(
        ValueError,
        match=("Task 9 does not require research but has evidence_refs: \\[1\\]"),
    ):
        fanout(
            make_state(
                plan=plan,
                evidence=[
                    make_evidence(1),
                ],
            )
        )
