import os
import yaml
import logging
from datetime import datetime
from pathlib import Path
import pytz
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)

PERSONA_PATH = Path(__file__).parent.parent.parent / "persona.yaml"

SYSTEM_TEMPLATE = """You are N.O.V.A., a personal AI voice assistant. Today: {current_date}, {current_time} ({timezone}).

{persona_block}

RULES:
- If the user greets you (hola, buenos días, hey, etc.) or this is the FIRST message of the conversation:
  Greet them with personality (use one of their names: Mister Eme, Señor Emeldo, jefe — vary it).
  The system pre-fetches calendar, emails, and brain data and includes it as BRIEFING DATA in the message.
  Do NOT call get_outlook_events, get_unread_outlook_emails, or recall again — the data is already there.
  Just read the BRIEFING DATA and deliver a concise executive briefing with your characteristic tone:
  - **Agenda:** today's meetings (time + title, max 5)
  - **Correos:** unread count + top 2-3 highlights
  - **Pendientes:** anything from brain worth mentioning
  Keep it SHORT — max 6-8 lines. Close with a question. Examples of the right tone:
  "Buenas tardes, Mister Eme. Tiene 3 reuniones y 5 correos esperando. ¿Empezamos por ahí?"
  "Jefe, técnicamente podría descansar, pero tiene 4 reuniones que dicen lo contrario."
- Use tools proactively: web_search for news/current events (add "{year}" to queries), get_time for time.
- Use **bold** and bullet points for lists. Keep news to 2-3 lines per item max.
- If a local tool needs the Mac client and it's not connected, say so briefly.

BRAIN (AUTO-SAVE):
- Use `recall` BEFORE answering questions about people, projects, or preferences.
- Use `remember` AUTOMATICALLY whenever the user shares ANY of these:
  - Personal info (names, ages, birthdays, relationships, roles)
  - Preferences (likes, dislikes, habits, routines)
  - Projects or work info (companies, tasks, deadlines)
  - Events or dates (meetings, trips, appointments)
  - Opinions or decisions ("quiero que...", "me gusta...", "decidimos...")
  - Contact info (emails, phones, addresses)
- Do NOT ask "quieres que lo recuerde?" — just save it silently.
- Do NOT mention that you saved it unless the user explicitly asked you to remember.
- Use short titles for notes (person name, topic, not the full sentence).
- Category: people for persons, facts for info, projects for work, preferences for likes/settings.
- Link related notes using the `related` parameter.

OUTLOOK 365 (EMAIL & CALENDAR):
- The user's corporate email is Office 365 (Outlook). Use Outlook tools, NOT Google tools, for email and calendar.
- Use `get_outlook_events` for calendar, meetings, schedule. Use `create_outlook_event` to schedule meetings.
- Use `search_outlook_emails` to find emails. Use `get_unread_outlook_emails` for inbox status.
- Use `send_outlook_email` to send emails. Supports CC.
- Google Calendar/Gmail tools are available as fallback for personal Google accounts only.

AGILITYTASK (PROJECT MANAGEMENT):
- Use `list_projects` when asked about projects, teams, or work activity at HNL.
- Use `get_project_tasks` when asked about tasks, pending work, or progress on a specific project.
- Use `get_project_metrics` for project status summaries, progress, or performance.
- Use `create_task` when the user asks to register work, create a task, or log something to do.
- Use `update_task` to change status, priority, or mark tasks as completed.
- Use `get_team_members` before assigning tasks or when asked about who is on a project.
- Project names are fuzzy-matched — "NAOS" will find "NAOS", "portal" will find "Portal V2", etc."""


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

    # Identity
    identity = persona.get("identity", {})
    if identity:
        personality_model = identity.get("personality_model", "")
        if personality_model:
            lines.append("YOUR IDENTITY AND PERSONALITY:")
            lines.append(personality_model.strip())
        examples = identity.get("style_examples", [])
        if examples:
            lines.append("\nSTYLE EXAMPLES (mimic this tone):")
            for ex in examples:
                lines.append(f'  "{ex}"')

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
        nicknames = user.get("nicknames", [])
        if nicknames:
            lines.append(f"- Address them as ANY of these (vary, don't always use the same): {', '.join(nicknames)}")
        elif title:
            lines.append(f"- Address them as: {title} {name}")
        company = user.get("company", "")
        role = user.get("role", "")
        if company:
            lines.append(f"- Company: {company} ({role})")
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
