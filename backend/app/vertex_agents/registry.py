"""Agent registry — load, save, match, and auto-route to Vertex AI agents."""

import logging
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)

AGENTS_CONFIG_PATH = Path(__file__).parent.parent.parent / "agents_config.yaml"

# Minimum confidence threshold for auto-routing (0-1)
MIN_CONFIDENCE = 0.3

# Valid agent types
AGENT_TYPE_REASONING_ENGINE = "reasoning_engine"
AGENT_TYPE_DIALOGFLOW_CX = "dialogflow_cx"


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

    Strategy 1: Weighted keyword scoring from specialties + description.
    Strategy 2: LLM classification with routing_prompt context (fallback).

    Returns None if no agent is confident enough (below MIN_CONFIDENCE).
    """
    agents = get_enabled_agents()
    if not agents:
        return None
    if len(agents) == 1:
        return agents[0]

    desc_lower = description.lower()

    # Score each agent
    scored = []
    for agent in agents:
        score = _score_agent(agent, desc_lower)
        scored.append((score, agent))

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_agent = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0

    # Clear winner with enough confidence
    if best_score > 0 and best_score > second_score * 1.5:
        logger.info(f"Auto-route: '{best_agent['name']}' (score={best_score:.1f}, 2nd={second_score:.1f})")
        return best_agent

    # Close scores or no keyword match — use LLM
    try:
        result = _llm_classify(description, agents)
        if result:
            return result
    except Exception as e:
        logger.warning(f"LLM agent classification failed: {e}")

    # Last resort: return best scorer if any match at all
    if best_score > 0:
        return best_agent

    return None


def _score_agent(agent: dict, desc_lower: str) -> float:
    """Score an agent's relevance to a description.

    Scoring:
    - Specialty keyword match: +1.0 per keyword found
    - Description word overlap: +0.3 per word
    - Agent name mentioned: +3.0
    """
    score = 0.0

    # Specialty keywords (strongest signal)
    for kw in agent.get("specialties", []):
        if kw.lower() in desc_lower:
            score += 1.0

    # Agent description word overlap (weaker signal)
    agent_desc = agent.get("description", "").lower()
    if agent_desc:
        desc_words = set(agent_desc.split())
        query_words = set(desc_lower.split())
        overlap = desc_words & query_words
        # Ignore common words
        stopwords = {"de", "la", "el", "en", "y", "a", "que", "para", "con", "los", "las", "un", "una", "the", "and", "for", "to"}
        overlap -= stopwords
        score += len(overlap) * 0.3

    # Agent name explicitly mentioned
    if agent["name"].lower() in desc_lower:
        score += 3.0

    return score


def _llm_classify(description: str, agents: list[dict]) -> dict | None:
    """Use LLM to pick the best agent, with routing_prompt context."""
    from app.tasks.workers.base import _llm_call

    agent_list = []
    for a in agents:
        entry = f"- {a['name']}: {a.get('description', '')}"
        specs = ", ".join(a.get("specialties", []))
        if specs:
            entry += f" (specialties: {specs})"
        routing = a.get("routing_prompt", "")
        if routing:
            entry += f"\n  Routing rules: {routing}"
        agent_list.append(entry)

    prompt = (
        f"Given this task:\n\"{description}\"\n\n"
        f"Which of these agents is the best match? If NONE of them fit well, reply 'NONE'.\n\n"
        f"{''.join(agent_list)}\n\n"
        f"Reply with ONLY the agent name (or 'NONE'). Nothing else."
    )

    result = _llm_call(prompt)
    result_clean = result.strip().strip('"').strip("'")

    if result_clean.upper() == "NONE":
        logger.info("LLM classified: no agent fits this task")
        return None

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
        routing = a.get("routing_prompt", "")
        agent_type = a.get("type", AGENT_TYPE_REASONING_ENGINE)
        type_label = "RE" if agent_type == AGENT_TYPE_REASONING_ENGINE else "CX"
        line = f"- **{a['name']}** [{type_label}]: {desc}"
        if specs:
            line += f" (specialties: {specs})"
        if routing:
            line += f"\n  When to use: {routing}"
        lines.append(line)

    return "\n".join(lines)
