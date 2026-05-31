"""
N.O.V.A. TTS — Microsoft Edge Neural voices via edge-tts.
Fast, free, no API key needed.
"""

import re
import asyncio
import logging
import edge_tts

logger = logging.getLogger(__name__)

# N.O.V.A. voice: Salome (Colombian Spanish)
VOICE_ES = "es-CO-SalomeNeural"
VOICE_EN = "en-US-AvaNeural"

# Spanish detection
_SPANISH_WORDS = re.compile(
    r'\b(hola|aquí|tienes|puedes|noticias|buscar|hora|tiempo|qué|cómo|dónde|'
    r'cuándo|también|está|esto|gracias|por favor|claro|bueno|para|como|'
    r'las|los|del|una|pero|más|hoy|información|encuentra|siguiente|'
    r'espero|ayudar|útil|quiero|necesito|dime|sobre)\b',
    re.IGNORECASE
)
_SPANISH_CHARS = re.compile(r'[ñáéíóú¿¡]')


def _is_spanish(text: str) -> bool:
    if _SPANISH_CHARS.search(text):
        return True
    matches = _SPANISH_WORDS.findall(text)
    return len(matches) >= 2


def _strip_markdown(text: str) -> str:
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'`(.+?)`', r'\1', text)
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
    text = re.sub(r'^#{1,3}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\d+[.)]\s+', '', text, flags=re.MULTILINE)
    return text.strip()


async def _synthesize_async(text: str) -> bytes:
    clean = _strip_markdown(text)
    voice = VOICE_ES if _is_spanish(clean) else VOICE_EN

    comm = edge_tts.Communicate(clean, voice)
    chunks = []
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])

    audio = b"".join(chunks)
    logger.info(f"TTS [{voice}]: {len(audio)} bytes")
    return audio


def synthesize_speech(text: str) -> bytes:
    """Convert text to speech using Microsoft Edge TTS. Returns MP3 bytes."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, _synthesize_async(text))
                return future.result(timeout=30)
        else:
            return loop.run_until_complete(_synthesize_async(text))
    except RuntimeError:
        return asyncio.run(_synthesize_async(text))
