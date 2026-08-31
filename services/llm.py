from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

from config.settings import (
    GEMINI_MODEL,
    REVISION_MODEL,
    WRITER_MODEL,
    rate_limiter,
)
from services.run_diagnostics import get_current_diagnostics


class InstrumentedRunnable:
    def __init__(self, runnable, provider: str):
        self._runnable = runnable
        self._provider = provider

    def invoke(self, *args, **kwargs):
        diagnostics = get_current_diagnostics()
        if diagnostics is not None:
            diagnostics.record_provider_call(self._provider)
        return self._runnable.invoke(*args, **kwargs)

    def with_structured_output(self, *args, **kwargs):
        return InstrumentedRunnable(
            self._runnable.with_structured_output(*args, **kwargs),
            self._provider,
        )

    def __getattr__(self, name):
        return getattr(self._runnable, name)

writer_llm = InstrumentedRunnable(ChatGroq(
    model=WRITER_MODEL,
    temperature=0.3,
    rate_limiter=rate_limiter,
    max_retries=0,
), "groq")


revision_llm = InstrumentedRunnable(ChatGroq(
    model=REVISION_MODEL,
    temperature=0.2,
    rate_limiter=rate_limiter,
    max_retries=0,
), "groq")


gemini_llm = InstrumentedRunnable(ChatGoogleGenerativeAI(
    model=GEMINI_MODEL,
    temperature=0.2,
    max_retries=0,
), "gemini")
