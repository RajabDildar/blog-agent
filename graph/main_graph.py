from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from config.settings import groq_retry_policy
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
from schemas.state import State


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


def route_after_editor(state: State):
    review = state["editorial_review"]

    if review is None:
        raise ValueError("Editorial review missing")

    # Article passed review.
    if review.approved:
        return "image_planner"

    # Only allow one revision cycle.
    if state["revision_count"] >= 1:
        return "image_planner"

    # Nothing specific to revise.
    if not review.sections_to_revise:
        return "image_planner"

    requested_ids = set(review.sections_to_revise)

    issue_map: dict[int, list[dict]] = {}

    for issue in review.issues:
        if issue.task_id in requested_ids:
            issue_map.setdefault(
                issue.task_id,
                [],
            ).append(issue.model_dump())

    sends = []

    for task_id in requested_ids:
        section = state["sections"].get(task_id)

        if section is None:
            continue

        task = next(task for task in state["plan"].tasks if task.id == task_id)

        sends.append(
            Send(
                "revision",
                {
                    "task": task.model_dump(),
                    "section": section.markdown,
                    "issues": issue_map.get(
                        task_id,
                        [],
                    ),
                },
            )
        )

    return sends


def mark_revision(
    state: State,
) -> dict:
    return {"revision_count": (state["revision_count"] + 1)}


builder = StateGraph(State)

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
    retry=groq_retry_policy,
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
    retry=groq_retry_policy,
)

builder.add_node(
    "mark_revision",
    mark_revision,
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

builder.add_edge(
    "merge",
    "editor",
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

builder.add_edge(
    "image_planner",
    "image_generator",
)

builder.add_edge(
    "image_generator",
    "validator",
)

builder.add_edge(
    "validator",
    END,
)


app = builder.compile()


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
            "final": "",
        },
        {
            "recursion_limit": 50,
        },
    )
