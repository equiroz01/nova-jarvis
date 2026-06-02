import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.api.routes_health import router as health_router
from app.api.routes_chat import router as chat_router
from app.api.routes_voice import router as voice_router
from app.api.routes_alexa import router as alexa_router
from app.api.routes_stream import router as stream_router
from app.api.websocket_bridge import router as ws_router
from app.api.routes_settings import router as settings_router


logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("N.O.V.A. backend starting up...")
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
    yield
    logger.info("Jarvis backend shutting down...")


app = FastAPI(title="Jarvis Backend", version="1.0.0", lifespan=lifespan)

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

# Serve frontend
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def serve_ui():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/settings")
async def serve_settings():
    return FileResponse(STATIC_DIR / "settings.html")
