"""Tests for POST /voice endpoint."""

import base64
from io import BytesIO
from unittest.mock import patch, MagicMock


class TestVoiceEndpoint:
    """Tests for the /voice endpoint that chains STT -> Agent -> TTS."""

    # ---- Happy path ----

    @patch("app.api.routes_voice.synthesize_speech", return_value=b"\x00\x01\x02")
    @patch("app.api.routes_voice.transcribe_audio", return_value="Hello Jarvis")
    def test_should_Return200_when_ValidAudioProvided(
        self, mock_stt, mock_tts, client
    ):
        audio_bytes = b"\x00" * 100
        resp = client.post(
            "/voice",
            files={"audio": ("test.wav", BytesIO(audio_bytes), "audio/wav")},
            data={"session_id": "s1", "language": "en-US"},
        )
        assert resp.status_code == 200

    @patch("app.api.routes_voice.synthesize_speech", return_value=b"\xff\xd8audio")
    @patch("app.api.routes_voice.transcribe_audio", return_value="Hello")
    def test_should_ReturnTranscript_when_STTSucceeds(
        self, mock_stt, mock_tts, client
    ):
        resp = client.post(
            "/voice",
            files={"audio": ("test.wav", BytesIO(b"\x00" * 50), "audio/wav")},
            data={"session_id": "s1"},
        )
        data = resp.json()
        assert data["transcript"] == "Hello"
        assert data["response"] == "Mocked agent response"
        assert data["session_id"] == "s1"

    @patch("app.api.routes_voice.synthesize_speech", return_value=b"\xab\xcd")
    @patch("app.api.routes_voice.transcribe_audio", return_value="Hi")
    def test_should_ReturnBase64Audio_when_TTSSucceeds(
        self, mock_stt, mock_tts, client
    ):
        resp = client.post(
            "/voice",
            files={"audio": ("test.wav", BytesIO(b"\x00" * 50), "audio/wav")},
        )
        data = resp.json()
        decoded = base64.b64decode(data["audio_base64"])
        assert decoded == b"\xab\xcd"

    # ---- Error paths ----

    def test_should_Return422_when_NoAudioFile(self, client):
        resp = client.post("/voice")
        assert resp.status_code == 422

    @patch("app.api.routes_voice.transcribe_audio", return_value="Hi")
    def test_should_Return400_when_AudioFileIsEmpty(self, mock_stt, client):
        resp = client.post(
            "/voice",
            files={"audio": ("empty.wav", BytesIO(b""), "audio/wav")},
        )
        assert resp.status_code == 400
        assert "Empty audio" in resp.json()["detail"]

    @patch("app.api.routes_voice.transcribe_audio", return_value="")
    def test_should_Return400_when_STTReturnsEmptyTranscript(self, mock_stt, client):
        resp = client.post(
            "/voice",
            files={"audio": ("test.wav", BytesIO(b"\x00" * 50), "audio/wav")},
        )
        assert resp.status_code == 400
        assert "transcribe" in resp.json()["detail"].lower()

    @patch("app.api.routes_voice.transcribe_audio", side_effect=RuntimeError("STT service down"))
    def test_should_Return500_when_STTFails(self, mock_stt, client):
        resp = client.post(
            "/voice",
            files={"audio": ("test.wav", BytesIO(b"\x00" * 50), "audio/wav")},
        )
        assert resp.status_code == 500
        assert "Speech recognition failed" in resp.json()["detail"]

    @patch("app.api.routes_voice.synthesize_speech", side_effect=RuntimeError("TTS down"))
    @patch("app.api.routes_voice.transcribe_audio", return_value="Hello")
    def test_should_ReturnEmptyAudio_when_TTSFails(self, mock_stt, mock_tts, client):
        """TTS failure is non-fatal -- returns empty audio_base64 but 200."""
        resp = client.post(
            "/voice",
            files={"audio": ("test.wav", BytesIO(b"\x00" * 50), "audio/wav")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["audio_base64"] == ""
        assert data["response"] == "Mocked agent response"

    @patch("app.api.routes_voice.transcribe_audio", return_value="Hi")
    def test_should_Return500_when_AgentFails(self, mock_stt, client, mock_agent_executor):
        mock_agent_executor.invoke.side_effect = RuntimeError("LLM boom")
        resp = client.post(
            "/voice",
            files={"audio": ("test.wav", BytesIO(b"\x00" * 50), "audio/wav")},
        )
        assert resp.status_code == 500
        assert "Agent error" in resp.json()["detail"]

    # ---- Session handling ----

    @patch("app.api.routes_voice.synthesize_speech", return_value=b"x")
    @patch("app.api.routes_voice.transcribe_audio", return_value="Hi")
    def test_should_GenerateSessionId_when_NotProvided(self, mock_stt, mock_tts, client):
        resp = client.post(
            "/voice",
            files={"audio": ("test.wav", BytesIO(b"\x00" * 50), "audio/wav")},
        )
        data = resp.json()
        assert len(data["session_id"]) == 36  # UUID

    # ---- Language detection ----

    @patch("app.api.routes_voice.synthesize_speech", return_value=b"x")
    @patch("app.api.routes_voice.transcribe_audio", return_value="Hola")
    def test_should_PassLanguageToSTT_when_SpanishSpecified(
        self, mock_stt, mock_tts, client
    ):
        client.post(
            "/voice",
            files={"audio": ("test.wav", BytesIO(b"\x00" * 50), "audio/wav")},
            data={"language": "es-ES"},
        )
        mock_stt.assert_called_once_with(b"\x00" * 50, language_code="es-ES")
