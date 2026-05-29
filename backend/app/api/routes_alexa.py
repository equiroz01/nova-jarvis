import logging
import uuid
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Any

from app.agent.orchestrator import invoke_agent

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/alexa")
async def alexa_webhook(req: Request):
    """Handle incoming Alexa skill requests. Alexa sends JSON with intent/slot data."""
    body = await req.json()

    request_type = body.get("request", {}).get("type", "")

    # Handle launch request
    if request_type == "LaunchRequest":
        return _alexa_response("Hello! I'm Jarvis. How can I help you?")

    # Handle intent request
    if request_type == "IntentRequest":
        intent_name = body.get("request", {}).get("intent", {}).get("name", "")

        if intent_name in ("AMAZON.StopIntent", "AMAZON.CancelIntent"):
            return _alexa_response("Goodbye, sir.", should_end=True)

        if intent_name == "AMAZON.HelpIntent":
            return _alexa_response(
                "You can ask me about the time, search the web, "
                "check your calendar, or control your smart home devices."
            )

        if intent_name == "AskJarvisIntent":
            slots = body.get("request", {}).get("intent", {}).get("slots", {})
            query = slots.get("query", {}).get("value", "")

            if not query:
                return _alexa_response("I didn't catch that. Could you repeat?")

            # Use Alexa user ID as session for continuity
            session_id = body.get("session", {}).get("user", {}).get("userId", str(uuid.uuid4()))
            executor = req.app.state.agent_executor

            try:
                response_text = invoke_agent(query, f"alexa-{session_id}", executor)
                return _alexa_response(response_text)
            except Exception as e:
                logger.error(f"Alexa agent error: {e}", exc_info=True)
                return _alexa_response("Sorry, I encountered an error processing your request.")

    # Handle session ended
    if request_type == "SessionEndedRequest":
        return _alexa_response("", should_end=True)

    return _alexa_response("I'm not sure how to handle that.")


def _alexa_response(text: str, should_end: bool = False) -> dict:
    """Format a standard Alexa JSON response."""
    return {
        "version": "1.0",
        "response": {
            "outputSpeech": {
                "type": "PlainText",
                "text": text,
            },
            "shouldEndSession": should_end,
        },
    }
