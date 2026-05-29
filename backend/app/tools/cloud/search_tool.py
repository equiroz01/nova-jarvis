from langchain.tools import tool
from ddgs import DDGS


@tool
def web_search(query: str) -> str:
    """Search the internet for real-time information. You MUST use this tool whenever the user asks about:
    - News, current events, or recent happenings
    - Weather or forecasts
    - Prices, stocks, or financial data
    - Sports scores or results
    - Any question that requires up-to-date information you don't have
    Always call this tool first before saying you can't find information."""
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
