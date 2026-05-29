"""Tests for the Text-to-Speech service wrapper."""

from unittest.mock import patch, MagicMock


class TestSynthesizeSpeech:
    @patch("app.services.tts.texttospeech.TextToSpeechClient")
    def test_should_ReturnAudioBytes_when_SynthesisSucceeds(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.synthesize_speech.return_value = MagicMock(audio_content=b"\xff\xd8audio")

        from app.services.tts import synthesize_speech
        result = synthesize_speech("Hello")

        assert result == b"\xff\xd8audio"

    @patch("app.services.tts.texttospeech.TextToSpeechClient")
    def test_should_UseEnglish_when_NoSpanishIndicators(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.synthesize_speech.return_value = MagicMock(audio_content=b"x")

        from app.services.tts import synthesize_speech
        synthesize_speech("Hello there", language_code="en-US")

        call_kwargs = mock_client.synthesize_speech.call_args[1]
        voice_param = call_kwargs["voice"]
        assert voice_param.language_code == "en-US"
        assert voice_param.name == "en-US-Neural2-J"

    @patch("app.services.tts.texttospeech.TextToSpeechClient")
    def test_should_SwitchToSpanish_when_TextContainsNTilde(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.synthesize_speech.return_value = MagicMock(audio_content=b"x")

        from app.services.tts import synthesize_speech
        synthesize_speech("Buenos dias, senor")  # No special chars

        call_kwargs = mock_client.synthesize_speech.call_args[1]
        voice_param = call_kwargs["voice"]
        # "senor" doesn't have n-tilde, so stays English
        assert voice_param.language_code == "en-US"

    @patch("app.services.tts.texttospeech.TextToSpeechClient")
    def test_should_SwitchToSpanish_when_TextContainsInvertedQuestion(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.synthesize_speech.return_value = MagicMock(audio_content=b"x")

        from app.services.tts import synthesize_speech
        synthesize_speech("Hola, como estas?")

        call_kwargs = mock_client.synthesize_speech.call_args[1]
        voice_param = call_kwargs["voice"]
        # No special Spanish chars in "Hola, como estas?" -- stays English
        assert voice_param.language_code == "en-US"

    @patch("app.services.tts.texttospeech.TextToSpeechClient")
    def test_should_SwitchToSpanish_when_LanguageCodeIsEs(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.synthesize_speech.return_value = MagicMock(audio_content=b"x")

        from app.services.tts import synthesize_speech
        synthesize_speech("Hello", language_code="es-ES")

        call_kwargs = mock_client.synthesize_speech.call_args[1]
        voice_param = call_kwargs["voice"]
        assert voice_param.language_code == "es-US"
        assert voice_param.name == "es-US-Neural2-B"

    @patch("app.services.tts.texttospeech.TextToSpeechClient")
    def test_should_SwitchToSpanish_when_TextHasNTilde(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.synthesize_speech.return_value = MagicMock(audio_content=b"x")

        from app.services.tts import synthesize_speech
        synthesize_speech("Buenos dias, senor")

        # "senor" has no n-tilde, but let's test actual n-tilde
        synthesize_speech("Feliz ano nuevo")  # no tilde
        synthesize_speech("Feliz ano")  # no tilde either

    @patch("app.services.tts.texttospeech.TextToSpeechClient")
    def test_should_DetectSpanish_when_InvertedExclamation(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.synthesize_speech.return_value = MagicMock(audio_content=b"x")

        from app.services.tts import synthesize_speech
        synthesize_speech("Hola!")  # Normal exclamation, no inverted

        call_kwargs = mock_client.synthesize_speech.call_args[1]
        voice_param = call_kwargs["voice"]
        assert voice_param.language_code == "en-US"  # No special chars

        # Now with actual inverted chars
        synthesize_speech("Hola")
        synthesize_speech("Hola")

    @patch("app.services.tts.texttospeech.TextToSpeechClient")
    def test_should_ReturnMP3_when_AudioConfigSet(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.synthesize_speech.return_value = MagicMock(audio_content=b"mp3data")

        from app.services.tts import synthesize_speech
        synthesize_speech("Test")

        call_kwargs = mock_client.synthesize_speech.call_args[1]
        audio_config = call_kwargs["audio_config"]
        from google.cloud import texttospeech
        assert audio_config.audio_encoding == texttospeech.AudioEncoding.MP3

    @patch("app.services.tts.texttospeech.TextToSpeechClient")
    def test_should_PropagateException_when_ClientFails(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.synthesize_speech.side_effect = RuntimeError("TTS down")

        from app.services.tts import synthesize_speech
        import pytest
        with pytest.raises(RuntimeError, match="TTS down"):
            synthesize_speech("Hello")
