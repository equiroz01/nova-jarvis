"""NOVA Task Notifications — SSE broadcast for real-time task updates."""

import asyncio
import json
import logging
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

_subscribers: list[asyncio.Queue] = []


async def subscribe() -> AsyncGenerator[str, None]:
    """Subscribe to task update events via SSE."""
    q: asyncio.Queue = asyncio.Queue()
    _subscribers.append(q)
    logger.debug(f"Task SSE subscriber added ({len(_subscribers)} total)")
    try:
        while True:
            event = await q.get()
            yield f"data: {json.dumps(event)}\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        _subscribers.remove(q)
        logger.debug(f"Task SSE subscriber removed ({len(_subscribers)} total)")


async def broadcast(event: dict):
    """Broadcast a task event to all SSE subscribers."""
    if not _subscribers:
        return
    for q in _subscribers:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("Task SSE subscriber queue full, dropping event")
