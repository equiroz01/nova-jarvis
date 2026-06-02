"""Streaming chat with filler phrases (muletillas) for natural conversation feel."""

import asyncio
import json
import logging
import random
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent.orchestrator import invoke_agent, _check_cache

_executor_pool = ThreadPoolExecutor(max_workers=4)

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Filler phrase banks (Colombian / natural Spanish) ──
FILLERS = {
    "search": [
        "Estoy buscando en internet...",
        "Déjeme buscar eso...",
        "Ya reviso, un segundo...",
        "Consultando fuentes...",
        "Buscando información...",
        "Déjeme revisar en la web...",
        "Ya lo busco...",
        "Chequeando en internet...",
        "Ay, ya voy, déjeme buscar...",
        "Listo, ya estoy buscando...",
        "Uy, déjeme mirar eso...",
        "Ya le averiguo...",
    ],
    "news": [
        "Revisando las noticias...",
        "Déjeme ver qué hay de nuevo...",
        "Buscando las últimas noticias...",
        "Revisando los titulares...",
        "A ver qué pasó hoy...",
        "Consultando las noticias...",
        "Uy, déjeme ver qué hay...",
        "Ya miro qué está pasando...",
        "Voy a revisar las novedades...",
        "Qué maravilla, ya le cuento qué hay...",
    ],
    "memory": [
        "Déjeme revisar mis notas...",
        "Un momento, reviso lo que sé...",
        "Verificando en mi memoria...",
        "Déjeme buscar en mis registros...",
        "Ya reviso lo que tengo guardado...",
        "A ver, déjeme recordar...",
        "Un segundito, ya miro...",
        "Uy, eso lo tengo por aquí...",
    ],
    "time": [
        "Ya verifico...",
        "Un segundo...",
        "Déjeme checar...",
        "Ya miro la hora...",
    ],
    "weather": [
        "Revisando el clima...",
        "Déjeme ver el pronóstico...",
        "Consultando el tiempo...",
        "Ya miro cómo está el clima...",
    ],
    "general": [
        "Un momento...",
        "Déjeme ver...",
        "Ya le digo, jefe...",
        "Permítame...",
        "Ehh, un segundo...",
        "Ya va...",
        "Déjeme pensar...",
        "A ver...",
        "Mmm, ya le respondo...",
        "Un segundito...",
        "Uy, buena pregunta...",
        "Ya le cuento...",
        "Listo, déjeme ver...",
        "Voy a revisar eso...",
        "Ay, ya voy...",
        "Qué maravilla, ya le digo...",
        "Espéreme un momentico...",
        "Ya casi, un segundo...",
        "Aja, déjeme mirar...",
        "Listo, ya voy por eso...",
    ],
}

# Track recent fillers to avoid repetition
_recent_fillers: list[str] = []
_MAX_RECENT = 5

# Keywords to detect query type
_SEARCH_KW = {"busca", "buscar", "search", "google", "internet", "web", "encuentra", "averigua"}
_NEWS_KW = {"noticias", "news", "novedades", "actualidad", "hoy", "reciente", "titulares", "pasó", "paso"}
_MEMORY_KW = {"recuerdas", "sabes", "conoces", "quién es", "quien es", "memoria", "brain", "guardado"}
_TIME_KW = {"hora", "time", "reloj", "clock", "qué hora"}
_WEATHER_KW = {"clima", "weather", "pronóstico", "pronostico", "temperatura", "lluvia", "llover"}


def _detect_type(msg: str) -> str:
    lower = msg.lower()
    words = set(lower.split())
    if words & _NEWS_KW:
        return "news"
    if words & _WEATHER_KW:
        return "weather"
    if words & _SEARCH_KW:
        return "search"
    if words & _MEMORY_KW:
        return "memory"
    if words & _TIME_KW:
        return "time"
    return "general"


def _pick_filler(query_type: str) -> str:
    """Pick a filler phrase, avoiding recent ones."""
    global _recent_fillers
    phrases = FILLERS.get(query_type, FILLERS["general"])
    # Filter out recently used
    available = [p for p in phrases if p not in _recent_fillers]
    if not available:
        _recent_fillers.clear()
        available = phrases
    choice = random.choice(available)
    _recent_fillers.append(choice)
    if len(_recent_fillers) > _MAX_RECENT:
        _recent_fillers.pop(0)
    return choice


class StreamRequest(BaseModel):
    message: str
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


@router.post("/chat/stream")
async def chat_stream(request: StreamRequest):
    """Stream response via SSE with filler phrases for natural conversation."""

    async def generate():
        try:
            # Check cache first — if cached, no filler needed
            cached = _check_cache(request.message)
            if cached:
                yield f"data: {json.dumps({'type': 'token', 'content': cached})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'response': cached, 'session_id': request.session_id})}\n\n"
                return

            # Send filler phrase IMMEDIATELY with flush padding
            query_type = _detect_type(request.message)
            filler = _pick_filler(query_type)
            # Padding ensures the SSE event flushes through any buffering layers
            yield f"data: {json.dumps({'type': 'filler', 'content': filler})}\n\n" + " " * 2048 + "\n\n"

            # Small yield to force the event loop to actually send the filler
            await asyncio.sleep(0)

            # Run LLM in thread pool so the filler yield above flushes first
            loop = asyncio.get_event_loop()
            output = await loop.run_in_executor(
                _executor_pool,
                invoke_agent,
                request.message,
                request.session_id,
            )

            # Stream actual response in chunks
            chunk_size = 15
            for i in range(0, len(output), chunk_size):
                yield f"data: {json.dumps({'type': 'token', 'content': output[i:i + chunk_size]})}\n\n"

            yield f"data: {json.dumps({'type': 'done', 'response': output, 'session_id': request.session_id})}\n\n"

        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            detail = "Rate limit. Wait and retry." if "429" in str(e) else str(e)
            yield f"data: {json.dumps({'type': 'error', 'detail': detail})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
