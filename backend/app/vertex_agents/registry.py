"""Agent registry — load, save, match, and auto-route to Vertex AI agents."""

import logging
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)

AGENTS_CONFIG_PATH = Path(__file__).parent.parent.parent / "agents_config.yaml"


def load_agents() -> list[dict]:
    """Load all agents from config."""
    if not AGENTS_CONFIG_PATH.exists():
        return []
    try:
        with open(AGENTS_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("agents") or []
    except Exception as e:
        logger.error(f"Agent config error: {e}")
        return []


def save_agents(agents: list[dict]):
    """Save agents list to config."""
    with open(AGENTS_CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump({"agents": agents}, f, default_flow_style=False, allow_unicode=True)


def get_enabled_agents() -> list[dict]:
    """Get only enabled agents."""
    return [a for a in load_agents() if a.get("enabled", True)]


def find_agent_by_name(name: str) -> dict | None:
    """Find agent by exact or fuzzy name match."""
    agents = get_enabled_agents()
    name_lower = name.lower().strip()

    # Exact match
    for a in agents:
        if a["name"].lower() == name_lower:
            return a

    # Partial match
    for a in agents:
        if name_lower in a["name"].lower() or a["name"].lower() in name_lower:
            return a

    return None


def find_best_agent(description: str) -> dict | None:
    """Auto-route: find the best agent for a task description.

    Strategy 1: keyword scoring from specialties.
    Strategy 2: LLM classification (fallback if tie or no match).
    """
    agents = get_enabled_agents()
    if not agents:
        return None
    if len(agents) == 1:
        return agents[0]

    desc_lower = description.lower()

    # Score by specialty keyword matches
    scores = []
    for agent in agents:
        specialties = agent.get("specialties", [])
        score = sum(1 for kw in specialties if kw.lower() in desc_lower)
        scores.append((score, agent))

    scores.sort(key=lambda x: x[0], reverse=True)

    # Clear winner
    if scores[0][0] > 0 and scores[0][0] > scores[1][0]:
        return scores[0][1]

    # Tie or no keyword match — use LLM
    try:
        return _llm_classify(description, agents)
    except Exception as e:
        logger.warning(f"LLM agent classification failed: {e}")
        # Return highest scorer or first agent
        return scores[0][1] if scores[0][0] > 0 else agents[0]


def _llm_classify(description: str, agents: list[dict]) -> dict | None:
    """Use LLM to pick the best agent."""
    from app.tasks.workers.base import llm_generate
    import asyncio

    agent_list = "\n".join(
        f"- {a['name']}: {a.get('description', '')} (specialties: {', '.join(a.get('specialties', []))})"
        for a in agents
    )

    prompt = (
        f"Given this task:\n\"{description}\"\n\n"
        f"Which of these agents is the best match?\n{agent_list}\n\n"
        f"Reply with ONLY the agent name, nothing else."
    )

    # Sync call since this may be called from sync context
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            from app.tasks.workers.base import _llm_call
            result = _llm_call(prompt)
        else:
            result = asyncio.run(llm_generate(prompt))
    except RuntimeError:
        from app.tasks.workers.base import _llm_call
        result = _llm_call(prompt)

    # Match result to agent name
    result_clean = result.strip().strip('"').strip("'")
    return find_agent_by_name(result_clean)


def get_agent_descriptions() -> str:
    """Get formatted agent descriptions for system prompt injection."""
    agents = get_enabled_agents()
    if not agents:
        return ""

    lines = ["Available agents:"]
    for a in agents:
        specs = ", ".join(a.get("specialties", []))
        desc = a.get("description", "")
        lines.append(f"- **{a['name']}**: {desc}" + (f" (specialties: {specs})" if specs else ""))

    return "\n".join(lines)
