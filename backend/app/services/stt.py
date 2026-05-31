"""
N.O.V.A. STT — Local speech-to-text using faster-whisper.
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

    t0 = time.time()
    segments, info = model.transcribe(
        audio_stream,
        language=None,  # auto-detect Spanish/English
        vad_filter=True,  # filter out silence
        vad_parameters=dict(min_silence_duration_ms=500),
    )

    transcript = " ".join(s.text for s in segments).strip()
    elapsed = time.time() - t0

    logger.info(
        f"STT [{info.language}] ({elapsed:.2f}s): {transcript[:80]}..."
        if transcript else f"STT: no speech detected ({elapsed:.2f}s)"
    )

    return transcript
