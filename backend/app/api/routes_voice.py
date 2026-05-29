import base64
import logging
import uuid

from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.agent.orchestrator import invoke_agent
from app.services.stt import transcribe_audio
from app.services.tts import synthesize_speech

logger = logging.getLogger(__name__)
router = APIRouter()


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
    language: Optional[str] = Form("en-US"),
):
    """Process voice input: STT -> Agent -> TTS. Returns text + audio."""
    if session_id is None:
        session_id = str(uuid.uuid4())

    # Read audio file
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")

    # Speech-to-Text
    try:
        transcript = transcribe_audio(audio_bytes, language_code=language)
    except Exception as e:
        logger.error(f"STT error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Speech recognition failed: {str(e)}")

    if not transcript:
        raise HTTPException(status_code=400, detail="Could not transcribe audio")

    # Agent processing
    executor = req.app.state.agent_executor
    try:
        response_text = invoke_agent(transcript, session_id, executor)
    except Exception as e:
        logger.error(f"Agent error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")

    # Text-to-Speech
    try:
        audio_response = synthesize_speech(response_text, language_code=language)
        audio_b64 = base64.b64encode(audio_response).decode("utf-8")
    except Exception as e:
        logger.error(f"TTS error: {e}", exc_info=True)
        audio_b64 = ""

    return VoiceResponse(
        transcript=transcript,
        response=response_text,
        audio_base64=audio_b64,
        session_id=session_id,
    )
