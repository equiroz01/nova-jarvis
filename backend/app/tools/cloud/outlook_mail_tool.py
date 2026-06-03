"""Outlook Mail tools for N.O.V.A. — Microsoft 365 email via Graph API."""

import logging
from langchain.tools import tool

logger = logging.getLogger(__name__)


@tool
def search_outlook_emails(query: str, max_results: int = 5) -> str:
    """Search Outlook emails. Use natural search terms or OData filters.
    Examples: 'from:karen', 'subject:factura', 'is:unread', a person's name, or any keyword.
    Use when the user asks about emails, messages, or inbox."""
    try:
        from app.services.microsoft_auth import graph_request

        # $search does not support $orderby — Graph returns by relevance
        endpoint = (
            f"me/messages?$search=\"{query}\""
            f"&$top={max_results}"
            f"&$select=subject,from,receivedDateTime,bodyPreview,isRead,webLink"
        )

        result = graph_request("GET", endpoint)
        messages = result.get("value", [])

        if not messages:
            return f"No se encontraron correos para: '{query}'"

        lines = []
        for msg in messages:
            subject = msg.get("subject", "Sin asunto")
            from_addr = msg.get("from", {}).get("emailAddress", {})
            sender = from_addr.get("name", from_addr.get("address", "Desconocido"))
            date = msg.get("receivedDateTime", "")[:16].replace("T", " ")
            preview = msg.get("bodyPreview", "")[:120]
            read_icon = "" if msg.get("isRead") else " [NO LEÍDO]"

            lines.append(f"- **{subject}**{read_icon}\n  De: {sender} | {date}\n  {preview}")

        return f"**{len(messages)} correo(s) encontrados:**\n\n" + "\n\n".join(lines)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        logger.error(f"Outlook mail search error: {e}", exc_info=True)
        return f"Error searching Outlook: {e}"


@tool
def send_outlook_email(to: str, subject: str, body: str, cc: str = "") -> str:
    """Send an email via Outlook. Provide recipient, subject, and body text.
    CC: comma-separated emails (optional).
    Use when the user asks to send an email, reply, or write a message."""
    try:
        from app.services.microsoft_auth import graph_request

        message = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [
                    {"emailAddress": {"address": email.strip()}}
                    for email in to.split(",") if email.strip()
                ],
            }
        }

        if cc:
            message["message"]["ccRecipients"] = [
                {"emailAddress": {"address": email.strip()}}
                for email in cc.split(",") if email.strip()
            ]

        graph_request("POST", "me/sendMail", message)
        return f"Correo enviado a {to} — Asunto: '{subject}'"
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        logger.error(f"Outlook send error: {e}", exc_info=True)
        return f"Error sending email: {e}"


@tool
def get_unread_outlook_emails(max_results: int = 10) -> str:
    """Get unread emails from Outlook inbox.
    Use when the user asks about new emails, unread messages, or inbox status."""
    try:
        from app.services.microsoft_auth import graph_request

        result = graph_request(
            "GET",
            f"me/mailFolders/inbox/messages"
            f"?$filter=isRead eq false"
            f"&$top={max_results}"
            f"&$select=subject,from,receivedDateTime,bodyPreview,importance"
            f"&$orderby=receivedDateTime desc",
        )

        messages = result.get("value", [])
        if not messages:
            return "No hay correos sin leer. Bandeja limpia."

        lines = []
        for msg in messages:
            subject = msg.get("subject", "Sin asunto")
            from_addr = msg.get("from", {}).get("emailAddress", {})
            sender = from_addr.get("name", from_addr.get("address", "?"))
            date = msg.get("receivedDateTime", "")[:16].replace("T", " ")
            importance = msg.get("importance", "normal")
            imp_icon = " [URGENTE]" if importance == "high" else ""

            lines.append(f"- **{subject}**{imp_icon}\n  De: {sender} | {date}")

        return f"**{len(messages)} correo(s) sin leer:**\n\n" + "\n\n".join(lines)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        logger.error(f"Outlook unread error: {e}", exc_info=True)
        return f"Error getting unread emails: {e}"
