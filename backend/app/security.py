"""Single source of truth for request trust decisions.

Both the global API-key middleware (main.py) and the /health detail gate use
these helpers, so the tunnel-vs-LAN auth logic lives in exactly one place.

Threat model: the box is reachable from the internet via a Cloudflare Tunnel.
cloudflared connects over loopback, so every tunnelled request looks local —
source-IP "is this LAN?" is meaningless for it. Cloudflare authoritatively stamps
CF-Connecting-IP / CF-Ray on everything it proxies (it overwrites client-supplied
values, so they cannot be forged); their presence means the request came from the
internet and must present the API key.
"""

import ipaddress
from fastapi import Request

from app.config import settings

_LAN_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
]


def is_lan(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
        return any(addr in net for net in _LAN_NETWORKS)
    except ValueError:
        return False


def via_tunnel(request: Request) -> bool:
    """True if the request was proxied by Cloudflare (i.e. came from the internet)."""
    return "cf-connecting-ip" in request.headers or "cf-ray" in request.headers


def has_valid_key(request: Request) -> bool:
    auth = request.headers.get("authorization", "")
    token = auth[len("Bearer "):].strip() if auth.startswith("Bearer ") else ""
    api_key_param = request.query_params.get("api_key", "")
    return bool(settings.nova_api_key) and (
        token == settings.nova_api_key or api_key_param == settings.nova_api_key
    )


def is_trusted_request(request: Request) -> bool:
    """True if the request is genuinely local (not tunnelled) or carries the key.

    Intentionally strict even in open mode (no key configured): health detail is
    only ever shown to a real LAN client or a key-bearer, never to tunnel traffic.
    """
    if not via_tunnel(request):
        client_ip = request.client.host if request.client else "0.0.0.0"
        if is_lan(client_ip):
            return True
    return has_valid_key(request)
