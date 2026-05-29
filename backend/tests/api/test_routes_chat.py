"""Tests for POST /chat endpoint."""

from unittest.mock import patch, MagicMock


class TestChatEndpoint:
    # ---- Happy path ----

    def test_should_Return200_when_ValidMessage(self, client):
        resp = client.post("/chat", json={"message": "Hello Jarvis"})
        assert resp.status_code == 200

    def test_should_ReturnAgentResponse_when_ValidMessage(self, client):
        data = client.post("/chat", json={"message": "Hello"}).json()
        assert data["response"] == "Mocked agent response"

    def test_should_ReturnSessionId_when_ProvidedByClient(self, client):
        data = client.post(
            "/chat", json={"message": "Hi", "session_id": "my-session-42"}
        ).json()
        assert data["session_id"] == "my-session-42"

    def test_should_GenerateSessionId_when_NotProvided(self, client):
        data = client.post("/chat", json={"message": "Hi"}).json()
        assert data["session_id"]  # non-empty UUID string
        assert len(data["session_id"]) == 36  # UUID format

    # ---- Validation / error paths ----

    def test_should_Return400_when_MessageIsEmpty(self, client):
        resp = client.post("/chat", json={"message": ""})
        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"].lower()

    def test_should_Return400_when_MessageIsWhitespace(self, client):
        resp = client.post("/chat", json={"message": "   "})
        assert resp.status_code == 400

    def test_should_Return422_when_MessageFieldMissing(self, client):
        resp = client.post("/chat", json={})
        assert resp.status_code == 422

    def test_should_Return422_when_BodyIsNotJson(self, client):
        resp = client.post("/chat", content=b"not json", headers={"Content-Type": "application/json"})
        assert resp.status_code == 422

    def test_should_Return500_when_AgentRaisesException(self, client, mock_agent_executor):
        mock_agent_executor.invoke.side_effect = RuntimeError("LLM down")
        resp = client.post("/chat", json={"message": "Hello"})
        assert resp.status_code == 500
        assert "Agent error" in resp.json()["detail"]

    # ---- Session isolation ----

    def test_should_PassSessionIdToAgent_when_Provided(self, client, mock_agent_executor):
        with patch("app.api.routes_chat.invoke_agent", wraps=lambda m, s, e: "ok") as mock_invoke:
            client.post("/chat", json={"message": "test", "session_id": "sess-1"})
            mock_invoke.assert_called_once_with("test", "sess-1", mock_agent_executor)

    # ---- Edge cases ----

    def test_should_HandleUnicodeMessage_when_SpanishInput(self, client):
        resp = client.post("/chat", json={"message": "Hola, como estas?"})
        assert resp.status_code == 200

    def test_should_HandleVeryLongMessage_when_InputIsLarge(self, client):
        long_msg = "a" * 10_000
        resp = client.post("/chat", json={"message": long_msg})
        assert resp.status_code == 200

    def test_should_HandleSpecialCharacters_when_InputHasNewlines(self, client):
        resp = client.post("/chat", json={"message": "line1\nline2\ttab"})
        assert resp.status_code == 200
