"""Code worker — enhanced coding via agent with MCP tools."""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from .base import get_workspace_dir

logger = logging.getLogger(__name__)

_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="worker-code")

# Files/dirs to skip when listing workspace contents
_SKIP_PATTERNS = {"__pycache__", ".pyc", "node_modules", ".git", ".env", ".DS_Store"}

CODE_PROMPT_TEMPLATE = """BACKGROUND CODING TASK — you must write all code yourself.

Title: {title}
Instructions: {description}

WORKSPACE: {workspace}

You are a senior software engineer. Follow these steps:
1. Plan the file structure first
2. Write each file using the filesystem MCP tools — save ALL files to the WORKSPACE directory above
3. If you need reference code, use GitHub tools to search/read repos
4. Create a README.md in the workspace explaining the project
5. Write complete, working code — no stubs or placeholders
6. Use best practices: proper error handling, clear naming, comments where needed

CRITICAL RULES:
- NEVER use create_background_task — you ARE the background task, write the code yourself
- NEVER delegate or create sub-tasks — implement everything directly
- Use filesystem_create_or_update_file to write files to the WORKSPACE path
- Return a summary of what you built and the file structure"""


async def code_worker(task, update_progress) -> str:
    """Execute a coding task using the agent with enhanced prompt."""
    task_id = task.id

    # Step 1: Prepare workspace
    await update_progress(task_id, "task_update", progress=5, progress_text="Preparando workspace...")
    workspace = get_workspace_dir(task_id)

    # Step 2: Build enhanced prompt
    await update_progress(task_id, "task_update", progress=10, progress_text="Configurando agente...")

    prompt = CODE_PROMPT_TEMPLATE.format(
        title=task.title,
        description=task.description,
        workspace=str(workspace),
    )

    # Step 3: Execute via agent
    await update_progress(task_id, "task_update", progress=20, progress_text="Agente programando...")

    from app.agent.orchestrator import invoke_agent

    loop = asyncio.get_event_loop()
    session_id = f"code-{task_id}"

    result = await loop.run_in_executor(_pool, invoke_agent, prompt, session_id)

    # Step 4: List created files (skip hidden/build artifacts)
    await update_progress(task_id, "task_update", progress=90, progress_text="Verificando archivos...")

    files = []
    for f in workspace.rglob("*"):
        if f.is_file() and not any(skip in str(f) for skip in _SKIP_PATTERNS):
            files.append(str(f.relative_to(workspace)))

    if files:
        result += f"\n\n---\n**Archivos creados en workspace** (`{workspace}`):\n"
        for f in sorted(files)[:50]:  # Cap at 50 files
            result += f"\n- `{f}`"

    logger.info(f"Code {task_id[:8]}: completed, {len(files)} files in workspace")
    return result
