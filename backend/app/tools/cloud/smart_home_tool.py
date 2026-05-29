import logging
import requests
from langchain.tools import tool

from app.config import settings

logger = logging.getLogger(__name__)


def _ha_headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.home_assistant_token}",
        "Content-Type": "application/json",
    }


@tool
def list_smart_devices() -> str:
    """List all smart home devices from Home Assistant."""
    if not settings.home_assistant_url or not settings.home_assistant_token:
        return "Smart home not configured. Set HOME_ASSISTANT_URL and HOME_ASSISTANT_TOKEN in .env"

    try:
        resp = requests.get(
            f"{settings.home_assistant_url}/api/states",
            headers=_ha_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        states = resp.json()

        # Filter to common device types
        device_types = {"light.", "switch.", "fan.", "climate.", "media_player.", "lock."}
        devices = [
            s for s in states
            if any(s["entity_id"].startswith(t) for t in device_types)
        ]

        if not devices:
            return "No smart devices found."

        lines = []
        for d in devices[:20]:
            name = d.get("attributes", {}).get("friendly_name", d["entity_id"])
            state = d["state"]
            lines.append(f"- {name} ({d['entity_id']}): {state}")

        return f"Smart devices ({len(devices)} total):\n" + "\n".join(lines)
    except Exception as e:
        logger.error(f"Home Assistant error: {e}", exc_info=True)
        return f"Error accessing Home Assistant: {e}"


@tool
def control_device(entity_id: str, action: str) -> str:
    """Control a smart home device. Actions: 'turn_on', 'turn_off', 'toggle'.
    Entity IDs look like 'light.living_room' or 'switch.bedroom_fan'."""
    if not settings.home_assistant_url or not settings.home_assistant_token:
        return "Smart home not configured. Set HOME_ASSISTANT_URL and HOME_ASSISTANT_TOKEN in .env"

    valid_actions = {"turn_on", "turn_off", "toggle"}
    if action not in valid_actions:
        return f"Invalid action '{action}'. Use one of: {', '.join(valid_actions)}"

    try:
        domain = entity_id.split(".")[0]
        resp = requests.post(
            f"{settings.home_assistant_url}/api/services/{domain}/{action}",
            headers=_ha_headers(),
            json={"entity_id": entity_id},
            timeout=10,
        )
        resp.raise_for_status()
        return f"Done: {action} on {entity_id}"
    except Exception as e:
        logger.error(f"Home Assistant control error: {e}", exc_info=True)
        return f"Error controlling device: {e}"
