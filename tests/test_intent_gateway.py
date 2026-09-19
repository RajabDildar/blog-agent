from unittest.mock import MagicMock, patch

import pytest
from langgraph.checkpoint.memory import MemorySaver

from blog_agent.graph.main_graph import build_graph
from blog_agent.nodes.intent_gateway import intent_gateway_node
from blog_agent.schemas.models import IntentAnalysis, RouterDecision
from blog_agent.schemas.state import State
from blog_agent.services.run_diagnostics import RunDiagnostics


def test_intent_gateway_deterministic_empty_rejected():
    state: State = {
        "run_id": "test-empty",
        "original_input": "   \n\t  ",
        "topic": "",
        "intent_status": "pending",
        "intent_category": "",
        "intent_message": "",
        "clarification_question": "",
        "clarification_options": [],
        "clarification_rounds": 0,
        "clarification_response": "",
        "proposed_topic": "",
    }
    with patch("blog_agent.nodes.intent_gateway.analyze_intent") as mock_analyze:
        result = intent_gateway_node(state)
        mock_analyze.assert_not_called()

    assert result["intent_status"] == "invalid"
    assert "cannot be empty" in result["intent_message"]
    assert result["topic"] == ""


def test_intent_gateway_deterministic_oversized_rejected():
    oversized = "a" * 1005
    state: State = {
        "run_id": "test-oversized",
        "original_input": oversized,
        "topic": "",
        "intent_status": "pending",
        "intent_category": "",
        "intent_message": "",
        "clarification_question": "",
        "clarification_options": [],
        "clarification_rounds": 0,
        "clarification_response": "",
        "proposed_topic": "",
    }
    with patch("blog_agent.nodes.intent_gateway.analyze_intent") as mock_analyze:
        result = intent_gateway_node(state)
        mock_analyze.assert_not_called()

    assert result["intent_status"] == "invalid"
    assert "exceeds maximum allowed length" in result["intent_message"]


def test_intent_gateway_accepted_clear_topic():
    state: State = {
        "run_id": "test-clear",
        "original_input": "How Kafka ensures exactly-once semantics",
        "topic": "",
        "intent_status": "pending",
        "intent_category": "",
        "intent_message": "",
        "clarification_question": "",
        "clarification_options": [],
        "clarification_rounds": 0,
        "clarification_response": "",
        "proposed_topic": "",
    }
    mock_analysis = IntentAnalysis(
        outcome="accepted",
        normalized_topic="Exactly-Once Semantics in Apache Kafka",
    )
    with patch(
        "blog_agent.nodes.intent_gateway.analyze_intent",
        return_value=mock_analysis,
    ):
        result = intent_gateway_node(state)

    assert result["intent_status"] == "safe"
    assert result["topic"] == "Exactly-Once Semantics in Apache Kafka"


def test_graph_intent_gateway_routes_to_router_with_finalized_topic():
    saver = MemorySaver()

    run_id = "test-route-to-router"
    config = {"configurable": {"thread_id": run_id}}
    diagnostics = RunDiagnostics(run_id=run_id, topic="")
    context = {"diagnostics": diagnostics}

    mock_intent = IntentAnalysis(
        outcome="accepted",
        normalized_topic="Deep Dive into Redis Clustering",
    )

    router_called_with_topic = []

    def mock_router(state: State):
        router_called_with_topic.append(state["topic"])
        raise StopIteration("router_reached")

    with patch(
        "blog_agent.nodes.intent_gateway.analyze_intent",
        return_value=mock_intent,
    ), patch(
        "blog_agent.graph.main_graph.router_node",
        side_effect=mock_router,
    ):
        app = build_graph(saver)
        initial_state = {
            "run_id": run_id,
            "original_input": "redis clustering overview",
            "topic": "",
            "intent_status": "pending",
            "intent_category": "",
            "intent_message": "",
            "clarification_question": "",
            "clarification_options": [],
            "clarification_rounds": 0,
            "clarification_response": "",
            "proposed_topic": "",
            "mode": "",
            "needs_research": False,
            "queries": [],
            "research_focus": [],
            "evidence": [],
            "research_brief": "",
            "plan": None,
            "sections": {},
            "merged_md": "",
            "citation_issues": [],
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
        }

        # We only run until router
        try:
            app.invoke(initial_state, config, context=context)
        except Exception:
            # Downstream may raise because plan.tasks is empty, which is fine
            pass

    assert len(router_called_with_topic) == 1
    # Router must see finalized topic, NOT the raw original_input
    assert router_called_with_topic[0] == "Deep Dive into Redis Clustering"


def test_graph_intent_gateway_blocked_never_calls_router():
    saver = MemorySaver()

    run_id = "test-blocked-graph"
    config = {"configurable": {"thread_id": run_id}}
    diagnostics = RunDiagnostics(run_id=run_id, topic="")
    context = {"diagnostics": diagnostics}

    mock_blocked = IntentAnalysis(
        outcome="blocked",
        block_category="cyber_abuse",
        user_message="Harmful request blocked.",
    )

    router_mock = MagicMock()

    with patch(
        "blog_agent.nodes.intent_gateway.analyze_intent",
        return_value=mock_blocked,
    ), patch(
        "blog_agent.graph.main_graph.router_node",
        router_mock,
    ):
        app = build_graph(saver)
        initial_state = {
            "run_id": run_id,
            "original_input": "how to hack an account",
            "topic": "",
            "intent_status": "pending",
            "intent_category": "",
            "intent_message": "",
            "clarification_question": "",
            "clarification_options": [],
            "clarification_rounds": 0,
            "clarification_response": "",
            "proposed_topic": "",
            "mode": "",
            "needs_research": False,
            "queries": [],
            "research_focus": [],
            "evidence": [],
            "research_brief": "",
            "plan": None,
            "sections": {},
            "merged_md": "",
            "citation_issues": [],
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
        }

        result = app.invoke(initial_state, config, context=context)

    router_mock.assert_not_called()
    assert result["intent_status"] == "blocked"
    assert result["intent_category"] == "cyber_abuse"
    assert result["intent_message"] == "Harmful request blocked."
