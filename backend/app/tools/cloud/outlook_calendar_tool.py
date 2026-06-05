"""Outlook Calendar tools for NOVA — Microsoft 365 calendar via Graph API."""

import logging
from datetime import datetime, timedelta
from langchain.tools import tool
import pytz

logger = logging.getLogger(__name__)

TIMEZONE = "America/Panama"  # UTC-5, same as America/Bogota


@tool
def get_outlook_events(days: int = 1) -> str:
    """Get upcoming Outlook calendar events for the next N days. Default is today's events.
    Use this when the user asks about their calendar, meetings, schedule, or appointments."""
    try:
        from app.services.microsoft_auth import graph_request

        tz = pytz.timezone(TIMEZONE)
        now = datetime.now(tz)
        start = now.isoformat()
        end = (now + timedelta(days=max(1, days))).isoformat()

        result = graph_request(
            "GET",
            f"me/calendarview?startDateTime={start}&endDateTime={end}"
            f"&$orderby=start/dateTime&$top=15"
            f"&$select=subject,start,end,location,organizer,isAllDay,webLink",
            headers={"Prefer": f'outlook.timezone="{TIMEZONE}"'},
        )

        events = result.get("value", [])
        if not events:
            return f"No hay eventos en los próximos {days} día(s)."

        lines = []
        for e in events:
            subj = e.get("subject", "Sin título")
            start_dt = e.get("start", {}).get("dateTime", "")[:16].replace("T", " ")
            end_dt = e.get("end", {}).get("dateTime", "")[:16].replace("T", " ")
            location = e.get("location", {}).get("displayName", "")
            organizer = e.get("organizer", {}).get("emailAddress", {}).get("name", "")
            all_day = e.get("isAllDay", False)

            time_str = "Todo el día" if all_day else f"{start_dt} → {end_dt}"
            loc_str = f" | {location}" if location else ""
            org_str = f" | Org: {organizer}" if organizer else ""

            lines.append(f"- **{subj}** — {time_str}{loc_str}{org_str}")

        return f"**Eventos próximos ({days} día(s)):**\n\n" + "\n".join(lines)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        logger.error(f"Outlook Calendar error: {e}", exc_info=True)
        return f"Error accessing Outlook Calendar: {e}"


@tool
def create_outlook_event(title: str, start_time: str, end_time: str, description: str = "", attendees: str = "") -> str:
    """Create a new Outlook calendar event. Times in ISO 8601 (e.g., 2026-06-05T14:00:00).
    Attendees: comma-separated emails (optional).
    Use when the user asks to schedule a meeting, create an event, or block time."""
    try:
        from app.services.microsoft_auth import graph_request

        event = {
            "subject": title,
            "body": {"contentType": "Text", "content": description},
            "start": {"dateTime": start_time, "timeZone": "America/Panama"},
            "end": {"dateTime": end_time, "timeZone": "America/Panama"},
        }

        if attendees:
            event["attendees"] = [
                {
                    "emailAddress": {"address": email.strip()},
                    "type": "required",
                }
                for email in attendees.split(",")
                if email.strip()
            ]

        result = graph_request("POST", "me/events", event)
        link = result.get("webLink", "")
        return f"Evento creado: **{title}** ({start_time} → {end_time})" + (f"\nLink: {link}" if link else "")
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        logger.error(f"Outlook Calendar create error: {e}", exc_info=True)
        return f"Error creating Outlook event: {e}"
