from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

from config.settings import (
    GEMINI_MODEL,
    REVISION_MODEL,
    WRITER_MODEL,
    rate_limiter,
)


writer_llm = ChatGroq(
    model=WRITER_MODEL,
    temperature=0.3,
    rate_limiter=rate_limiter,
    max_retries=0,
)


revision_llm = ChatGroq(
    model=REVISION_MODEL,
    temperature=0.2,
    rate_limiter=rate_limiter,
    max_retries=0,
)


gemini_llm = ChatGoogleGenerativeAI(
    model=GEMINI_MODEL,
    temperature=0.2,
    max_retries=0,
)
