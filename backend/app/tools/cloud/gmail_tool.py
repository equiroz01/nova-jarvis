import base64
import logging
from email.mime.text import MIMEText
from langchain.tools import tool
from googleapiclient.discovery import build

from app.services.google_auth import get_google_credentials

logger = logging.getLogger(__name__)


@tool
def search_emails(query: str, max_results: int = 5) -> str:
    """Search emails in Gmail. Use Gmail search syntax (e.g., 'from:someone@email.com', 'is:unread', 'subject:hello')."""
    try:
        creds = get_google_credentials()
        service = build("gmail", "v1", credentials=creds)

        results = service.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()

        messages = results.get("messages", [])
        if not messages:
            return f"No emails found for query: '{query}'"

        lines = []
        for msg_ref in messages:
            msg = service.users().messages().get(
                userId="me", id=msg_ref["id"], format="metadata",
                metadataHeaders=["Subject", "From", "Date"],
            ).execute()

            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            subject = headers.get("Subject", "No subject")
            from_addr = headers.get("From", "Unknown")
            date = headers.get("Date", "Unknown date")
            snippet = msg.get("snippet", "")[:100]

            lines.append(f"- [{date}] From: {from_addr}\n  Subject: {subject}\n  Preview: {snippet}")

        return f"Found {len(messages)} email(s):\n" + "\n\n".join(lines)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        logger.error(f"Gmail search error: {e}", exc_info=True)
        return f"Error searching emails: {e}"


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email via Gmail. Provide the recipient address, subject, and body text."""
    try:
        creds = get_google_credentials()
        service = build("gmail", "v1", credentials=creds)

        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()

        return f"Email sent to {to} with subject: '{subject}'"
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        logger.error(f"Gmail send error: {e}", exc_info=True)
        return f"Error sending email: {e}"
