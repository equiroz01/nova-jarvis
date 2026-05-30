import os
import yaml
import logging
from datetime import datetime
from pathlib import Path
import pytz
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)

PERSONA_PATH = Path(__file__).parent.parent.parent / "persona.yaml"

SYSTEM_TEMPLATE = """You are Jarvis, a personal AI assistant.

CURRENT CONTEXT:
- Date: {current_date}
- Time: {current_time} ({timezone})
- Day: {day_of_week}
- Year: {year}

{persona_block}

TOOL RULES:
- When the user asks about news, current events, weather, prices, or anything that \
requires real-time data, you MUST use the web_search tool. Never say you don't have \
information without searching first.
- When searching, ALWAYS include the current date or "today" or "{year}" in your search \
query to get the most recent results.
- When the user asks about time in a city, use the get_time tool.
- Always use your tools proactively.

RESPONSE FORMAT:
- Use markdown formatting: **bold** for key terms, bullet points for lists.
- When presenting news or search results, organize them clearly with bold titles and descriptions.
- Be thorough: include details, names, numbers, and context from search results.
- Don't just list links — summarize what each result says.

If a tool requires the local Mac client and it's not connected, let the user know."""


def _load_persona() -> dict:
    """Load persona.yaml configuration."""
    if not PERSONA_PATH.exists():
        logger.warning(f"persona.yaml not found at {PERSONA_PATH}")
        return {}
    try:
        with open(PERSONA_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Error loading persona.yaml: {e}")
        return {}


def _build_persona_block(persona: dict) -> str:
    """Convert persona.yaml into prompt instructions."""
    if not persona:
        return "You are a helpful, conversational AI assistant."

    lines = []

    # User info
    user = persona.get("user", {})
    if user:
        name = user.get("name", "")
        title = user.get("title", "")
        full_name = user.get("full_name", "")
        lang = user.get("language", "es")
        location = user.get("location", "")

        lines.append("YOUR USER:")
        lines.append(f"- Name: {full_name or name}")
        if title:
            lines.append(f"- Always address them as: {title} {name}")
        if location:
            lines.append(f"- Location: {location}")
        if lang == "es":
            lines.append("- Primary language: Spanish. Always respond in Spanish unless they speak English.")
        else:
            lines.append("- Primary language: English. Always respond in English unless they speak Spanish.")

    # Contacts
    contacts = persona.get("contacts", [])
    if contacts:
        lines.append("\nPEOPLE THE USER KNOWS:")
        for c in contacts:
            rel = c.get("relation", "")
            title = c.get("title", "")
            name = c.get("name", "")
            lines.append(f"- {name} ({rel}) — address as {title} {name}")

    # Personality
    personality = persona.get("personality", {})
    traits = personality.get("traits", [])
    avoid = personality.get("avoid", [])
    if traits:
        lines.append("\nYOUR PERSONALITY:")
        for t in traits:
            lines.append(f"- {t}")
    if avoid:
        lines.append("\nNEVER DO:")
        for a in avoid:
            lines.append(f"- {a}")

    # Interests
    interests = persona.get("interests", [])
    if interests:
        lines.append(f"\nUSER'S INTERESTS (prioritize these topics):")
        for i in interests:
            lines.append(f"- {i}")

    # Special instructions
    instructions = persona.get("instructions", [])
    if instructions:
        lines.append("\nSPECIAL INSTRUCTIONS:")
        for inst in instructions:
            lines.append(f"- {inst}")

    return "\n".join(lines)


def build_prompt() -> ChatPromptTemplate:
    """Build prompt with current date/time and persona injected."""
    persona = _load_persona()

    tz_name = persona.get("user", {}).get("timezone", "America/Panama")
    now = datetime.now(pytz.timezone(tz_name))

    persona_block = _build_persona_block(persona)

    prompt_text = SYSTEM_TEMPLATE.format(
        current_date=now.strftime("%B %d, %Y"),
        current_time=now.strftime("%I:%M %p"),
        day_of_week=now.strftime("%A"),
        year=now.strftime("%Y"),
        timezone=tz_name,
        persona_block=persona_block,
    )

    return ChatPromptTemplate.from_messages(
        [
            ("system", prompt_text),
            ("placeholder", "{chat_history}"),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ]
    )
