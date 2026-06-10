"""Agent worker — delegate tasks to Vertex AI agents with result validation."""

import logging

from app.vertex_agents.registry import find_agent_by_name, find_best_agent
from app.vertex_agents.client import query_agent
from app.tasks.workers.base import llm_generate

logger = logging.getLogger(__name__)

MAX_TURNS = 3
MAX_RETRIES = 2

# Patterns that indicate the agent didn't actually answer
FAILURE_PATTERNS = [
    "no entendí",
    "no comprendo",
    "could you clarify",
    "can you rephrase",
    "i don't understand",
    "no tengo información",
    "i don't have",
    "no puedo ayudar",
    "fuera de mi alcance",
    "out of scope",
    "no response from agent",
]


def _is_valid_response(response: str) -> bool:
    """Check if the agent response is actually useful."""
    if not response or len(response.strip()) < 10:
        return False
    response_lower = response.lower()
    if any(p in response_lower for p in FAILURE_PATTERNS):
        return False
    return True


def _is_question(text: str) -> bool:
    """Heuristic: does the agent response look like a question?"""
    text = text.strip()
    if text.endswith("?"):
        return True
    question_markers = [
        "could you", "can you", "please provide", "what is",
        "which", "how many", "podría", "puede", "cuál", "qué",
        "por favor proporcione", "me puede decir",
    ]
    text_lower = text.lower()
    return any(m in text_lower for m in question_markers)


async def agent_worker(task, update_progress) -> str:
    """Execute a task by delegating to a Vertex AI agent.

    Pipeline: find agent → call detectIntent → validate → retry if bad → return
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
            return "Error: No agents configured or no agent matches this task. Add agents in Settings > Vertex AI Agents."

    logger.info(f"Agent task {task_id[:8]}: routing to '{agent['name']}'")
    await update_progress(
        task_id, "task_update",
        progress=15, progress_text=f"Delegando a: {agent['name']}",
    )

    # Step 2: Call the Vertex AI agent with retry and validation
    session_id = f"task-{task_id[:8]}"
    final_response = None

    for attempt in range(MAX_RETRIES + 1):
        if attempt > 0:
            await update_progress(
                task_id, "task_update",
                progress=20, progress_text=f"Reintentando (intento {attempt + 1})...",
            )

        response = await _converse_with_agent(
            agent, session_id, task.description, task_id, update_progress,
            progress_start=20 + (attempt * 10),
        )

        if _is_valid_response(response):
            final_response = response
            break
        else:
            logger.warning(
                f"Agent task {task_id[:8]}: attempt {attempt + 1} got invalid response: {response[:80]}"
            )
            # Reformulate for retry
            if attempt < MAX_RETRIES:
                session_id = f"task-{task_id[:8]}-r{attempt + 1}"

    # Step 3: Validate and format result
    await update_progress(task_id, "task_update", progress=85, progress_text="Validando resultado...")

    if not final_response or not _is_valid_response(final_response):
        # Last resort: ask Nova's own LLM to answer using whatever partial info we have
        logger.warning(f"Agent task {task_id[:8]}: all attempts failed, using LLM fallback")
        await update_progress(task_id, "task_update", progress=88, progress_text="Agente no respondió, generando respuesta propia...")

        fallback = await _llm_fallback(task.description, agent["name"], final_response)
        return (
            f"**Agent: {agent['name']}** (respuesta generada por NOVA — el agente no pudo resolver)\n\n"
            f"{fallback}"
        )

    # Quality check: is the response complete?
    quality = await _assess_quality(task.description, final_response)

    await update_progress(task_id, "task_update", progress=95, progress_text="Completado")

    result = f"**Agent: {agent['name']}**\n\n{final_response}"
    if quality == "incomplete":
        result += "\n\n---\n*Nota: La respuesta puede estar incompleta. Considere hacer preguntas de seguimiento.*"

    return result


async def _converse_with_agent(
    agent: dict, session_id: str, message: str, task_id: str,
    update_progress, progress_start: int = 20,
) -> str:
    """Multi-turn conversation with the agent."""
    responses = []

    for turn in range(MAX_TURNS):
        progress = progress_start + int(40 * turn / MAX_TURNS)
        await update_progress(
            task_id, "task_update",
            progress=progress, progress_text=f"Turno {turn + 1}: comunicándose con agente...",
        )

        response = query_agent(agent, session_id, message)

        if response.startswith("Error:"):
            return response

        responses.append(response)
        logger.info(f"Agent task {task_id[:8]}: turn {turn + 1} got {len(response)} chars")

        # If agent asks a follow-up question, provide more context
        if turn < MAX_TURNS - 1 and _is_question(response):
            message = (
                f"Contexto original: {message}\n\n"
                f"Tu pregunta fue: {response}\n\n"
                f"Por favor proporciona la respuesta más completa posible "
                f"basándote en el contexto original. Si no tienes suficiente "
                f"información, responde con lo que puedas."
            )
        else:
            break

    return responses[-1] if responses else ""


async def _assess_quality(original_question: str, response: str) -> str:
    """Quick LLM check: is the response complete?

    Returns: "complete", "incomplete", or "error"
    """
    try:
        check = await llm_generate(
            f"Question: {original_question[:200]}\n\n"
            f"Answer: {response[:500]}\n\n"
            f"Is this answer complete and relevant? Reply with ONLY one word: complete, incomplete, or irrelevant.",
            system="You are a quality checker. Assess if the answer addresses the question adequately.",
        )
        result = check.strip().lower()
        if "incomplete" in result:
            return "incomplete"
        if "irrelevant" in result:
            return "incomplete"
        return "complete"
    except Exception:
        return "complete"  # Don't block on quality check failure


async def _llm_fallback(description: str, agent_name: str, partial_response: str = None) -> str:
    """Generate a response using Nova's own LLM when the agent fails."""
    context = f"El agente '{agent_name}' no pudo responder adecuadamente."
    if partial_response:
        context += f"\n\nRespuesta parcial del agente: {partial_response[:300]}"

    try:
        return await llm_generate(
            f"{context}\n\nPregunta original: {description}\n\n"
            f"Genera la mejor respuesta posible basándote en tu conocimiento.",
            system="You are a helpful assistant. Answer the question as best you can. Write in the same language as the question.",
        )
    except Exception as e:
        return f"No se pudo generar una respuesta. Error: {e}"
