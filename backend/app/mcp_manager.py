"""
NOVA MCP Manager — Connects to MCP servers and exposes their tools to the agent.
Supports: stdio, sse, http (streamable HTTP)
"""

import asyncio
import json
import logging
import yaml
from pathlib import Path
from typing import Optional
from langchain.tools import StructuredTool
from pydantic import BaseModel, Field, create_model

logger = logging.getLogger(__name__)

MCP_CONFIG_PATH = Path(__file__).parent.parent / "mcp_config.yaml"


def _load_config() -> list[dict]:
    if not MCP_CONFIG_PATH.exists():
        return []
    try:
        with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("servers") or []
    except Exception as e:
        logger.error(f"MCP config error: {e}")
        return []


class MCPConnection:
    """Manages a single MCP server connection."""

    def __init__(self, config: dict):
        self.name = config["name"]
        self.type = config.get("type", "stdio")
        self.config = config
        self.session = None
        self.client = None
        self.tools_cache = []

    async def connect(self):
        """Connect to the MCP server and discover tools."""
        try:
            if self.type == "stdio":
                await self._connect_stdio()
            elif self.type == "sse":
                await self._connect_sse()
            elif self.type == "http":
                await self._connect_http()
            else:
                logger.warning(f"MCP [{self.name}]: Unknown type '{self.type}'")
                return

            # List available tools
            if self.session:
                result = await self.session.list_tools()
                self.tools_cache = result.tools
                logger.info(f"MCP [{self.name}]: {len(self.tools_cache)} tools discovered")
                for t in self.tools_cache:
                    logger.info(f"  - {t.name}: {t.description[:60] if t.description else 'no description'}")

        except Exception as e:
            logger.error(f"MCP [{self.name}]: Connection failed — {e}")

    async def _connect_stdio(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        cmd = self.config.get("command", "")
        args = self.config.get("args", [])
        env = self.config.get("env", {})

        if not cmd:
            logger.warning(f"MCP [{self.name}]: No command specified")
            return

        params = StdioServerParameters(command=cmd, args=args, env=env if env else None)
        self._transport = stdio_client(params)
        read, write = await self._transport.__aenter__()
        self.session = ClientSession(read, write)
        await self.session.__aenter__()
        await self.session.initialize()
        logger.info(f"MCP [{self.name}]: Connected via stdio ({cmd})")

    async def _connect_sse(self):
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        url = self.config.get("url", "")
        if not url:
            logger.warning(f"MCP [{self.name}]: No URL specified for SSE")
            return

        headers = self.config.get("headers", {})
        self._transport = sse_client(url, headers=headers)
        read, write = await self._transport.__aenter__()
        self.session = ClientSession(read, write)
        await self.session.__aenter__()
        await self.session.initialize()
        logger.info(f"MCP [{self.name}]: Connected via SSE ({url})")

    async def _connect_http(self):
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        url = self.config.get("url", "")
        if not url:
            logger.warning(f"MCP [{self.name}]: No URL specified for HTTP")
            return

        headers = self.config.get("headers", {})
        self._transport = streamablehttp_client(url, headers=headers)
        read, write, _ = await self._transport.__aenter__()
        self.session = ClientSession(read, write)
        await self.session.__aenter__()
        await self.session.initialize()
        logger.info(f"MCP [{self.name}]: Connected via HTTP ({url})")

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Call a tool on this MCP server."""
        if not self.session:
            return f"MCP [{self.name}] not connected"
        try:
            result = await self.session.call_tool(tool_name, arguments=arguments)
            # Extract text from result content
            texts = []
            for content in result.content:
                if hasattr(content, 'text'):
                    texts.append(content.text)
            return "\n".join(texts) if texts else str(result)
        except Exception as e:
            return f"MCP tool error [{self.name}/{tool_name}]: {e}"

    async def disconnect(self):
        try:
            if self.session:
                await self.session.__aexit__(None, None, None)
            if hasattr(self, '_transport'):
                await self._transport.__aexit__(None, None, None)
        except Exception:
            pass


def _make_langchain_tool(connection: MCPConnection, mcp_tool) -> StructuredTool:
    """Convert an MCP tool into a LangChain StructuredTool."""
    tool_name = f"{connection.name.lower().replace(' ', '_')}_{mcp_tool.name}"
    description = mcp_tool.description or f"Tool from {connection.name}"

    # Build input schema from MCP tool's inputSchema
    schema = mcp_tool.inputSchema or {}
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    # Create dynamic Pydantic model for the tool args
    fields = {}
    for prop_name, prop_info in properties.items():
        prop_type = str  # default to string
        default = ... if prop_name in required else ""
        desc = prop_info.get("description", "")
        fields[prop_name] = (prop_type, Field(default=default, description=desc))

    if fields:
        InputModel = create_model(f"{tool_name}_input", **fields)
    else:
        InputModel = create_model(f"{tool_name}_input", query=(str, Field(default="", description="Input")))

    def _call_sync(**kwargs):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, connection.call_tool(mcp_tool.name, kwargs))
                    return future.result(timeout=30)
            else:
                return loop.run_until_complete(connection.call_tool(mcp_tool.name, kwargs))
        except RuntimeError:
            return asyncio.run(connection.call_tool(mcp_tool.name, kwargs))

    return StructuredTool(
        name=tool_name,
        description=f"[{connection.name}] {description}",
        func=_call_sync,
        args_schema=InputModel,
    )


# ── Global MCP state ──
_connections: list[MCPConnection] = []
_mcp_tools: list[StructuredTool] = []


async def initialize_mcp_servers():
    """Load config, connect to enabled servers, and build tools."""
    global _connections, _mcp_tools

    # Disconnect existing
    for c in _connections:
        await c.disconnect()
    _connections = []
    _mcp_tools = []

    servers = _load_config()
    enabled = [s for s in servers if s.get("enabled", True)]

    if not enabled:
        logger.info("MCP: No enabled servers configured")
        return

    logger.info(f"MCP: Connecting to {len(enabled)} server(s)...")

    for server_config in enabled:
        conn = MCPConnection(server_config)
        await conn.connect()
        _connections.append(conn)

        # Convert MCP tools to LangChain tools
        for mcp_tool in conn.tools_cache:
            lc_tool = _make_langchain_tool(conn, mcp_tool)
            _mcp_tools.append(lc_tool)

    logger.info(f"MCP: {len(_mcp_tools)} total tools from {len(_connections)} server(s)")


def get_mcp_tools() -> list[StructuredTool]:
    """Get all LangChain tools from connected MCP servers."""
    return list(_mcp_tools)


def get_mcp_status() -> list[dict]:
    """Get status of all MCP connections."""
    return [
        {
            "name": c.name,
            "type": c.type,
            "connected": c.session is not None,
            "tools": len(c.tools_cache),
            "tool_names": [t.name for t in c.tools_cache],
        }
        for c in _connections
    ]
