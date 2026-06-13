"""Vertex AI Agent client — supports both Dialogflow CX and Reasoning Engine agents.

Features:
- Engine object cache with TTL (avoids re-fetching from GCP control plane)
- Session pool per (client_id, agent_id) with auto-expiry
- HTTP connection pooling for REST fallback
- Pre-warming at startup
"""

import json
import logging
import os
import time
from pathlib import Path
from threading import Lock

import requests as http_requests

logger = logging.getLogger(__name__)

# ── Credentials ──

_credentials = None
_credentials_lock = Lock()


def _get_credentials():
    """Get Google Cloud credentials from service account or ADC."""
    global _credentials
    with _credentials_lock:
        if _credentials and _credentials.valid:
            return _credentials

        from google.oauth2 import service_account
        from google.auth.transport.requests import Request

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
            from google.auth import default
            _credentials, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])

        _credentials.refresh(Request())
        return _credentials


# ── HTTP Connection Pool ──

_http_session: http_requests.Session | None = None


def _get_http_session() -> http_requests.Session:
    """Get a pooled HTTP session for REST API calls."""
    global _http_session
    if _http_session is None:
        _http_session = http_requests.Session()
        adapter = http_requests.adapters.HTTPAdapter(
            pool_connections=2,
            pool_maxsize=10,
            max_retries=1,
        )
        _http_session.mount("https://", adapter)
    return _http_session


# ── Vertex AI SDK Init ──

_re_initialized = False


def _init_vertex():
    """Initialize Vertex AI SDK once."""
    global _re_initialized
    if _re_initialized:
        return
    import vertexai
    vertexai.init(project="hypernovalabs-sa", location="us-central1")
    _re_initialized = True


# ── Engine Object Cache ──

_engine_cache: dict[str, tuple[object, float]] = {}  # agent_id -> (engine, fetched_at)
_engine_cache_lock = Lock()
ENGINE_CACHE_TTL = 3600  # 1 hour


def _get_reasoning_engine(agent_id: str, force_refresh: bool = False):
    """Get a cached Reasoning Engine object. Fetches from GCP only on miss or TTL expiry."""
    _init_vertex()

    now = time.time()
    if not force_refresh:
        with _engine_cache_lock:
            if agent_id in _engine_cache:
                engine, fetched_at = _engine_cache[agent_id]
                if now - fetched_at < ENGINE_CACHE_TTL:
                    return engine

    from vertexai import agent_engines
    engine = agent_engines.get(agent_id)

    with _engine_cache_lock:
        _engine_cache[agent_id] = (engine, now)

    logger.info(f"RE engine cached: {agent_id}")
    return engine


def invalidate_engine_cache(agent_id: str = None):
    """Invalidate one or all cached engines. Call after agent redeployment."""
    with _engine_cache_lock:
        if agent_id:
            _engine_cache.pop(agent_id, None)
        else:
            _engine_cache.clear()
    logger.info(f"Engine cache invalidated: {'all' if not agent_id else agent_id}")


def prewarm_engines() -> int:
    """Pre-warm all enabled RE engines at startup. Returns count of cached engines."""
    from app.vertex_agents.registry import get_enabled_agents
    agents = get_enabled_agents()
    re_agents = [a for a in agents if a.get("type", "reasoning_engine") == "reasoning_engine"]

    count = 0
    for agent in re_agents:
        try:
            _get_reasoning_engine(agent["agent_id"])
            count += 1
        except Exception as e:
            logger.warning(f"Pre-warm failed for {agent['name']}: {e}")

    return count


def get_cache_stats() -> dict:
    """Get engine cache and session pool stats for health endpoint."""
    with _engine_cache_lock:
        engine_count = len(_engine_cache)
    with _session_pool_lock:
        session_count = len(_session_pool)
    return {
        "engines_cached": engine_count,
        "sessions_pooled": session_count,
        "engine_cache_ttl": ENGINE_CACHE_TTL,
    }


# ── Session Pool ──

# (client_id, agent_id) -> {"session_id": str, "created_at": float, "last_used": float}
_session_pool: dict[tuple[str, str], dict] = {}
_session_pool_lock = Lock()
SESSION_MAX_AGE = 1800   # 30 min
SESSION_MAX_IDLE = 600   # 10 min idle


def _get_or_create_session(
    engine, agent_id: str, client_id: str, user_id: str,
) -> str:
    """Get an existing RE session for this client+agent, or create a new one."""
    key = (client_id, agent_id)
    now = time.time()

    with _session_pool_lock:
        entry = _session_pool.get(key)
        if entry:
            age = now - entry["created_at"]
            idle = now - entry["last_used"]
            if age < SESSION_MAX_AGE and idle < SESSION_MAX_IDLE:
                entry["last_used"] = now
                logger.debug(f"RE session reused: client={client_id} agent={agent_id}")
                return entry["session_id"]

    # Create new session (outside lock — network call)
    session = engine.create_session(user_id=user_id)
    session_id = session["id"] if isinstance(session, dict) else session.id

    with _session_pool_lock:
        _session_pool[key] = {
            "session_id": session_id,
            "created_at": now,
            "last_used": now,
        }

    logger.info(f"RE session created: client={client_id} agent={agent_id} session={session_id}")
    return session_id


def _evict_session(client_id: str, agent_id: str):
    """Remove a session from the pool (e.g., on server-side expiry error)."""
    key = (client_id, agent_id)
    with _session_pool_lock:
        _session_pool.pop(key, None)


def cleanup_expired_sessions():
    """Periodic cleanup of expired session pool entries."""
    now = time.time()
    expired_keys = []
    with _session_pool_lock:
        for key, entry in _session_pool.items():
            if now - entry["created_at"] > SESSION_MAX_AGE or now - entry["last_used"] > SESSION_MAX_IDLE:
                expired_keys.append(key)
        for key in expired_keys:
            del _session_pool[key]
    if expired_keys:
        logger.info(f"Cleaned up {len(expired_keys)} expired RE sessions")


# ── Reasoning Engine Query ──

def reasoning_engine_query(
    agent_config: dict,
    session_id: str,
    message: str,
    user_id: str = "nova-user",
    client_id: str = "default",
) -> str:
    """Send a message to a Reasoning Engine agent.

    Tries SDK first (with session pool), falls back to REST API.
    """
    agent_id = agent_config["agent_id"]

    # Try SDK first
    try:
        result = _re_query_sdk(agent_config, session_id, message, user_id, client_id)
        logger.debug(f"RE served by SDK for agent {agent_id}")
        return result
    except Exception as sdk_err:
        logger.warning(f"RE SDK failed for agent {agent_id}, trying REST: {sdk_err}")

    # Fallback to REST. Logged at INFO so a silently always-failing SDK (every
    # response served by REST) is visible instead of looking healthy.
    try:
        result = _re_query_rest(agent_config, session_id, message, user_id, client_id)
        logger.info(f"RE served by REST fallback for agent {agent_id} (SDK failed)")
        return result
    except Exception as rest_err:
        logger.error(f"RE REST also failed for agent {agent_id}: {rest_err}", exc_info=True)
        return _re_format_error(agent_config, rest_err)


def _re_query_sdk(
    agent_config: dict, session_id: str, message: str,
    user_id: str, client_id: str,
) -> str:
    """Query via Vertex AI Python SDK with engine cache + session pool."""
    agent_id = agent_config["agent_id"]
    engine = _get_reasoning_engine(agent_id)

    # Use session pool
    re_session_id = _get_or_create_session(engine, agent_id, client_id, user_id)

    try:
        response_texts = []
        for event in engine.stream_query(
            session_id=re_session_id,
            message=message,
        ):
            text = _extract_re_event_text(event)
            if text:
                response_texts.append(text)

        if response_texts:
            return "\n".join(response_texts)

        return "Agent responded but no text was returned."

    except Exception as e:
        # Session may have expired server-side — evict and retry once
        error_str = str(e).lower()
        if "session" in error_str and ("not found" in error_str or "expired" in error_str or "invalid" in error_str):
            logger.warning(f"RE session expired for client={client_id} agent={agent_id}, retrying...")
            _evict_session(client_id, agent_id)
            re_session_id = _get_or_create_session(engine, agent_id, client_id, user_id)

            response_texts = []
            for event in engine.stream_query(session_id=re_session_id, message=message):
                text = _extract_re_event_text(event)
                if text:
                    response_texts.append(text)
            return "\n".join(response_texts) if response_texts else "Agent responded but no text was returned."

        raise


def _re_query_rest(
    agent_config: dict, session_id: str, message: str,
    user_id: str, client_id: str,
) -> str:
    """Query via REST API (fallback) with HTTP connection pooling."""
    agent_id = agent_config["agent_id"]
    project_id = agent_config.get("project_id", "hypernovalabs-sa")
    location = agent_config.get("location", "us-central1")
    base_url = (
        f"https://{location}-aiplatform.googleapis.com/v1beta1/"
        f"projects/{project_id}/locations/{location}/reasoningEngines/{agent_id}"
    )

    creds = _get_credentials()
    if not creds.valid:
        from google.auth.transport.requests import Request
        creds.refresh(Request())

    headers = {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
    }

    http = _get_http_session()

    # Check session pool first
    key = (client_id, agent_id)
    now = time.time()
    re_session_id = None

    with _session_pool_lock:
        entry = _session_pool.get(key)
        if entry:
            age = now - entry["created_at"]
            idle = now - entry["last_used"]
            if age < SESSION_MAX_AGE and idle < SESSION_MAX_IDLE:
                re_session_id = entry["session_id"]
                entry["last_used"] = now

    # Create session if needed
    if not re_session_id:
        resp = http.post(
            f"{base_url}:query",
            json={"class_method": "create_session", "input": {"user_id": user_id}},
            headers=headers, timeout=30,
        )
        resp.raise_for_status()
        re_session_id = resp.json()["output"]["id"]
        with _session_pool_lock:
            _session_pool[key] = {
                "session_id": re_session_id,
                "created_at": now,
                "last_used": now,
            }
        logger.info(f"RE REST session created: client={client_id} agent={agent_id}")

    # Stream query
    resp = http.post(
        f"{base_url}:streamQuery",
        json={
            "class_method": "stream_query",
            "input": {
                "user_id": user_id,
                "session_id": re_session_id,
                "message": message,
            },
        },
        headers=headers, timeout=90,
    )
    resp.raise_for_status()

    # Parse response
    raw = resp.text.strip()
    if not raw:
        return "Agent responded but no text was returned."

    try:
        data = json.loads(raw)
        return _extract_re_rest_text(data)
    except json.JSONDecodeError:
        pass

    # SSE format fallback
    texts = []
    for line in raw.split("\n"):
        line = line.strip()
        if line.startswith("data:"):
            line = line[5:].strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            text = _extract_re_rest_text(data)
            if text:
                texts.append(text)
        except json.JSONDecodeError:
            continue

    return "\n".join(texts) if texts else "Agent responded but could not parse response."


# ── REST Response Parsing ──

def _extract_re_rest_text(data: dict) -> str:
    """Extract text from a REST API Reasoning Engine response."""
    content = data.get("content", {})
    if isinstance(content, dict):
        parts = content.get("parts", [])
        texts = [p["text"] for p in parts if isinstance(p, dict) and "text" in p]
        if texts:
            return " ".join(texts)

    output = data.get("output", "")
    if isinstance(output, str) and output:
        return output

    if isinstance(output, list):
        texts = []
        for item in output:
            if isinstance(item, dict):
                c = item.get("content", {})
                if isinstance(c, dict):
                    for p in c.get("parts", []):
                        if isinstance(p, dict) and "text" in p:
                            texts.append(p["text"])
        if texts:
            return " ".join(texts)

    return ""


def _re_format_error(agent_config: dict, err: Exception) -> str:
    """Format a Reasoning Engine error into a user-friendly message."""
    error_str = str(err)
    name = agent_config.get("name", agent_config["agent_id"])

    if "404" in error_str or "not found" in error_str.lower():
        return f"Error: Reasoning Engine agent '{name}' not found. Verify agent_id."
    if "429" in error_str:
        return "Error: Rate limit exceeded. Try again in a moment."
    if "403" in error_str or "permission" in error_str.lower():
        return "Error: Permission denied. Check service account has roles/aiplatform.user."
    if "Failed to create session" in error_str:
        return f"Error: Agent '{name}' cannot create sessions. Check session backend config in Agent Builder."
    return f"Error communicating with Reasoning Engine agent: {err}"


# ── SDK Event Parsing ──

def _extract_re_event_text(event) -> str:
    """Extract text from a Reasoning Engine stream event."""
    if isinstance(event, str):
        return event

    if isinstance(event, dict):
        if "content" in event:
            content = event["content"]
            if isinstance(content, str):
                return content
            if isinstance(content, dict) and "parts" in content:
                parts = content["parts"]
                return " ".join(p.get("text", "") for p in parts if isinstance(p, dict))
        if "text" in event:
            return event["text"]
        if "message" in event:
            msg = event["message"]
            if isinstance(msg, str):
                return msg
            if isinstance(msg, dict):
                return msg.get("text", "")
        if "actions" in event:
            return ""
        if "author" in event and event.get("author") == "agent":
            parts = event.get("content", {}).get("parts", [])
            return " ".join(p.get("text", "") for p in parts if isinstance(p, dict) and "text" in p)

    for attr in ("text", "content", "message"):
        val = getattr(event, attr, None)
        if val and isinstance(val, str):
            return val

    return ""


# ── Session Helpers (public API) ──

def reasoning_engine_create_session(
    agent_config: dict,
    user_id: str = "nova-user",
) -> str:
    """Create a new session for a Reasoning Engine agent. Returns session_id."""
    agent_id = agent_config["agent_id"]
    try:
        engine = _get_reasoning_engine(agent_id)
        session = engine.create_session(user_id=user_id)
        sid = session["id"] if isinstance(session, dict) else session.id
        logger.info(f"RE agent {agent_id}: created session {sid}")
        return sid
    except Exception as e:
        logger.error(f"RE session creation error: {e}", exc_info=True)
        return ""


def reasoning_engine_list_sessions(
    agent_config: dict,
    user_id: str = "nova-user",
) -> list[dict]:
    """List sessions for a Reasoning Engine agent."""
    agent_id = agent_config["agent_id"]
    try:
        engine = _get_reasoning_engine(agent_id)
        sessions = engine.list_sessions(user_id=user_id)
        return [
            {"id": s["id"] if isinstance(s, dict) else s.id}
            for s in sessions
        ]
    except Exception as e:
        logger.error(f"RE list sessions error: {e}", exc_info=True)
        return []


# ── Dialogflow CX (legacy) ──

def detect_intent(
    agent_config: dict,
    session_id: str,
    message: str,
    language: str = "es",
) -> str:
    """Send a message to a Dialogflow CX agent and return the response text."""
    agent_id = agent_config["agent_id"]
    project_id = agent_config.get("project_id", "gen-lang-client-0486673441")
    location = agent_config.get("location", "us-central1")

    try:
        creds = _get_credentials()

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

        http = _get_http_session()
        response = http.post(url, json=body, headers=headers, timeout=30)

        if response.status_code == 401:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            headers["Authorization"] = f"Bearer {creds.token}"
            response = http.post(url, json=body, headers=headers, timeout=30)

        if response.status_code == 404:
            return f"Error: Agent '{agent_config.get('name', agent_id)}' not found. Verify agent_id and location."

        if response.status_code == 429:
            return "Error: Rate limit exceeded. Try again in a moment."

        response.raise_for_status()
        result = response.json()

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

    messages = query_result.get("responseMessages", [])
    texts = []
    for msg in messages:
        if "text" in msg:
            text_parts = msg["text"].get("text", [])
            texts.extend(text_parts)

    if texts:
        return "\n".join(texts)

    fulfillment = query_result.get("text", "")
    if fulfillment:
        return fulfillment

    return "Agent responded but no text was returned."


# ── Unified Interface ──

def query_agent(
    agent_config: dict,
    session_id: str,
    message: str,
    language: str = "es",
    user_id: str = "nova-user",
    client_id: str = "default",
) -> str:
    """Unified query: routes to the correct backend based on agent type.

    agent_config["type"] can be:
      - "reasoning_engine" (default) — Vertex AI Agent Engine
      - "dialogflow_cx" — legacy Dialogflow CX
    """
    agent_type = agent_config.get("type", "reasoning_engine")

    if agent_type == "dialogflow_cx":
        return detect_intent(agent_config, session_id, message, language)
    else:
        return reasoning_engine_query(agent_config, session_id, message, user_id, client_id)


def test_agent(agent_config: dict) -> dict:
    """Test connectivity to an agent. Returns {ok, message}."""
    try:
        response = query_agent(
            agent_config,
            session_id="nova-test",
            message="Hello, are you there? Respond briefly.",
            language="en",
            client_id="nova-test",
        )
        is_error = response.startswith("Error:")
        return {
            "ok": not is_error,
            "message": response[:200],
        }
    except Exception as e:
        return {"ok": False, "message": str(e)}


# ── Discovery ──

def discover_agent(agent_config: dict) -> dict:
    """Interview an agent to discover its capabilities."""
    agent_type = agent_config.get("type", "reasoning_engine")

    if agent_type == "reasoning_engine":
        return _discover_reasoning_engine(agent_config)
    else:
        return _discover_dialogflow(agent_config)


def _discover_reasoning_engine(agent_config: dict) -> dict:
    """Discovery for Reasoning Engine agents."""
    discovery = {"raw_responses": []}
    user_id = "nova-discovery"

    session_id = reasoning_engine_create_session(agent_config, user_id=user_id)
    if not session_id:
        discovery["raw_responses"].append("Error: Could not create discovery session")
        return discovery

    questions = [
        "Describe briefly what you do, what topics you handle, and what type of questions you can answer. Be specific.",
        "What can you NOT do? What questions should NOT be sent to you? Be specific about your limitations.",
        "Give me 3-5 example questions or tasks that you handle best.",
    ]

    for q in questions:
        r = reasoning_engine_query(agent_config, session_id, q, user_id=user_id, client_id="nova-discovery")
        discovery["raw_responses"].append(r)

    return _synthesize_discovery(agent_config, discovery)


def _discover_dialogflow(agent_config: dict) -> dict:
    """Discovery for Dialogflow CX agents."""
    session_id = "nova-discovery"
    discovery = {"raw_responses": []}

    questions = [
        ("Describe briefly what you do, what topics you handle, and what type of questions you can answer. Be specific.", "es"),
        ("What can you NOT do? What questions should NOT be sent to you? Be specific about your limitations.", "es"),
        ("Give me 3-5 example questions or tasks that you handle best.", "es"),
    ]

    for q, lang in questions:
        r = detect_intent(agent_config, session_id, q, language=lang)
        discovery["raw_responses"].append(r)

    return _synthesize_discovery(agent_config, discovery)


def _synthesize_discovery(agent_config: dict, discovery: dict) -> dict:
    """Use LLM to structure discovery responses into registry fields."""
    r1, r2, r3 = discovery["raw_responses"][:3] if len(discovery["raw_responses"]) >= 3 else (
        discovery["raw_responses"] + [""] * 3
    )[:3]

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
            discovery["description"] = r1[:200] if not r1.startswith("Error:") else ""
            discovery["specialties"] = []
            discovery["routing_prompt"] = ""
    except Exception as e:
        logger.warning(f"Discovery synthesis failed: {e}")
        discovery["description"] = r1[:200] if not r1.startswith("Error:") else ""
        discovery["specialties"] = []
        discovery["routing_prompt"] = ""

    return discovery
