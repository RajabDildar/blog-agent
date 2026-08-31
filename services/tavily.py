import os

from tavily import TavilyClient

from services.run_diagnostics import get_current_diagnostics

client = TavilyClient(
    api_key=os.environ["TAVILY_API_KEY"],
)


def _normalize_result(
    result: dict,
) -> dict:
    return {
        **result,
        "title": result.get("title") or "",
        "url": result.get("url") or "",
        "score": result.get("score") or 0,
        "content": result.get("content") or "",
        "raw_content": result.get("raw_content") or "",
        "published_at": (result.get("published_date") or result.get("published_at")),
    }


def tavily_search(
    query: str,
    *,
    max_results: int = 5,
) -> list[dict]:
    diagnostics = get_current_diagnostics()
    if diagnostics is not None:
        diagnostics.record_provider_call("tavily")

    response = client.search(
        query=query,
        search_depth="advanced",
        max_results=max_results,
        include_raw_content=True,
        include_answer=False,
    )

    results = response.get("results") or []

    return [_normalize_result(result) for result in results]
