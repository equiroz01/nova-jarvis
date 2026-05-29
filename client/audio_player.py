import os
import tempfile
import subprocess
import logging

logger = logging.getLogger(__name__)


def play_audio(audio_bytes: bytes, format: str = "mp3"):
    """Play audio bytes on macOS using afplay."""
    if not audio_bytes:
        logger.warning("No audio to play")
        return

    with tempfile.NamedTemporaryFile(suffix=f".{format}", delete=False) as f:
        f.write(audio_bytes)
        temp_path = f.name

    try:
        subprocess.run(["afplay", temp_path], check=True)
    except FileNotFoundError:
        logger.error("afplay not found. Are you on macOS?")
    except subprocess.CalledProcessError as e:
        logger.error(f"Audio playback failed: {e}")
    finally:
        os.unlink(temp_path)
