from langchain_tavily import TavilySearch


def tavily_search(query: str, max_results: int = 5) -> list[dict]:
    tool = TavilySearch(max_results=max_results)

    results = tool.invoke({"query": query})["results"]

    normalized: list[dict] = []

    for r in results or []:
        normalized.append(
            {
                "title": r.get("title") or "",
                "url": r.get("url") or "",
                "snippet": r.get("content") or "",
            }
        )

    return normalized
