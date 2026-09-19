from unittest.mock import MagicMock, patch
import pytest

from blog_agent.nodes.intent_gateway import intent_gateway_node
from blog_agent.schemas.models import IntentAnalysis
from blog_agent.schemas.state import State
from blog_agent.services.intent_analysis import (
    IntentAnalysisUnavailable,
    analyze_intent,
)


def test_gemini_success_does_not_call_groq():
    mock_result = IntentAnalysis(
        outcome="accepted",
        normalized_topic="Building Scalable Event-Driven Architectures",
    )

    mock_gemini_llm = MagicMock()
    mock_gemini_structured = MagicMock()
    mock_gemini_structured.invoke.return_value = mock_result
    mock_gemini_llm.with_structured_output.return_value = mock_gemini_structured

    mock_groq_llm = MagicMock()

    with patch(
        "blog_agent.services.intent_analysis.get_gemini_intent_llm",
        return_value=mock_gemini_llm,
    ), patch(
        "blog_agent.services.intent_analysis.get_groq_intent_llm",
        return_value=mock_groq_llm,
    ):
        result = analyze_intent("event-driven systems")

    assert result.outcome == "accepted"
    assert result.normalized_topic == "Building Scalable Event-Driven Architectures"
    mock_gemini_structured.invoke.assert_called_once()
    mock_groq_llm.with_structured_output.assert_not_called()


def test_gemini_failure_triggers_groq_fallback():
    mock_groq_result = IntentAnalysis(
        outcome="accepted",
        normalized_topic="Building Scalable Event-Driven Architectures",
    )

    mock_gemini_llm = MagicMock()
    mock_gemini_structured = MagicMock()
    mock_gemini_structured.invoke.side_effect = RuntimeError("Gemini 503 Server Error")
    mock_gemini_llm.with_structured_output.return_value = mock_gemini_structured

    mock_groq_llm = MagicMock()
    mock_groq_structured = MagicMock()
    mock_groq_structured.invoke.return_value = mock_groq_result
    mock_groq_llm.with_structured_output.return_value = mock_groq_structured

    with patch(
        "blog_agent.services.intent_analysis.get_gemini_intent_llm",
        return_value=mock_gemini_llm,
    ), patch(
        "blog_agent.services.intent_analysis.get_groq_intent_llm",
        return_value=mock_groq_llm,
    ):
        result = analyze_intent("event-driven systems")

    assert result.outcome == "accepted"
    mock_gemini_structured.invoke.assert_called_once()
    mock_groq_structured.invoke.assert_called_once()


def test_gemini_validation_error_triggers_groq_fallback():
    mock_groq_result = IntentAnalysis(
        outcome="accepted",
        normalized_topic="Valid Schema From Groq",
    )

    mock_gemini_llm = MagicMock()
    mock_gemini_structured = MagicMock()
    # Gemini returned invalid dictionary that fails IntentAnalysis validation
    mock_gemini_structured.invoke.return_value = {
        "outcome": "accepted",
        "normalized_topic": "",  # invalid for accepted!
    }
    mock_gemini_llm.with_structured_output.return_value = mock_gemini_structured

    mock_groq_llm = MagicMock()
    mock_groq_structured = MagicMock()
    mock_groq_structured.invoke.return_value = mock_groq_result
    mock_groq_llm.with_structured_output.return_value = mock_groq_structured

    with patch(
        "blog_agent.services.intent_analysis.get_gemini_intent_llm",
        return_value=mock_gemini_llm,
    ), patch(
        "blog_agent.services.intent_analysis.get_groq_intent_llm",
        return_value=mock_groq_llm,
    ):
        result = analyze_intent("event-driven systems")

    assert result.outcome == "accepted"
    assert result.normalized_topic == "Valid Schema From Groq"
    mock_groq_structured.invoke.assert_called_once()


def test_both_providers_fail_raises_intent_analysis_unavailable():
    mock_gemini_llm = MagicMock()
    mock_gemini_structured = MagicMock()
    mock_gemini_structured.invoke.side_effect = RuntimeError("Gemini Down")
    mock_gemini_llm.with_structured_output.return_value = mock_gemini_structured

    mock_groq_llm = MagicMock()
    mock_groq_structured = MagicMock()
    mock_groq_structured.invoke.side_effect = RuntimeError("Groq Down")
    mock_groq_llm.with_structured_output.return_value = mock_groq_structured

    with patch(
        "blog_agent.services.intent_analysis.get_gemini_intent_llm",
        return_value=mock_gemini_llm,
    ), patch(
        "blog_agent.services.intent_analysis.get_groq_intent_llm",
        return_value=mock_groq_llm,
    ):
        with pytest.raises(IntentAnalysisUnavailable) as exc_info:
            analyze_intent("event-driven systems")

    assert "All intent analysis providers failed" in str(exc_info.value)


def test_intent_gateway_node_handles_double_provider_failure():
    state: State = {
        "run_id": "test-double-fail",
        "original_input": "event-driven systems",
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

    with patch(
        "blog_agent.nodes.intent_gateway.analyze_intent",
        side_effect=IntentAnalysisUnavailable("Both down"),
    ):
        result = intent_gateway_node(state)

    assert result["intent_status"] == "invalid"
    assert result["intent_message"] == "Unable to understand request. Please retry."
    assert result["topic"] == ""
