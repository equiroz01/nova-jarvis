"""NOVA Task Runner — background worker that executes tasks autonomously."""

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import store
from .models import TaskStatus
from .notifications import broadcast

logger = logging.getLogger(__name__)

_thread_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="task-worker")

# Max execution time per task (10 minutes)
TASK_TIMEOUT_S = 600


async def _safe_broadcast(event: dict):
    """Broadcast without propagating errors."""
    try:
        await broadcast(event)
    except Exception as e:
        logger.warning(f"Broadcast failed: {e}")


async def _update_and_broadcast(task_id: str, event_type: str, **fields):
    """Update store and broadcast in one step, with null safety."""
    await store.update(task_id, **fields)
    task = await store.get(task_id)
    if task:
        await _safe_broadcast({"type": event_type, "task": task.model_dump()})


class TaskRunner:
    """Background task runner with configurable concurrency."""

    def __init__(self, max_concurrent: int = 2):
        self.max_concurrent = max_concurrent
        self._queue: asyncio.Queue = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._running = False

    async def start(self):
        """Start worker coroutines and load pending tasks from DB."""
        self._running = True

        # Load queued tasks from DB (crash recovery)
        queued = await store.list_tasks(status=TaskStatus.queued.value)
        for task in queued:
            await self._queue.put(task.id)
        if queued:
            logger.info(f"TaskRunner: loaded {len(queued)} queued task(s)")

        for i in range(self.max_concurrent):
            worker = asyncio.create_task(self._worker(i))
            self._workers.append(worker)

        logger.info(f"TaskRunner started with {self.max_concurrent} workers")

    async def stop(self):
        """Gracefully stop all workers."""
        self._running = False
        for task_id, atask in self._running_tasks.items():
            atask.cancel()
        for w in self._workers:
            w.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        self._running_tasks.clear()
        logger.info("TaskRunner stopped")

    async def submit(self, task_id: str):
        """Submit a task for execution."""
        await self._queue.put(task_id)
        logger.info(f"TaskRunner: task {task_id[:8]} submitted")

    async def cancel(self, task_id: str) -> bool:
        """Cancel a running task."""
        if task_id in self._running_tasks:
            self._running_tasks[task_id].cancel()
            now = datetime.now(timezone.utc).isoformat()
            await _update_and_broadcast(
                task_id, "task_cancelled",
                status=TaskStatus.cancelled, completed_at=now,
            )
            self._running_tasks.pop(task_id, None)
            logger.info(f"TaskRunner: task {task_id[:8]} cancelled")
            return True
        return False

    async def _worker(self, worker_id: int):
        """Worker loop: pick tasks from queue and execute them."""
        logger.debug(f"TaskRunner worker-{worker_id} started")
        while self._running:
            try:
                task_id = await asyncio.wait_for(self._queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            task = await store.get(task_id)
            if not task or task.status != TaskStatus.queued:
                continue

            # Mark as running
            now = datetime.now(timezone.utc).isoformat()
            await _update_and_broadcast(
                task_id, "task_update",
                status=TaskStatus.running, started_at=now,
            )

            # Execute with timeout
            exec_task = asyncio.create_task(self._execute_task(task_id))
            self._running_tasks[task_id] = exec_task

            try:
                await asyncio.wait_for(exec_task, timeout=TASK_TIMEOUT_S)
            except asyncio.TimeoutError:
                logger.error(f"Task {task_id[:8]} timed out after {TASK_TIMEOUT_S}s")
                exec_task.cancel()
                now = datetime.now(timezone.utc).isoformat()
                await _update_and_broadcast(
                    task_id, "task_failed",
                    status=TaskStatus.failed,
                    error=f"Task timed out after {TASK_TIMEOUT_S}s",
                    completed_at=now,
                )
            except asyncio.CancelledError:
                logger.info(f"Task {task_id[:8]} was cancelled")
            except Exception as e:
                logger.error(f"Task {task_id[:8]} failed: {e}", exc_info=True)
                now = datetime.now(timezone.utc).isoformat()
                await _update_and_broadcast(
                    task_id, "task_failed",
                    status=TaskStatus.failed, error=str(e), completed_at=now,
                )
            finally:
                self._running_tasks.pop(task_id, None)

    async def _execute_task(self, task_id: str):
        """Execute a task based on its type."""
        task = await store.get(task_id)
        if not task:
            return

        logger.info(f"Executing task {task_id[:8]}: {task.title} (type={task.type})")

        result = await self._run_with_agent(task)

        now = datetime.now(timezone.utc).isoformat()
        await _update_and_broadcast(
            task_id, "task_complete",
            status=TaskStatus.completed, progress=100,
            progress_text="Completed", result=result, completed_at=now,
        )
        logger.info(f"Task {task_id[:8]} completed successfully")

    async def _run_with_agent(self, task) -> str:
        """Run a task using the existing LangChain agent executor."""
        from app.agent.orchestrator import invoke_agent

        await _update_and_broadcast(
            task.id, "task_update", progress=10, progress_text="Starting agent...",
        )

        prompt = (
            f"BACKGROUND TASK — work autonomously until done.\n"
            f"Title: {task.title}\n"
            f"Instructions: {task.description}\n\n"
            f"Provide a complete, detailed result. Use all available tools as needed. "
            f"Search the web, check your brain/memory, and be thorough."
        )

        loop = asyncio.get_event_loop()
        session_id = f"task-{task.id[:8]}"

        await _update_and_broadcast(
            task.id, "task_update", progress=30, progress_text="Agent working...",
        )

        t0 = time.time()
        result = await loop.run_in_executor(
            _thread_pool, invoke_agent, prompt, session_id
        )
        elapsed = time.time() - t0

        await _update_and_broadcast(
            task.id, "task_update", progress=90, progress_text="Finalizing...",
        )

        logger.info(f"Task {task.id[:8]} agent finished in {elapsed:.1f}s")
        return result
