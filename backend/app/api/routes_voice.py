import asyncio
import base64
import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from app.agent.orchestrator import invoke_agent
from app.services.stt import transcribe_audio
from app.services.tts import synthesize_speech

logger = logging.getLogger(__name__)
router = APIRouter()

# Dedicated pool so STT/agent work never starves the event loop
_voice_pool = ThreadPoolExecutor(max_workers=4)


class VoiceResponse(BaseModel):
    transcript: str
    response: str
    audio_base64: str
    session_id: str


@router.post("/voice", response_model=VoiceResponse)
async def voice(
    req: Request,
    audio: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    language: Optional[str] = Form("es"),
    stt_provider: Optional[str] = Form("auto"),
):
    """Process voice input: STT -> Agent -> TTS. Returns text + audio."""
    if session_id is None:
        session_id = str(uuid.uuid4())

    # Read audio file
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")

    logger.info(f"Received audio: {len(audio_bytes)} bytes")

    # Voice ID — verify speaker (only for local client, not browser)
    # Browser audio has different compression and mic characteristics
    from app.services.voice_id import verify, is_enrolled
    is_local_client = session_id and session_id.startswith("mac-")
    if is_enrolled() and is_local_client:
        is_owner, similarity = verify(audio_bytes)
        if not is_owner:
            logger.info(f"Voice rejected (similarity={similarity:.3f})")
            return VoiceResponse(
                transcript="", response="", audio_base64="", session_id=session_id,
            )

    # Speech-to-Text
    try:
        transcript = transcribe_audio(audio_bytes, language_code=language, provider=stt_provider or "auto")
    except Exception as e:
        logger.error(f"STT error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Speech recognition failed: {str(e)}")

    if not transcript:
        # No speech detected — return friendly message instead of error
        return VoiceResponse(
            transcript="",
            response="No le escuché bien, Señor. ¿Puede repetirme?",
            audio_base64="",
            session_id=session_id,
        )

    logger.info(f"Transcript: {transcript}")

    # Agent processing
    executor = req.app.state.agent_executor
    try:
        response_text = invoke_agent(transcript, session_id, executor)
    except Exception as e:
        logger.error(f"Agent error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")

    # Text-to-Speech
    audio_b64 = ""
    try:
        audio_response = synthesize_speech(response_text)
        audio_b64 = base64.b64encode(audio_response).decode("utf-8")
    except Exception as e:
        logger.warning(f"TTS failed (client will use browser TTS): {e}")

    return VoiceResponse(
        transcript=transcript,
        response=response_text,
        audio_base64=audio_b64,
        session_id=session_id,
    )


@router.post("/voice/stream")
async def voice_stream(
    req: Request,
    audio: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    language: Optional[str] = Form("es"),
    tts: Optional[str] = Form("true"),
    stt_provider: Optional[str] = Form("auto"),
):
    """Streaming voice pipeline (NDJSON). Events arrive as each stage finishes:

    1. {"type": "transcript", transcript, query_type, filler_text, filler_audio_base64}
       — sent right after STT, with a context-aware filler the client plays
         while the agent thinks.
    2. {"type": "result", response, audio_base64, session_id}
       — final agent response. audio_base64 is empty when tts=false
         (hands-free mode re-synthesizes per sentence via /tts/chunked).
    """
    if session_id is None:
        session_id = str(uuid.uuid4())

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")

    want_tts = (tts or "true").lower() != "false"
    executor = req.app.state.agent_executor
    loop = asyncio.get_running_loop()

    async def generate():
        # Voice ID — same gate as /voice (local client only)
        from app.services.voice_id import verify, is_enrolled
        is_local_client = session_id and session_id.startswith("mac-")
        if is_enrolled() and is_local_client:
            is_owner, similarity = verify(audio_bytes)
            if not is_owner:
                logger.info(f"Voice rejected (similarity={similarity:.3f})")
                yield json.dumps({"type": "result", "response": "", "transcript": "",
                                  "audio_base64": "", "session_id": session_id}) + "\n"
                return

        # 1. STT in worker thread
        try:
            transcript = await loop.run_in_executor(
                _voice_pool,
                lambda: transcribe_audio(audio_bytes, language_code=language, provider=stt_provider or "auto"),
            )
        except Exception as e:
            logger.error(f"STT error: {e}", exc_info=True)
            yield json.dumps({"type": "error", "detail": "Speech recognition failed"}) + "\n"
            return

        if not transcript:
            yield json.dumps({"type": "result", "transcript": "",
                              "response": "No le escuché bien, Señor. ¿Puede repetirme?",
                              "audio_base64": "", "session_id": session_id}) + "\n"
            return

        # 2. Transcript + context-aware filler, immediately
        from app.services.filler_cache import get_filler, detect_query_type
        qtype = detect_query_type(transcript)
        filler_text, filler_audio = get_filler(qtype)
        yield json.dumps({
            "type": "transcript",
            "transcript": transcript,
            "query_type": qtype,
            "filler_text": filler_text,
            "filler_audio_base64": base64.b64encode(filler_audio).decode("utf-8") if filler_audio else "",
        }) + "\n"

        # 3. Agent in worker thread
        try:
            response_text = await loop.run_in_executor(
                _voice_pool, lambda: invoke_agent(transcript, session_id, executor)
            )
        except Exception as e:
            logger.error(f"Agent error: {e}", exc_info=True)
            yield json.dumps({"type": "error", "detail": "Agent error"}) + "\n"
            return

        # 4. Optional full TTS (push-to-talk). Hands-free skips this and
        #    uses /tts/chunked for sentence-level playback instead.
        audio_b64 = ""
        if want_tts:
            try:
                audio_response = await loop.run_in_executor(
                    _voice_pool, lambda: synthesize_speech(response_text)
                )
                audio_b64 = base64.b64encode(audio_response).decode("utf-8")
            except Exception as e:
                logger.warning(f"TTS failed (client will use browser TTS): {e}")

        yield json.dumps({"type": "result", "transcript": transcript,
                          "response": response_text, "audio_base64": audio_b64,
                          "session_id": session_id}) + "\n"

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
