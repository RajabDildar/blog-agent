import logging
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

from blog_agent.config.settings import (
    GROQ_INTENT_MODEL,
    INTENT_GEMINI_MODEL,
    rate_limiter,
)
from blog_agent.prompts.intent_gateway import (
    INTENT_SYSTEM_PROMPT,
    PROPOSED_TOPIC_SYSTEM_PROMPT,
)
from blog_agent.schemas.models import IntentAnalysis, ProposedTopicAnalysis
from blog_agent.services.llm import InstrumentedRunnable
from blog_agent.services.run_diagnostics import get_current_diagnostics

logger = logging.getLogger(__name__)


class IntentAnalysisUnavailable(RuntimeError):
    """Raised when both primary (Gemini) and fallback (Groq) intent analysis fail."""
    pass


def get_gemini_intent_llm() -> InstrumentedRunnable:
    return InstrumentedRunnable(
        ChatGoogleGenerativeAI(
            model=INTENT_GEMINI_MODEL,
            max_retries=0,
        ),
        "gemini",
    )


def get_groq_intent_llm() -> InstrumentedRunnable:
    return InstrumentedRunnable(
        ChatGroq(
            model=GROQ_INTENT_MODEL,
            temperature=0.2,
            rate_limiter=rate_limiter,
            max_retries=0,
        ),
        "groq",
    )


def analyze_intent(
    text: str,
    *,
    clarification_context: str | None = None,
) -> IntentAnalysis:
    """Analyze user intent with Gemini primary and Groq fallback.

    Fails closed: raises IntentAnalysisUnavailable if both providers fail.
    """
    diagnostics = get_current_diagnostics()
    if diagnostics is not None:
        diagnostics.record_intent_check_started()

    content = f"User Request:\n{text}"
    if clarification_context:
        content = (
            f"Original Request:\n{text}\n\n"
            f"User Clarification Response:\n{clarification_context}\n\n"
            "Please evaluate the combined clarified intent."
        )

    messages = [
        SystemMessage(content=INTENT_SYSTEM_PROMPT),
        HumanMessage(content=content),
    ]

    # 1. Attempt Primary: Gemini
    gemini_exc: Exception | None = None
    try:
        gemini_llm = get_gemini_intent_llm()
        structured_gemini = gemini_llm.with_structured_output(IntentAnalysis)
        result = structured_gemini.invoke(messages)
        if isinstance(result, dict):
            result = IntentAnalysis.model_validate(result)
        if diagnostics is not None:
            diagnostics.record_intent_check_succeeded(
                provider="gemini",
                outcome=result.outcome,
            )
        return result
    except Exception as exc:
        gemini_exc = exc
        logger.warning(
            "Gemini intent analysis failed, attempting Groq fallback: %s",
            exc,
        )
        if diagnostics is not None:
            diagnostics.record_intent_provider_fallback(
                failed_provider="gemini",
                exc=exc,
            )

    # 2. Attempt Fallback: Groq
    try:
        groq_llm = get_groq_intent_llm()
        structured_groq = groq_llm.with_structured_output(IntentAnalysis)
        result = structured_groq.invoke(messages)
        if isinstance(result, dict):
            result = IntentAnalysis.model_validate(result)
        if diagnostics is not None:
            diagnostics.record_intent_check_succeeded(
                provider="groq",
                outcome=result.outcome,
            )
        return result
    except Exception as groq_exc:
        logger.error(
            "Groq fallback intent analysis failed after Gemini failure. Gemini error: %s; Groq error: %s",
            gemini_exc,
            groq_exc,
        )
        if diagnostics is not None:
            diagnostics.record_intent_check_failed(groq_exc)
        raise IntentAnalysisUnavailable(
            f"All intent analysis providers failed. Gemini: {gemini_exc}; Groq: {groq_exc}"
        ) from groq_exc


def generate_proposed_topic(
    original_input: str,
    clarification_response: str,
) -> str:
    """Generate a single focused proposed topic when the clarified response is still too vague."""
    content = (
        f"Original Request: {original_input}\n"
        f"Clarification Provided: {clarification_response}\n\n"
        "Please provide one focused, compelling technical article topic synthesizing these inputs."
    )
    messages = [
        SystemMessage(content=PROPOSED_TOPIC_SYSTEM_PROMPT),
        HumanMessage(content=content),
    ]

    # Try Gemini first
    try:
        gemini_llm = get_gemini_intent_llm()
        structured = gemini_llm.with_structured_output(ProposedTopicAnalysis)
        result = structured.invoke(messages)
        if isinstance(result, dict):
            result = ProposedTopicAnalysis.model_validate(result)
        return result.proposed_topic.strip()
    except Exception as exc:
        logger.warning("Gemini proposed topic generation failed, trying Groq: %s", exc)

    # Try Groq fallback
    try:
        groq_llm = get_groq_intent_llm()
        structured = groq_llm.with_structured_output(ProposedTopicAnalysis)
        result = structured.invoke(messages)
        if isinstance(result, dict):
            result = ProposedTopicAnalysis.model_validate(result)
        return result.proposed_topic.strip()
    except Exception as exc:
        logger.warning("Groq proposed topic generation failed: %s", exc)

    # Deterministic fallback synthesis
    return f"{original_input.strip()}: {clarification_response.strip()}"
