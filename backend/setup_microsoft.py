#!/usr/bin/env python3
"""
Generate Microsoft OAuth2 refresh token for NOVA
Run after registering an app in Azure AD.

Usage:
    python3 setup_microsoft.py
"""

import json
import urllib.request
import urllib.parse
import http.server
import threading
import webbrowser

REDIRECT_PORT = 8400
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}"
SCOPES = "Mail.Read Mail.Send Calendars.ReadWrite User.Read offline_access"


def main():
    print("\n╔══════════════════════════════════════╗")
    print("║  NOVA — Microsoft 365 Setup      ║")
    print("╚══════════════════════════════════════╝\n")

    client_id = input("  Client ID (Application ID): ").strip()
    client_secret = input("  Client Secret (Value): ").strip()
    tenant_id = input("  Tenant ID (Directory ID): ").strip()

    if not all([client_id, client_secret, tenant_id]):
        print("\n  ERROR: All 3 values are required.")
        return

    # Build auth URL
    auth_url = (
        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize?"
        + urllib.parse.urlencode({
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPES,
            "response_mode": "query",
        })
    )

    # Start local server to capture the code
    auth_code = None
    server_done = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal auth_code
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            auth_code = params.get("code", [None])[0]

            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            if auth_code:
                self.wfile.write(b"<h2>NOVA authorized! You can close this tab.</h2>")
            else:
                error = params.get("error_description", ["Unknown error"])[0]
                self.wfile.write(f"<h2>Error: {error}</h2>".encode())
            server_done.set()

        def log_message(self, format, *args):
            pass  # Suppress server logs

    server = http.server.HTTPServer(("localhost", REDIRECT_PORT), Handler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    print(f"\n  Opening browser for Microsoft login...")
    webbrowser.open(auth_url)
    print(f"  Waiting for authorization...")

    server_done.wait(timeout=120)
    server.server_close()

    if not auth_code:
        print("\n  ERROR: Authorization failed or timed out.")
        return

    print(f"  Authorization code received. Exchanging for tokens...")

    # Exchange code for tokens
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "code": auth_code,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
        "scope": SCOPES,
    }).encode()

    req = urllib.request.Request(token_url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
    except Exception as e:
        print(f"\n  ERROR: Token exchange failed: {e}")
        return

    refresh_token = result.get("refresh_token", "")
    if not refresh_token:
        print(f"\n  ERROR: No refresh token received. Make sure 'offline_access' scope is granted.")
        return

    # Save to Keychain
    print(f"\n  Saving to macOS Keychain...")
    try:
        import subprocess
        secrets = {
            "microsoft_client_id": client_id,
            "microsoft_client_secret": client_secret,
            "microsoft_refresh_token": refresh_token,
            "microsoft_tenant_id": tenant_id,
        }
        for key, value in secrets.items():
            subprocess.run([
                "security", "delete-generic-password",
                "-s", f"nova.{key}", "-a", "nova",
            ], capture_output=True)
            subprocess.run([
                "security", "add-generic-password",
                "-s", f"nova.{key}", "-a", "nova",
                "-w", value, "-U",
            ], check=True, capture_output=True)
        print(f"  Stored 4 secrets in Keychain")
    except Exception as e:
        print(f"  WARNING: Could not save to Keychain: {e}")

    # Print for manual .env setup
    print(f"\n  ╔══════════════════════════════════════╗")
    print(f"  ║         Setup Complete!               ║")
    print(f"  ╚══════════════════════════════════════╝")
    print(f"\n  Secrets saved to macOS Keychain.")
    print(f"\n  If you also want them in .env, add:")
    print(f"  MICROSOFT_CLIENT_ID={client_id}")
    print(f"  MICROSOFT_CLIENT_SECRET={client_secret}")
    print(f"  MICROSOFT_TENANT_ID={tenant_id}")
    print(f"  MICROSOFT_REFRESH_TOKEN={refresh_token[:20]}...")
    print(f"\n  Restart NOVA backend and test:")
    print(f'  "Jarvis, ¿qué reuniones tengo hoy?"')
    print(f'  "Jarvis, ¿hay correos sin leer?"')
    print()


if __name__ == "__main__":
    main()
