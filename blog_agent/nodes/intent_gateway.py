from blog_agent.schemas.models import IntentAnalysis
import logging
from langgraph.types import interrupt

from blog_agent.config.settings import MAX_USER_INPUT_CHARS
from blog_agent.schemas.models import IntentHumanResponse
from blog_agent.schemas.state import State
from blog_agent.services.intent_analysis import (
    IntentAnalysisUnavailable,
    analyze_intent,
    generate_proposed_topic,
)
from blog_agent.services.run_diagnostics import get_current_diagnostics

logger = logging.getLogger(__name__)

_intent_cache: dict[tuple[str, str, str | None], IntentAnalysis] = {}
_proposed_cache: dict[tuple[str, str, str], str] = {}


def clear_intent_gateway_caches() -> None:
    _intent_cache.clear()
    _proposed_cache.clear()


def intent_gateway_node(state: State) -> dict:
    """The first node in Blog Agent. Validates, classifies, and finalizes user intent."""
    raw_input = state.get("original_input", "")
    run_id = state.get("run_id", "")
    diagnostics = get_current_diagnostics()

    # 1. Deterministic Pre-validation
    cleaned_input = " ".join(raw_input.strip().split())

    if not cleaned_input:
        msg = "Topic cannot be empty. Please provide a technical article topic."
        if diagnostics is not None:
            diagnostics.record_input_invalid(
                reason="insufficient_information",
                message=msg,
            )
        return {
            "intent_status": "invalid",
            "intent_category": "insufficient_information",
            "intent_message": msg,
            "topic": "",
        }

    if len(raw_input) > MAX_USER_INPUT_CHARS:
        msg = (
            f"Input exceeds maximum allowed length of {MAX_USER_INPUT_CHARS} characters "
            f"(received {len(raw_input)})."
        )
        if diagnostics is not None:
            diagnostics.record_input_invalid(
                reason="insufficient_information",
                message=msg,
            )
        return {
            "intent_status": "invalid",
            "intent_category": "insufficient_information",
            "intent_message": msg,
            "topic": "",
        }

    # 2. Semantic Intent Classification
    cache_key = (run_id, cleaned_input, None)
    if cache_key in _intent_cache:
        analysis = _intent_cache[cache_key]
    else:
        try:
            analysis = analyze_intent(cleaned_input)
            _intent_cache[cache_key] = analysis
        except IntentAnalysisUnavailable as exc:
            msg = "Unable to understand request. Please retry."
            if diagnostics is not None:
                diagnostics.record_input_invalid(
                    reason="service_unavailable",
                    message=msg,
                )
            return {
                "intent_status": "invalid",
                "intent_category": "service_unavailable",
                "intent_message": msg,
                "topic": "",
            }

    # 3. Handle Analysis Outcomes
    if analysis.outcome == "blocked":
        if diagnostics is not None:
            diagnostics.record_input_blocked(
                category=analysis.block_category,
                message=analysis.user_message,
            )
        return {
            "intent_status": "blocked",
            "intent_category": analysis.block_category,
            "intent_message": analysis.user_message,
            "topic": "",
        }

    if analysis.outcome == "invalid":
        if diagnostics is not None:
            diagnostics.record_input_invalid(
                reason=analysis.invalid_reason,
                message=analysis.user_message,
            )
        return {
            "intent_status": "invalid",
            "intent_category": analysis.invalid_reason,
            "intent_message": analysis.user_message,
            "topic": "",
        }

    if analysis.outcome == "accepted":
        if diagnostics is not None:
            diagnostics.record_topic_finalized(analysis.normalized_topic)
        return {
            "intent_status": "safe",
            "topic": analysis.normalized_topic,
        }

    # 4. Clarification Loop (needs_clarification)
    if diagnostics is not None:
        diagnostics.record_clarification_required(
            question=analysis.clarification_question,
            options=analysis.clarification_options,
        )

    clarification_payload = {
        "type": "clarification_required",
        "question": analysis.clarification_question,
        "options": analysis.clarification_options,
        "allow_custom_input": True,
    }

    # Human interrupt
    raw_response = interrupt(clarification_payload)

    if isinstance(raw_response, dict):
        human_resp = IntentHumanResponse.model_validate(raw_response)
    elif isinstance(raw_response, IntentHumanResponse):
        human_resp = raw_response
    else:
        raise ValueError(f"Invalid clarification response type: {type(raw_response)}")

    if human_resp.action == "cancel":
        if diagnostics is not None:
            diagnostics.record_input_cancelled()
        return {
            "intent_status": "cancelled",
            "intent_message": "Article generation cancelled by user.",
            "clarification_rounds": 1,
            "clarification_question": analysis.clarification_question,
            "clarification_options": analysis.clarification_options,
            "topic": "",
        }

    if human_resp.action == "select_option":
        if human_resp.value not in analysis.clarification_options:
            raise ValueError(
                f"Selected option '{human_resp.value}' is not among offered options: "
                f"{analysis.clarification_options}"
            )
        selected_text = human_resp.value
    elif human_resp.action == "custom_input":
        if len(human_resp.value) > MAX_USER_INPUT_CHARS:
            raise ValueError(
                f"Custom clarification exceeds maximum limit of {MAX_USER_INPUT_CHARS} characters."
            )
        selected_text = human_resp.value.strip()
    else:
        raise ValueError(
            f"Action '{human_resp.action}' is not valid during clarification."
        )

    rounds = 1
    clarification_response = selected_text

    # 5. Re-check Clarified Intent
    recheck_key = (run_id, cleaned_input, selected_text)
    if recheck_key in _intent_cache:
        second_analysis = _intent_cache[recheck_key]
    else:
        try:
            second_analysis = analyze_intent(
                cleaned_input,
                clarification_context=selected_text,
            )
            _intent_cache[recheck_key] = second_analysis
        except IntentAnalysisUnavailable:
            msg = "Unable to understand request. Please retry."
            if diagnostics is not None:
                diagnostics.record_input_invalid(
                    reason="service_unavailable",
                    message=msg,
                )
            return {
                "intent_status": "invalid",
                "intent_category": "service_unavailable",
                "intent_message": msg,
                "clarification_rounds": rounds,
                "clarification_question": analysis.clarification_question,
                "clarification_options": analysis.clarification_options,
                "clarification_response": clarification_response,
                "topic": "",
            }

    if second_analysis.outcome == "blocked":
        if diagnostics is not None:
            diagnostics.record_input_blocked(
                category=second_analysis.block_category,
                message=second_analysis.user_message,
            )
        return {
            "intent_status": "blocked",
            "intent_category": second_analysis.block_category,
            "intent_message": second_analysis.user_message,
            "clarification_rounds": rounds,
            "clarification_question": analysis.clarification_question,
            "clarification_options": analysis.clarification_options,
            "clarification_response": clarification_response,
            "topic": "",
        }

    if second_analysis.outcome == "invalid":
        if diagnostics is not None:
            diagnostics.record_input_invalid(
                reason=second_analysis.invalid_reason,
                message=second_analysis.user_message,
            )
        return {
            "intent_status": "invalid",
            "intent_category": second_analysis.invalid_reason,
            "intent_message": second_analysis.user_message,
            "clarification_rounds": rounds,
            "clarification_question": analysis.clarification_question,
            "clarification_options": analysis.clarification_options,
            "clarification_response": clarification_response,
            "topic": "",
        }

    if second_analysis.outcome == "accepted":
        if diagnostics is not None:
            diagnostics.record_topic_finalized(second_analysis.normalized_topic)
        return {
            "intent_status": "safe",
            "topic": second_analysis.normalized_topic,
            "clarification_rounds": rounds,
            "clarification_question": analysis.clarification_question,
            "clarification_options": analysis.clarification_options,
            "clarification_response": clarification_response,
        }

    # 6. Still vague: derivation of single proposed topic + Confirmation Interrupt
    proposed_key = (run_id, cleaned_input, selected_text)
    if proposed_key in _proposed_cache:
        proposed = _proposed_cache[proposed_key]
    else:
        proposed = generate_proposed_topic(cleaned_input, selected_text)
        _proposed_cache[proposed_key] = proposed
    if diagnostics is not None:
        diagnostics.record_topic_confirmation_required(proposed_topic=proposed)

    confirm_payload = {
        "type": "topic_confirmation_required",
        "proposed_topic": proposed,
        "message": "Your request is still broad. I can generate the following article topic.",
        "actions": ["proceed", "cancel"],
    }

    raw_conf_response = interrupt(confirm_payload)

    if isinstance(raw_conf_response, dict):
        human_conf = IntentHumanResponse.model_validate(raw_conf_response)
    elif isinstance(raw_conf_response, IntentHumanResponse):
        human_conf = raw_conf_response
    else:
        raise ValueError(
            f"Invalid confirmation response type: {type(raw_conf_response)}"
        )

    if human_conf.action == "proceed":
        if diagnostics is not None:
            diagnostics.record_topic_finalized(proposed)
        return {
            "intent_status": "safe",
            "topic": proposed,
            "proposed_topic": proposed,
            "clarification_rounds": rounds,
            "clarification_question": analysis.clarification_question,
            "clarification_options": analysis.clarification_options,
            "clarification_response": clarification_response,
        }
    else:
        if diagnostics is not None:
            diagnostics.record_input_cancelled()
        return {
            "intent_status": "cancelled",
            "intent_message": "Article generation cancelled by user.",
            "proposed_topic": proposed,
            "clarification_rounds": rounds,
            "clarification_question": analysis.clarification_question,
            "clarification_options": analysis.clarification_options,
            "clarification_response": clarification_response,
            "topic": "",
        }


def blocked_terminal_node(state: State) -> dict:
    """Terminal node for blocked requests."""
    return {}


def invalid_terminal_node(state: State) -> dict:
    """Terminal node for invalid or out of scope requests."""
    return {}


def cancelled_terminal_node(state: State) -> dict:
    """Terminal node for cancelled requests."""
    return {}
