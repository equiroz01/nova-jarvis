import base64
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
    tts: bool = Field(default=True, description="Generate TTS audio in response")


class ChatResponse(BaseModel):
    response: str
    session_id: str
    audio_base64: Optional[str] = None


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, req: Request):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    executor = req.app.state.agent_executor
    try:
        output = invoke_agent(request.message, request.session_id, executor)

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
