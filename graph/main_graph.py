from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from config.settings import (
    groq_retry_policy,
    MAX_EDITORIAL_REVISIONS,
    MAX_ARTICLE_REPAIRS,
)
from nodes.editor import editor_node
from nodes.image_generator import generate_images_node
from nodes.image_planner import image_planner_node
from nodes.merger import merge_content
from nodes.orchestrator import orchestrator_node
from nodes.research import research_node
from nodes.revision import revision_node
from nodes.router import route_next, router_node
from nodes.validator import validator_node
from nodes.worker import worker_node
from nodes.repair import repair_node
from nodes.save import save_node
from schemas.state import State
from nodes.article_validator import (
    article_validator_node,
)


def fanout(state: State):
    plan = state["plan"]

    if plan is None:
        raise ValueError("Plan missing")

    sends = []

    for index, task in enumerate(plan.tasks):
        previous_summary = ""
        next_goal = ""

        if index > 0:
            previous = plan.tasks[index - 1]

            previous_summary = f"{previous.title}: {previous.goal}"

        if index < len(plan.tasks) - 1:
            next_task = plan.tasks[index + 1]

            next_goal = f"{next_task.title}: {next_task.goal}"

        sends.append(
            Send(
                "worker",
                {
                    "task": task.model_dump(),
                    "topic": state["topic"],
                    "mode": state["mode"],
                    "plan": plan.model_dump(),
                    "evidence": [
                        e.model_dump()
                        for e in state.get(
                            "evidence",
                            [],
                        )
                    ],
                    "previous_summary": previous_summary,
                    "next_goal": next_goal,
                },
            )
        )

    return sends


def route_after_merge(state: State):
    if state["revision_count"] >= MAX_EDITORIAL_REVISIONS:
        return "article_validator"

    return "editor"


def route_after_editor(
    state: State,
):
    review = state["editorial_review"]

    if review is None:
        raise ValueError("Editorial review missing.")

    # Approved article goes to structural validation.
    if review.approved:
        return "article_validator"

    issue_map: dict[int, list[dict]] = {}

    for issue in review.issues:
        if issue.task_id is None:
            continue

        issue_map.setdefault(
            issue.task_id,
            [],
        ).append(issue.model_dump())

    requested_ids = {
        task_id for task_id in review.sections_to_revise if task_id in issue_map
    }

    if not requested_ids:
        return "article_validator"

    sends = []

    if state["plan"] is None:
        raise ValueError("Plan missing during revision routing.")

    for task_id in requested_ids:
        section = state["sections"].get(task_id)

        if section is None:
            raise ValueError(f"Missing section {task_id} requested for revision.")

        task = next(
            (task for task in state["plan"].tasks if task.id == task_id),
            None,
        )

        if task is None:
            raise ValueError(f"Unknown task ID {task_id}.")

        sends.append(
            Send(
                "revision",
                {
                    "task": task.model_dump(),
                    "section": section.body_markdown,
                    "issues": issue_map[task_id],
                },
            )
        )

    return sends


def route_after_article_validation(
    state: State,
):
    if state["article_validation_passed"]:
        return "image_planner"

    if state["article_repair_count"] < MAX_ARTICLE_REPAIRS:
        return "repair"

    return "article_validation_failure"


def route_after_final_validation(
    state: State,
):
    if state["final_validation_passed"]:
        return "save"

    return "final_validation_failure"


def mark_revision(
    state: State,
) -> dict:
    return {"revision_count": (state["revision_count"] + 1)}


def article_validation_failure_node(
    state: State,
) -> dict:
    errors = state.get(
        "article_validation_errors",
        [],
    )

    raise RuntimeError(
        "Article validation failed after repair:\n"
        + "\n".join(f"- {error}" for error in errors)
    )


def final_validation_failure_node(
    state: State,
) -> dict:
    errors = state.get(
        "final_validation_errors",
        [],
    )

    raise RuntimeError(
        "Final artifact validation failed:\n"
        + "\n".join(f"- {error}" for error in errors)
    )


# Building graph


def build_graph():
    builder = StateGraph(State)

    # ----------------------- Nodes ---------------------------

    builder.add_node(
        "router",
        router_node,
    )

    builder.add_node(
        "research",
        research_node,
    )

    builder.add_node(
        "orchestrator",
        orchestrator_node,
    )

    builder.add_node(
        "worker",
        worker_node,
        retry_policy=groq_retry_policy,
    )

    builder.add_node(
        "merge",
        merge_content,
    )

    builder.add_node(
        "editor",
        editor_node,
    )

    builder.add_node(
        "revision",
        revision_node,
        retry_policy=groq_retry_policy,
    )

    builder.add_node(
        "mark_revision",
        mark_revision,
    )

    builder.add_node(
        "article_validator",
        article_validator_node,
    )

    builder.add_node(
        "repair",
        repair_node,
        retry_policy=groq_retry_policy,
    )

    builder.add_node(
        "article_validation_failure",
        article_validation_failure_node,
    )

    builder.add_node(
        "image_planner",
        image_planner_node,
    )

    builder.add_node(
        "image_generator",
        generate_images_node,
    )

    builder.add_node(
        "validator",
        validator_node,
    )

    builder.add_node(
        "final_validation_failure",
        final_validation_failure_node,
    )

    builder.add_node(
        "save",
        save_node,
    )

    # ----------------------- Edges ---------------------------

    builder.add_edge(
        START,
        "router",
    )

    builder.add_conditional_edges(
        "router",
        route_next,
        {
            "research": "research",
            "orchestrator": "orchestrator",
        },
    )

    builder.add_edge(
        "research",
        "orchestrator",
    )

    builder.add_conditional_edges(
        "orchestrator",
        fanout,
        ["worker"],
    )

    builder.add_edge(
        "worker",
        "merge",
    )

    builder.add_conditional_edges(
        "merge",
        route_after_merge,
        {
            "editor": "editor",
            "article_validator": "article_validator",
        },
    )

    builder.add_conditional_edges(
        "editor",
        route_after_editor,
    )

    builder.add_edge(
        "revision",
        "mark_revision",
    )

    builder.add_edge(
        "mark_revision",
        "merge",
    )

    builder.add_conditional_edges(
        "article_validator",
        route_after_article_validation,
        {
            "image_planner": "image_planner",
            "repair": "repair",
            "article_validation_failure": ("article_validation_failure"),
        },
    )

    builder.add_edge(
        "repair",
        "article_validator",
    )

    builder.add_edge(
        "article_validation_failure",
        END,
    )

    builder.add_edge(
        "image_planner",
        "image_generator",
    )

    builder.add_edge(
        "image_generator",
        "validator",
    )

    builder.add_conditional_edges(
        "validator",
        route_after_final_validation,
        {
            "save": "save",
            "final_validation_failure": ("final_validation_failure"),
        },
    )

    builder.add_edge(
        "save",
        END,
    )

    builder.add_edge(
        "final_validation_failure",
        END,
    )

    return builder.compile()


app = build_graph()


def run(topic: str):
    return app.invoke(
        {
            "topic": topic,
            "mode": "",
            "needs_research": False,
            "queries": [],
            "research_focus": [],
            "evidence": [],
            "research_brief": "",
            "plan": None,
            "sections": {},
            "merged_md": "",
            "editorial_review": None,
            "revision_count": 0,
            "image_specs": [],
            "image_results": [],
            "final": "",
            "article_validation_errors": [],
            "article_validation_passed": False,
            "article_repair_count": 0,
            "final_validation_errors": [],
            "final_validation_passed": False,
            "saved_path": "",
        },
        {
            "recursion_limit": 50,
        },
    )
