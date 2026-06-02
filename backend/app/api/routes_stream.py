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

# ── Filler phrase banks ──
FILLERS = {
    "search": [
        "Estoy buscando en internet...",
        "Déjeme buscar eso...",
        "Ya reviso, un segundo...",
        "Consultando fuentes...",
    ],
    "news": [
        "Revisando las noticias...",
        "Déjeme ver qué hay de nuevo...",
        "Buscando las últimas noticias...",
    ],
    "memory": [
        "Déjeme revisar mis notas...",
        "Un momento, reviso lo que sé...",
        "Verificando en mi memoria...",
    ],
    "time": [
        "Ya verifico...",
        "Un segundo...",
    ],
    "general": [
        "Un momento...",
        "Déjeme ver...",
        "Ya le digo...",
        "Permítame...",
        "Ehh, un segundo...",
        "Ya va...",
    ],
}

# Keywords to detect query type
_SEARCH_KW = {"busca", "buscar", "search", "google", "internet", "web", "encuentra"}
_NEWS_KW = {"noticias", "news", "novedades", "actualidad", "hoy", "reciente"}
_MEMORY_KW = {"recuerdas", "sabes", "conoces", "quién es", "quien es", "memoria", "brain"}
_TIME_KW = {"hora", "time", "reloj", "clock"}


def _detect_type(msg: str) -> str:
    lower = msg.lower()
    words = set(lower.split())
    if words & _NEWS_KW:
        return "news"
    if words & _SEARCH_KW:
        return "search"
    if words & _MEMORY_KW:
        return "memory"
    if words & _TIME_KW:
        return "time"
    return "general"


def _pick_filler(query_type: str) -> str:
    phrases = FILLERS.get(query_type, FILLERS["general"])
    return random.choice(phrases)


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

            # Send filler phrase IMMEDIATELY
            query_type = _detect_type(request.message)
            filler = _pick_filler(query_type)
            yield f"data: {json.dumps({'type': 'filler', 'content': filler})}\n\n"

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
