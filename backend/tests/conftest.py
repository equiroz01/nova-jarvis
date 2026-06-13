"""Shared fixtures for Jarvis backend tests.

All external services (Gemini, Google Cloud STT/TTS, Gmail, Calendar,
Home Assistant, DuckDuckGo, WebSocket clients) are mocked at the fixture
level so no real API calls are ever made.
"""

import os
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Set the critical env vars at MODULE level (conftest is imported before test
# collection) so the pydantic `settings` singleton is built with test values no
# matter when it is first constructed — i.e. even if a test module imports an app
# module at import time. The autouse fixture below still re-applies them per-test.
_TEST_ENV = {
    "GEMINI_API_KEY": "test-gemini-key",
    "ALLOWED_ORIGINS": "*",
    "LOG_LEVEL": "WARNING",
    "GOOGLE_CLIENT_ID": "test-client-id",
    "GOOGLE_CLIENT_SECRET": "test-client-secret",
    "GOOGLE_REFRESH_TOKEN": "test-refresh-token",
    "HOME_ASSISTANT_URL": "http://ha-test.local:8123",
    "HOME_ASSISTANT_TOKEN": "test-ha-token",
    "ALEXA_SKILL_ID": "amzn1.ask.skill.test",
}
for _k, _v in _TEST_ENV.items():
    os.environ.setdefault(_k, _v)


# ---------------------------------------------------------------------------
# Patch settings BEFORE importing anything that reads them at module level
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch, tmp_path):
    """Ensure every test gets safe, deterministic settings."""
    for _k, _v in _TEST_ENV.items():
        monkeypatch.setenv(_k, _v)
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
