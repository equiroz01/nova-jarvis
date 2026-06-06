import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import ipaddress

from app.config import settings
from app.api.routes_health import router as health_router
from app.api.routes_chat import router as chat_router
from app.api.routes_voice import router as voice_router
from app.api.routes_alexa import router as alexa_router
from app.api.routes_stream import router as stream_router
from app.api.websocket_bridge import router as ws_router
from app.api.routes_settings import router as settings_router
from app.api.routes_tasks import router as tasks_router


logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("NOVA backend starting up...")
    from app.agent.orchestrator import build_agent
    app.state.agent_executor = build_agent()
    logger.info("Agent executor ready.")
    from app.services.stt import load_model
    load_model()
    logger.info("Whisper STT ready.")
    from app.mcp_manager import initialize_mcp_servers
    await initialize_mcp_servers()
    logger.info("MCP servers initialized.")
    import asyncio
    from app.services.voice_id import load_voiceprint
    load_voiceprint()
    from app.services.filler_cache import preload_fillers
    asyncio.create_task(preload_fillers())
    logger.info("Filler phrases caching in background...")

    # Background task system
    from app.tasks import store as task_store
    from app.tasks.runner import TaskRunner
    from app.tools.cloud.task_tool import set_loop as set_task_loop
    await task_store.init_db()
    app.state.task_runner = TaskRunner(max_concurrent=2)
    await app.state.task_runner.start()
    set_task_loop(asyncio.get_event_loop(), app.state.task_runner)
    logger.info("Task runner started.")

    yield

    # Shutdown
    await app.state.task_runner.stop()
    await task_store.close_db()
    logger.info("Jarvis backend shutting down...")


app = FastAPI(title="NOVA Backend", version=settings.nova_version, lifespan=lifespan)

# ── API key middleware for external (non-LAN) requests ──
_LAN_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
]
_PUBLIC_PATHS = {"/health", "/alexa"}  # Always allowed without API key


def _is_lan(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
        return any(addr in net for net in _LAN_NETWORKS)
    except ValueError:
        return False


@app.middleware("http")
async def api_key_guard(request: Request, call_next):
    """Require NOVA_API_KEY for non-LAN requests (skip health and alexa)."""
    if not settings.nova_api_key:
        return await call_next(request)  # No key configured = open access

    path = request.url.path
    if path in _PUBLIC_PATHS or path.startswith("/static"):
        return await call_next(request)

    client_ip = request.client.host if request.client else "0.0.0.0"
    # Check X-Forwarded-For for tunnel requests
    forwarded = request.headers.get("x-forwarded-for", "")
    real_ip = forwarded.split(",")[0].strip() if forwarded else client_ip

    if _is_lan(real_ip):
        return await call_next(request)

    # External request — require API key
    auth = request.headers.get("authorization", "")
    token = auth.replace("Bearer ", "") if auth.startswith("Bearer ") else ""
    api_key_param = request.query_params.get("api_key", "")

    if token == settings.nova_api_key or api_key_param == settings.nova_api_key:
        return await call_next(request)

    return JSONResponse(status_code=401, content={"detail": "API key required"})

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(chat_router)
app.include_router(voice_router)
app.include_router(alexa_router)
app.include_router(stream_router)
app.include_router(ws_router)
app.include_router(settings_router)
app.include_router(tasks_router)

# Serve frontend
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def serve_ui():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/settings")
async def serve_settings():
    return FileResponse(STATIC_DIR / "settings.html")


@app.get("/tasks")
async def serve_tasks():
    return FileResponse(STATIC_DIR / "tasks.html")
