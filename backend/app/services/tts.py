import logging
from google.cloud import texttospeech

logger = logging.getLogger(__name__)


def synthesize_speech(
    text: str,
    language_code: str = "en-US",
    voice_name: str = "en-US-Neural2-J",
) -> bytes:
    """Convert text to speech using Google Cloud Text-to-Speech. Returns MP3 bytes."""
    client = texttospeech.TextToSpeechClient()

    # Auto-detect Spanish
    if any(c in text.lower() for c in ["ñ", "¿", "¡"]) or language_code.startswith("es"):
        language_code = "es-US"
        voice_name = "es-US-Neural2-B"

    synthesis_input = texttospeech.SynthesisInput(text=text)

    voice = texttospeech.VoiceSelectionParams(
        language_code=language_code,
        name=voice_name,
    )

    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=1.0,
        pitch=0.0,
    )

    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config,
    )

    logger.info(f"Synthesized {len(response.audio_content)} bytes of audio")
    return response.audio_content
