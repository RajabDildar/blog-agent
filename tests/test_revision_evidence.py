import pytest

from graph.main_graph import route_after_editor
from schemas.models import (
    EditorialIssue,
    EditorialReview,
    Plan,
    ResearchEvidence,
    SectionOutput,
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
        blog_title="Revision evidence test",
        thesis="Test task-scoped revision evidence routing.",
        opening_angle="Start with the problem.",
        reader_promise="Explain how revision evidence is scoped.",
        audience="Technical readers",
        tone="Clear",
        tasks=list(tasks),
    )


def make_editorial_review(
    task_id: int,
) -> EditorialReview:
    return EditorialReview(
        approved=False,
        overall_score=5,
        issues=[
            EditorialIssue(
                task_id=task_id,
                category="citation",
                severity="high",
                problem="Section cites an unsupported source.",
                correction="Use only evidence assigned to this task.",
            )
        ],
        sections_to_revise=[task_id],
    )


def make_state(
    *,
    plan: Plan,
    review: EditorialReview,
    sections: dict[int, SectionOutput],
    evidence: list[ResearchEvidence],
) -> dict:
    return {
        "plan": plan,
        "topic": "Revision evidence",
        "mode": "hybrid",
        "evidence": evidence,
        "sections": sections,
        "editorial_review": review,
    }


def test_revision_send_targets_revision_node() -> None:
    plan = make_plan(
        make_task(
            task_id=1,
            requires_research=True,
            evidence_refs=[3, 1, 7],
        ),
    )

    state = make_state(
        plan=plan,
        review=make_editorial_review(task_id=1),
        sections={
            1: SectionOutput(body_markdown="## Task 1\n\nNeeds revision."),
        },
        evidence=[
            make_evidence(1),
            make_evidence(2),
            make_evidence(3),
            make_evidence(4),
            make_evidence(5),
            make_evidence(6),
            make_evidence(7),
        ],
    )

    sends = route_after_editor(state)

    assert len(sends) == 1
    assert sends[0].node == "revision"
    assert sends[0].arg["task"]["id"] == 1


def test_revision_send_includes_only_selected_task_evidence_in_ref_order() -> None:
    plan = make_plan(
        make_task(
            task_id=1,
            requires_research=True,
            evidence_refs=[3, 1, 7],
        ),
        make_task(
            task_id=2,
            requires_research=True,
            evidence_refs=[5],
        ),
    )

    state = make_state(
        plan=plan,
        review=make_editorial_review(task_id=1),
        sections={
            1: SectionOutput(body_markdown="## Task 1\n\nNeeds revision."),
        },
        evidence=[
            make_evidence(1),
            make_evidence(2),
            make_evidence(3),
            make_evidence(4),
            make_evidence(5),
            make_evidence(6),
            make_evidence(7),
        ],
    )

    sends = route_after_editor(state)

    payload = sends[0].arg

    # Only task 1's referenced evidence, in task 1's reference order, and
    # never the unreferenced global evidence (2, 4, 5, 6) or task 2's (5).
    assert [item["id"] for item in payload["evidence"]] == [3, 1, 7]


def test_revision_send_for_non_research_task_has_empty_evidence() -> None:
    plan = make_plan(
        make_task(
            task_id=1,
            requires_research=False,
            evidence_refs=[],
        ),
    )

    state = make_state(
        plan=plan,
        review=make_editorial_review(task_id=1),
        sections={
            1: SectionOutput(body_markdown="## Task 1\n\nNeeds revision."),
        },
        evidence=[
            make_evidence(1),
            make_evidence(2),
        ],
    )

    sends = route_after_editor(state)

    assert sends[0].arg["evidence"] == []


def test_revision_sends_respect_sections_to_revise() -> None:
    plan = make_plan(
        make_task(
            task_id=1,
            requires_research=True,
            evidence_refs=[1],
        ),
        make_task(
            task_id=2,
            requires_research=True,
            evidence_refs=[2],
        ),
    )

    review = make_editorial_review(task_id=1)
    review.issues.append(
        EditorialIssue(
            task_id=2,
            category="style",
            severity="medium",
            problem="Repetitive wording.",
            correction="Rewrite for variety.",
        )
    )
    review.sections_to_revise = [1, 2]

    state = make_state(
        plan=plan,
        review=review,
        sections={
            1: SectionOutput(body_markdown="## Task 1\n\nNeeds revision."),
            2: SectionOutput(body_markdown="## Task 2\n\nNeeds revision."),
        },
        evidence=[
            make_evidence(1),
            make_evidence(2),
        ],
    )

    sends = route_after_editor(state)

    # Two tasks requested, so two revision Sends. Content is deterministic;
    # sort by task id because cross-task iteration order is not guaranteed here.
    payloads_by_task = {
        send.arg["task"]["id"]: send.arg for send in sends
    }

    assert set(payloads_by_task) == {1, 2}
    assert [item["id"] for item in payloads_by_task[1]["evidence"]] == [1]
    assert [item["id"] for item in payloads_by_task[2]["evidence"]] == [2]


def test_revision_send_rejects_unknown_evidence_ref_deterministically() -> None:
    plan = make_plan(
        make_task(
            task_id=1,
            requires_research=True,
            evidence_refs=[99],
        ),
    )

    state = make_state(
        plan=plan,
        review=make_editorial_review(task_id=1),
        sections={
            1: SectionOutput(body_markdown="## Task 1\n\nNeeds revision."),
        },
        evidence=[
            make_evidence(1),
        ],
    )

    with pytest.raises(
        ValueError,
        match=("Task 1 references unknown evidence ID: 99"),
    ):
        route_after_editor(state)
