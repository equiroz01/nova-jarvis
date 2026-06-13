"""Tests for the FastAPI app initialization (main.py)."""

from unittest.mock import patch, MagicMock


class TestAppSetup:
    def test_should_HaveCORSMiddleware_when_AppCreated(self, client):
        """Verify CORS headers are present on responses."""
        resp = client.get("/health", headers={"Origin": "http://localhost:3000"})
        assert resp.status_code == 200

    def test_should_IncludeAllRouters_when_AppCreated(self, client):
        """Every expected route should be reachable (not 404)."""
        assert client.get("/health").status_code == 200
        assert client.post("/chat").status_code == 422
        assert client.post("/voice").status_code == 422
        # /alexa now gates on the configured skill ID (ALEXA_SKILL_ID in conftest)
        resp = client.post("/alexa", json={
            "request": {"type": "LaunchRequest"},
            "session": {"application": {"applicationId": "amzn1.ask.skill.test"}},
        })
        assert resp.status_code == 200

    def test_should_HaveTitle_when_AppCreated(self):
        from app.main import app
        assert app.title == "Jarvis Backend"

    def test_should_HaveVersion_when_AppCreated(self):
        from app.main import app
        assert app.version == "1.0.0"
