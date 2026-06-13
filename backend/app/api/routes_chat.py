import asyncio
import base64
import json
import logging
import uuid
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Request, HTTPException

from app.agent.orchestrator import invoke_agent

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_id: str = Field(default="default", description="Client identifier for session isolation")
    tts: bool = Field(default=True, description="Generate TTS audio in response")


class ChatResponse(BaseModel):
    response: str
    session_id: str
    audio_base64: Optional[str] = None


class TTSRequest(BaseModel):
    text: str


class TTSResponse(BaseModel):
    audio_base64: str


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, req: Request):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    executor = req.app.state.agent_executor
    try:
        output = invoke_agent(request.message, request.session_id, executor, client_id=request.client_id)

        audio_b64 = None
        if request.tts:
            try:
                from app.services.tts import synthesize_speech
                audio_bytes = synthesize_speech(output)
                audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
            except Exception as e:
                logger.warning(f"TTS failed (falling back to browser): {e}")

        return ChatResponse(response=output, session_id=request.session_id, audio_base64=audio_b64)
    except Exception as e:
        logger.error(f"Agent error: {e}", exc_info=True)
        if "429" in str(e):
            raise HTTPException(status_code=429, detail="Gemini API rate limit exceeded. Wait a minute and try again.")
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")


@router.post("/tts", response_model=TTSResponse)
async def tts_endpoint(request: TTSRequest):
    """Generate TTS audio separately. For async TTS after receiving text response."""
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    try:
        from app.services.tts import synthesize_speech
        audio_bytes = synthesize_speech(request.text)
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        return TTSResponse(audio_base64=audio_b64)
    except Exception as e:
        logger.error(f"TTS error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"TTS error: {str(e)}")


class FillerRequest(BaseModel):
    query_type: str = "general"


class FillerResponse(BaseModel):
    text: str
    audio_base64: str


@router.post("/filler", response_model=FillerResponse)
async def filler_endpoint(request: FillerRequest):
    """Get a pre-cached filler phrase with Salome audio. Instant response."""
    from app.services.filler_cache import get_filler
    text, audio = get_filler(request.query_type)
    audio_b64 = base64.b64encode(audio).decode("utf-8") if audio else ""
    return FillerResponse(text=text, audio_base64=audio_b64)


@router.get("/filler/preload")
async def filler_preload(per_category: int = 4):
    """Bundle of filler audios per category for client-side caching.
    The browser plays these with zero roundtrip while requests process."""
    from app.services.filler_cache import get_preload_bundle
    return get_preload_bundle(per_category=min(per_category, 8))


class TTSChunkedRequest(BaseModel):
    text: str


@router.post("/tts/chunked")
async def tts_chunked(request: TTSChunkedRequest):
    """Stream TTS chunks as NDJSON — each sentence generates and sends immediately.
    Client starts playing the first sentence while the rest are still generating."""
    import re
    from fastapi.responses import StreamingResponse
    from app.services.tts import _synthesize_async

    text = request.text.strip()
    if not text:
        return StreamingResponse(iter([]), media_type="application/x-ndjson")

    # Split into sentences
    parts = re.split(r'(?<=[.!?])\s+|(?<=:)\n|\n(?=[-*•\d])', text)
    sentences = []
    buf = ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        buf = (buf + " " + p).strip() if buf else p
        if len(buf) >= 40:
            sentences.append(buf)
            buf = ""
    if buf:
        sentences.append(buf)

    async def generate():
        # Pipeline: synthesize sentence n+1 while n streams to the client.
        next_task = asyncio.ensure_future(_synthesize_async(sentences[0]))
        for i, s in enumerate(sentences):
            try:
                audio = await next_task
            except Exception as e:
                logger.warning(f"TTS chunk failed: {e}")
                audio = None
            if i + 1 < len(sentences):
                next_task = asyncio.ensure_future(_synthesize_async(sentences[i + 1]))
            if audio:
                chunk = {
                    "text": s,
                    "audio_base64": base64.b64encode(audio).decode("utf-8"),
                }
                yield json.dumps(chunk) + "\n"

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
