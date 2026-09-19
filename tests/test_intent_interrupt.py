from unittest.mock import MagicMock, patch

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from blog_agent.graph.main_graph import build_graph
from blog_agent.schemas.models import IntentAnalysis, IntentHumanResponse
from blog_agent.schemas.state import State
from blog_agent.services.run_diagnostics import RunDiagnostics


def test_vague_input_triggers_clarification_interrupt():
    saver = MemorySaver()
    app = build_graph(saver)

    run_id = "test-clarify-interrupt"
    config = {"configurable": {"thread_id": run_id}}
    diagnostics = RunDiagnostics(run_id=run_id, topic="")
    context = {"diagnostics": diagnostics}

    mock_analysis = IntentAnalysis(
        outcome="needs_clarification",
        clarification_question="What aspect of AI would you like to cover?",
        clarification_options=[
            "Modern AI architectures and LLMs",
            "AI agents and workflow automation",
            "Fine-tuning vs RAG for enterprise data",
        ],
    )

    with patch(
        "blog_agent.nodes.intent_gateway.analyze_intent",
        return_value=mock_analysis,
    ):
        initial_state = {
            "run_id": run_id,
            "original_input": "AI",
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

    # Graph should be interrupted
    state = app.get_state(config)
    assert len(state.tasks) > 0
    assert len(state.tasks[0].interrupts) == 1

    interrupt_val = state.tasks[0].interrupts[0].value
    assert interrupt_val["type"] == "clarification_required"
    assert interrupt_val["question"] == "What aspect of AI would you like to cover?"
    assert len(interrupt_val["options"]) == 3
    assert interrupt_val["allow_custom_input"] is True


def test_resume_with_selected_option_finalizes_topic():
    saver = MemorySaver()

    run_id = "test-resume-option"
    config = {"configurable": {"thread_id": run_id}}
    diagnostics = RunDiagnostics(run_id=run_id, topic="")
    context = {"diagnostics": diagnostics}

    first_analysis = IntentAnalysis(
        outcome="needs_clarification",
        clarification_question="What aspect of AI would you like to cover?",
        clarification_options=[
            "Modern AI architectures and LLMs",
            "AI agents and workflow automation",
            "Fine-tuning vs RAG for enterprise data",
        ],
    )
    second_analysis = IntentAnalysis(
        outcome="accepted",
        normalized_topic="Architectural Patterns for Autonomous AI Agents",
    )

    router_topics = []

    def mock_router(state: State):
        router_topics.append(state["topic"])
        raise StopIteration("router_reached")

    with patch(
        "blog_agent.nodes.intent_gateway.analyze_intent",
        side_effect=[first_analysis, second_analysis],
    ), patch(
        "blog_agent.graph.main_graph.router_node",
        side_effect=mock_router,
    ):
        app = build_graph(saver)
        initial_state = {
            "run_id": run_id,
            "original_input": "AI",
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

        # Step 1: initial run pauses
        app.invoke(initial_state, config, context=context)

        # Step 2: resume with chosen option
        human_resp = IntentHumanResponse(
            action="select_option",
            value="AI agents and workflow automation",
        )
        try:
            app.invoke(
                Command(resume=human_resp.model_dump()),
                config,
                context=context,
            )
        except Exception:
            pass

    assert len(router_topics) == 1
    assert router_topics[0] == "Architectural Patterns for Autonomous AI Agents"


def test_resume_with_custom_input_finalizes_topic():
    saver = MemorySaver()

    run_id = "test-resume-custom"
    config = {"configurable": {"thread_id": run_id}}
    diagnostics = RunDiagnostics(run_id=run_id, topic="")
    context = {"diagnostics": diagnostics}

    first_analysis = IntentAnalysis(
        outcome="needs_clarification",
        clarification_question="What aspect of database design?",
        clarification_options=[
            "Relational modeling",
            "NoSQL document stores",
            "Time-series optimization",
        ],
    )
    second_analysis = IntentAnalysis(
        outcome="accepted",
        normalized_topic="Implementing LSM Trees in Modern Storage Engines",
    )

    router_topics = []

    def mock_router(state: State):
        router_topics.append(state["topic"])
        raise StopIteration("router_reached")

    with patch(
        "blog_agent.nodes.intent_gateway.analyze_intent",
        side_effect=[first_analysis, second_analysis],
    ), patch(
        "blog_agent.graph.main_graph.router_node",
        side_effect=mock_router,
    ):
        app = build_graph(saver)
        initial_state = {
            "run_id": run_id,
            "original_input": "Databases",
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

        # Step 1: pause
        app.invoke(initial_state, config, context=context)

        # Step 2: resume with custom text
        human_resp = IntentHumanResponse(
            action="custom_input",
            value="How LSM trees work internally",
        )
        try:
            app.invoke(
                Command(resume=human_resp.model_dump()),
                config,
                context=context,
            )
        except Exception:
            pass

    assert len(router_topics) == 1
    assert router_topics[0] == "Implementing LSM Trees in Modern Storage Engines"


def test_second_vague_response_triggers_confirmation_proceed_and_cancel():
    saver = MemorySaver()
    app = build_graph(saver)

    run_id = "test-second-vague"
    config = {"configurable": {"thread_id": run_id}}
    diagnostics = RunDiagnostics(run_id=run_id, topic="")
    context = {"diagnostics": diagnostics}

    # First is vague -> needs_clarification
    first_analysis = IntentAnalysis(
        outcome="needs_clarification",
        clarification_question="What aspect of AI?",
        clarification_options=["Option A", "Option B", "Option C"],
    )
    # Second is still vague -> needs_clarification
    second_analysis = IntentAnalysis(
        outcome="needs_clarification",
        clarification_question="Still too broad. What specific area?",
        clarification_options=["Option D", "Option E", "Option F"],
    )

    with patch(
        "blog_agent.nodes.intent_gateway.analyze_intent",
        side_effect=[first_analysis, second_analysis],
    ), patch(
        "blog_agent.nodes.intent_gateway.generate_proposed_topic",
        return_value="The Evolution of Modern AI Systems in 2026",
    ):
        initial_state = {
            "run_id": run_id,
            "original_input": "AI",
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

        # Step 1: pause at clarification
        app.invoke(initial_state, config, context=context)

        # Step 2: resume with another vague custom input -> should pause at confirmation
        vague_human = IntentHumanResponse(
            action="custom_input",
            value="just AI generally",
        )
        app.invoke(
            Command(resume=vague_human.model_dump()),
            config,
            context=context,
        )

        state = app.get_state(config)
        assert len(state.tasks[0].interrupts) == 1
        conf_val = state.tasks[0].interrupts[0].value
        assert conf_val["type"] == "topic_confirmation_required"
        assert conf_val["proposed_topic"] == "The Evolution of Modern AI Systems in 2026"
        assert "proceed" in conf_val["actions"]
        assert "cancel" in conf_val["actions"]

        # Step 3a: test Cancel
        cancel_resp = IntentHumanResponse(action="cancel")
        cancel_result = app.invoke(
            Command(resume=cancel_resp.model_dump()),
            config,
            context=context,
        )
        assert cancel_result["intent_status"] == "cancelled"
        assert cancel_result["topic"] == ""


def test_sequential_interrupt_resumes_via_resume_function(tmp_path):
    from blog_agent.services.checkpointer import create_checkpointer
    handle = create_checkpointer(tmp_path / "checkpoints.sqlite")
    run_id = "test-sequential-resume-func"

    first_analysis = IntentAnalysis(
        outcome="needs_clarification",
        clarification_question="What aspect of AI?",
        clarification_options=["Option A", "Option B", "Option C"],
    )
    second_analysis = IntentAnalysis(
        outcome="needs_clarification",
        clarification_question="Still too broad.",
        clarification_options=["Option D", "Option E", "Option F"],
    )

    router_topics = []

    class RouterReached(Exception):
        pass

    def mock_router(state: State):
        router_topics.append(state["topic"])
        raise RouterReached("router_reached")

    from blog_agent.graph import main_graph
    original_app = main_graph.app
    original_handle = main_graph._checkpointer_handle

    main_graph._checkpointer_handle = handle

    try:
        with patch(
            "blog_agent.nodes.intent_gateway.analyze_intent",
            side_effect=[first_analysis, second_analysis],
        ), patch(
            "blog_agent.nodes.intent_gateway.generate_proposed_topic",
            return_value="Proposed RAG Pipeline Topic",
        ), patch(
            "blog_agent.graph.main_graph.router_node",
            side_effect=mock_router,
        ):
            main_graph.app = main_graph.build_graph(handle.saver)
            initial_state = {
                "run_id": run_id,
                "original_input": "AI",
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

            # Step 1: Initial run pauses at clarification interrupt
            diagnostics = RunDiagnostics(run_id=run_id, topic="")
            context = {"diagnostics": diagnostics}
            config = {"configurable": {"thread_id": run_id}}
            main_graph.app.invoke(initial_state, config, context=context)

            # Step 2: Resume clarification via main_graph.resume()
            custom_resp = IntentHumanResponse(
                action="custom_input",
                value="getting started with ai",
            )
            res2 = main_graph.resume(run_id, human_response=custom_resp)
            assert res2.get("intent_status") == "pending"

            # Step 3: Resume confirmation via main_graph.resume()
            proceed_resp = IntentHumanResponse(action="proceed")
            try:
                main_graph.resume(run_id, human_response=proceed_resp)
            except RouterReached:
                pass

            assert len(router_topics) == 1
            assert router_topics[0] == "Proposed RAG Pipeline Topic"
    finally:
        main_graph.app = original_app
        main_graph._checkpointer_handle = original_handle
        handle.close()

