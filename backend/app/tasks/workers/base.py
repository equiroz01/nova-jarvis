"""Shared utilities for all task workers."""

import asyncio
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

_llm = None
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="worker-llm")


def get_llm() -> ChatGoogleGenerativeAI:
    """Get cached LLM instance (same config as orchestrator)."""
    global _llm
    if _llm is None:
        from app.config import settings
        _llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=settings.gemini_api_key,
            temperature=0.7,
        )
    return _llm


def _llm_call(prompt: str, system: str = None) -> str:
    """Sync LLM call (runs in thread pool)."""
    llm = get_llm()
    messages = []
    if system:
        messages.append(SystemMessage(content=system))
    messages.append(HumanMessage(content=prompt))
    response = llm.invoke(messages)
    return response.content


async def llm_generate(prompt: str, system: str = None) -> str:
    """Async wrapper for LLM generation."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_pool, _llm_call, prompt, system)


def brave_search(query: str, count: int = 5, news: bool = False) -> list[dict]:
    """Direct Brave Search API call, returns list of {title, description, url}."""
    try:
        from app.tools.cloud.search_tool import _brave_request
        endpoint = "news/search" if news else "web/search"
        data = _brave_request(endpoint, {"q": query, "count": count})

        if news:
            results = data.get("results", [])
            return [
                {
                    "title": r.get("title", ""),
                    "description": r.get("description", ""),
                    "url": r.get("url", ""),
                    "source": r.get("meta_url", {}).get("hostname", ""),
                    "age": r.get("age", ""),
                }
                for r in results
            ]
        else:
            results = data.get("web", {}).get("results", [])
            return [
                {
                    "title": r.get("title", ""),
                    "description": r.get("description", "")[:200],
                    "url": r.get("url", ""),
                }
                for r in results
            ]
    except Exception as e:
        logger.warning(f"Brave search failed for '{query}': {e}")
        return []


def get_workspace_dir(task_id: str) -> Path:
    """Get/create workspace directory for a task."""
    nova_home = os.environ.get("NOVA_HOME", str(Path.home() / ".nova"))
    workspace = Path(nova_home) / "data" / "workspaces" / task_id[:8]
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def save_to_brain(title: str, content: str, category: str = "facts"):
    """Save content to NOVA's brain (Obsidian vault)."""
    try:
        from app.knowledge.brain import save_note
        save_note(title, content, category=category)
        logger.info(f"Saved to brain: {title}")
    except Exception as e:
        logger.warning(f"Failed to save to brain: {e}")


def parse_json_response(text: str) -> list | dict | None:
    """Parse JSON from LLM response, handling markdown code blocks."""
    # Strip markdown code fences
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first and last lines (fences)
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse JSON from LLM response: {cleaned[:100]}...")
        return None
