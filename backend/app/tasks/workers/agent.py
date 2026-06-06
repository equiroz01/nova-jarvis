"""Agent worker — delegate tasks to Vertex AI agents."""

import logging

from app.vertex_agents.registry import find_agent_by_name, find_best_agent
from app.vertex_agents.client import detect_intent

logger = logging.getLogger(__name__)

MAX_TURNS = 3


async def agent_worker(task, update_progress) -> str:
    """Execute a task by delegating to a Vertex AI agent.

    Pipeline: find agent → call detectIntent → multi-turn if needed → return
    """
    task_id = task.id

    # Step 1: Find the target agent
    await update_progress(task_id, "task_update", progress=5, progress_text="Buscando agente...")

    agent = None
    agent_name = getattr(task, "agent_name", None)

    if agent_name:
        agent = find_agent_by_name(agent_name)
        if not agent:
            return f"Error: Agent '{agent_name}' not found in registry."
    else:
        agent = find_best_agent(task.description)
        if not agent:
            return "Error: No agents configured. Add agents in Settings > Vertex AI Agents."

    logger.info(f"Agent task {task_id[:8]}: routing to '{agent['name']}'")
    await update_progress(
        task_id, "task_update",
        progress=15, progress_text=f"Delegando a: {agent['name']}",
    )

    # Step 2: Call the Vertex AI agent (with multi-turn support)
    session_id = f"task-{task_id[:8]}"
    message = task.description
    responses = []

    for turn in range(MAX_TURNS):
        progress = 20 + int(60 * turn / MAX_TURNS)
        await update_progress(
            task_id, "task_update",
            progress=progress, progress_text=f"Turno {turn + 1}: esperando respuesta...",
        )

        response = detect_intent(agent, session_id, message)

        if response.startswith("Error:"):
            return response

        responses.append(response)
        logger.info(f"Agent task {task_id[:8]}: turn {turn + 1} got {len(response)} chars")

        # Check if agent is asking a follow-up question
        if turn < MAX_TURNS - 1 and _is_question(response):
            # Provide more context as follow-up
            message = (
                f"Context: {task.description}\n\n"
                f"Your question was: {response}\n\n"
                f"Please provide the most complete answer you can based on the original request."
            )
        else:
            break

    # Step 3: Format result
    await update_progress(task_id, "task_update", progress=90, progress_text="Formateando respuesta...")

    final = responses[-1] if responses else "No response from agent."
    result = f"**Agent: {agent['name']}**\n\n{final}"

    if len(responses) > 1:
        result += f"\n\n---\n*Conversation required {len(responses)} turns.*"

    logger.info(f"Agent task {task_id[:8]}: completed via '{agent['name']}'")
    return result


def _is_question(text: str) -> bool:
    """Heuristic: does the agent response look like a question?"""
    text = text.strip()
    if text.endswith("?"):
        return True
    question_markers = [
        "could you", "can you", "please provide", "what is",
        "which", "how many", "podría", "puede", "cuál", "qué",
    ]
    text_lower = text.lower()
    return any(m in text_lower for m in question_markers)
