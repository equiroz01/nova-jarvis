"""Tests for the WebSocket bridge (client registry, request_local_tool, heartbeat)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.websocket_bridge import (
    _clients,
    _pending_requests,
    get_connected_client,
    has_any_client,
    request_local_tool,
)


@pytest.fixture(autouse=True)
def _clean_registries():
    """Ensure client and pending-request registries are empty between tests."""
    _clients.clear()
    _pending_requests.clear()
    yield
    _clients.clear()
    _pending_requests.clear()


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------

class TestClientRegistry:
    def test_should_ReturnNone_when_ClientNotConnected(self):
        assert get_connected_client("nonexistent") is None

    def test_should_ReturnWebSocket_when_ClientIsRegistered(self):
        ws = MagicMock()
        _clients["c1"] = ws
        assert get_connected_client("c1") is ws

    def test_should_ReturnFalse_when_NoClientsConnected(self):
        assert has_any_client() is False

    def test_should_ReturnTrue_when_AtLeastOneClientConnected(self):
        _clients["c1"] = MagicMock()
        assert has_any_client() is True


# ---------------------------------------------------------------------------
# request_local_tool
# ---------------------------------------------------------------------------

class TestRequestLocalTool:
    @pytest.mark.asyncio
    async def test_should_ReturnNoClient_when_NoClientsConnected(self):
        result = await request_local_tool("screenshot")
        assert "No local Mac client" in result

    @pytest.mark.asyncio
    async def test_should_SendJsonToClient_when_ClientConnected(self):
        ws = AsyncMock()
        _clients["c1"] = ws

        # Simulate the client responding immediately
        async def respond_to_ws(*args, **kwargs):
            # After send_json is called, resolve the pending future
            await asyncio.sleep(0.01)
            for req_id, future in list(_pending_requests.items()):
                if not future.done():
                    future.set_result("screenshot_data_here")

        ws.send_json.side_effect = respond_to_ws

        result = await request_local_tool("screenshot", timeout=2.0)
        assert result == "screenshot_data_here"
        ws.send_json.assert_called_once()
        sent = ws.send_json.call_args[0][0]
        assert sent["action"] == "screenshot"
        assert "request_id" in sent

    @pytest.mark.asyncio
    async def test_should_ReturnTimeout_when_ClientDoesNotRespond(self):
        ws = AsyncMock()
        ws.send_json = AsyncMock()  # Does nothing -- no response comes
        _clients["c1"] = ws

        result = await request_local_tool("screenshot", timeout=0.1)
        assert "timed out" in result.lower()

    @pytest.mark.asyncio
    async def test_should_CleanupPending_when_TimeoutOccurs(self):
        ws = AsyncMock()
        ws.send_json = AsyncMock()
        _clients["c1"] = ws

        await request_local_tool("screenshot", timeout=0.1)
        assert len(_pending_requests) == 0  # cleaned up in finally

    @pytest.mark.asyncio
    async def test_should_PassParams_when_Provided(self):
        ws = AsyncMock()
        _clients["c1"] = ws

        async def respond(*a, **kw):
            await asyncio.sleep(0.01)
            for req_id, future in list(_pending_requests.items()):
                if not future.done():
                    future.set_result("ok")

        ws.send_json.side_effect = respond
        await request_local_tool("ocr", params={"format": "text"}, timeout=2.0)
        sent = ws.send_json.call_args[0][0]
        assert sent["params"] == {"format": "text"}

    @pytest.mark.asyncio
    async def test_should_DefaultParamsToEmptyDict_when_NoneProvided(self):
        ws = AsyncMock()
        _clients["c1"] = ws

        async def respond(*a, **kw):
            await asyncio.sleep(0.01)
            for req_id, future in list(_pending_requests.items()):
                if not future.done():
                    future.set_result("ok")

        ws.send_json.side_effect = respond
        await request_local_tool("arp_scan", timeout=2.0)
        sent = ws.send_json.call_args[0][0]
        assert sent["params"] == {}

    @pytest.mark.asyncio
    async def test_should_ReturnError_when_SendRaises(self):
        ws = AsyncMock()
        ws.send_json.side_effect = ConnectionError("pipe broken")
        _clients["c1"] = ws

        result = await request_local_tool("screenshot", timeout=1.0)
        assert "Error executing local tool" in result
