"""AgilityTask API tools for N.O.V.A. — project and task management for Hypernova Labs."""

import json
import logging
import urllib.request
import urllib.error
from pathlib import Path
from langchain.tools import tool

logger = logging.getLogger(__name__)

_BASE_URL = "https://agilitytask.hnlapps.com"
_API_KEY = None


def _load_credentials() -> tuple[str, str]:
    """Load API key and base URL. Priority: cache → Keychain → credentials file."""
    global _API_KEY
    if _API_KEY:
        return _API_KEY, _BASE_URL

    # Try Keychain first
    try:
        from app.services.keychain import keychain
        kc_key = keychain.get("agilitytask_api_key")
        if kc_key:
            _API_KEY = kc_key
            return _API_KEY, _BASE_URL
    except Exception:
        pass

    # Fallback to credentials file
    creds_paths = [
        Path(__file__).parent.parent.parent.parent / ".agilitytask" / "credentials.json",
        Path.home() / ".agilitytask" / "credentials.json",
    ]
    for p in creds_paths:
        if p.exists():
            creds = json.loads(p.read_text())
            _API_KEY = creds.get("apiKey", "")
            base = creds.get("baseUrl", _BASE_URL)
            return _API_KEY, base

    raise RuntimeError("AgilityTask credentials not found. Use Keychain or .agilitytask/credentials.json")


def _api(method: str, path: str, data: dict | None = None) -> dict | list | str:
    """Make an authenticated API call to AgilityTask."""
    api_key, base_url = _load_credentials()
    url = f"{base_url}/api/v1/{path}"

    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Skill-Source": "nova-agent",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {"status": "ok"}
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        return {"error": True, "status": e.code, "message": body[:500]}
    except Exception as e:
        return {"error": True, "message": str(e)}


def _fmt_tasks(tasks: list, limit: int = 10) -> str:
    lines = []
    for t in tasks[:limit]:
        assignees = ", ".join(a.get("name", "?") for a in t.get("assignees", []))
        assignee_str = f" → {assignees}" if assignees else ""
        lines.append(
            f"- **{t.get('title', '?')}** — {t.get('status', '?')} | {t.get('priority', '?')}{assignee_str} (id: {t['id'][:8]}…)"
        )
    total = len(tasks)
    if total > limit:
        lines.append(f"_(+{total - limit} más)_")
    return "\n".join(lines) if lines else "No hay tareas."


@tool
def list_projects() -> str:
    """List all projects in AgilityTask. Use this when the user asks about projects, work status, or team activity."""
    try:
        result = _api("GET", "projects?limit=50")
        if isinstance(result, dict) and result.get("error"):
            return f"Error: {result.get('message', 'unknown')}"

        projects = result.get("data", []) if isinstance(result, dict) else result
        if not projects:
            return "No hay proyectos en AgilityTask."

        lines = []
        for p in projects:
            tasks = p.get("taskCount", 0)
            members = p.get("memberCount", 0)
            lines.append(f"- **{p['name']}** — {tasks} tareas, {members} miembros (id: {p['id'][:8]}…)")

        meta = result.get("meta", {}) if isinstance(result, dict) else {}
        total = meta.get("total", len(projects))
        return f"**{total} proyectos en AgilityTask:**\n\n" + "\n".join(lines)
    except Exception as e:
        logger.error(f"AgilityTask list_projects error: {e}", exc_info=True)
        return f"Error listing projects: {e}"


@tool
def get_project_tasks(project_name: str, status: str = "") -> str:
    """Get tasks for a project by name. Optionally filter by status: TODO, IN_PROGRESS, IN_REVIEW, COMPLETED, DISCARDED.
    Use this when the user asks about tasks, pending work, or project progress."""
    try:
        # Find project by name
        result = _api("GET", "projects?limit=50")
        projects = result.get("data", []) if isinstance(result, dict) else []
        match = None
        for p in projects:
            if project_name.lower() in p["name"].lower():
                match = p
                break

        if not match:
            names = ", ".join(p["name"] for p in projects[:10])
            return f"No encontré proyecto '{project_name}'. Disponibles: {names}"

        # Get tasks
        query = f"tasks?projectId={match['id']}&limit=20"
        if status:
            query += f"&status={status.upper()}"
        result = _api("GET", query)

        if isinstance(result, dict) and result.get("error"):
            return f"Error: {result.get('message', 'unknown')}"

        tasks = result.get("data", []) if isinstance(result, dict) else result
        header = f"**Tareas de {match['name']}**"
        if status:
            header += f" (status: {status.upper()})"
        header += f":\n\n"

        return header + _fmt_tasks(tasks, limit=15)
    except Exception as e:
        logger.error(f"AgilityTask get_project_tasks error: {e}", exc_info=True)
        return f"Error: {e}"


@tool
def get_project_metrics(project_name: str) -> str:
    """Get metrics and progress for a project. Use this when the user asks about project status, progress, or performance."""
    try:
        result = _api("GET", "projects?limit=50")
        projects = result.get("data", []) if isinstance(result, dict) else []
        match = None
        for p in projects:
            if project_name.lower() in p["name"].lower():
                match = p
                break

        if not match:
            return f"No encontré proyecto '{project_name}'."

        metrics = _api("GET", f"projects/{match['id']}/metrics")
        if isinstance(metrics, dict) and metrics.get("error"):
            return f"Error: {metrics.get('message', 'unknown')}"

        return f"**Métricas de {match['name']}:**\n```json\n{json.dumps(metrics, indent=2, ensure_ascii=False)[:1500]}\n```"
    except Exception as e:
        logger.error(f"AgilityTask metrics error: {e}", exc_info=True)
        return f"Error: {e}"


@tool
def create_task(project_name: str, title: str, description: str = "", priority: str = "MEDIUM") -> str:
    """Create a new task in a project. Priority: HIGH, MEDIUM, LOW. Use when user asks to create a task or register work."""
    try:
        result = _api("GET", "projects?limit=50")
        projects = result.get("data", []) if isinstance(result, dict) else []
        match = None
        for p in projects:
            if project_name.lower() in p["name"].lower():
                match = p
                break

        if not match:
            return f"No encontré proyecto '{project_name}'."

        task_data = {
            "projectId": match["id"],
            "title": title,
            "description": description,
            "priority": priority.upper(),
            "status": "TODO",
            "assigneeIds": [],
        }
        result = _api("PUT", "tasks", task_data)

        if isinstance(result, dict) and result.get("error"):
            return f"Error creando tarea: {result.get('message', 'unknown')}"

        task = result.get("data", result) if isinstance(result, dict) else result
        task_id = task.get("id", "?")
        return f"Tarea creada en **{match['name']}**: **{title}** (id: {task_id[:8]}…, priority: {priority.upper()})"
    except Exception as e:
        logger.error(f"AgilityTask create_task error: {e}", exc_info=True)
        return f"Error: {e}"


@tool
def update_task(task_id: str, status: str = "", priority: str = "", feedback: str = "", hours_spent: float = 0) -> str:
    """Update a task's status, priority, feedback, or hours. Status: TODO, IN_PROGRESS, IN_REVIEW, COMPLETED, DISCARDED.
    Use when the user asks to update, complete, or change a task."""
    try:
        patch = {}
        if status:
            patch["status"] = status.upper()
        if priority:
            patch["priority"] = priority.upper()
        if feedback:
            patch["feedback"] = feedback
        if hours_spent > 0:
            patch["hoursSpent"] = hours_spent

        if not patch:
            return "No hay cambios para aplicar."

        result = _api("PATCH", f"tasks/{task_id}", patch)
        if isinstance(result, dict) and result.get("error"):
            return f"Error: {result.get('message', 'unknown')}"

        changes = ", ".join(f"{k}: {v}" for k, v in patch.items())
        return f"Tarea actualizada ({task_id[:8]}…): {changes}"
    except Exception as e:
        logger.error(f"AgilityTask update_task error: {e}", exc_info=True)
        return f"Error: {e}"


@tool
def get_team_members(project_name: str) -> str:
    """Get team members of a project. Use when the user asks about who is on a project or to assign tasks."""
    try:
        result = _api("GET", "projects?limit=50")
        projects = result.get("data", []) if isinstance(result, dict) else []
        match = None
        for p in projects:
            if project_name.lower() in p["name"].lower():
                match = p
                break

        if not match:
            return f"No encontré proyecto '{project_name}'."

        members = _api("GET", f"members?projectId={match['id']}")
        if isinstance(members, dict) and members.get("error"):
            return f"Error: {members.get('message', 'unknown')}"

        data = members.get("data", members) if isinstance(members, dict) else members
        if not data:
            return f"No hay miembros en {match['name']}."

        lines = []
        for m in data:
            name = m.get("name", m.get("user", {}).get("name", "?"))
            email = m.get("email", m.get("user", {}).get("email", ""))
            role = m.get("role", "")
            lines.append(f"- **{name}** — {email} {f'({role})' if role else ''}")

        return f"**Equipo de {match['name']}:**\n\n" + "\n".join(lines)
    except Exception as e:
        logger.error(f"AgilityTask members error: {e}", exc_info=True)
        return f"Error: {e}"
