"""
Voice Activity Detection using Silero VAD.

Detects human speech only — ignores music, TV, fan noise, background chatter.
Returns audio chunks only when someone is actively speaking into the mic.
"""

import logging
import struct
import numpy as np
import torch

logger = logging.getLogger(__name__)

# Silero VAD model
_model = None
_SAMPLE_RATE = 16000
_FRAME_MS = 32  # 32ms frames (512 samples at 16kHz — Silero minimum)
_FRAME_SIZE = 512

# Thresholds
SPEECH_THRESHOLD = 0.5  # probability above this = speech
SILENCE_FRAMES = 30  # ~900ms of silence to end utterance
MIN_SPEECH_FRAMES = 10  # ~300ms minimum to count as real speech


def load_model():
    """Load Silero VAD model (tiny, CPU, ~1MB)."""
    global _model
    if _model is not None:
        return _model
    logger.info("Loading Silero VAD model...")
    _model, _ = torch.hub.load(
        repo_or_dir="snakers4/silero-vad",
        model="silero_vad",
        force_reload=False,
        onnx=False,
    )
    logger.info("Silero VAD ready")
    return _model


def is_speech(audio_chunk: np.ndarray) -> float:
    """Check if audio chunk contains speech. Returns probability 0.0-1.0."""
    model = load_model()
    if len(audio_chunk) != _FRAME_SIZE:
        return 0.0
    tensor = torch.from_numpy(audio_chunk.astype(np.float32))
    if tensor.abs().max() > 1.0:
        tensor = tensor / 32768.0  # normalize int16 to float
    with torch.no_grad():
        prob = model(tensor, _SAMPLE_RATE).item()
    return prob


def reset():
    """Reset VAD model state between utterances."""
    if _model is not None:
        _model.reset_states()


def _to_wav(audio: np.ndarray) -> bytes:
    """Convert int16 numpy array to WAV bytes."""
    data = audio.astype(np.int16).tobytes()
    n_channels = 1
    sample_width = 2
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(data),
        b"WAVE",
        b"fmt ",
        16,  # chunk size
        1,  # PCM
        n_channels,
        _SAMPLE_RATE,
        _SAMPLE_RATE * n_channels * sample_width,
        n_channels * sample_width,
        sample_width * 8,
        b"data",
        len(data),
    )
    return header + data


class VoiceDetector:
    """
    Streaming voice activity detector.

    Feed audio frames via process_frame(). It returns:
    - None while waiting for speech
    - Complete utterance audio (WAV bytes) when speech ends

    Ignores music, TV, fan noise — only triggers on voice.
    """

    def __init__(self, speech_threshold=SPEECH_THRESHOLD,
                 silence_frames=SILENCE_FRAMES,
                 min_speech_frames=MIN_SPEECH_FRAMES,
                 max_duration_s=20):
        self.speech_threshold = speech_threshold
        self.silence_frames = silence_frames
        self.min_speech_frames = min_speech_frames
        self.max_frames = int(max_duration_s * 1000 / _FRAME_MS)

        self._audio_buffer = []
        self._speech_count = 0
        self._silence_count = 0
        self._recording = False
        self._total_frames = 0

    def process_frame(self, frame: np.ndarray):
        """
        Process a 30ms audio frame (480 int16 samples at 16kHz).
        Returns WAV bytes when a complete utterance is detected, None otherwise.
        """
        prob = is_speech(frame)

        if prob >= self.speech_threshold:
            self._speech_count += 1
            self._silence_count = 0

            if not self._recording and self._speech_count >= 3:
                # Start recording — 3 consecutive speech frames (~90ms)
                self._recording = True
                self._total_frames = 0
                logger.debug("VAD: speech started")

        else:
            if self._recording:
                self._silence_count += 1
            else:
                self._speech_count = max(0, self._speech_count - 1)

        if self._recording:
            self._audio_buffer.append(frame.copy())
            self._total_frames += 1

            # End conditions: enough silence or max duration
            if self._silence_count >= self.silence_frames or self._total_frames >= self.max_frames:
                if self._speech_count >= self.min_speech_frames:
                    # Valid utterance — return WAV
                    audio = np.concatenate(self._audio_buffer)
                    wav_bytes = _to_wav(audio)
                    logger.debug(f"VAD: utterance ({len(self._audio_buffer)} frames, {len(wav_bytes)} bytes)")
                    self._reset()
                    return wav_bytes
                else:
                    # Too short — noise, discard
                    logger.debug("VAD: too short, discarded")
                    self._reset()

        return None

    def _reset(self):
        self._audio_buffer.clear()
        self._speech_count = 0
        self._silence_count = 0
        self._recording = False
        self._total_frames = 0
        reset()

    @property
    def frame_size(self):
        return _FRAME_SIZE

    @property
    def sample_rate(self):
        return _SAMPLE_RATE
