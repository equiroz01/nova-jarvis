"""
NOVA STT — Local speech-to-text using faster-whisper.
Runs on CPU, no API key needed, supports Spanish and English.
"""

import io
import logging
import time
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

# Singleton model — loaded once at startup
_model: WhisperModel = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        logger.info("Loading Whisper model (base)...")
        t0 = time.time()
        _model = WhisperModel("small", device="cpu", compute_type="int8")
        logger.info(f"Whisper model loaded in {time.time()-t0:.1f}s")
    return _model


def load_model():
    """Pre-load the model at startup."""
    _get_model()


def transcribe_audio(
    audio_bytes: bytes,
    language_code: str = None,
    **kwargs,
) -> str:
    """Transcribe audio bytes using faster-whisper locally."""
    model = _get_model()

    audio_stream = io.BytesIO(audio_bytes)

    # Force Spanish — user speaks Spanish. Prevents Whisper from
    # hallucinating Japanese/Russian/English on short noisy audio.
    lang = "es"
    if language_code and language_code.startswith("en"):
        lang = "en"

    # Prompt biasing: helps Whisper distinguish "Nova" from "nueva", etc.
    prompt_hint = {
        "es": "Nova es la asistente virtual. Nova, Hypernova Labs, Salome.",
        "en": "Nova is the virtual assistant. Nova, Hypernova Labs.",
    }

    t0 = time.time()
    segments, info = model.transcribe(
        audio_stream,
        language=lang,
        initial_prompt=prompt_hint.get(lang, prompt_hint["es"]),
        beam_size=3,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
    )

    transcript = " ".join(s.text for s in segments).strip()
    elapsed = time.time() - t0

    # Filter out Whisper hallucinations on silence/noise
    if transcript and len(transcript) < 4 and not any(c.isalpha() for c in transcript):
        transcript = ""

    logger.info(
        f"STT [{lang}] ({elapsed:.2f}s): {transcript[:80]}..."
        if transcript else f"STT: no speech detected ({elapsed:.2f}s)"
    )

    return transcript
