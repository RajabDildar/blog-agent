from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
)

from schemas.models import ResearchPack
from schemas.state import State
from services.llm import gemini_llm
from services.tavily import tavily_search
from prompts.research import RESEARCH_SYSTEM


def research_node(
    state: State,
) -> dict:
    queries = state.get("queries", [])

    raw_results: list[dict] = []

    for query in queries[:5]:
        raw_results.extend(
            tavily_search(
                query,
                max_results=3,
            )
        )

    if not raw_results:
        return {
            "evidence": [],
            "research_brief": "",
        }

    unique: dict[str, dict] = {}

    for result in raw_results:
        url = result.get("url")

        if url and url not in unique:
            unique[url] = result

    compact_results = []

    for result in unique.values():
        compact_results.append(
            {
                "title": result.get(
                    "title",
                    "",
                ),
                "url": result.get(
                    "url",
                    "",
                ),
                "score": result.get(
                    "score",
                    0,
                ),
                "content": result.get(
                    "content",
                    "",
                )[:2000],
                "raw_content": result.get(
                    "raw_content",
                    "",
                )[:2500],
            }
        )

    extractor = gemini_llm.with_structured_output(ResearchPack)

    pack = extractor.invoke(
        [
            SystemMessage(content=RESEARCH_SYSTEM),
            HumanMessage(
                content=(
                    f"Topic: {state['topic']}\n\n"
                    f"Research focus:\n"
                    f"{state.get('research_focus', [])}\n\n"
                    f"Search results:\n"
                    f"{compact_results}"
                )
            ),
        ]
    )

    return {
        "evidence": pack.evidence,
        "research_brief": pack.research_brief,
    }
