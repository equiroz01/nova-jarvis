"""Agent delegation tool — lets NOVA call Vertex AI agents in real-time."""

import asyncio
import logging
import uuid
from langchain.tools import tool

logger = logging.getLogger(__name__)


@tool
def delegate_to_agent(agent_name: str, message: str) -> str:
    """Delegate a question or task to a specialized Vertex AI agent for an immediate answer.
    Use this when the user's request matches a specific agent's domain.

    Available agents are listed in the system prompt under VERTEX AI AGENTS.

    Args:
        agent_name: Name of the agent to call (e.g. "Data Analyst")
        message: The question or request to send to the agent
    """
    try:
        from app.vertex_agents.registry import find_agent_by_name, get_enabled_agents
        from app.vertex_agents.client import detect_intent

        agent = find_agent_by_name(agent_name)
        if not agent:
            available = get_enabled_agents()
            names = [a["name"] for a in available]
            return (
                f"Agent '{agent_name}' not found. "
                f"Available agents: {', '.join(names) if names else 'none configured'}"
            )

        session_id = f"nova-rt-{uuid.uuid4().hex[:8]}"
        response = detect_intent(agent, session_id, message)

        if response.startswith("Error:"):
            return response

        return f"**{agent['name']}** responds:\n\n{response}"

    except Exception as e:
        logger.error(f"Agent delegation error: {e}", exc_info=True)
        return f"Error delegating to agent: {e}"
