import asyncio
import logging
from langchain.tools import tool

from app.api.websocket_bridge import request_local_tool

logger = logging.getLogger(__name__)


def _run_local(action: str, params: dict = None) -> str:
    """Helper to run async local tool request from sync context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, request_local_tool(action, params))
                return future.result(timeout=35)
        else:
            return loop.run_until_complete(request_local_tool(action, params))
    except Exception as e:
        return f"Error calling local tool: {e}"


@tool
def take_screenshot() -> str:
    """Take a screenshot of the user's Mac screen. Requires the local Jarvis client to be running."""
    return _run_local("screenshot")


@tool
def read_screen_text() -> str:
    """Read text from the latest screenshot using OCR. Requires the local Jarvis client to be running."""
    return _run_local("ocr")


@tool
def run_arp_scan() -> str:
    """Scan the local network for connected devices. Requires the local Jarvis client to be running."""
    return _run_local("arp_scan")
