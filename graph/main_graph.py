from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from config.settings import groq_retry_policy
from nodes.orchestrator import orchestrator_node
from nodes.research import research_node
from nodes.router import route_next, router_node
from nodes.worker import worker_node
from graph.reducer_graph import reducer_subgraph
from schemas.state import State


def fanout(state: State):
    return [
        Send(
            "worker",
            {
                "task": task.model_dump(),
                "topic": state["topic"],
                "mode": state["mode"],
                "plan": state["plan"].model_dump(),
                "evidence": [e.model_dump() for e in state.get("evidence", [])],
            },
        )
        for task in state["plan"].tasks
    ]


g = StateGraph(State)

g.add_node(
    "router",
    router_node,
)

g.add_node(
    "research",
    research_node,
)

g.add_node(
    "orchestrator",
    orchestrator_node,
)

g.add_node(
    "worker",
    worker_node,
    retry=groq_retry_policy,
)

g.add_node(
    "reducer",
    reducer_subgraph,
)


g.add_edge(
    START,
    "router",
)

g.add_conditional_edges(
    "router",
    route_next,
    {
        "research": "research",
        "orchestrator": "orchestrator",
    },
)

g.add_edge(
    "research",
    "orchestrator",
)

g.add_conditional_edges(
    "orchestrator",
    fanout,
    ["worker"],
)

g.add_edge(
    "worker",
    "reducer",
)

g.add_edge(
    "reducer",
    END,
)


app = g.compile()


def run(topic: str):
    out = app.invoke(
        {
            "topic": topic,
            "mode": "",
            "needs_research": False,
            "queries": [],
            "evidence": [],
            "plan": None,
            "sections": [],
            "merged_md": "",
            "md_with_placeholders": "",
            "image_specs": [],
            "final": "",
        }
    )

    return out
