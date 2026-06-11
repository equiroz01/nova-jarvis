import logging
import os
import uuid
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app.config import settings
from app.security import is_trusted_request
from app.context import request_id_var
from app.logging_config import setup_logging
from app.ratelimit import RateLimiter
from app.api.routes_health import router as health_router
from app.api.routes_chat import router as chat_router
from app.api.routes_voice import router as voice_router
from app.api.routes_alexa import router as alexa_router
from app.api.routes_stream import router as stream_router
from app.api.websocket_bridge import router as ws_router
from app.api.routes_settings import router as settings_router
from app.api.routes_tasks import router as tasks_router


setup_logging(settings.log_level)
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

# ── API key middleware ──
# Trust logic lives in app.security (single source of truth, shared with /health).
# Reachable without the API key. /alexa is public at the edge (Amazon controls the
# request and cannot send our Bearer token) but is gated by skill-ID inside the route.
_PUBLIC_PATHS = {"/health", "/alexa"}


@app.middleware("http")
async def api_key_guard(request: Request, call_next):
    """Require NOVA_API_KEY for any tunnelled (internet) request; trust real LAN."""
    if not settings.nova_api_key:
        return await call_next(request)  # No key configured = open access

    path = request.url.path
    if path in _PUBLIC_PATHS or path.startswith("/static"):
        return await call_next(request)

    if is_trusted_request(request):
        return await call_next(request)

    return JSONResponse(status_code=401, content={"detail": "API key required"})

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Per-client token bucket on the expensive paths, so a runaway retry loop or a
# stuck Alexa can't burn the Gemini quota / both task workers and take NOVA down.
_RL_PER_MIN = int(os.environ.get("NOVA_RATE_LIMIT_PER_MIN", "30"))
_rate_limiter = RateLimiter(capacity=_RL_PER_MIN, refill_per_sec=_RL_PER_MIN / 60.0)
_RATE_LIMITED_PATHS = ("/chat", "/voice")


def _client_key(request: Request) -> str:
    # Real external IP when tunnelled, else the socket peer (loopback for local).
    return request.headers.get("cf-connecting-ip") or (
        request.client.host if request.client else "unknown"
    )


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path.startswith(_RATE_LIMITED_PATHS):
        if not _rate_limiter.allow(_client_key(request)):
            logger.warning("Rate limit hit for %s on %s", _client_key(request), request.url.path)
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit ({_RL_PER_MIN}/min). Slow down and retry."},
            )
    return await call_next(request)


# Added last = outermost: stamps the request_id before anything else logs, so every
# line for one request (auth, handler, tool calls) shares `req=<id>`.
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    req_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:8]
    token = request_id_var.set(req_id)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response
    finally:
        request_id_var.reset(token)


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
