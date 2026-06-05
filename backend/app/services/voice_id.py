"""
NOVA Voice ID — Speaker verification using voice embeddings.
Learns the owner's voice and only responds to them.
"""

import io
import json
import logging
import wave
import numpy as np
from pathlib import Path
from resemblyzer import VoiceEncoder, preprocess_wav

logger = logging.getLogger(__name__)

VOICEPRINT_PATH = Path(__file__).parent.parent.parent / "voiceprint.json"
SIMILARITY_THRESHOLD = 0.72  # Minimum cosine similarity to accept as owner

_encoder: VoiceEncoder = None
_owner_embedding: np.ndarray = None


def _get_encoder() -> VoiceEncoder:
    global _encoder
    if _encoder is None:
        logger.info("Loading voice encoder...")
        _encoder = VoiceEncoder()
        logger.info("Voice encoder ready.")
    return _encoder


def load_voiceprint():
    """Load saved voiceprint from disk."""
    global _owner_embedding
    if VOICEPRINT_PATH.exists():
        try:
            data = json.loads(VOICEPRINT_PATH.read_text())
            _owner_embedding = np.array(data["embedding"])
            logger.info(f"Voiceprint loaded ({data.get('name', 'unknown')})")
            return True
        except Exception as e:
            logger.error(f"Error loading voiceprint: {e}")
    return False


def is_enrolled() -> bool:
    """Check if a voiceprint exists."""
    return _owner_embedding is not None


def _wav_bytes_to_array(wav_bytes: bytes) -> np.ndarray:
    """Convert WAV bytes to numpy array for resemblyzer."""
    wav_io = io.BytesIO(wav_bytes)
    try:
        with wave.open(wav_io) as wf:
            frames = wf.readframes(wf.getnframes())
            sample_width = wf.getsampwidth()
            n_channels = wf.getnchannels()
            sample_rate = wf.getframerate()

            if sample_width == 2:
                audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            elif sample_width == 4:
                audio = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
            else:
                audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

            if n_channels > 1:
                audio = audio[::n_channels]  # Take first channel

            return preprocess_wav(audio, source_sr=sample_rate)
    except Exception as e:
        logger.error(f"Error processing WAV: {e}")
        return np.array([])


def enroll(audio_samples: list[bytes], name: str = "owner") -> dict:
    """Create a voiceprint from multiple audio samples.

    Args:
        audio_samples: List of WAV bytes (3+ samples recommended)
        name: Name of the speaker

    Returns:
        dict with status and info
    """
    global _owner_embedding
    encoder = _get_encoder()

    embeddings = []
    for i, sample in enumerate(audio_samples):
        audio = _wav_bytes_to_array(sample)
        if len(audio) < 1600:  # Too short
            logger.warning(f"Sample {i+1} too short, skipping")
            continue
        emb = encoder.embed_utterance(audio)
        embeddings.append(emb)
        logger.info(f"Sample {i+1}: embedding created ({len(audio)} samples)")

    if len(embeddings) < 1:
        return {"status": "error", "detail": "No valid audio samples. Speak louder or longer."}

    # Average all embeddings for a robust voiceprint
    _owner_embedding = np.mean(embeddings, axis=0)

    # Save to disk
    data = {
        "name": name,
        "embedding": _owner_embedding.tolist(),
        "num_samples": len(embeddings),
    }
    VOICEPRINT_PATH.write_text(json.dumps(data))

    logger.info(f"Voiceprint created for '{name}' from {len(embeddings)} samples")
    return {
        "status": "ok",
        "name": name,
        "samples_used": len(embeddings),
    }


def verify(audio_bytes: bytes) -> tuple[bool, float]:
    """Verify if the audio matches the owner's voiceprint.

    Returns:
        (is_owner, similarity_score)
    """
    if _owner_embedding is None:
        return True, 1.0  # No voiceprint = accept everyone

    encoder = _get_encoder()
    audio = _wav_bytes_to_array(audio_bytes)

    if len(audio) < 1600:
        return False, 0.0  # Too short to verify

    emb = encoder.embed_utterance(audio)

    # Cosine similarity
    similarity = np.dot(_owner_embedding, emb) / (
        np.linalg.norm(_owner_embedding) * np.linalg.norm(emb)
    )
    similarity = float(similarity)

    is_owner = similarity >= SIMILARITY_THRESHOLD
    logger.info(f"Voice ID: similarity={similarity:.3f} threshold={SIMILARITY_THRESHOLD} → {'MATCH' if is_owner else 'REJECTED'}")

    return is_owner, similarity
