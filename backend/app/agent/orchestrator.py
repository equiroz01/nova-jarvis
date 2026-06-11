import logging
import time
from datetime import datetime
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import AgentExecutor, create_tool_calling_agent

from app.config import settings
from app.agent.prompts import build_prompt, current_datetime_vars
from app.context import client_id_var
from app.agent.session import get_memory, persist_turn
from app.tools.cloud.time_tool import get_time
from app.tools.cloud.search_tool import web_search
from app.tools.cloud.calendar_tool import get_upcoming_events, create_calendar_event
from app.tools.cloud.gmail_tool import search_emails, send_email
from app.tools.cloud.smart_home_tool import list_smart_devices, control_device
from app.tools.cloud.brain_tool import remember, recall, read_memory, brain_stats
from app.tools.cloud.agilitytask_tool import (
    list_projects, get_project_tasks, get_project_metrics,
    create_task, update_task, get_team_members,
)
from app.tools.cloud.outlook_calendar_tool import get_outlook_events, create_outlook_event
from app.tools.cloud.outlook_mail_tool import search_outlook_emails, send_outlook_email, get_unread_outlook_emails
from app.tools.local.proxy import take_screenshot, read_screen_text, run_arp_scan
from app.tools.cloud.task_tool import create_background_task
from app.tools.cloud.agent_delegate_tool import delegate_to_agent

logger = logging.getLogger(__name__)

CLOUD_TOOLS = [
    get_time, web_search,
    get_upcoming_events, create_calendar_event,
    search_emails, send_email,
    list_smart_devices, control_device,
    remember, recall, read_memory, brain_stats,
    list_projects, get_project_tasks, get_project_metrics,
    create_task, update_task, get_team_members,
    get_outlook_events, create_outlook_event,
    search_outlook_emails, send_outlook_email, get_unread_outlook_emails,
    create_background_task,
    delegate_to_agent,
]

LOCAL_TOOLS = [take_screenshot, read_screen_text, run_arp_scan]

from app.guardrails import wrap_tools

# Audit (and optionally gate) every side-effecting tool — single touchpoint.
ALL_TOOLS = wrap_tools(list(CLOUD_TOOLS) + list(LOCAL_TOOLS))

# ── Cached LLM and executor ──
_llm = None
_executor = None  # built once; date/time injected fresh at invoke time


def _get_llm() -> ChatGoogleGenerativeAI:
    global _llm
    if _llm is None:
        _llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=settings.gemini_api_key,
            temperature=0.7,
        )
    return _llm


def _get_executor() -> AgentExecutor:
    """Build the agent executor ONCE and reuse it. Date/time are no longer baked
    into the prompt (they are injected per-invoke), so the executor never expires —
    this avoids rebuilding the agent + re-reading every MCP tool 1,440 times/day."""
    global _executor

    if _executor is None:
        from app.mcp_manager import get_mcp_tools
        mcp_tools = get_mcp_tools()
        all_tools = ALL_TOOLS + mcp_tools

        llm = _get_llm()
        prompt = build_prompt()
        agent = create_tool_calling_agent(llm=llm, tools=all_tools, prompt=prompt)
        _executor = AgentExecutor(
            agent=agent,
            tools=all_tools,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=5,
            max_execution_time=120,
        )
        logger.info(f"Executor built: {len(ALL_TOOLS)} built-in + {len(mcp_tools)} MCP tools")

    return _executor


# ── Response cache for frequent queries ──
_cache: dict[str, tuple[str, float]] = {}
CACHE_TTL = 30  # seconds

CACHEABLE_PATTERNS = {
    "hola": True, "hi": True, "hello": True,
    "como estas": True, "how are you": True,
    "que puedes hacer": True, "what can you do": True,
    "quien eres": True, "who are you": True,
    "cuanto conocimiento": True,
}


def _check_cache(message: str) -> str | None:
    key = message.lower().strip().rstrip("?!.,")
    if key in _cache:
        cached, ts = _cache[key]
        if time.time() - ts < CACHE_TTL:
            logger.debug(f"Cache hit: {key}")
            return cached
    return None


def _set_cache(message: str, response: str):
    key = message.lower().strip().rstrip("?!.,")
    if key in CACHEABLE_PATTERNS or len(key.split()) <= 3:
        _cache[key] = (response, time.time())


def build_agent() -> str:
    """Verify LLM and tools at startup."""
    llm = _get_llm()
    _get_executor()  # pre-build
    logger.info(f"LLM ready: {llm.model}")
    logger.info(f"Agent: {len(ALL_TOOLS)} tools: {[t.name for t in ALL_TOOLS]}")
    return "ready"


_GREETING_WORDS = {"hola", "hello", "hi", "hey", "buenos", "buenas", "good", "buen"}

# Briefing cache per session — pre-fetched data available for follow-ups
_briefing_cache: dict[str, tuple[str, float]] = {}
_BRIEFING_TTL = 300  # 5 min — after that, fetch fresh

# Words that match pre-fetched data (today's calendar, unread emails)
_BRIEFING_MATCH = {"hoy", "today", "agenda", "correos", "emails", "reuniones",
                    "meetings", "pendientes", "calendario", "inbox", "sin leer",
                    "unread", "bandeja", "schedule", "día", "dia"}


def _is_greeting(message: str) -> bool:
    words = message.lower().strip().rstrip("!.?,").split()
    return len(words) <= 4 and any(w in _GREETING_WORDS for w in words)


def _prefetch_briefing() -> str:
    """Fetch calendar, unread emails, and brain in parallel for the greeting briefing."""
    import concurrent.futures

    def _calendar():
        try:
            return get_outlook_events.invoke({"days": 1})
        except Exception as e:
            return f"Calendar unavailable: {e}"

    def _emails():
        try:
            return get_unread_outlook_emails.invoke({"max_results": 5})
        except Exception as e:
            return f"Email unavailable: {e}"

    def _brain():
        try:
            return recall.invoke({"query": "pendientes proyectos seguimiento"})
        except Exception as e:
            return ""

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        f_cal = pool.submit(_calendar)
        f_mail = pool.submit(_emails)
        f_brain = pool.submit(_brain)

        try:
            cal = f_cal.result(timeout=25)
        except (TimeoutError, Exception) as e:
            logger.warning(f"Calendar prefetch failed: {e}")
            cal = "Calendario no disponible temporalmente."
        try:
            mail = f_mail.result(timeout=25)
        except (TimeoutError, Exception) as e:
            logger.warning(f"Mail prefetch failed: {e}")
            mail = "Correos no disponibles temporalmente."
        try:
            brain = f_brain.result(timeout=5)
        except (TimeoutError, Exception) as e:
            brain = ""

    parts = [
        "BRIEFING DATA (pre-fetched, use this to respond — do NOT call these tools again):",
        f"\n[CALENDAR]\n{cal}",
        f"\n[UNREAD EMAILS]\n{mail}",
    ]
    if brain and "No relevant" not in brain:
        parts.append(f"\n[BRAIN MEMORY]\n{brain}")

    return "\n".join(parts)


def get_current_client_id() -> str:
    """Get the client_id for the current request context (used by agent tools)."""
    return client_id_var.get()


def invoke_agent(message: str, session_id: str, executor=None, retries: int = 2, client_id: str = "default") -> str:
    """Invoke the agent with caching, memory, and retry."""
    # Bind client_id to the current context so tools (and the Vertex session pool)
    # read the right value — survives the executor hop the task runner makes.
    client_id_var.set(client_id)

    # Check cache first
    cached = _check_cache(message)
    if cached:
        return cached

    memory = get_memory(session_id)
    ex = _get_executor()

    # Pre-fetch briefing on greeting, reuse for follow-ups about the same data
    enriched_message = message
    msg_words = set(message.lower().strip().rstrip("?!.,").split())

    if _is_greeting(message) and not memory.chat_memory.messages:
        # First greeting — pre-fetch silently in background, cache for follow-ups
        # Do NOT inject into prompt — greeting should be short, no data dump
        import threading
        def _bg_fetch():
            t0 = time.time()
            briefing = _prefetch_briefing()
            _briefing_cache[session_id] = (briefing, time.time())
            logger.info(f"Briefing pre-fetched in background ({time.time()-t0:.1f}s)")
        threading.Thread(target=_bg_fetch, daemon=True).start()
    elif session_id in _briefing_cache and msg_words & _BRIEFING_MATCH:
        cached_data, cached_at = _briefing_cache[session_id]
        if time.time() - cached_at < _BRIEFING_TTL:
            # Follow-up about same data — reuse, don't re-call APIs
            logger.info("Reusing pre-fetched briefing for follow-up")
            enriched_message = f"{message}\n\nYou already have this data pre-fetched. Use it directly, do NOT call these tools again:\n{cached_data}"

    for attempt in range(retries + 1):
        try:
            response = ex.invoke(
                {
                    "input": enriched_message,
                    "chat_history": memory.chat_memory.messages,
                    **current_datetime_vars(),
                }
            )
            output = response["output"]
            memory.chat_memory.add_user_message(message)
            memory.chat_memory.add_ai_message(output)
            persist_turn(session_id, message, output)  # survive restarts
            _set_cache(message, output)
            return output
        except Exception as e:
            if "429" in str(e) and attempt < retries:
                wait = 5 * (attempt + 1)
                logger.warning(f"Rate limited, retrying in {wait}s ({attempt + 1}/{retries})")
                time.sleep(wait)
                continue
            raise
