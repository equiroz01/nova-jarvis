import asyncio
import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()

# Registry of connected local clients
_clients: dict[str, WebSocket] = {}
_pending_requests: dict[str, asyncio.Future] = {}


def get_connected_client(client_id: str) -> Optional[WebSocket]:
    return _clients.get(client_id)


def has_any_client() -> bool:
    return len(_clients) > 0


async def request_local_tool(action: str, params: dict = None, timeout: float = 30.0) -> str:
    """Send a tool execution request to the first connected local client and wait for the result."""
    if not _clients:
        return "No local Mac client connected. Start the Jarvis client on your computer."

    client_id, ws = next(iter(_clients.items()))
    request_id = str(uuid.uuid4())

    future = asyncio.get_event_loop().create_future()
    _pending_requests[request_id] = future

    try:
        await ws.send_json({
            "request_id": request_id,
            "action": action,
            "params": params or {},
        })
        result = await asyncio.wait_for(future, timeout=timeout)
        return result
    except asyncio.TimeoutError:
        return f"Local tool '{action}' timed out after {timeout}s"
    except Exception as e:
        return f"Error executing local tool '{action}': {e}"
    finally:
        _pending_requests.pop(request_id, None)


@router.websocket("/ws/client/{client_id}")
async def websocket_client(websocket: WebSocket, client_id: str):
    await websocket.accept()
    _clients[client_id] = websocket
    logger.info(f"Local client connected: {client_id}")

    try:
        while True:
            data = await websocket.receive_json()

            # Handle tool execution responses
            request_id = data.get("request_id")
            if request_id and request_id in _pending_requests:
                _pending_requests[request_id].set_result(data.get("result", ""))

            # Handle heartbeat
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info(f"Local client disconnected: {client_id}")
    except Exception as e:
        logger.error(f"WebSocket error for {client_id}: {e}")
    finally:
        _clients.pop(client_id, None)
