"""Tests for POST /alexa endpoint (Alexa webhook handler)."""

from unittest.mock import patch

# Matches ALEXA_SKILL_ID set in conftest._patch_settings. Every real Alexa request
# carries this applicationId, and /alexa now gates on it (fail-closed) — see 1.3.
TEST_SKILL_ID = "amzn1.ask.skill.test"


def _alexa_request(request_type, intent_name=None, slots=None, user_id="user-123"):
    """Helper to build an Alexa-shaped JSON body."""
    body = {
        "session": {
            "user": {"userId": user_id},
            "application": {"applicationId": TEST_SKILL_ID},
        },
        "request": {"type": request_type},
    }
    if intent_name:
        body["request"]["intent"] = {"name": intent_name}
        if slots:
            body["request"]["intent"]["slots"] = slots
    return body


class TestAlexaLaunchRequest:
    def test_should_ReturnGreeting_when_LaunchRequestReceived(self, client):
        body = _alexa_request("LaunchRequest")
        resp = client.post("/alexa", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "1.0"
        assert "Jarvis" in data["response"]["outputSpeech"]["text"]
        assert data["response"]["shouldEndSession"] is False


class TestAlexaStopAndCancel:
    def test_should_SayGoodbye_when_StopIntent(self, client):
        body = _alexa_request("IntentRequest", "AMAZON.StopIntent")
        data = client.post("/alexa", json=body).json()
        assert "Goodbye" in data["response"]["outputSpeech"]["text"]
        assert data["response"]["shouldEndSession"] is True

    def test_should_SayGoodbye_when_CancelIntent(self, client):
        body = _alexa_request("IntentRequest", "AMAZON.CancelIntent")
        data = client.post("/alexa", json=body).json()
        assert data["response"]["shouldEndSession"] is True


class TestAlexaHelpIntent:
    def test_should_ReturnCapabilities_when_HelpIntentReceived(self, client):
        body = _alexa_request("IntentRequest", "AMAZON.HelpIntent")
        data = client.post("/alexa", json=body).json()
        text = data["response"]["outputSpeech"]["text"]
        assert "calendar" in text.lower()
        assert "smart home" in text.lower()


class TestAlexaAskJarvisIntent:
    def test_should_ReturnAgentResponse_when_QueryProvided(self, client):
        body = _alexa_request(
            "IntentRequest",
            "AskJarvisIntent",
            slots={"query": {"value": "What time is it?"}},
        )
        data = client.post("/alexa", json=body).json()
        assert data["response"]["outputSpeech"]["text"] == "Mocked agent response"

    def test_should_AskForRepeat_when_QuerySlotEmpty(self, client):
        body = _alexa_request(
            "IntentRequest",
            "AskJarvisIntent",
            slots={"query": {"value": ""}},
        )
        data = client.post("/alexa", json=body).json()
        assert "didn't catch" in data["response"]["outputSpeech"]["text"].lower()

    def test_should_AskForRepeat_when_QuerySlotMissing(self, client):
        body = _alexa_request("IntentRequest", "AskJarvisIntent", slots={})
        data = client.post("/alexa", json=body).json()
        assert "didn't catch" in data["response"]["outputSpeech"]["text"].lower()

    def test_should_PrefixSessionWithAlexa_when_UserIdProvided(
        self, client, mock_agent_executor
    ):
        with patch("app.api.routes_alexa.invoke_agent", wraps=lambda m, s, e: "ok") as mock_invoke:
            body = _alexa_request(
                "IntentRequest",
                "AskJarvisIntent",
                slots={"query": {"value": "test"}},
                user_id="amzn-user-1",
            )
            client.post("/alexa", json=body)
            _, call_args, _ = mock_invoke.mock_calls[0]
            assert call_args[1] == "alexa-amzn-user-1"

    def test_should_ReturnErrorMessage_when_AgentFails(
        self, client, mock_agent_executor
    ):
        mock_agent_executor.invoke.side_effect = RuntimeError("boom")
        body = _alexa_request(
            "IntentRequest",
            "AskJarvisIntent",
            slots={"query": {"value": "test"}},
        )
        data = client.post("/alexa", json=body).json()
        assert "error" in data["response"]["outputSpeech"]["text"].lower()
        assert data["response"]["shouldEndSession"] is False


class TestAlexaSessionEnd:
    def test_should_EndSession_when_SessionEndedRequest(self, client):
        body = _alexa_request("SessionEndedRequest")
        data = client.post("/alexa", json=body).json()
        assert data["response"]["shouldEndSession"] is True

    def test_should_ReturnEmptyText_when_SessionEndedRequest(self, client):
        body = _alexa_request("SessionEndedRequest")
        data = client.post("/alexa", json=body).json()
        assert data["response"]["outputSpeech"]["text"] == ""


class TestAlexaUnknownRequest:
    def test_should_ReturnFallback_when_UnknownRequestType(self, client):
        body = _alexa_request("SomeNewRequestType")
        data = client.post("/alexa", json=body).json()
        assert "not sure" in data["response"]["outputSpeech"]["text"].lower()

    def test_should_ReturnFallback_when_UnknownIntent(self, client):
        body = _alexa_request("IntentRequest", "SomeCustomIntent")
        data = client.post("/alexa", json=body).json()
        # Falls through all known intents to the default
        assert "not sure" in data["response"]["outputSpeech"]["text"].lower()


class TestAlexaResponseFormat:
    def test_should_ContainVersion_when_AnyResponse(self, client):
        body = _alexa_request("LaunchRequest")
        data = client.post("/alexa", json=body).json()
        assert data["version"] == "1.0"

    def test_should_ContainOutputSpeech_when_AnyResponse(self, client):
        body = _alexa_request("LaunchRequest")
        data = client.post("/alexa", json=body).json()
        assert data["response"]["outputSpeech"]["type"] == "PlainText"


class TestAlexaSkillIdGate:
    """The /alexa endpoint is public (Amazon controls the request), so it must
    fail closed: reject anything not carrying the configured skill ID."""

    def test_should_Reject_when_SkillIdMissing(self, client):
        body = {"request": {"type": "LaunchRequest"}, "session": {}}
        resp = client.post("/alexa", json=body)
        assert resp.status_code == 403

    def test_should_Reject_when_SkillIdMismatch(self, client):
        body = _alexa_request("LaunchRequest")
        body["session"]["application"]["applicationId"] = "amzn1.ask.skill.ATTACKER"
        resp = client.post("/alexa", json=body)
        assert resp.status_code == 403

    def test_should_Accept_when_SkillIdInContextOnly(self, client):
        # SessionEndedRequest et al. carry the id under context.System, not session
        body = {
            "request": {"type": "LaunchRequest"},
            "context": {"System": {"application": {"applicationId": TEST_SKILL_ID}}},
        }
        resp = client.post("/alexa", json=body)
        assert resp.status_code == 200

    def test_should_Reject_when_SkillIdNotConfigured(self, client, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "alexa_skill_id", None)
        body = _alexa_request("LaunchRequest")
        resp = client.post("/alexa", json=body)
        assert resp.status_code == 403
