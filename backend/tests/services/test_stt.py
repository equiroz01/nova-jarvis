"""Tests for the Speech-to-Text service wrapper."""

from unittest.mock import patch, MagicMock


class TestTranscribeAudio:
    @patch("app.services.stt.speech.SpeechClient")
    def test_should_ReturnTranscript_when_RecognitionSucceeds(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        alt = MagicMock()
        alt.transcript = "Hello Jarvis"
        result_obj = MagicMock()
        result_obj.alternatives = [alt]
        mock_client.recognize.return_value = MagicMock(results=[result_obj])

        from app.services.stt import transcribe_audio
        text = transcribe_audio(b"\x00" * 100)

        assert text == "Hello Jarvis"

    @patch("app.services.stt.speech.SpeechClient")
    def test_should_ReturnEmptyString_when_NoResults(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.recognize.return_value = MagicMock(results=[])

        from app.services.stt import transcribe_audio
        text = transcribe_audio(b"\x00" * 100)

        assert text == ""

    @patch("app.services.stt.speech.SpeechClient")
    def test_should_JoinMultipleResults_when_MultipleSegments(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        alt1 = MagicMock()
        alt1.transcript = "Hello"
        r1 = MagicMock()
        r1.alternatives = [alt1]

        alt2 = MagicMock()
        alt2.transcript = "Jarvis"
        r2 = MagicMock()
        r2.alternatives = [alt2]

        mock_client.recognize.return_value = MagicMock(results=[r1, r2])

        from app.services.stt import transcribe_audio
        text = transcribe_audio(b"\x00" * 100)

        assert text == "Hello Jarvis"

    @patch("app.services.stt.speech.SpeechClient")
    def test_should_SkipEmptyAlternatives_when_ResultHasNone(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        r_empty = MagicMock()
        r_empty.alternatives = []

        alt = MagicMock()
        alt.transcript = "test"
        r_ok = MagicMock()
        r_ok.alternatives = [alt]

        mock_client.recognize.return_value = MagicMock(results=[r_empty, r_ok])

        from app.services.stt import transcribe_audio
        text = transcribe_audio(b"\x00" * 100)

        assert text == "test"

    @patch("app.services.stt.speech.SpeechClient")
    def test_should_UseProvidedLanguageCode_when_Specified(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.recognize.return_value = MagicMock(results=[])

        from app.services.stt import transcribe_audio
        transcribe_audio(b"\x00", language_code="es-ES")

        config_arg = mock_client.recognize.call_args[1]["config"]
        assert config_arg.language_code == "es-ES"

    @patch("app.services.stt.speech.SpeechClient")
    def test_should_IncludeSpanishAlt_when_Called(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.recognize.return_value = MagicMock(results=[])

        from app.services.stt import transcribe_audio
        transcribe_audio(b"\x00")

        config_arg = mock_client.recognize.call_args[1]["config"]
        assert "es-ES" in config_arg.alternative_language_codes

    @patch("app.services.stt.speech.SpeechClient")
    def test_should_PropagateException_when_ClientFails(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.recognize.side_effect = RuntimeError("quota exceeded")

        from app.services.stt import transcribe_audio
        import pytest
        with pytest.raises(RuntimeError, match="quota exceeded"):
            transcribe_audio(b"\x00")
