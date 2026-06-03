import os
import tempfile
import subprocess
import logging
import threading

logger = logging.getLogger(__name__)

# Flag to signal when N.O.V.A. is speaking — mic should ignore audio
is_speaking = threading.Event()


def play_audio(audio_bytes: bytes, format: str = "mp3"):
    """Play audio bytes on macOS using afplay. Sets is_speaking flag to mute mic."""
    if not audio_bytes:
        logger.warning("No audio to play")
        return

    with tempfile.NamedTemporaryFile(suffix=f".{format}", delete=False) as f:
        f.write(audio_bytes)
        temp_path = f.name

    try:
        is_speaking.set()
        subprocess.run(["afplay", temp_path], check=True)
    except FileNotFoundError:
        logger.error("afplay not found. Are you on macOS?")
    except subprocess.CalledProcessError as e:
        logger.error(f"Audio playback failed: {e}")
    finally:
        is_speaking.clear()
        os.unlink(temp_path)
