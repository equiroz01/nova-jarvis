"""Background task tool — lets NOVA dispatch autonomous work."""

import asyncio
import logging
from langchain.tools import tool

logger = logging.getLogger(__name__)

# References set by main.py during startup — avoids circular imports
_main_loop: asyncio.AbstractEventLoop = None
_task_runner = None


def set_loop(loop: asyncio.AbstractEventLoop, runner=None):
    global _main_loop, _task_runner
    _main_loop = loop
    _task_runner = runner


@tool
def create_background_task(title: str, description: str, task_type: str = "general", agent_name: str = "") -> str:
    """Create a background task that NOVA will work on autonomously.
    Use this when the user asks you to do something that takes a long time:
    - Research a topic deeply and write a report
    - Build or code something
    - Create a document or presentation
    - Delegate to a Vertex AI agent
    - Any work that should continue in the background

    The task runs autonomously — the user can check progress anytime.

    Args:
        title: Short name for the task (2-6 words)
        description: Detailed instructions for what to do
        task_type: One of: research, code, document, agent, general
        agent_name: Name of the Vertex AI agent to use (only for type="agent")
    """
    try:
        from app.tasks.models import TaskCreate
        from app.tasks import store

        task_in = TaskCreate(
            title=title,
            description=description,
            type=task_type,
            agent_name=agent_name or None,
        )

        if not (_main_loop and _main_loop.is_running()):
            return "Error: no se pudo crear la tarea (event loop no disponible)"

        # Create task in DB
        future = asyncio.run_coroutine_threadsafe(
            store.create(task_in), _main_loop
        )
        task = future.result(timeout=10)

        # Submit to runner
        if _task_runner:
            asyncio.run_coroutine_threadsafe(
                _task_runner.submit(task.id), _main_loop
            ).result(timeout=5)

        return (
            f"Tarea creada: **{task.title}** (ID: {task.id[:8]})\n"
            f"Tipo: {task.type} | Estado: en cola\n"
            f"Se ejecutará en background. El usuario puede ver el progreso en /tasks."
        )

    except Exception as e:
        logger.error(f"Error creating background task: {e}", exc_info=True)
        return f"Error creating task: {e}"
