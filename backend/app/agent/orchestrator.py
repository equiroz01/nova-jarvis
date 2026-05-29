import logging
import time
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import AgentExecutor, create_tool_calling_agent

from app.config import settings
from app.agent.prompts import agent_prompt
from app.agent.session import get_memory
from app.tools.cloud.time_tool import get_time
from app.tools.cloud.search_tool import web_search
from app.tools.cloud.calendar_tool import get_upcoming_events, create_calendar_event
from app.tools.cloud.gmail_tool import search_emails, send_email
from app.tools.cloud.smart_home_tool import list_smart_devices, control_device
from app.tools.local.proxy import take_screenshot, read_screen_text, run_arp_scan

logger = logging.getLogger(__name__)

CLOUD_TOOLS = [
    get_time,
    web_search,
    get_upcoming_events,
    create_calendar_event,
    search_emails,
    send_email,
    list_smart_devices,
    control_device,
]

LOCAL_TOOLS = [
    take_screenshot,
    read_screen_text,
    run_arp_scan,
]


def _get_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=settings.gemini_api_key,
        temperature=0.7,
    )


def build_agent() -> AgentExecutor:
    """Build the default agent executor with cloud tools only."""
    llm = _get_llm()
    all_tools = list(CLOUD_TOOLS) + list(LOCAL_TOOLS)

    agent = create_tool_calling_agent(llm=llm, tools=all_tools, prompt=agent_prompt)
    executor = AgentExecutor(
        agent=agent,
        tools=all_tools,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=5,
    )
    logger.info(f"Agent built with {len(all_tools)} tools: {[t.name for t in all_tools]}")
    return executor


def invoke_agent(message: str, session_id: str, executor: AgentExecutor, retries: int = 2) -> str:
    """Invoke the agent with conversation memory and retry on rate limits."""
    memory = get_memory(session_id)

    for attempt in range(retries + 1):
        try:
            response = executor.invoke(
                {"input": message, "chat_history": memory.chat_memory.messages}
            )
            output = response["output"]
            memory.chat_memory.add_user_message(message)
            memory.chat_memory.add_ai_message(output)
            return output
        except Exception as e:
            if "429" in str(e) and attempt < retries:
                wait = 5 * (attempt + 1)
                logger.warning(f"Rate limited, retrying in {wait}s (attempt {attempt + 1}/{retries})")
                time.sleep(wait)
                continue
            raise
