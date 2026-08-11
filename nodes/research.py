from langchain_core.messages import HumanMessage, SystemMessage

from schemas.models import EvidencePack
from schemas.state import State
from services.llm import llm
from services.tavily import tavily_search


RESEARCH_SYSTEM = """You are a research synthesizer for technical writing.

Given raw web search results, produce a deduplicated list of EvidenceItem objects.

Rules:
- Only include items with a non-empty url.
- Prefer relevant + authoritative sources (company blogs, docs, reputable outlets).
- If a published date is explicitly present in the result payload, keep it as YYYY-MM-DD.
  If missing or unclear, set published_at=null. Do NOT guess.
- Keep snippets short.
- Deduplicate by URL.
"""


def research_node(state: State) -> dict:
    queries = state.get("queries", []) or []
    max_results = 3

    raw_results: list[dict] = []

    for q in queries:
        raw_results.extend(
            tavily_search(
                q,
                max_results=max_results,
            )
        )

    if not raw_results:
        return {"evidence": []}

    extractor = llm.with_structured_output(EvidencePack)

    pack = extractor.invoke(
        [
            SystemMessage(content=RESEARCH_SYSTEM),
            HumanMessage(content=f"Raw results:\n{raw_results}"),
        ]
    )

    dedup = {}

    for e in pack.evidence:
        if e.url:
            dedup[e.url] = e

    return {
        "evidence": list(dedup.values()),
    }
