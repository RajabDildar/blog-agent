import os

from tavily import TavilyClient


client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])


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

    return response.get("results", [])
