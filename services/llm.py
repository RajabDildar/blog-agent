from langchain_groq import ChatGroq

from config.settings import (
    EDITOR_MODEL,
    PLANNER_MODEL,
    RESEARCH_MODEL,
    REVISION_MODEL,
    ROUTER_MODEL,
    WRITER_MODEL,
    rate_limiter,
)


def create_llm(
    model: str,
    *,
    temperature: float,
) -> ChatGroq:
    return ChatGroq(
        model=model,
        temperature=temperature,
        rate_limiter=rate_limiter,
    )


router_llm = create_llm(
    ROUTER_MODEL,
    temperature=0.1,
)

research_llm = create_llm(
    RESEARCH_MODEL,
    temperature=0.1,
)

planner_llm = create_llm(
    PLANNER_MODEL,
    temperature=0.3,
)

writer_llm = create_llm(
    WRITER_MODEL,
    temperature=0.5,
)

editor_llm = create_llm(
    EDITOR_MODEL,
    temperature=0.1,
)

revision_llm = create_llm(
    REVISION_MODEL,
    temperature=0.3,
)
