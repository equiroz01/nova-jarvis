"""Settings API — manage MCP servers and N.O.V.A. configuration."""

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
