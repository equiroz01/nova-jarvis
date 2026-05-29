import logging
from google.cloud import speech

logger = logging.getLogger(__name__)


def transcribe_audio(
    audio_bytes: bytes,
    sample_rate_hertz: int = 16000,
    language_code: str = "en-US",
    encoding: speech.RecognitionConfig.AudioEncoding = speech.RecognitionConfig.AudioEncoding.LINEAR16,
) -> str:
    """Transcribe audio bytes using Google Cloud Speech-to-Text."""
    client = speech.SpeechClient()

    audio = speech.RecognitionAudio(content=audio_bytes)
    config = speech.RecognitionConfig(
        encoding=encoding,
        sample_rate_hertz=sample_rate_hertz,
        language_code=language_code,
        alternative_language_codes=["es-ES"],
        enable_automatic_punctuation=True,
    )

    response = client.recognize(config=config, audio=audio)

    if not response.results:
        return ""

    transcript = " ".join(
        result.alternatives[0].transcript
        for result in response.results
        if result.alternatives
    )
    logger.info(f"Transcribed: {transcript}")
    return transcript
