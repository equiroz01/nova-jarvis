"""Streaming chat endpoint — SSE with chunked text delivery."""

import json
import logging
import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent.orchestrator import invoke_agent

logger = logging.getLogger(__name__)
router = APIRouter()


class StreamRequest(BaseModel):
    message: str
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


@router.post("/chat/stream")
async def chat_stream(request: StreamRequest):
    """Stream response via SSE. Tokens arrive as chunks for live rendering."""

    async def generate():
        try:
            output = invoke_agent(request.message, request.session_id)

            # Stream in chunks for typing effect
            chunk_size = 15
            for i in range(0, len(output), chunk_size):
                yield f"data: {json.dumps({'type': 'token', 'content': output[i:i+chunk_size]})}\n\n"

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
