"""Durable conversation history backed by SQLite.

Uses its OWN database file (sessions.db) separate from the task store
(tasks.db) to avoid write contention — the task runner's async aiosqlite
connection would frequently hold the WAL write lock, causing "database
is locked" errors here.

invoke_agent is synchronous, so we use the stdlib sqlite3 driver.
The in-memory ConversationBufferWindowMemory remains the live cache (see
session.py); this layer only hydrates it on first access and appends on
each turn.
"""

import logging
import sqlite3
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_conn: sqlite3.Connection | None = None
_lock = threading.Lock()


def _resolve_sessions_db() -> str:
    """Return path to the sessions database (~/.nova/data/sessions.db)."""
    nova_home = Path.home() / ".nova"
    data_dir = nova_home / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "sessions.db")


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        path = _resolve_sessions_db()
        _conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA busy_timeout=5000")
        _conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role       TEXT NOT NULL,
                content    TEXT NOT NULL,
                ts         REAL NOT NULL
            )
            """
        )
        _conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_sid ON sessions(session_id, id)"
        )
        _conn.commit()

        # One-time migration: move sessions from tasks.db if they exist there
        _migrate_from_tasks_db(path)

        logger.info("Session store ready: %s", path)
    return _conn


def _migrate_from_tasks_db(new_path: str) -> None:
    """Migrate session rows from the old shared tasks.db (if any) to sessions.db."""
    try:
        from app.tasks.store import _resolve_db_path
        old_path = _resolve_db_path()
        old_conn = sqlite3.connect(old_path, timeout=5)
        # Check if sessions table exists in old DB
        tables = old_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
        ).fetchall()
        if not tables:
            old_conn.close()
            return

        count = old_conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        if count == 0:
            old_conn.close()
            return

        # Check if we already migrated (new DB has rows)
        existing = _conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        if existing > 0:
            old_conn.close()
            return

        # Copy rows
        rows = old_conn.execute(
            "SELECT session_id, role, content, ts FROM sessions ORDER BY id"
        ).fetchall()
        _conn.executemany(
            "INSERT INTO sessions (session_id, role, content, ts) VALUES (?, ?, ?, ?)",
            rows,
        )
        _conn.commit()

        # Drop old table
        old_conn.execute("DROP TABLE sessions")
        old_conn.execute("DROP INDEX IF EXISTS idx_sessions_sid")
        old_conn.commit()
        old_conn.close()

        logger.info("Migrated %d session rows from tasks.db to sessions.db", len(rows))
    except Exception:
        logger.debug("Session migration skipped (no old data or already done)", exc_info=True)


def load_recent(session_id: str, limit: int) -> list[tuple[str, str]]:
    """Return the last `limit` (role, content) turns for a session, oldest first."""
    try:
        rows = _db().execute(
            "SELECT role, content FROM "
            "(SELECT role, content, id FROM sessions WHERE session_id = ? "
            " ORDER BY id DESC LIMIT ?) ORDER BY id ASC",
            (session_id, limit),
        ).fetchall()
        return [(r[0], r[1]) for r in rows]
    except Exception:
        logger.warning("Session load failed for %s", session_id, exc_info=True)
        return []


def append(session_id: str, role: str, content: str) -> None:
    """Persist a single turn. Best-effort: a storage failure must not break chat."""
    try:
        with _lock:
            c = _db()
            c.execute(
                "INSERT INTO sessions (session_id, role, content, ts) VALUES (?, ?, ?, ?)",
                (session_id, role, content, time.time()),
            )
            c.commit()
    except Exception:
        logger.warning("Session append failed for %s", session_id, exc_info=True)


def append_turn(session_id: str, user_message: str, ai_response: str) -> None:
    """Persist a complete turn (user + AI) in a single transaction.

    This is preferred over two separate append() calls because it takes
    the SQLite write lock only once, reducing 'database is locked' errors
    when the task store is active on the same file.
    """
    now = time.time()
    try:
        with _lock:
            c = _db()
            c.executemany(
                "INSERT INTO sessions (session_id, role, content, ts) VALUES (?, ?, ?, ?)",
                [
                    (session_id, "user", user_message, now),
                    (session_id, "ai", ai_response, now + 0.001),
                ],
            )
            c.commit()
    except Exception:
        logger.warning("Session turn append failed for %s", session_id, exc_info=True)


def clear(session_id: str) -> None:
    try:
        with _lock:
            c = _db()
            c.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            c.commit()
    except Exception:
        logger.warning("Session clear failed for %s", session_id, exc_info=True)
