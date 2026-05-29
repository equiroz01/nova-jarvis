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
            # Try news search first for news-related queries
            news_keywords = ["noticias", "news", "hoy", "today", "reciente", "latest", "actual"]
            if any(kw in query.lower() for kw in news_keywords):
                results = list(ddgs.news(query, max_results=5))
                if results:
                    formatted = []
                    for i, r in enumerate(results, 1):
                        title = r.get("title", "")
                        body = r.get("body", "")
                        source = r.get("source", "")
                        url = r.get("url", "")
                        date = r.get("date", "")
                        formatted.append(
                            f"{i}. [{source}] {title}\n   {body}\n   Date: {date}\n   URL: {url}"
                        )
                    return f"News results for '{query}':\n\n" + "\n\n".join(formatted)

            # Fallback to regular text search
            results = list(ddgs.text(query, region="wt-wt", safesearch="Moderate", max_results=5))

        if not results:
            return f"No results found for: '{query}'"

        formatted = []
        for i, r in enumerate(results, 1):
            formatted.append(f"{i}. {r['title']}\n   {r['body']}\n   URL: {r['href']}")

        return f"Search results for '{query}':\n\n" + "\n\n".join(formatted)
    except Exception as e:
        return f"Search error: {e}"
