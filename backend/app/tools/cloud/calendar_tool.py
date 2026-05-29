import logging
from datetime import datetime, timedelta
from langchain.tools import tool
from googleapiclient.discovery import build

from app.services.google_auth import get_google_credentials

logger = logging.getLogger(__name__)


@tool
def get_upcoming_events(days: int = 1) -> str:
    """Get upcoming calendar events for the next N days. Default is today's events."""
    try:
        creds = get_google_credentials()
        service = build("calendar", "v3", credentials=creds)

        now = datetime.utcnow()
        time_min = now.isoformat() + "Z"
        time_max = (now + timedelta(days=max(1, days))).isoformat() + "Z"

        events_result = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            maxResults=10,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = events_result.get("items", [])
        if not events:
            return f"No events found for the next {days} day(s)."

        lines = []
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            summary = event.get("summary", "No title")
            lines.append(f"- {start}: {summary}")

        return f"Upcoming events ({days} day(s)):\n" + "\n".join(lines)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        logger.error(f"Calendar error: {e}", exc_info=True)
        return f"Error accessing calendar: {e}"


@tool
def create_calendar_event(title: str, start_time: str, end_time: str, description: str = "") -> str:
    """Create a new calendar event. Times should be in ISO 8601 format (e.g., 2024-01-15T14:00:00)."""
    try:
        creds = get_google_credentials()
        service = build("calendar", "v3", credentials=creds)

        event = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start_time, "timeZone": "America/New_York"},
            "end": {"dateTime": end_time, "timeZone": "America/New_York"},
        }

        created = service.events().insert(calendarId="primary", body=event).execute()
        return f"Event created: '{title}' - Link: {created.get('htmlLink', 'N/A')}"
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        logger.error(f"Calendar create error: {e}", exc_info=True)
        return f"Error creating event: {e}"
