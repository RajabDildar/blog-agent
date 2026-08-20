import os

from tavily import TavilyClient

client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])


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
    }


def tavily_search(
    query: str,
    *,
    max_results: int = 5,
) -> list[dict]:
    response = client.search(
        query=query,
        search_depth="advanced",
        max_results=max_results,
        include_raw_content=True,
        include_answer=False,
    )

    results = response.get("results") or []

    return [_normalize_result(result) for result in results]
