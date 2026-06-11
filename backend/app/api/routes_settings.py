"""Settings API — manage MCP servers, Voice ID, AgilityTask, Vertex AI Agents and NOVA configuration."""

import json
import yaml
import logging
from pathlib import Path
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, UploadFile, File, Form

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings")

MCP_CONFIG_PATH = Path(__file__).parent.parent.parent / "mcp_config.yaml"


class MCPServer(BaseModel):
    name: str
    description: str = ""
    type: str = "stdio"  # stdio, sse, http
    command: str = ""
    args: list[str] = []
    env: dict[str, str] = {}
    url: str = ""  # for SSE/HTTP type
    headers: dict[str, str] = {}  # for SSE/HTTP auth headers
    enabled: bool = True


class MCPConfigResponse(BaseModel):
    servers: list[MCPServer]


def _load_config() -> dict:
    if not MCP_CONFIG_PATH.exists():
        return {"servers": []}
    try:
        with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data if "servers" in data else {"servers": []}
    except Exception as e:
        logger.error(f"Error loading MCP config: {e}")
        return {"servers": []}


def _save_config(data: dict):
    with open(MCP_CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


@router.get("/mcp", response_model=MCPConfigResponse)
async def get_mcp_servers():
    config = _load_config()
    servers = config.get("servers") or []
    return MCPConfigResponse(servers=[MCPServer(**s) for s in servers])


@router.post("/mcp", response_model=MCPConfigResponse)
async def save_mcp_servers(config: MCPConfigResponse):
    data = {"servers": [s.dict() for s in config.servers]}
    _save_config(data)
    return config


@router.post("/mcp/add", response_model=MCPServer)
async def add_mcp_server(server: MCPServer):
    config = _load_config()
    servers = config.get("servers") or []
    # Check duplicate
    for s in servers:
        if s.get("name") == server.name:
            raise HTTPException(status_code=400, detail=f"Server '{server.name}' already exists")
    servers.append(server.dict())
    config["servers"] = servers
    _save_config(config)
    return server


@router.delete("/mcp/{name}")
async def delete_mcp_server(name: str):
    config = _load_config()
    servers = config.get("servers") or []
    config["servers"] = [s for s in servers if s.get("name") != name]
    if len(config["servers"]) == len(servers):
        raise HTTPException(status_code=404, detail=f"Server '{name}' not found")
    _save_config(config)
    return {"deleted": name}


@router.patch("/mcp/{name}/toggle")
async def toggle_mcp_server(name: str):
    config = _load_config()
    servers = config.get("servers") or []
    for s in servers:
        if s.get("name") == name:
            s["enabled"] = not s.get("enabled", True)
            _save_config(config)
            return {"name": name, "enabled": s["enabled"]}
    raise HTTPException(status_code=404, detail=f"Server '{name}' not found")


# ── Voice ID ──

@router.get("/voice-id/status")
async def voice_id_status():
    from app.services.voice_id import is_enrolled
    return {"enrolled": is_enrolled()}


@router.post("/voice-id/enroll")
async def voice_id_enroll(
    samples: list[UploadFile] = File(...),
    name: str = Form("Emeldo"),
):
    """Enroll voice: upload 3+ WAV samples to create voiceprint."""
    from app.services.voice_id import enroll
    audio_list = []
    for s in samples:
        audio_list.append(await s.read())
    result = enroll(audio_list, name=name)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["detail"])
    return result


# ── MCP ──

@router.post("/mcp/reconnect")
async def reconnect_mcp_servers():
    """Reconnect all MCP servers after config changes."""
    from app.mcp_manager import initialize_mcp_servers, get_mcp_status
    await initialize_mcp_servers()
    return {"status": "reconnected", "servers": get_mcp_status()}


@router.get("/mcp/status")
async def mcp_status():
    """Get connection status of all MCP servers."""
    from app.mcp_manager import get_mcp_status
    return {"servers": get_mcp_status()}


# ── AgilityTask ──

AGILITY_CREDS_PATHS = [
    Path(__file__).parent.parent.parent.parent / ".agilitytask" / "credentials.json",
    Path.home() / ".agilitytask" / "credentials.json",
]


def _find_agility_creds() -> Path | None:
    for p in AGILITY_CREDS_PATHS:
        if p.exists():
            return p
    return None


def _load_agility_creds() -> dict:
    p = _find_agility_creds()
    if not p:
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _save_agility_creds(data: dict):
    p = AGILITY_CREDS_PATHS[0]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))


@router.get("/agilitytask/status")
async def agilitytask_status():
    """Check AgilityTask connection status."""
    import urllib.request
    import urllib.error

    creds = _load_agility_creds()
    api_key = creds.get("apiKey", "")
    email = creds.get("email", "")
    base_url = creds.get("baseUrl", "https://agilitytask.hnlapps.com")

    if not api_key:
        return {"configured": False, "connected": False, "email": "", "projects": 0}

    try:
        req = urllib.request.Request(
            f"{base_url}/api/v1/projects?limit=1",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
            total = data.get("meta", {}).get("total", 0)
            return {"configured": True, "connected": True, "email": email, "projects": total}
    except Exception as e:
        logger.warning(f"AgilityTask connection check failed: {e}")
        return {"configured": True, "connected": False, "email": email, "projects": 0}


@router.get("/agilitytask/credentials")
async def agilitytask_get_credentials():
    """Get AgilityTask credentials (masked API key)."""
    creds = _load_agility_creds()
    api_key = creds.get("apiKey", "")
    masked = api_key[:6] + "…" + api_key[-4:] if len(api_key) > 10 else ""
    return {
        "apiKey": masked,
        "email": creds.get("email", ""),
        "baseUrl": creds.get("baseUrl", "https://agilitytask.hnlapps.com"),
    }


@router.post("/agilitytask/credentials")
async def agilitytask_save_credentials(
    apiKey: str = Form(""),
    email: str = Form(""),
    baseUrl: str = Form("https://agilitytask.hnlapps.com"),
):
    """Save AgilityTask credentials."""
    if not apiKey or not email:
        raise HTTPException(status_code=400, detail="API Key and email are required")

    creds = _load_agility_creds()
    creds["apiKey"] = apiKey
    creds["email"] = email
    creds["baseUrl"] = baseUrl or "https://agilitytask.hnlapps.com"
    _save_agility_creds(creds)

    # Clear cached API key in tool (best-effort; the save above already succeeded)
    try:
        from app.tools.cloud.agilitytask_tool import _load_credentials
        import app.tools.cloud.agilitytask_tool as at
        at._API_KEY = None
    except Exception:
        logger.warning("AgilityTask API-key cache clear failed after save", exc_info=True)

    return {"status": "saved"}


@router.delete("/agilitytask/credentials")
async def agilitytask_delete_credentials():
    """Remove AgilityTask credentials."""
    p = _find_agility_creds()
    if p and p.exists():
        p.unlink()
    try:
        import app.tools.cloud.agilitytask_tool as at
        at._API_KEY = None
    except Exception:
        logger.warning("AgilityTask API-key cache clear failed after delete", exc_info=True)
    return {"status": "deleted"}


# ── Microsoft 365 ──

@router.get("/microsoft/status")
async def microsoft_status():
    """Check Microsoft 365 connection status."""
    from app.services.keychain import keychain

    client_id = keychain.get("microsoft_client_id")
    refresh_token = keychain.get("microsoft_refresh_token")
    tenant_id = keychain.get("microsoft_tenant_id")

    if not client_id or not refresh_token:
        # Fallback to settings
        client_id = client_id or getattr(settings, "microsoft_client_id", "") or ""
        refresh_token = refresh_token or getattr(settings, "microsoft_refresh_token", "") or ""

    if not client_id or not refresh_token:
        return {"configured": False, "connected": False, "email": "", "name": ""}

    try:
        from app.services.microsoft_auth import graph_request
        me = graph_request("GET", "me?$select=displayName,mail,userPrincipalName")
        return {
            "configured": True,
            "connected": True,
            "email": me.get("mail") or me.get("userPrincipalName", ""),
            "name": me.get("displayName", ""),
        }
    except Exception as e:
        logger.warning(f"Microsoft 365 status check failed: {e}")
        return {"configured": True, "connected": False, "email": "", "name": str(e)[:100]}


@router.delete("/microsoft/credentials")
async def microsoft_delete_credentials():
    """Remove Microsoft 365 credentials from Keychain."""
    from app.services.keychain import keychain
    for key in ["microsoft_client_id", "microsoft_client_secret", "microsoft_refresh_token", "microsoft_tenant_id"]:
        keychain.delete(key)
    # Clear cached token (best-effort; the Keychain delete above already succeeded)
    try:
        import app.services.microsoft_auth as ma
        ma._access_token = ""
        ma._token_expiry = 0
    except Exception:
        logger.warning("Microsoft token cache clear failed after delete", exc_info=True)
    return {"status": "deleted"}


# ── Keychain ──

@router.get("/keychain/list")
async def keychain_list():
    """List all secrets in NOVA Keychain (masked values)."""
    from app.services.keychain import keychain
    keys = keychain.list()
    secrets = []
    for k in sorted(keys):
        val = keychain.get(k)
        masked = val[:4] + "…" + val[-4:] if len(val) > 8 else "****"
        secrets.append({"key": k, "masked": masked})
    return {"secrets": secrets, "count": len(secrets)}


@router.post("/keychain/set")
async def keychain_set(key: str = Form(...), value: str = Form(...)):
    """Store a secret in macOS Keychain."""
    from app.services.keychain import keychain
    if not key or not value:
        raise HTTPException(status_code=400, detail="Key and value are required")
    ok = keychain.set(key, value)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to store in Keychain")
    return {"status": "stored", "key": key}


@router.delete("/keychain/{key}")
async def keychain_delete(key: str):
    """Remove a secret from Keychain."""
    from app.services.keychain import keychain
    keychain.delete(key)
    return {"status": "deleted", "key": key}


@router.post("/keychain/import")
async def keychain_import_all():
    """Import all secrets from .env, mcp_config.yaml, and AgilityTask into Keychain."""
    from app.services.keychain import keychain
    results = {}
    results.update(keychain.import_from_env())
    results.update(keychain.import_from_mcp_config())
    results.update(keychain.import_from_agilitytask())
    return {"imported": results, "total": sum(1 for v in results.values() if v)}


# ── Vertex AI Agents ──

class VertexAgentRequest(BaseModel):
    name: str
    description: str = ""
    agent_id: str
    type: str = "reasoning_engine"  # reasoning_engine or dialogflow_cx
    project_id: str = "hypernovalabs-sa"
    location: str = "us-central1"
    specialties: list[str] = []
    routing_prompt: str = ""
    enabled: bool = True


@router.get("/agents")
async def list_agents():
    """List all Vertex AI agents."""
    from app.vertex_agents.registry import load_agents
    return {"agents": load_agents()}


@router.post("/agents/add")
async def add_agent(req: VertexAgentRequest):
    """Add a new Vertex AI agent. Auto-discovers capabilities by interviewing the agent."""
    from app.vertex_agents.registry import load_agents, save_agents
    from app.vertex_agents.client import discover_agent

    agents = load_agents()
    if any(a["name"].lower() == req.name.lower() for a in agents):
        raise HTTPException(400, f"Agent '{req.name}' already exists")

    agent_data = req.model_dump()

    # Auto-discover: interview the agent to learn what it does
    try:
        discovery = discover_agent(agent_data)

        # Fill in missing fields from discovery (don't overwrite user-provided values)
        if not agent_data.get("description") and discovery.get("description"):
            agent_data["description"] = discovery["description"]
        if not agent_data.get("specialties") and discovery.get("specialties"):
            agent_data["specialties"] = discovery["specialties"]
        if not agent_data.get("routing_prompt") and discovery.get("routing_prompt"):
            agent_data["routing_prompt"] = discovery["routing_prompt"]

        # Save to brain for long-term memory
        try:
            from app.knowledge.brain import save_note
            brain_content = (
                f"## Agent: {agent_data['name']}\n\n"
                f"**Description:** {agent_data.get('description', 'N/A')}\n\n"
                f"**Specialties:** {', '.join(agent_data.get('specialties', []))}\n\n"
                f"**When to use:** {agent_data.get('routing_prompt', 'N/A')}\n\n"
                f"**Discovery responses:**\n"
            )
            for i, r in enumerate(discovery.get("raw_responses", []), 1):
                brain_content += f"\n### Response {i}\n{r}\n"
            save_note(f"Agent: {agent_data['name']}", brain_content, category="facts")
        except Exception as e:
            logger.warning(f"Failed to save agent discovery to brain: {e}")

        agent_data["_discovery"] = {
            "discovered": True,
            "raw_responses": discovery.get("raw_responses", []),
        }
    except Exception as e:
        logger.warning(f"Agent discovery failed for '{req.name}': {e}")
        agent_data["_discovery"] = {"discovered": False, "error": str(e)}

    # Remove internal fields before saving to YAML
    discovery_result = agent_data.pop("_discovery", {})

    agents.append(agent_data)
    save_agents(agents)

    return {
        "status": "added",
        "agent": agent_data,
        "discovery": discovery_result,
    }


@router.delete("/agents/{name}")
async def delete_agent(name: str):
    """Delete a Vertex AI agent."""
    from app.vertex_agents.registry import load_agents, save_agents
    agents = load_agents()
    filtered = [a for a in agents if a["name"].lower() != name.lower()]
    if len(filtered) == len(agents):
        raise HTTPException(404, f"Agent '{name}' not found")
    save_agents(filtered)
    return {"status": "deleted"}


@router.patch("/agents/{name}/toggle")
async def toggle_agent(name: str):
    """Toggle a Vertex AI agent enabled/disabled."""
    from app.vertex_agents.registry import load_agents, save_agents
    agents = load_agents()
    for a in agents:
        if a["name"].lower() == name.lower():
            a["enabled"] = not a.get("enabled", True)
            save_agents(agents)
            return {"status": "toggled", "enabled": a["enabled"]}
    raise HTTPException(404, f"Agent '{name}' not found")


@router.post("/agents/test/{name}")
async def test_agent(name: str):
    """Test connectivity to a Vertex AI agent."""
    from app.vertex_agents.registry import find_agent_by_name
    from app.vertex_agents.client import test_agent as _test
    agent = find_agent_by_name(name)
    if not agent:
        raise HTTPException(404, f"Agent '{name}' not found")
    return _test(agent)
