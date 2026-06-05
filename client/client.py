#!/usr/bin/env python3
"""NOVA Mac Client — Wake word + voice interaction with Silero VAD."""

import base64
import io
import logging
import time
import threading

import numpy as np
import pyaudio
import requests

from config import BACKEND_URL, CLIENT_ID, WAKE_WORD, MIC_INDEX, CONVERSATION_TIMEOUT
from audio_player import play_audio, is_speaking
from local_executor import LocalExecutor
from vad import VoiceDetector, load_model as load_vad

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Audio config
SAMPLE_RATE = 16000
CHANNELS = 1
FORMAT = pyaudio.paInt16
FRAME_SIZE = 512  # 32ms at 16kHz (Silero VAD minimum)


def send_voice(audio_bytes: bytes, session_id: str) -> dict:
    """Send audio to the backend /voice endpoint."""
    response = requests.post(
        f"{BACKEND_URL}/voice",
        files={"audio": ("command.wav", io.BytesIO(audio_bytes), "audio/wav")},
        data={"session_id": session_id, "language": "es"},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def send_chat(message: str, session_id: str) -> dict:
    """Send text to the backend /chat endpoint."""
    response = requests.post(
        f"{BACKEND_URL}/chat",
        json={"message": message, "session_id": session_id},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def contains_wake_word(wav_bytes: bytes, wake_word: str) -> str:
    """Send short audio to backend STT to check for wake word. Returns transcript."""
    try:
        response = requests.post(
            f"{BACKEND_URL}/voice",
            files={"audio": ("wake.wav", io.BytesIO(wav_bytes), "audio/wav")},
            data={"session_id": "wake-check", "language": "es"},
            timeout=10,
        )
        if response.ok:
            data = response.json()
            transcript = data.get("transcript", "")
            if transcript:
                logger.info(f"Heard: {transcript}")
                if wake_word.lower() in transcript.lower():
                    return transcript
    except Exception as e:
        logger.debug(f"Wake word check failed: {e}")
    return ""


def main():
    logger.info("=" * 50)
    logger.info("NOVA Mac Client (Silero VAD)")
    logger.info(f"Backend: {BACKEND_URL}")
    logger.info(f"Wake word: '{WAKE_WORD}'")
    logger.info("=" * 50)

    # Load VAD model
    load_vad()

    # Start local executor for WebSocket tool bridge
    executor = LocalExecutor(BACKEND_URL, CLIENT_ID)
    executor.start()

    # Init audio stream
    pa = pyaudio.PyAudio()
    stream = pa.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=SAMPLE_RATE,
        input=True,
        input_device_index=MIC_INDEX,
        frames_per_buffer=FRAME_SIZE,
    )

    session_id = f"mac-{CLIENT_ID}"
    conversation_mode = False
    last_interaction = None

    # Two detectors: short for wake word, long for commands
    wake_detector = VoiceDetector(
        speech_threshold=0.5,
        silence_frames=15,     # ~450ms silence to cut (short for wake word)
        min_speech_frames=5,   # ~150ms min speech
        max_duration_s=4,      # wake word should be < 4s
    )
    cmd_detector = VoiceDetector(
        speech_threshold=0.45,
        silence_frames=30,     # ~900ms silence to cut (longer for natural speech)
        min_speech_frames=10,  # ~300ms min speech
        max_duration_s=20,     # commands up to 20s
    )

    logger.info("Microphone ready. Listening for wake word...")

    try:
        while True:
            # Skip while NOVA is speaking
            if is_speaking.is_set():
                time.sleep(0.05)
                continue

            # Read audio frame from mic
            try:
                raw = stream.read(FRAME_SIZE, exception_on_overflow=False)
            except Exception:
                time.sleep(0.01)
                continue

            frame = np.frombuffer(raw, dtype=np.int16)

            if not conversation_mode:
                # ── Wake word mode ──
                wav = wake_detector.process_frame(frame)
                if wav is not None:
                    # Got a short utterance — check if it contains the wake word
                    transcript = contains_wake_word(wav, WAKE_WORD)
                    if transcript:
                        logger.info("Wake word detected!")
                        conversation_mode = True
                        last_interaction = time.time()
                        logger.info("Conversation mode ON")

                        # Send greeting to get briefing
                        try:
                            result = send_voice(wav, session_id)
                            response_text = result.get("response", "")
                            audio_b64 = result.get("audio_base64", "")
                            if response_text:
                                logger.info(f"NOVA: {response_text[:100]}...")
                            if audio_b64:
                                play_audio(base64.b64decode(audio_b64))
                            last_interaction = time.time()
                        except Exception as e:
                            logger.error(f"Greeting error: {e}")
            else:
                # ── Conversation mode ──
                wav = cmd_detector.process_frame(frame)
                if wav is not None:
                    logger.info("Processing command...")
                    try:
                        result = send_voice(wav, session_id)

                        transcript = result.get("transcript", "")
                        response_text = result.get("response", "")
                        audio_b64 = result.get("audio_base64", "")

                        if transcript:
                            logger.info(f"You: {transcript}")
                        if response_text:
                            logger.info(f"NOVA: {response_text[:100]}...")

                        if audio_b64:
                            play_audio(base64.b64decode(audio_b64))

                        last_interaction = time.time()

                    except requests.exceptions.ConnectionError:
                        logger.error(f"Cannot connect to backend at {BACKEND_URL}")
                    except Exception as e:
                        logger.error(f"Error: {e}")
                        time.sleep(0.5)

                # Check timeout
                if last_interaction and time.time() - last_interaction > CONVERSATION_TIMEOUT:
                    logger.info("Timeout — returning to wake word mode")
                    conversation_mode = False
                    cmd_detector._reset()

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()
        executor.stop()


if __name__ == "__main__":
    main()
