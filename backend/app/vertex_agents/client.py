"""Vertex AI Agent client — REST calls to Dialogflow CX detectIntent."""

import logging
import os
from pathlib import Path

import requests as http_requests

logger = logging.getLogger(__name__)

_credentials = None


def _get_credentials():
    """Get Google Cloud credentials from service account."""
    global _credentials
    if _credentials and _credentials.valid:
        return _credentials

    from google.oauth2 import service_account
    from google.auth.transport.requests import Request

    # Try explicit path first
    sa_path = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS",
        str(Path(__file__).parent.parent.parent.parent / "secrets" / "gcp-service-account.json"),
    )

    if Path(sa_path).exists():
        _credentials = service_account.Credentials.from_service_account_file(
            sa_path,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
    else:
        # Fallback to application default credentials
        from google.auth import default
        _credentials, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])

    _credentials.refresh(Request())
    return _credentials


def detect_intent(
    agent_config: dict,
    session_id: str,
    message: str,
    language: str = "es",
) -> str:
    """Send a message to a Vertex AI agent and return the response text.

    Args:
        agent_config: Dict with agent_id, project_id, location
        session_id: Unique session ID for conversation continuity
        message: User message to send
        language: Language code (default: es)

    Returns:
        Agent response text, or error string
    """
    agent_id = agent_config["agent_id"]
    project_id = agent_config.get("project_id", "gen-lang-client-0486673441")
    location = agent_config.get("location", "us-central1")

    try:
        creds = _get_credentials()

        # Refresh if expired
        if not creds.valid:
            from google.auth.transport.requests import Request
            creds.refresh(Request())

        url = (
            f"https://{location}-dialogflow.googleapis.com/v3/"
            f"projects/{project_id}/locations/{location}/agents/{agent_id}/"
            f"sessions/{session_id}:detectIntent"
        )

        headers = {
            "Authorization": f"Bearer {creds.token}",
            "Content-Type": "application/json",
        }

        body = {
            "queryInput": {
                "text": {"text": message},
                "languageCode": language,
            }
        }

        response = http_requests.post(url, json=body, headers=headers, timeout=30)

        if response.status_code == 401:
            # Token expired, force refresh and retry
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            headers["Authorization"] = f"Bearer {creds.token}"
            response = http_requests.post(url, json=body, headers=headers, timeout=30)

        if response.status_code == 404:
            return f"Error: Agent '{agent_config.get('name', agent_id)}' not found. Verify agent_id and location."

        if response.status_code == 429:
            return "Error: Rate limit exceeded. Try again in a moment."

        response.raise_for_status()
        result = response.json()

        # Extract text from response
        return _extract_response_text(result)

    except http_requests.exceptions.Timeout:
        logger.error("Vertex AI agent call timed out")
        return "Error: Agent did not respond in time (30s timeout)."
    except http_requests.exceptions.HTTPError as e:
        logger.error(f"Vertex AI HTTP error: {e.response.status_code} — {e.response.text[:200]}")
        return f"Error: Vertex AI returned {e.response.status_code}"
    except Exception as e:
        logger.error(f"Vertex AI agent error: {e}", exc_info=True)
        return f"Error communicating with agent: {e}"


def _extract_response_text(result: dict) -> str:
    """Extract readable text from detectIntent response."""
    query_result = result.get("queryResult", {})

    # Get response messages
    messages = query_result.get("responseMessages", [])
    texts = []
    for msg in messages:
        if "text" in msg:
            text_parts = msg["text"].get("text", [])
            texts.extend(text_parts)

    if texts:
        return "\n".join(texts)

    # Fallback: fulfillment text
    fulfillment = query_result.get("text", "")
    if fulfillment:
        return fulfillment

    return "Agent responded but no text was returned."


def test_agent(agent_config: dict) -> dict:
    """Test connectivity to an agent. Returns {ok, message}."""
    try:
        response = detect_intent(
            agent_config,
            session_id="nova-test",
            message="Hello",
            language="en",
        )
        is_error = response.startswith("Error:")
        return {
            "ok": not is_error,
            "message": response[:200],
        }
    except Exception as e:
        return {"ok": False, "message": str(e)}
