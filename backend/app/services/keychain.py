"""
NOVA Keychain — Centralized secret management via macOS Keychain.

All secrets stored under service prefix "nova." in the login keychain.
Fallback: reads from .env / config files if Keychain is unavailable.

Usage:
    from app.services.keychain import keychain
    keychain.set("gemini_api_key", "AIza...")
    key = keychain.get("gemini_api_key")
    keychain.delete("gemini_api_key")
    all_secrets = keychain.list()
"""

import subprocess
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SERVICE_PREFIX = "nova"


class NovaKeychain:
    """macOS Keychain wrapper for NOVA secrets."""

    def _run(self, args: list[str], input_data: str = None) -> tuple[int, str]:
        """Run a security command."""
        try:
            result = subprocess.run(
                ["security"] + args,
                capture_output=True, text=True, timeout=5,
                input=input_data,
            )
            return result.returncode, result.stdout.strip()
        except Exception as e:
            logger.warning(f"Keychain command failed: {e}")
            return 1, ""

    def _service(self, key: str) -> str:
        return f"{SERVICE_PREFIX}.{key}"

    def get(self, key: str, default: str = "") -> str:
        """Get a secret from Keychain."""
        code, output = self._run([
            "find-generic-password",
            "-s", self._service(key),
            "-a", SERVICE_PREFIX,
            "-w",  # output password only
        ])
        if code == 0 and output:
            return output
        return default

    def set(self, key: str, value: str) -> bool:
        """Store a secret in Keychain. Updates if exists."""
        # Delete first to avoid duplicates
        self.delete(key)
        code, _ = self._run([
            "add-generic-password",
            "-s", self._service(key),
            "-a", SERVICE_PREFIX,
            "-w", value,
            "-U",  # update if exists
        ])
        if code == 0:
            logger.info(f"Keychain: stored '{key}'")
            return True
        logger.warning(f"Keychain: failed to store '{key}'")
        return False

    def delete(self, key: str) -> bool:
        """Remove a secret from Keychain."""
        code, _ = self._run([
            "delete-generic-password",
            "-s", self._service(key),
            "-a", SERVICE_PREFIX,
        ])
        return code == 0

    def list(self) -> list[str]:
        """List all NOVA secret keys in Keychain."""
        code, output = self._run(["dump-keychain"])
        if code != 0:
            return []
        keys = []
        prefix = f'"{SERVICE_PREFIX}.'
        for line in output.split("\n"):
            if '"svce"' in line and prefix in line:
                # Extract service name: "nova.gemini_api_key"
                start = line.find(prefix) + 1
                end = line.find('"', start)
                if start > 0 and end > start:
                    full = line[start:end]
                    keys.append(full.replace(f"{SERVICE_PREFIX}.", ""))
        return keys

    def has(self, key: str) -> bool:
        """Check if a key exists."""
        code, _ = self._run([
            "find-generic-password",
            "-s", self._service(key),
            "-a", SERVICE_PREFIX,
        ])
        return code == 0

    def import_from_env(self, env_path: str = None) -> dict[str, bool]:
        """Import secrets from .env file into Keychain."""
        if env_path is None:
            env_path = Path(__file__).parent.parent.parent / ".env"
        else:
            env_path = Path(env_path)

        if not env_path.exists():
            return {}

        results = {}
        secret_keys = {
            "GEMINI_API_KEY": "gemini_api_key",
            "NOVA_API_KEY": "nova_api_key",
            "GOOGLE_CLIENT_ID": "google_client_id",
            "GOOGLE_CLIENT_SECRET": "google_client_secret",
            "GOOGLE_REFRESH_TOKEN": "google_refresh_token",
            "HOME_ASSISTANT_TOKEN": "home_assistant_token",
            "GITHUB_TOKEN": "github_token",
        }

        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key in secret_keys and value:
                kc_key = secret_keys[key]
                results[kc_key] = self.set(kc_key, value)

        return results

    def import_from_mcp_config(self, config_path: str = None) -> dict[str, bool]:
        """Import tokens from mcp_config.yaml into Keychain."""
        import yaml
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "mcp_config.yaml"
        else:
            config_path = Path(config_path)

        if not config_path.exists():
            return {}

        results = {}
        try:
            data = yaml.safe_load(config_path.read_text()) or {}
            for server in data.get("servers", []):
                env = server.get("env", {})
                for env_key, env_val in env.items():
                    if "TOKEN" in env_key or "KEY" in env_key or "SECRET" in env_key:
                        if env_val:
                            kc_key = f"mcp.{server['name'].lower().replace(' ', '_')}.{env_key.lower()}"
                            results[kc_key] = self.set(kc_key, env_val)
        except Exception as e:
            logger.warning(f"Failed to import MCP config: {e}")

        return results

    def import_from_agilitytask(self, creds_path: str = None) -> dict[str, bool]:
        """Import AgilityTask credentials into Keychain."""
        paths = [
            Path(creds_path) if creds_path else None,
            Path(__file__).parent.parent.parent.parent / ".agilitytask" / "credentials.json",
            Path.home() / ".agilitytask" / "credentials.json",
        ]
        results = {}
        for p in paths:
            if p and p.exists():
                try:
                    creds = json.loads(p.read_text())
                    api_key = creds.get("apiKey", "")
                    if api_key:
                        results["agilitytask_api_key"] = self.set("agilitytask_api_key", api_key)
                    email = creds.get("email", "")
                    if email:
                        results["agilitytask_email"] = self.set("agilitytask_email", email)
                    return results
                except Exception as e:
                    logger.warning(f"Failed to import AgilityTask creds: {e}")
        return results

    def get_summary(self) -> str:
        """Get a summary of all stored secrets (masked)."""
        keys = self.list()
        if not keys:
            return "No secrets in Keychain."
        lines = []
        for k in sorted(keys):
            val = self.get(k)
            masked = val[:4] + "…" + val[-4:] if len(val) > 8 else "****"
            lines.append(f"  {k}: {masked}")
        return f"NOVA Keychain ({len(keys)} secrets):\n" + "\n".join(lines)


# Singleton
keychain = NovaKeychain()
