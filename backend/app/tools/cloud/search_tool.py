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
        logger.debug("Keychain read for brave_api_key failed; falling back to env", exc_info=True)
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


def _brave_search(query: str) -> str:
    """Primary backend. Raises on key/network/HTTP failure so web_search can fall back."""
    news_keywords = ["noticias", "news", "hoy", "today", "reciente", "latest", "actual",
                     "pasó", "paso", "novedades", "titulares"]
    is_news = any(kw in query.lower() for kw in news_keywords)

    if is_news:
        # Try news endpoint first; a news miss falls through to web (not an outage).
        try:
            data = _brave_request("news/search", {"q": query, "count": 5})
            results = data.get("results", [])
            if results:
                formatted = []
                for i, r in enumerate(results, 1):
                    source = r.get("meta_url", {}).get("hostname", "")
                    formatted.append(
                        f"{i}. [{source}] {r.get('title','')}\n   {r.get('description','')[:150]}\n"
                        f"   {r.get('age','')} | {r.get('url','')}"
                    )
                return f"Noticias para '{query}':\n\n" + "\n\n".join(formatted)
        except urllib.error.HTTPError:
            raise  # real outage → let web_search fall back
        except Exception:
            logger.debug("Brave news miss, trying web", exc_info=True)

    data = _brave_request("web/search", {"q": query, "count": 5})
    results = data.get("web", {}).get("results", [])
    if not results:
        return f"No se encontraron resultados para: '{query}'"

    formatted = []
    for i, r in enumerate(results, 1):
        formatted.append(f"{i}. {r.get('title','')}\n   {r.get('description','')[:150]}\n   {r.get('url','')}")
    return f"Resultados para '{query}':\n\n" + "\n\n".join(formatted)


def _ddg_search(query: str) -> str:
    """Keyless backstop (DuckDuckGo Instant Answer). Degraded but beats a dead worker."""
    qs = urllib.parse.urlencode({"q": query, "format": "json", "no_html": 1, "skip_disambig": 1})
    req = urllib.request.Request(
        f"https://api.duckduckgo.com/?{qs}",
        headers={"Accept": "application/json", "User-Agent": "NOVA/1.0"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())

    parts = []
    if data.get("AbstractText"):
        parts.append(f"{data['AbstractText']}\n   {data.get('AbstractURL','')}")
    for topic in data.get("RelatedTopics", []):
        if len(parts) >= 5:
            break
        text = topic.get("Text")
        if text:
            parts.append(f"{text}\n   {topic.get('FirstURL','')}")

    if not parts:
        return f"No se encontraron resultados para: '{query}'"
    body = "\n\n".join(f"{i}. {p}" for i, p in enumerate(parts, 1))
    return f"Resultados para '{query}' (vía DuckDuckGo):\n\n{body}"


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
        return _brave_search(query)
    except Exception as brave_err:
        # Brave outage / missing key → degrade to DuckDuckGo instead of dying silently.
        logger.warning("Brave search failed (%s); falling back to DuckDuckGo", brave_err)
        try:
            return _ddg_search(query)
        except Exception as ddg_err:
            logger.error("Both search providers failed: brave=%s ddg=%s", brave_err, ddg_err, exc_info=True)
            return f"Error de búsqueda (Brave y DuckDuckGo no disponibles): {brave_err}"
