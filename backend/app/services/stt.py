"""
NOVA STT — Hybrid speech-to-text.
Local faster-whisper (free, private, no network) as primary;
Google Cloud Speech as automatic fallback when local confidence is low,
or as forced provider for external devices.
"""

import io
import logging
import time
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

# Singleton model — loaded once at startup
_model: WhisperModel = None

# Google Cloud Speech client (lazy) — None until first use, False if unavailable
_google_client = None

# Below this avg_logprob the local transcript is considered unreliable
# (typical values: > -0.3 great, < -0.8 garbage/hallucination territory)
CONFIDENCE_FALLBACK_THRESHOLD = -0.75


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        logger.info("Loading Whisper model (small)...")
        t0 = time.time()
        _model = WhisperModel("small", device="cpu", compute_type="int8")
        logger.info(f"Whisper model loaded in {time.time()-t0:.1f}s")
    return _model


def load_model():
    """Pre-load the model at startup."""
    _get_model()


def is_loaded() -> bool:
    """True if the Whisper model is loaded and ready (for /health probes)."""
    return _model is not None


def _transcribe_local(audio_bytes: bytes, lang: str) -> tuple[str, float]:
    """Transcribe with faster-whisper. Returns (transcript, confidence)
    where confidence is the duration-weighted avg_logprob across segments."""
    model = _get_model()
    audio_stream = io.BytesIO(audio_bytes)

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
        beam_size=1,  # greedy — short conversational utterances, ~2x faster than beam 3
        condition_on_previous_text=False,  # avoids repetition loops, slightly faster
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
    )

    seg_list = list(segments)
    transcript = " ".join(s.text for s in seg_list).strip()
    elapsed = time.time() - t0

    # Duration-weighted confidence
    confidence = 0.0
    total_dur = sum(max(s.end - s.start, 0.01) for s in seg_list)
    if seg_list and total_dur > 0:
        confidence = sum(s.avg_logprob * max(s.end - s.start, 0.01) for s in seg_list) / total_dur

    # Filter out Whisper hallucinations on silence/noise
    if transcript and len(transcript) < 4 and not any(c.isalpha() for c in transcript):
        transcript = ""

    logger.info(
        f"STT local [{lang}] ({elapsed:.2f}s, conf={confidence:.2f}): {transcript[:80]}"
        if transcript else f"STT local: no speech detected ({elapsed:.2f}s)"
    )
    return transcript, confidence


def _decode_to_pcm16_mono_16k(audio_bytes: bytes) -> bytes:
    """Decode arbitrary audio (m4a/AAC/ogg/…) to raw PCM s16le, mono, 16 kHz.

    Mobile clients (Expo) record in m4a/AAC. faster-whisper decodes those
    natively via PyAV, but Google Cloud Speech needs LINEAR16 — so we
    transcode here before the Google fallback. Raises on failure.
    """
    import av  # PyAV — already a faster-whisper dependency

    container = av.open(io.BytesIO(audio_bytes))
    try:
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
        pcm = bytearray()
        for frame in container.decode(audio=0):
            for rframe in resampler.resample(frame):
                pcm += bytes(rframe.planes[0])
        # Flush any samples buffered inside the resampler.
        for rframe in resampler.resample(None):
            pcm += bytes(rframe.planes[0])
        return bytes(pcm)
    finally:
        container.close()


def _get_google_client():
    """Lazy Google Speech client. Returns None if lib/credentials unavailable."""
    global _google_client
    if _google_client is False:
        return None
    if _google_client is None:
        try:
            from google.cloud import speech
            _google_client = speech.SpeechClient()
        except Exception as e:
            logger.warning(f"Google STT unavailable, local-only mode: {e}")
            _google_client = False
            return None
    return _google_client


def _transcribe_google(audio_bytes: bytes, lang: str) -> str:
    """Transcribe with Google Cloud Speech. Raises on failure."""
    from google.cloud import speech
    client = _get_google_client()
    if client is None:
        raise RuntimeError("Google STT client unavailable")

    config_kwargs = dict(
        # es-US = Latin American Spanish; es-PA isn't supported by latest_short
        language_code="es-US" if lang == "es" else "en-US",
        enable_automatic_punctuation=True,
        # latest_short: optimized for voice commands. NOTE: it does not
        # support alternative_language_codes — don't add them here.
        model="latest_short",
        # Same biasing as the Whisper prompt hint — without it Google hears "noah"
        speech_contexts=[speech.SpeechContext(
            phrases=["Nova", "Hypernova Labs", "Salome", "NAOS", "AgilityTask"],
            boost=15.0,
        )],
    )
    content = audio_bytes
    if not audio_bytes.startswith(b"RIFF"):
        # Not a WAV container. Could be raw PCM (browser) or m4a/AAC (mobile).
        # Compressed formats must be transcoded; raw PCM passes through.
        try:
            content = _decode_to_pcm16_mono_16k(audio_bytes)
        except Exception as e:
            logger.warning(f"Audio transcode failed, sending bytes as-is: {e}")
        config_kwargs["encoding"] = speech.RecognitionConfig.AudioEncoding.LINEAR16
        config_kwargs["sample_rate_hertz"] = 16000

    t0 = time.time()
    response = client.recognize(
        config=speech.RecognitionConfig(**config_kwargs),
        audio=speech.RecognitionAudio(content=content),
        timeout=10,  # fast-fail back to local — never stall the voice turn
        retry=None,
    )
    transcript = " ".join(
        r.alternatives[0].transcript for r in response.results if r.alternatives
    ).strip()
    logger.info(f"STT google [{lang}] ({time.time()-t0:.2f}s): {transcript[:80]}")
    return transcript


def transcribe_audio(
    audio_bytes: bytes,
    language_code: str = None,
    provider: str = "auto",
    **kwargs,
) -> str:
    """Hybrid transcription.

    provider:
      - "auto"   (default): local whisper first; if empty or low confidence,
                  retry with Google Cloud Speech.
      - "local":  whisper only (private, offline).
      - "google": Google first (external devices / noisy environments),
                  local as fallback if Google errors.
    """
    # Force Spanish — user speaks Spanish. Prevents Whisper from
    # hallucinating Japanese/Russian/English on short noisy audio.
    lang = "es"
    if language_code and language_code.startswith("en"):
        lang = "en"

    if provider == "google":
        try:
            transcript = _transcribe_google(audio_bytes, lang)
            if transcript:
                return transcript
        except Exception as e:
            logger.warning(f"Google STT failed, falling back to local: {e}")
        transcript, _ = _transcribe_local(audio_bytes, lang)
        return transcript

    transcript, confidence = _transcribe_local(audio_bytes, lang)

    if provider == "local":
        return transcript

    # auto: rescue empty or low-confidence local results with Google
    if (not transcript or confidence < CONFIDENCE_FALLBACK_THRESHOLD) and _get_google_client():
        try:
            google_transcript = _transcribe_google(audio_bytes, lang)
            if google_transcript:
                logger.info(
                    f"STT hybrid: Google rescued low-confidence local "
                    f"(conf={confidence:.2f}, local='{transcript[:40]}')"
                )
                return google_transcript
        except Exception as e:
            logger.warning(f"Google STT fallback failed: {e}")

    return transcript
