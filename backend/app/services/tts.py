import re
import logging
from google.cloud import texttospeech

logger = logging.getLogger(__name__)

# Jarvis voice: Charon (Chirp3-HD) for both languages
VOICE_ES = ("es-US", "es-US-Chirp3-HD-Charon")
VOICE_EN = ("en-US", "en-US-Chirp3-HD-Charon")

# Spanish detection patterns
_SPANISH_WORDS = re.compile(
    r'\b(hola|aquí|tienes|puedes|noticias|buscar|hora|tiempo|qué|cómo|dónde|'
    r'cuándo|también|está|esto|gracias|por favor|claro|bueno|para|como|'
    r'las|los|del|una|pero|más|hoy|información|encuentra|siguiente|'
    r'espero|ayudar|útil|quiero|necesito|dime|sobre)\b',
    re.IGNORECASE
)
_SPANISH_CHARS = re.compile(r'[ñáéíóú¿¡]')


def _is_spanish(text: str) -> bool:
    """Detect if text is Spanish based on common words and characters."""
    if _SPANISH_CHARS.search(text):
        return True
    matches = _SPANISH_WORDS.findall(text)
    return len(matches) >= 2


def _strip_markdown(text: str) -> str:
    """Remove markdown formatting for cleaner TTS."""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'`(.+?)`', r'\1', text)
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
    text = re.sub(r'^#{1,3}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\d+[.)]\s+', '', text, flags=re.MULTILINE)
    return text.strip()


def synthesize_speech(text: str) -> bytes:
    """Convert text to speech using Google Cloud TTS with Orus voice."""
    client = texttospeech.TextToSpeechClient()

    clean_text = _strip_markdown(text)

    language_code, voice_name = VOICE_ES if _is_spanish(clean_text) else VOICE_EN

    response = client.synthesize_speech(
        input=texttospeech.SynthesisInput(text=clean_text),
        voice=texttospeech.VoiceSelectionParams(
            language_code=language_code,
            name=voice_name,
        ),
        audio_config=texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
        ),
    )

    logger.info(f"TTS [{voice_name}]: {len(response.audio_content)} bytes")
    return response.audio_content
