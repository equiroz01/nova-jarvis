"""Audit log + optional confirmation gate for side-effecting tools.

For a single trusted user this is not RBAC — it is the "what did NOVA actually do
today" record. Every tool that changes the outside world (send mail, touch the
calendar, control a device, create/mutate a task) appends one line to an audit log
before it runs, correlated by client_id / request_id. When NOVA does something
unexpected, this is the difference between "I know what happened" and log archaeology.

Wiring: orchestrator wraps ALL_TOOLS through wrap_tools() once at build time, so
there is a single touchpoint and the individual tool files stay untouched.
"""

import json
import logging
import os
import time
from functools import wraps
from pathlib import Path

from app.config import settings
from app.context import client_id_var, request_id_var

logger = logging.getLogger(__name__)

# Tools that change the outside world — every call is logged.
AUDIT_TOOLS = {
    "send_email",
    "send_outlook_email",
    "create_calendar_event",
    "control_device",
    "create_task",
    "update_task",
}

# Highest-stakes subset — gated behind a confirmation flag (default off) so a
# hallucinated call can't silently fire. Enable with NOVA_GUARDRAILS_CONFIRM=1.
CONFIRM_TOOLS = {"send_email", "send_outlook_email", "control_device"}

_MARK = "_nova_audited"


def _audit_path() -> str:
    nova_home = os.environ.get("NOVA_HOME", str(Path.home() / ".nova"))
    data_dir = Path(nova_home) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "audit.log")


def _summarize(args: tuple, kwargs: dict) -> str:
    """Compact, length-capped repr of the call args (no full email bodies)."""
    parts = [repr(a)[:80] for a in args]
    parts += [f"{k}={repr(v)[:80]}" for k, v in kwargs.items()]
    s = ", ".join(parts)
    return s[:300]


def _write(tool_name: str, args: tuple, kwargs: dict) -> None:
    """Append one audit line. Best-effort: never break the tool on a log failure."""
    line = {
        "ts": time.time(),
        "tool": tool_name,
        "client_id": client_id_var.get(),
        "request_id": request_id_var.get(),
        "args": _summarize(args, kwargs),
    }
    try:
        with open(_audit_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception:
        logger.warning("Audit log write failed for %s", tool_name, exc_info=True)
    # Also surface in the normal log stream (carries req=/client= already).
    logger.info("AUDIT tool=%s args=%s", tool_name, line["args"])


def _confirm_enabled() -> bool:
    return bool(getattr(settings, "guardrails_confirm", False)) or \
        os.environ.get("NOVA_GUARDRAILS_CONFIRM", "") in ("1", "true", "True")


def _wrap_func(tool_name: str, fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if tool_name in CONFIRM_TOOLS and _confirm_enabled():
            _write(f"{tool_name}:BLOCKED_NEEDS_CONFIRM", args, kwargs)
            return (
                f"⚠️ '{tool_name}' requires confirmation and was NOT executed. "
                f"Confirmation gating is enabled (NOVA_GUARDRAILS_CONFIRM). "
                f"Ask the user to confirm, then retry."
            )
        _write(tool_name, args, kwargs)
        return fn(*args, **kwargs)
    return wrapper


def wrap_tools(tools: list) -> list:
    """Return a new tool list where side-effecting tools are replaced by audited
    COPIES. The original global tool singletons are left untouched (so importing
    this doesn't mutate shared objects / pollute tests); only the returned list
    carries the gate. Non-side-effecting tools pass through unchanged.
    """
    out = []
    for tool in tools:
        name = getattr(tool, "name", None)
        fn = getattr(tool, "func", None)
        if name not in AUDIT_TOOLS or fn is None:
            out.append(tool)
            continue
        wrapped = _wrap_func(name, fn)
        try:
            out.append(tool.model_copy(update={"func": wrapped}))
        except Exception:
            # Fallback for non-pydantic tool objects: shallow-wrap in place once.
            if not getattr(tool, _MARK, False):
                try:
                    tool.func = wrapped
                    object.__setattr__(tool, _MARK, True)
                except Exception:
                    logger.warning("Could not wrap tool %s for audit", name, exc_info=True)
            out.append(tool)
    return out
