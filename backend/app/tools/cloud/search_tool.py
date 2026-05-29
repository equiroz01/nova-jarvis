from langchain.tools import tool
from duckduckgo_search import DDGS


@tool
def web_search(query: str) -> str:
    """Search the web using DuckDuckGo for up-to-date information.
    Use this when the user asks about current events, weather, news, or anything
    that requires real-time internet data."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, region="wt-wt", safesearch="Moderate", max_results=3))

        if not results:
            return f"No results found for: '{query}'"

        formatted = []
        for i, r in enumerate(results, 1):
            formatted.append(f"{i}. {r['title']}\n   {r['body']}\n   URL: {r['href']}")

        return f"Search results for '{query}':\n\n" + "\n\n".join(formatted)
    except Exception as e:
        return f"Search error: {e}"
