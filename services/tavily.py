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
    topic: str = "general",
    time_range: str | None = None,
    include_raw_content: bool = False,
) -> list[dict]:
    """
    Execute a Tavily search.

    Official docs:
    - published_date is only available when topic="news".
    - topic values: "general", "news", "finance".
    - time_range values: "day", "week", "month", "year" or shorthand "d","w","m","y".
    """
    diagnostics = get_current_diagnostics()
    if diagnostics is not None:
        diagnostics.record_provider_call("tavily")

    kwargs: dict = {
        "query": query,
        "search_depth": "advanced",
        "max_results": max_results,
        "include_raw_content": include_raw_content,
        "include_answer": False,
        "topic": topic,
    }

    if time_range is not None:
        kwargs["time_range"] = time_range

    response = client.search(**kwargs)

    results = response.get("results") or []

    return [_normalize_result(result) for result in results]
