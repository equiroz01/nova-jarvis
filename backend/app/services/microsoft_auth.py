"""
Microsoft OAuth2 — authenticate with Microsoft Graph API for Outlook Mail and Calendar.

Uses MSAL (Microsoft Authentication Library) with refresh token flow.
"""

import json
import logging
import urllib.request
import urllib.parse
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

SCOPES = [
    "Mail.Read",
    "Mail.Send",
    "Calendars.ReadWrite",
    "User.Read",
    "offline_access",
]

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# Token cache
_access_token: str = ""
_token_expiry: float = 0


def _get_credentials() -> tuple[str, str, str, str]:
    """Get Microsoft credentials from Keychain, then fallback to settings."""
    client_id = ""
    client_secret = ""
    refresh_token = ""
    tenant_id = ""

    # Try Keychain first
    try:
        from app.services.keychain import keychain
        client_id = keychain.get("microsoft_client_id")
        client_secret = keychain.get("microsoft_client_secret")
        refresh_token = keychain.get("microsoft_refresh_token")
        tenant_id = keychain.get("microsoft_tenant_id")
    except Exception:
        logger.warning("Keychain read for Microsoft creds failed; falling back to .env", exc_info=True)

    # Fallback to settings/.env
    client_id = client_id or getattr(settings, "microsoft_client_id", "") or ""
    client_secret = client_secret or getattr(settings, "microsoft_client_secret", "") or ""
    refresh_token = refresh_token or getattr(settings, "microsoft_refresh_token", "") or ""
    tenant_id = tenant_id or getattr(settings, "microsoft_tenant_id", "") or ""

    return client_id, client_secret, refresh_token, tenant_id


def get_access_token() -> str:
    """Get a valid Microsoft Graph access token using refresh token."""
    global _access_token, _token_expiry
    import time

    if _access_token and time.time() < _token_expiry - 60:
        return _access_token

    client_id, client_secret, refresh_token, tenant_id = _get_credentials()

    if not client_id or not refresh_token:
        raise RuntimeError(
            "Microsoft OAuth not configured. Set microsoft_client_id, "
            "microsoft_client_secret, microsoft_refresh_token, and "
            "microsoft_tenant_id in Keychain or .env"
        )

    token_url = f"https://login.microsoftonline.com/{tenant_id or 'common'}/oauth2/v2.0/token"

    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
        "scope": " ".join(SCOPES),
    }).encode()

    req = urllib.request.Request(token_url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            _access_token = result["access_token"]
            _token_expiry = time.time() + result.get("expires_in", 3600)

            # Update refresh token if rotated
            new_refresh = result.get("refresh_token")
            if new_refresh and new_refresh != refresh_token:
                try:
                    from app.services.keychain import keychain
                    keychain.set("microsoft_refresh_token", new_refresh)
                    logger.info("Microsoft refresh token rotated and saved to Keychain")
                except Exception:
                    logger.warning("Could not save rotated refresh token to Keychain")

            return _access_token
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        logger.error(f"Microsoft token error: {e.code} — {body}")
        raise RuntimeError(f"Microsoft auth failed ({e.code}). Check credentials.")
    except Exception as e:
        raise RuntimeError(f"Microsoft auth error: {e}")


def graph_request(method: str, endpoint: str, data: dict = None, headers: dict = None) -> dict:
    """Make an authenticated request to Microsoft Graph API."""
    token = get_access_token()
    # Encode query params properly — preserve OData operators
    if "?" in endpoint:
        path, qs = endpoint.split("?", 1)
        encoded_parts = []
        for part in qs.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                safe_chars = "$,/:@!'()*+"
                encoded_parts.append(f"{k}={urllib.parse.quote(v, safe=safe_chars)}")
            else:
                encoded_parts.append(part)
        url = f"{GRAPH_BASE}/{path}?{'&'.join(encoded_parts)}"
    else:
        url = f"{GRAPH_BASE}/{endpoint}"

    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        logger.error(f"Graph API error: {method} {endpoint} → {e.code}: {body[:300]}")
        raise RuntimeError(f"Microsoft Graph error ({e.code}): {body[:200]}")
