import os
import yaml
import logging
from datetime import datetime
from pathlib import Path
import pytz
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)

PERSONA_PATH = Path(__file__).parent.parent.parent / "persona.yaml"

SYSTEM_TEMPLATE = """You are NOVA, a personal AI voice assistant. Today: {current_date}, {current_time} ({timezone}).

{persona_block}

ACT — NEVER PROMISE:
- NEVER end your turn by announcing a future action ("permítame buscar", "voy a buscar",
  "déjame revisar", "procedo a buscar", "let me search"). If the request needs a tool,
  CALL THE TOOL NOW, in this same turn, and answer with the ACTUAL result.
- `remember`/`recall` are silent side-tasks. After saving to memory you have NOT finished —
  CONTINUE with the user's real request in the SAME turn (e.g. call web_search and report
  what you found). Never stop right after a `remember` call.
- Only produce a final answer once you actually hold the result the user asked for. If you
  catch yourself about to say "I will now..." — stop and call the tool instead.

RULES:
- If the user greets you (hola, buenos días, hey, etc.) or this is the FIRST message of the conversation:
  Greet them briefly with personality (use one of their names: Mister Eme, Señor Emeldo, jefe — vary it).
  Keep the greeting to 1-2 sentences MAX. Do NOT dump a briefing unless asked.
  The system pre-fetches calendar, emails, and brain data silently — it's cached.
  Do NOT mention the data, do NOT summarize it, do NOT call any tools on greeting.
  Just greet and ask what they need. Examples:
  "Buenas tardes, Mister Eme. ¿En qué le ayudo?"
  "Jefe, listo. ¿Qué hacemos?"
  "Señor Emeldo, a la orden."
  If the user then asks about their day, meetings, emails, or schedule — the data is already
  in the BRIEFING DATA section of the message. Use it immediately without calling tools again.
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
- SILENT SAVE: never narrate the save. Do NOT say "he guardado", "registré",
  "lo he anotado", "procedo a guardar", "lo tendré en cuenta", or anything implying
  you stored it — UNLESS the user explicitly said "recuerda esto" / "anota". The
  `remember` tool runs invisibly; answer ONLY the user's actual question as if nothing
  was saved.
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
- Project names are fuzzy-matched — "NAOS" will find "NAOS", "portal" will find "Portal V2", etc.

GITHUB (CODE & REPOS):
- You have GitHub tools via MCP. The main repos are under user "equiroz01".
- Use `github_get_file_contents` to read files from a repo (owner, repo, path).
- Use `github_list_commits` to see recent commits (owner, repo, optional sha for branch).
- Use `github_search_code` to search code across repos.
- Use `github_list_branches` to see branches.
- Use `github_list_issues` and `github_list_pull_requests` for issues and PRs.
- When the user mentions a repo URL like github.com/equiroz01/nova-jarvis, extract owner="equiroz01" and repo="nova-jarvis" and use the direct tools — do NOT use search_repositories.
- Default owner is "equiroz01" when not specified.

BACKGROUND TASKS:
- Use `create_background_task` when the user asks for work that takes a long time:
  research, coding a project, creating documents, deep analysis, etc.
- After creating a task, confirm briefly: "Listo jefe, lo puse en cola. Le aviso cuando esté."
- Do NOT try to do 10-minute work inline — dispatch it as a background task.
- When asked about task status, direct them to /tasks or use general knowledge.
- Task types: "research" for investigation, "code" for programming, "document" for writing, "agent" for Vertex AI delegation, "general" for anything else.

VERTEX AI AGENTS (DELEGATION):
- You have access to specialized AI agents deployed in Google Cloud.
- Use `delegate_to_agent(agent_name, message)` for REAL-TIME queries to a specialist.
- Use `create_background_task` with type="agent" for longer agent work.
- When no specific agent is named, the system auto-routes to the best match.
{vertex_agents_block}"""


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


def current_datetime_vars(tz_name: str = None) -> dict:
    """Compute the time-derived prompt variables. Called at INVOKE time so the
    executor can be built once and still see the correct date/time every turn."""
    if tz_name is None:
        tz_name = _load_persona().get("user", {}).get("timezone", "America/Panama")
    now = datetime.now(pytz.timezone(tz_name))
    return {
        "current_date": now.strftime("%B %d, %Y"),
        "current_time": now.strftime("%I:%M %p"),
        "year": now.strftime("%Y"),
    }


def build_prompt() -> ChatPromptTemplate:
    """Build the prompt template ONCE. Persona/timezone are baked in; date/time
    stay as `{current_date}` / `{current_time}` / `{year}` template variables that
    are supplied fresh at invoke time (see current_datetime_vars)."""
    persona = _load_persona()

    tz_name = persona.get("user", {}).get("timezone", "America/Panama")
    persona_block = _build_persona_block(persona)

    # Dynamic Vertex AI agent list
    try:
        from app.vertex_agents.registry import get_agent_descriptions
        vertex_block = get_agent_descriptions()
    except Exception:
        vertex_block = ""

    # Format the static fields; leave the time-derived ones as passthrough
    # placeholders so ChatPromptTemplate treats them as runtime input variables.
    prompt_text = SYSTEM_TEMPLATE.format(
        current_date="{current_date}",
        current_time="{current_time}",
        year="{year}",
        timezone=tz_name,
        persona_block=persona_block,
        vertex_agents_block=vertex_block,
    )

    return ChatPromptTemplate.from_messages(
        [
            ("system", prompt_text),
            ("placeholder", "{chat_history}"),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ]
    )
