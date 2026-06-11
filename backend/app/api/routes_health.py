import time
import logging
from fastapi import APIRouter
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

_start_time = time.time()


@router.get("/health")
async def health():
    uptime_s = int(time.time() - _start_time)
    hours, remainder = divmod(uptime_s, 3600)
    minutes, seconds = divmod(remainder, 60)

    info = {
        "status": "ok",
        "service": "nova-backend",
        "version": settings.nova_version,
        "uptime": f"{hours}h {minutes}m {seconds}s",
    }

    # Tools count
    try:
        from app.agent.orchestrator import ALL_TOOLS
        info["tools"] = len(ALL_TOOLS)
    except Exception:
        info["tools"] = 0

    # MCP status
    try:
        from app.mcp_manager import get_mcp_status
        mcp = get_mcp_status()
        info["mcp_servers"] = len(mcp)
        info["mcp_connected"] = sum(1 for s in mcp if s.get("connected"))
    except Exception:
        logger.warning("Health probe: MCP status failed", exc_info=True)

    # Voice ID
    try:
        from app.services.voice_id import is_enrolled
        info["voice_id"] = is_enrolled()
    except Exception:
        info["voice_id"] = False

    # Brain stats
    try:
        from app.knowledge.brain import get_stats
        stats = get_stats()
        info["brain_notes"] = stats.get("total_notes", 0)
    except Exception:
        logger.warning("Health probe: brain stats failed", exc_info=True)

    return info
