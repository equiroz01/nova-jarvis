import time
import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from app.config import settings
from app.security import is_trusted_request

logger = logging.getLogger(__name__)
router = APIRouter()

_start_time = time.time()


def _probe(name: str, fn):
    """Run a health probe, returning its value or an {"error": ...} marker."""
    try:
        return fn()
    except Exception as e:
        logger.warning("Health probe failed: %s", name, exc_info=True)
        return {"error": str(e)}


@router.get("/health")
async def health(request: Request):
    """Per-subsystem health. Returns 200 only when the CRITICAL deps are green
    (LLM configured + agent built + task DB writable), 503 otherwise, so a single
    `curl /health` tells you what actually died instead of log archaeology."""
    uptime_s = int(time.time() - _start_time)
    hours, remainder = divmod(uptime_s, 3600)
    minutes, seconds = divmod(remainder, 60)

    # Bare liveness for untrusted (public/tunnel-without-key) callers — don't leak
    # subsystem topology to the internet. Full detail only for trusted requests.
    if not is_trusted_request(request):
        return JSONResponse(status_code=200, content={
            "status": "ok",
            "service": "nova-backend",
            "uptime": f"{hours}h {minutes}m {seconds}s",
        })

    checks: dict = {}

    # ── Critical: LLM configured + agent executor built ──
    def _llm():
        from app.agent import orchestrator
        return {
            "configured": bool(settings.gemini_api_key),
            "executor_built": orchestrator._executor is not None,
        }
    checks["llm"] = _probe("llm", _llm)
    llm_ok = isinstance(checks["llm"], dict) and checks["llm"].get("configured") \
        and checks["llm"].get("executor_built")

    # ── Critical: task DB writable ──
    db_ok = False
    try:
        from app.tasks import store
        db_ok = await store.healthcheck()
        checks["task_db"] = "ok" if db_ok else "down"
    except Exception as e:
        logger.warning("Health probe failed: task_db", exc_info=True)
        checks["task_db"] = {"error": str(e)}

    # ── Critical: task runner alive ──
    runner = getattr(request.app.state, "task_runner", None)
    runner_ok = bool(runner and getattr(runner, "_running", False))
    checks["task_runner"] = {
        "running": runner_ok,
        "active": len(getattr(runner, "_running_tasks", {})) if runner else 0,
    }

    # ── Degradable subsystems (reported, do not fail the check) ──
    checks["tools"] = _probe("tools", lambda: __import__(
        "app.agent.orchestrator", fromlist=["ALL_TOOLS"]).ALL_TOOLS.__len__())

    def _whisper():
        from app.services.stt import is_loaded
        return is_loaded()
    checks["whisper_loaded"] = _probe("whisper", _whisper)

    def _mcp():
        from app.mcp_manager import get_mcp_status
        mcp = get_mcp_status()
        return {"servers": len(mcp), "connected": sum(1 for s in mcp if s.get("connected"))}
    checks["mcp"] = _probe("mcp", _mcp)

    def _vertex():
        from app.vertex_agents.client import get_cache_stats
        return get_cache_stats()
    checks["vertex"] = _probe("vertex", _vertex)

    checks["voice_id"] = _probe("voice_id", lambda: __import__(
        "app.services.voice_id", fromlist=["is_enrolled"]).is_enrolled())

    def _brain():
        from app.knowledge.brain import get_stats
        return get_stats().get("total_notes", 0)
    checks["brain_notes"] = _probe("brain", _brain)

    critical_ok = bool(llm_ok and db_ok and runner_ok)
    body = {
        "status": "ok" if critical_ok else "degraded",
        "service": "nova-backend",
        "version": settings.nova_version,
        "uptime": f"{hours}h {minutes}m {seconds}s",
        "critical_ok": critical_ok,
        "checks": checks,
    }
    return JSONResponse(status_code=200 if critical_ok else 503, content=body)
