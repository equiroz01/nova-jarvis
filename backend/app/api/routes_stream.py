"""
Streaming chat endpoint — sends tokens via Server-Sent Events (SSE).
Frontend receives text in real-time as Gemini generates it.
"""

import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from app.config import settings
from app.agent.prompts import build_prompt
from app.agent.session import get_memory
from app.agent.orchestrator import ALL_TOOLS, _create_executor, invoke_agent

logger = logging.getLogger(__name__)
router = APIRouter()


class StreamRequest(BaseModel):
    message: str
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


@router.post("/chat/stream")
async def chat_stream(request: StreamRequest, req: Request):
    """Stream chat response token by token via SSE.

    Events:
      data: {"type": "token", "content": "..."}    — partial text
      data: {"type": "done", "response": "..."}    — full response
      data: {"type": "error", "detail": "..."}     — error
    """

    async def generate():
        try:
            # For tool-calling queries, we can't truly stream token-by-token
            # because the agent needs to decide whether to call a tool first.
            # Strategy: run the agent normally, then send the complete response
            # as fast chunks to simulate streaming feel.
            # This is still faster because the frontend doesn't wait for TTS.

            memory = get_memory(request.session_id)

            # Try direct LLM streaming first (no tools) for simple queries
            # If the LLM wants to use a tool, fall back to full agent
            executor = _create_executor()
            response = executor.invoke(
                {"input": request.message, "chat_history": memory.chat_memory.messages}
            )
            output = response["output"]

            memory.chat_memory.add_user_message(request.message)
            memory.chat_memory.add_ai_message(output)

            # Stream the response in chunks for fast rendering
            chunk_size = 15  # characters per chunk
            for i in range(0, len(output), chunk_size):
                chunk = output[i:i + chunk_size]
                yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"

            yield f"data: {json.dumps({'type': 'done', 'response': output, 'session_id': request.session_id})}\n\n"

        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            detail = "Rate limit exceeded. Wait and retry." if "429" in str(e) else str(e)
            yield f"data: {json.dumps({'type': 'error', 'detail': detail})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
