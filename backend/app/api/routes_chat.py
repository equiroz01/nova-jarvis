import logging
import uuid
from pydantic import BaseModel, Field
from fastapi import APIRouter, Request, HTTPException

from app.agent.orchestrator import invoke_agent

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class ChatResponse(BaseModel):
    response: str
    session_id: str


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, req: Request):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    executor = req.app.state.agent_executor
    try:
        output = invoke_agent(request.message, request.session_id, executor)
        return ChatResponse(response=output, session_id=request.session_id)
    except Exception as e:
        logger.error(f"Agent error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")
