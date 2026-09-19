import pytest

from blog_agent.graph.main_graph import (
    citation_release_gate_failure_node,
    route_after_article_validation,
    route_after_citation_verifier,
    route_after_editor,
)
from blog_agent.schemas.models import EditorialIssue, EditorialReview, Plan, Task


def make_task(task_id: int) -> Task:
    return Task(
        id=task_id,
        title=f"Task {task_id}",
        goal=f"Goal for task {task_id}",
        bullets=["b1", "b2", "b3"],
        target_words=200,
        requires_research=True,
        evidence_refs=[task_id],
    )


def test_route_after_article_validation_routes_to_citation_verifier_on_pass():
    state = {"article_validation_passed": True, "article_repair_count": 0}
    assert route_after_article_validation(state) == "citation_verifier"


def test_route_after_article_validation_routes_to_repair_on_failure():
    state = {"article_validation_passed": False, "article_repair_count": 0}
    assert route_after_article_validation(state) == "repair"


def test_route_after_article_validation_routes_to_failure_node_when_repairs_exhausted():
    state = {"article_validation_passed": False, "article_repair_count": 3}
    assert route_after_article_validation(state) == "article_validation_failure"


def test_route_after_citation_verifier_routes_to_editor_on_first_pass():
    state = {"revision_count": 0, "citation_issues": []}
    assert route_after_citation_verifier(state) == "editor"


def test_route_after_citation_verifier_blocks_publication_if_high_severity_issues_remain():
    state = {
        "revision_count": 1,
        "citation_issues": [
            EditorialIssue(
                task_id=1,
                category="citation",
                severity="high",
                problem="Missing inline citation link for required task.",
                correction="Add citation.",
            )
        ],
    }
    assert route_after_citation_verifier(state) == "citation_release_gate_failure"


def test_route_after_citation_verifier_proceeds_to_image_planner_if_no_high_severity_issues():
    state = {
        "revision_count": 1,
        "citation_issues": [
            EditorialIssue(
                task_id=1,
                category="citation",
                severity="medium",
                problem="Low authority source warning.",
                correction="Consider primary source.",
            )
        ],
    }
    assert route_after_citation_verifier(state) == "image_planner"


def test_route_after_editor_routes_approved_article_to_image_planner():
    review = EditorialReview(
        approved=True,
        overall_score=9,
        issues=[],
        sections_to_revise=[],
    )
    state = {"editorial_review": review}
    assert route_after_editor(state) == "image_planner"


def test_route_after_editor_raises_error_if_approved_false_but_no_actionable_issues():
    plan = Plan(
        blog_title="Test",
        thesis="Thesis",
        opening_angle="Angle",
        reader_promise="Promise",
        audience="Audience",
        tone="Tone",
        tasks=[make_task(1)],
    )
    review = EditorialReview(
        approved=False,
        overall_score=6,
        issues=[],
        sections_to_revise=[],
    )
    state = {"editorial_review": review, "plan": plan}

    with pytest.raises(
        ValueError,
        match="approved=False but no actionable section issues remain",
    ):
        route_after_editor(state)


def test_citation_release_gate_failure_node_raises_runtime_error():
    state = {
        "citation_issues": [
            EditorialIssue(
                task_id=1,
                category="citation",
                severity="high",
                problem="Task 1 missing citation",
                correction="Add link",
            ),
            EditorialIssue(
                task_id=None,
                category="citation",
                severity="high",
                problem="Sources section contains unsupported URL",
                correction="Fix Sources",
            ),
        ]
    }

    with pytest.raises(
        RuntimeError,
        match="Article publication blocked by citation release gate",
    ) as exc_info:
        citation_release_gate_failure_node(state)

    err_msg = str(exc_info.value)
    assert "Task 1 missing citation" in err_msg
    assert "Sources section contains unsupported URL" in err_msg
