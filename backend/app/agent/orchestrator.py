import logging
import time
from datetime import datetime
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import AgentExecutor, create_tool_calling_agent

from app.config import settings
from app.agent.prompts import build_prompt
from app.agent.session import get_memory
from app.tools.cloud.time_tool import get_time
from app.tools.cloud.search_tool import web_search
from app.tools.cloud.calendar_tool import get_upcoming_events, create_calendar_event
from app.tools.cloud.gmail_tool import search_emails, send_email
from app.tools.cloud.smart_home_tool import list_smart_devices, control_device
from app.tools.cloud.brain_tool import remember, recall, read_memory, brain_stats
from app.tools.local.proxy import take_screenshot, read_screen_text, run_arp_scan

logger = logging.getLogger(__name__)

CLOUD_TOOLS = [
    get_time, web_search,
    get_upcoming_events, create_calendar_event,
    search_emails, send_email,
    list_smart_devices, control_device,
    remember, recall, read_memory, brain_stats,
]

LOCAL_TOOLS = [take_screenshot, read_screen_text, run_arp_scan]

ALL_TOOLS = list(CLOUD_TOOLS) + list(LOCAL_TOOLS)

# ── Cached LLM and executor ──
_llm = None
_executor = None
_executor_minute = None  # refresh prompt every minute for fresh date/time


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
    """Get cached executor, refresh prompt only once per minute."""
    global _executor, _executor_minute
    now_minute = datetime.now().strftime("%Y%m%d%H%M")

    if _executor is None or _executor_minute != now_minute:
        llm = _get_llm()
        prompt = build_prompt()
        agent = create_tool_calling_agent(llm=llm, tools=ALL_TOOLS, prompt=prompt)
        _executor = AgentExecutor(
            agent=agent,
            tools=ALL_TOOLS,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=5,
        )
        _executor_minute = now_minute
        logger.debug("Executor refreshed")

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


def invoke_agent(message: str, session_id: str, executor=None, retries: int = 2) -> str:
    """Invoke the agent with caching, memory, and retry."""
    # Check cache first
    cached = _check_cache(message)
    if cached:
        return cached

    memory = get_memory(session_id)
    ex = _get_executor()

    for attempt in range(retries + 1):
        try:
            response = ex.invoke(
                {"input": message, "chat_history": memory.chat_memory.messages}
            )
            output = response["output"]
            memory.chat_memory.add_user_message(message)
            memory.chat_memory.add_ai_message(output)
            _set_cache(message, output)
            return output
        except Exception as e:
            if "429" in str(e) and attempt < retries:
                wait = 5 * (attempt + 1)
                logger.warning(f"Rate limited, retrying in {wait}s ({attempt + 1}/{retries})")
                time.sleep(wait)
                continue
            raise
