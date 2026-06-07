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


def discover_agent(agent_config: dict) -> dict:
    """Interview an agent to discover its capabilities.

    Sends discovery questions and returns structured info:
    {description, specialties, routing_prompt, raw_responses}
    """
    session_id = "nova-discovery"
    discovery = {"raw_responses": []}

    # Question 1: What do you do?
    r1 = detect_intent(
        agent_config, session_id,
        "Describe briefly what you do, what topics you handle, and what type of questions you can answer. Be specific.",
        language="es",
    )
    discovery["raw_responses"].append(r1)

    # Question 2: What are your limitations?
    r2 = detect_intent(
        agent_config, session_id,
        "What can you NOT do? What questions should NOT be sent to you? Be specific about your limitations.",
        language="es",
    )
    discovery["raw_responses"].append(r2)

    # Question 3: Example use cases
    r3 = detect_intent(
        agent_config, session_id,
        "Give me 3-5 example questions or tasks that you handle best.",
        language="es",
    )
    discovery["raw_responses"].append(r3)

    # Now use LLM to structure the discovery into registry fields
    from app.tasks.workers.base import _llm_call, parse_json_response

    synthesis_prompt = (
        f"An AI agent named '{agent_config.get('name', 'Unknown')}' was interviewed.\n\n"
        f"What it does:\n{r1}\n\n"
        f"What it cannot do:\n{r2}\n\n"
        f"Example use cases:\n{r3}\n\n"
        f"Based on this, generate a JSON object with:\n"
        f'{{"description": "one sentence describing what it does (in Spanish)",\n'
        f'"specialties": ["keyword1", "keyword2", ...] (8-12 lowercase keywords for matching),\n'
        f'"routing_prompt": "When to use this agent and when NOT to use it (in Spanish, 2-3 sentences)"}}\n\n'
        f"Return ONLY the JSON object."
    )

    try:
        result = _llm_call(synthesis_prompt)
        parsed = parse_json_response(result)
        if isinstance(parsed, dict):
            discovery["description"] = parsed.get("description", "")
            discovery["specialties"] = parsed.get("specialties", [])
            discovery["routing_prompt"] = parsed.get("routing_prompt", "")
        else:
            # Fallback: use raw response as description
            discovery["description"] = r1[:200] if not r1.startswith("Error:") else ""
            discovery["specialties"] = []
            discovery["routing_prompt"] = ""
    except Exception as e:
        logger.warning(f"Discovery synthesis failed: {e}")
        discovery["description"] = r1[:200] if not r1.startswith("Error:") else ""
        discovery["specialties"] = []
        discovery["routing_prompt"] = ""

    return discovery
