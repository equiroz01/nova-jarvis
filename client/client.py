#!/usr/bin/env python3
"""Jarvis Mac Client - Wake word detection + voice interaction with cloud backend."""

import base64
import io
import logging
import time

import requests
import speech_recognition as sr

from config import BACKEND_URL, CLIENT_ID, WAKE_WORD, MIC_INDEX, CONVERSATION_TIMEOUT
from audio_player import play_audio, is_speaking
from local_executor import LocalExecutor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

recognizer = sr.Recognizer()
recognizer.dynamic_energy_threshold = True
recognizer.dynamic_energy_adjustment_damping = 0.15
recognizer.dynamic_energy_ratio = 1.5
recognizer.pause_threshold = 0.8  # seconds of silence to consider phrase complete
recognizer.non_speaking_duration = 0.5
mic = sr.Microphone(device_index=MIC_INDEX)


def send_voice(audio_bytes: bytes, session_id: str) -> dict:
    """Send audio to the backend /voice endpoint."""
    response = requests.post(
        f"{BACKEND_URL}/voice",
        files={"audio": ("command.wav", io.BytesIO(audio_bytes), "audio/wav")},
        data={"session_id": session_id, "language": "en-US"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def send_chat(message: str, session_id: str) -> dict:
    """Send text to the backend /chat endpoint (fallback)."""
    response = requests.post(
        f"{BACKEND_URL}/chat",
        json={"message": message, "session_id": session_id},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def record_audio(source) -> bytes:
    """Record audio from microphone and return WAV bytes."""
    audio = recognizer.listen(source, timeout=10, phrase_time_limit=20)
    return audio.get_wav_data()


def main():
    logger.info("=" * 50)
    logger.info("Jarvis Mac Client")
    logger.info(f"Backend: {BACKEND_URL}")
    logger.info(f"Wake word: '{WAKE_WORD}'")
    logger.info("=" * 50)

    # Start local executor for WebSocket tool bridge
    executor = LocalExecutor(BACKEND_URL, CLIENT_ID)
    executor.start()

    session_id = f"mac-{CLIENT_ID}"
    conversation_mode = False
    last_interaction = None

    try:
        with mic as source:
            logger.info("Calibrating for ambient noise (3s)...")
            recognizer.adjust_for_ambient_noise(source, duration=3)
            # Bump threshold a bit above measured floor to ignore fan noise
            recognizer.energy_threshold = max(recognizer.energy_threshold * 1.3, 300)
            logger.info(f"Noise floor set: energy_threshold={recognizer.energy_threshold:.0f}")
            logger.info("Microphone ready. Listening...")

            while True:
                try:
                    # Skip listening while N.O.V.A. is speaking
                    if is_speaking.is_set():
                        time.sleep(0.1)
                        continue

                    if not conversation_mode:
                        # Wake word detection mode
                        logger.debug("Listening for wake word...")
                        audio = recognizer.listen(source, timeout=5, phrase_time_limit=4)
                        transcript = recognizer.recognize_google(audio)
                        logger.info(f"Heard: {transcript}")

                        if WAKE_WORD.lower() in transcript.lower():
                            logger.info("Wake word detected!")
                            # Send a quick "Yes sir?" via local TTS or backend
                            try:
                                result = send_chat("The user just said my name to activate me. Respond with a very short greeting.", session_id)
                                if result.get("response"):
                                    # Get TTS for greeting
                                    pass
                            except Exception:
                                pass

                            conversation_mode = True
                            last_interaction = time.time()
                            logger.info("Conversation mode ON")
                    else:
                        # Conversation mode - process commands
                        logger.info("Listening for command...")
                        wav_data = record_audio(source)

                        # Send to backend voice endpoint
                        try:
                            result = send_voice(wav_data, session_id)

                            transcript = result.get("transcript", "")
                            response_text = result.get("response", "")
                            audio_b64 = result.get("audio_base64", "")

                            logger.info(f"You: {transcript}")
                            logger.info(f"Jarvis: {response_text}")

                            # Play audio response
                            if audio_b64:
                                audio_bytes = base64.b64decode(audio_b64)
                                play_audio(audio_bytes)

                            last_interaction = time.time()

                        except requests.exceptions.ConnectionError:
                            logger.error(f"Cannot connect to backend at {BACKEND_URL}")
                            # Fallback: use local speech recognition
                            try:
                                text = recognizer.recognize_google(sr.AudioData(wav_data, 16000, 2))
                                result = send_chat(text, session_id)
                                logger.info(f"Jarvis: {result.get('response', 'Error')}")
                            except Exception as e:
                                logger.error(f"Fallback also failed: {e}")

                        # Check timeout
                        if time.time() - last_interaction > CONVERSATION_TIMEOUT:
                            logger.info("Timeout - returning to wake word mode")
                            conversation_mode = False

                except sr.WaitTimeoutError:
                    if conversation_mode and time.time() - last_interaction > CONVERSATION_TIMEOUT:
                        logger.info("Timeout - returning to wake word mode")
                        conversation_mode = False
                except sr.UnknownValueError:
                    logger.debug("Could not understand audio")
                except requests.exceptions.RequestException as e:
                    logger.error(f"Backend request error: {e}")
                    time.sleep(1)
                except Exception as e:
                    logger.error(f"Error: {e}")
                    time.sleep(1)

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        executor.stop()


if __name__ == "__main__":
    main()
