"""NOVA Task Store — SQLite-backed persistent task storage."""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from .models import Task, TaskCreate, TaskStatus

logger = logging.getLogger(__name__)

_db_path: str = None
_db: aiosqlite.Connection = None


def _resolve_db_path() -> str:
    nova_home = os.environ.get("NOVA_HOME", str(Path.home() / ".nova"))
    data_dir = Path(nova_home) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "tasks.db")


async def init_db():
    """Initialize the task database."""
    global _db_path, _db
    _db_path = _resolve_db_path()
    _db = await aiosqlite.connect(_db_path)
    _db.row_factory = aiosqlite.Row

    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL DEFAULT 'general',
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'queued',
            progress INTEGER DEFAULT 0,
            progress_text TEXT DEFAULT '',
            result TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            session_id TEXT
        )
    """)
    await _db.commit()

    # Crash recovery: reset stuck running tasks to queued
    cursor = await _db.execute(
        "UPDATE tasks SET status = ? WHERE status = ?",
        (TaskStatus.queued.value, TaskStatus.running.value),
    )
    if cursor.rowcount > 0:
        await _db.commit()
        logger.info(f"Task store: recovered {cursor.rowcount} stuck task(s)")

    count = await _db.execute_fetchall("SELECT COUNT(*) FROM tasks")
    logger.info(f"Task store initialized: {_db_path} ({count[0][0]} tasks)")


async def close_db():
    """Close the database connection."""
    global _db
    if _db:
        await _db.close()
        _db = None


async def create(task_in: TaskCreate) -> Task:
    """Create a new task."""
    task = Task(
        title=task_in.title,
        description=task_in.description,
        type=task_in.type,
        session_id=task_in.session_id,
    )
    await _db.execute(
        """INSERT INTO tasks (id, type, title, description, status, progress,
           progress_text, result, error, created_at, started_at, completed_at, session_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            task.id, task.type.value, task.title, task.description,
            task.status.value, task.progress, task.progress_text,
            task.result, task.error, task.created_at,
            task.started_at, task.completed_at, task.session_id,
        ),
    )
    await _db.commit()
    logger.info(f"Task created: {task.id} — {task.title}")
    return task


async def get(task_id: str) -> Task | None:
    """Get a task by ID."""
    row = await _db.execute_fetchall(
        "SELECT * FROM tasks WHERE id = ?", (task_id,)
    )
    if not row:
        return None
    return _row_to_task(row[0])


async def list_tasks(status: str = None, limit: int = 50) -> list[Task]:
    """List tasks, optionally filtered by status."""
    if status:
        rows = await _db.execute_fetchall(
            "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?",
            (status, limit),
        )
    else:
        rows = await _db.execute_fetchall(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
        )
    return [_row_to_task(r) for r in rows]


async def update(task_id: str, **fields) -> Task | None:
    """Update task fields."""
    if not fields:
        return await get(task_id)

    sets = []
    values = []
    for key, val in fields.items():
        if val is not None:
            if isinstance(val, TaskStatus):
                val = val.value
            sets.append(f"{key} = ?")
            values.append(val)

    if not sets:
        return await get(task_id)

    values.append(task_id)
    await _db.execute(
        f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", values
    )
    await _db.commit()
    return await get(task_id)


async def delete(task_id: str) -> bool:
    """Delete a task."""
    cursor = await _db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    await _db.commit()
    return cursor.rowcount > 0


def _row_to_task(row) -> Task:
    """Convert a database row to a Task model."""
    return Task(
        id=row[0],
        type=row[1],
        title=row[2],
        description=row[3],
        status=row[4],
        progress=row[5],
        progress_text=row[6] or "",
        result=row[7],
        error=row[8],
        created_at=row[9],
        started_at=row[10],
        completed_at=row[11],
        session_id=row[12],
    )
