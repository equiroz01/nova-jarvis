"""Shared fixtures for Jarvis backend tests.

All external services (Gemini, Google Cloud STT/TTS, Gmail, Calendar,
Home Assistant, DuckDuckGo, WebSocket clients) are mocked at the fixture
level so no real API calls are ever made.
"""

from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Patch settings BEFORE importing anything that reads them at module level
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch, tmp_path):
    """Ensure every test gets safe, deterministic settings."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("ALLOWED_ORIGINS", "*")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "test-refresh-token")
    monkeypatch.setenv("HOME_ASSISTANT_URL", "http://ha-test.local:8123")
    monkeypatch.setenv("HOME_ASSISTANT_TOKEN", "test-ha-token")
    monkeypatch.setenv("ALEXA_SKILL_ID", "amzn1.ask.skill.test")
    # Isolate durable state (task + session SQLite) to a per-test temp dir, and
    # reset the cached connection / in-memory session cache so no state bleeds
    # across tests or into the real ~/.nova/data DB.
    monkeypatch.setenv("NOVA_HOME", str(tmp_path))
    import app.agent.session as _session
    import app.agent.session_store as _session_store
    _session._sessions.clear()
    if _session_store._conn is not None:
        _session_store._conn.close()
        _session_store._conn = None
    yield
    _session._sessions.clear()
    if _session_store._conn is not None:
        _session_store._conn.close()
        _session_store._conn = None


@pytest.fixture()
def mock_agent_executor():
    """Return a mock AgentExecutor whose invoke() returns a canned response."""
    executor = MagicMock()
    executor.invoke.return_value = {"output": "Mocked agent response"}
    return executor


@pytest.fixture()
def client(mock_agent_executor):
    """Synchronous TestClient with a mocked agent executor.

    We replace the app lifespan with a no-op version that injects our mock
    executor, so the real build_agent (which calls Gemini) is never invoked.
    """
    from app.main import app

    @asynccontextmanager
    async def _test_lifespan(app_instance):
        app_instance.state.agent_executor = mock_agent_executor
        yield

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _test_lifespan
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.router.lifespan_context = original_lifespan


@pytest.fixture()
def mock_google_creds():
    """Mocked Google OAuth2 credentials that never hit the network."""
    creds = MagicMock()
    creds.token = "mock-access-token"
    creds.valid = True
    creds.expired = False
    return creds
