"""Web search using Brave Search API — reliable, fast, real API with news support."""

import json
import logging
import urllib.request
import urllib.parse
import urllib.error
from langchain.tools import tool

logger = logging.getLogger(__name__)

_API_KEY = None
_BASE_URL = "https://api.search.brave.com/res/v1"


def _get_api_key() -> str:
    global _API_KEY
    if _API_KEY:
        return _API_KEY
    # Try Keychain first
    try:
        from app.services.keychain import keychain
        key = keychain.get("brave_api_key")
        if key:
            _API_KEY = key
            return key
    except Exception:
        pass
    # Fallback to env
    import os
    key = os.environ.get("BRAVE_API_KEY", "")
    if key:
        _API_KEY = key
    return key


def _brave_request(endpoint: str, params: dict) -> dict:
    """Make authenticated request to Brave Search API."""
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("Brave Search API key not configured. Add to Keychain or BRAVE_API_KEY env.")

    qs = urllib.parse.urlencode(params)
    url = f"{_BASE_URL}/{endpoint}?{qs}"
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "X-Subscription-Token": api_key,
    })
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


@tool
def web_search(query: str) -> str:
    """Search the internet for real-time information using Brave Search. You MUST use this tool whenever the user asks about:
    - News, current events, or recent happenings
    - Weather or forecasts
    - Prices, stocks, or financial data
    - Sports scores or results
    - Any question that requires up-to-date information you don't have
    Always call this tool first before saying you can't find information."""
    try:
        news_keywords = ["noticias", "news", "hoy", "today", "reciente", "latest", "actual",
                         "pasó", "paso", "novedades", "titulares"]
        is_news = any(kw in query.lower() for kw in news_keywords)

        if is_news:
            # Try news endpoint first
            try:
                data = _brave_request("news/search", {
                    "q": query,
                    "count": 5,
                })
                results = data.get("results", [])
                if results:
                    formatted = []
                    for i, r in enumerate(results, 1):
                        title = r.get("title", "")
                        desc = r.get("description", "")
                        source = r.get("meta_url", {}).get("hostname", "")
                        age = r.get("age", "")
                        url = r.get("url", "")
                        formatted.append(
                            f"{i}. [{source}] {title}\n   {desc[:150]}\n   {age} | {url}"
                        )
                    return f"Noticias para '{query}':\n\n" + "\n\n".join(formatted)
            except Exception:
                pass  # Fall through to web search

        # Web search
        data = _brave_request("web/search", {
            "q": query,
            "count": 5,
        })

        results = data.get("web", {}).get("results", [])
        if not results:
            return f"No se encontraron resultados para: '{query}'"

        formatted = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            desc = r.get("description", "")[:150]
            url = r.get("url", "")
            formatted.append(f"{i}. {title}\n   {desc}\n   {url}")

        return f"Resultados para '{query}':\n\n" + "\n\n".join(formatted)

    except RuntimeError as e:
        return str(e)
    except urllib.error.HTTPError as e:
        logger.error(f"Brave Search error: {e.code}")
        return f"Error de búsqueda ({e.code}). Verifica la API key."
    except Exception as e:
        logger.error(f"Search error: {e}", exc_info=True)
        return f"Error de búsqueda: {e}"
