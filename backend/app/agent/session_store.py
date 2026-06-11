"""Durable conversation history backed by SQLite.

Conversation memory used to live in a plain in-memory dict, so every launchd
restart wiped every thread mid-conversation. This persists each turn to the SAME
SQLite file the task system uses (WAL mode allows the async task store and this
synchronous connection to share it). invoke_agent is synchronous, so we use the
stdlib sqlite3 driver here rather than bridging to the async aiosqlite store.

The in-memory ConversationBufferWindowMemory remains the live cache (see
session.py); this layer only hydrates it on first access and appends on each turn.
"""

import logging
import sqlite3
import threading
import time

from app.tasks.store import _resolve_db_path

logger = logging.getLogger(__name__)

_conn: sqlite3.Connection | None = None
_lock = threading.Lock()


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        path = _resolve_db_path()  # ~/.nova/data/tasks.db (shared file)
        _conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA busy_timeout=8000")  # wait up to 8s for locks
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
        logger.info("Session store ready: %s", path)
    return _conn


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
