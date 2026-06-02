"""
Pre-generate filler phrase audio using Salome voice (edge-tts).
Cached at startup so fillers play instantly without TTS delay.
"""

import asyncio
import logging
import random
from pathlib import Path
import edge_tts
from app.services.tts import VOICE_ES, RATE

logger = logging.getLogger(__name__)

FILLERS = {
    "general": [
        "Un momento...", "Déjeme ver...", "Ya le digo, jefe...", "Permítame...",
        "Ehh, un segundo...", "Ya va...", "Déjeme pensar...", "A ver...",
        "Mmm, ya le respondo...", "Un segundito...", "Uy, buena pregunta...",
        "Ya le cuento...", "Listo, déjeme ver...", "Voy a revisar eso...",
        "Ay, ya voy...", "Qué maravilla, ya le digo...", "Espéreme un momentico...",
        "Ya casi, un segundo...", "Aja, déjeme mirar...", "Listo, ya voy por eso...",
    ],
    "search": [
        "Estoy buscando en internet...", "Déjeme buscar eso...", "Ya reviso, un segundo...",
        "Buscando información...", "Déjeme revisar en la web...",
        "Ya lo busco...", "Chequeando en internet...", "Ay, ya voy, déjeme buscar...",
        "Listo, ya estoy buscando...", "Uy, déjeme mirar eso...", "Ya le averiguo...",
    ],
    "news": [
        "Revisando las noticias...", "Déjeme ver qué hay de nuevo...",
        "Buscando las últimas noticias...", "Revisando los titulares...",
        "A ver qué pasó hoy...", "Consultando las noticias...",
        "Uy, déjeme ver qué hay...", "Ya miro qué está pasando...",
        "Voy a revisar las novedades...", "Qué maravilla, ya le cuento qué hay...",
    ],
    "memory": [
        "Déjeme revisar mis notas...", "Un momento, reviso lo que sé...",
        "Verificando en mi memoria...", "Déjeme buscar en mis registros...",
        "Ya reviso lo que tengo guardado...", "A ver, déjeme recordar...",
        "Un segundito, ya miro...", "Uy, eso lo tengo por aquí...",
    ],
    "time": ["Ya verifico...", "Un segundo...", "Déjeme checar...", "Ya miro la hora..."],
    "weather": ["Revisando el clima...", "Déjeme ver el pronóstico...", "Consultando el tiempo...", "Ya miro cómo está el clima..."],
}

# Cache: phrase -> mp3 bytes
_audio_cache: dict[str, bytes] = {}
_recent: list[str] = []


async def _generate_one(phrase: str) -> bytes:
    """Generate TTS audio forcing Salome voice — no language detection."""
    comm = edge_tts.Communicate(phrase, VOICE_ES, rate="+18%", pitch="+0Hz")
    chunks = []
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    return b"".join(chunks)


async def preload_fillers():
    """Pre-generate audio for all filler phrases at startup."""
    all_phrases = []
    for phrases in FILLERS.values():
        all_phrases.extend(phrases)
    all_phrases = list(set(all_phrases))

    logger.info(f"Pre-generating {len(all_phrases)} filler audios with Salome...")
    for phrase in all_phrases:
        try:
            audio = await _generate_one(phrase)
            _audio_cache[phrase] = audio
        except Exception as e:
            logger.warning(f"Filler TTS failed for '{phrase[:30]}': {e}")

    logger.info(f"Filler cache ready: {len(_audio_cache)} phrases")


def get_filler(query_type: str = "general") -> tuple[str, bytes]:
    """Pick a filler phrase and return (text, mp3_bytes). Never repeats last 5."""
    global _recent
    bank = FILLERS.get(query_type, FILLERS["general"])
    available = [p for p in bank if p not in _recent and p in _audio_cache]
    if not available:
        _recent.clear()
        available = [p for p in bank if p in _audio_cache]
    if not available:
        return ("Un momento...", b"")

    phrase = random.choice(available)
    _recent.append(phrase)
    if len(_recent) > 5:
        _recent.pop(0)

    return (phrase, _audio_cache.get(phrase, b""))


def detect_query_type(msg: str) -> str:
    """Detect query type from message text."""
    lower = msg.lower()
    if any(w in lower for w in ["noticias", "news", "novedades", "titulares", "pasó", "actualidad"]):
        return "news"
    if any(w in lower for w in ["clima", "weather", "pronóstico", "temperatura", "lluvia"]):
        return "weather"
    if any(w in lower for w in ["busca", "search", "google", "internet", "encuentra", "averigua"]):
        return "search"
    if any(w in lower for w in ["recuerdas", "sabes", "conoces", "quién es", "quien es", "memoria"]):
        return "memory"
    if any(w in lower for w in ["hora", "time", "reloj"]):
        return "time"
    return "general"
