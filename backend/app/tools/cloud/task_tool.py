"""Background task tool — lets NOVA dispatch autonomous work."""

import asyncio
import logging
from langchain.tools import tool

logger = logging.getLogger(__name__)

# Reference to the main event loop — set by main.py during startup
_main_loop: asyncio.AbstractEventLoop = None


def set_loop(loop: asyncio.AbstractEventLoop):
    global _main_loop
    _main_loop = loop


@tool
def create_background_task(title: str, description: str, task_type: str = "general") -> str:
    """Create a background task that NOVA will work on autonomously.
    Use this when the user asks you to do something that takes a long time:
    - Research a topic deeply and write a report
    - Build or code something
    - Create a document or presentation
    - Any work that should continue in the background

    The task runs autonomously — the user can check progress anytime.

    Args:
        title: Short name for the task (2-6 words)
        description: Detailed instructions for what to do
        task_type: One of: research, code, document, general
    """
    try:
        from app.tasks.models import TaskCreate
        from app.tasks import store

        task_in = TaskCreate(
            title=title,
            description=description,
            type=task_type,
        )

        if _main_loop and _main_loop.is_running():
            # Create task in DB
            future = asyncio.run_coroutine_threadsafe(
                store.create(task_in), _main_loop
            )
            task = future.result(timeout=10)

            # Submit to runner — get it from the FastAPI app state
            # We need to import at runtime to avoid circular imports
            async def _submit():
                from app.main import app
                await app.state.task_runner.submit(task.id)

            asyncio.run_coroutine_threadsafe(_submit(), _main_loop).result(timeout=5)

            return (
                f"Tarea creada: **{task.title}** (ID: {task.id[:8]})\n"
                f"Tipo: {task.type} | Estado: en cola\n"
                f"Se ejecutará en background. El usuario puede ver el progreso en /tasks."
            )
        else:
            return "Error: no se pudo crear la tarea (event loop no disponible)"

    except Exception as e:
        logger.error(f"Error creating background task: {e}", exc_info=True)
        return f"Error creating task: {e}"
