"""Task management API — CRUD + SSE stream for background tasks."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.tasks import store
from app.tasks.models import TaskCreate, TaskStatus
from app.tasks.notifications import subscribe

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class CreateTaskRequest(BaseModel):
    title: str
    description: str
    type: str = "general"
    agent_name: Optional[str] = None


@router.post("")
async def create_task(req: CreateTaskRequest, request: Request):
    """Create a new background task."""
    task_in = TaskCreate(
        title=req.title,
        description=req.description,
        type=req.type,
        agent_name=req.agent_name,
    )
    task = await store.create(task_in)

    # Submit to runner
    runner = request.app.state.task_runner
    await runner.submit(task.id)

    return task.model_dump()


@router.get("")
async def list_tasks(status: Optional[str] = None, limit: int = 50):
    """List tasks, optionally filtered by status."""
    tasks = await store.list_tasks(status=status, limit=limit)
    return [t.model_dump() for t in tasks]


@router.get("/stream")
async def task_stream():
    """SSE stream of task update events."""
    return StreamingResponse(
        subscribe(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{task_id}")
async def get_task(task_id: str):
    """Get a single task by ID."""
    task = await store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.model_dump()


@router.patch("/{task_id}")
async def update_task(task_id: str, request: Request):
    """Update a task (cancel, etc.)."""
    body = await request.json()
    task = await store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Handle cancellation
    if body.get("status") == "cancelled":
        runner = request.app.state.task_runner
        cancelled = await runner.cancel(task_id)
        if not cancelled:
            # Not running, just update DB
            await store.update(task_id, status=TaskStatus.cancelled)
        task = await store.get(task_id)
        return task.model_dump()

    # General update
    updated = await store.update(task_id, **body)
    return updated.model_dump()


@router.delete("/{task_id}")
async def delete_task(task_id: str, request: Request):
    """Delete a task."""
    # Cancel if running
    runner = request.app.state.task_runner
    await runner.cancel(task_id)

    deleted = await store.delete(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"deleted": True}
