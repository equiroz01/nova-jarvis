# N.O.V.A. — Setup Guide

## Quick Install (Mac Studio)

```bash
git clone https://github.com/tuuser/jarvis.git ~/.nova/app
~/.nova/app/install.sh
```

The installer handles everything: Python, dependencies, venv, .env config, Cloudflare Tunnel, launchd services.

## Management CLI

```bash
nova status       # check all services
nova start        # start backend + client + tunnel
nova stop         # stop everything
nova restart      # restart all
nova logs         # tail backend logs
nova logs client  # tail client logs
nova update       # git pull + pip install + restart
nova tunnel       # show Cloudflare Tunnel URL
nova uninstall    # remove services and optionally all data
```

## Architecture

```
Mac Studio (always on)
├── N.O.V.A. Backend (:8080) — FastAPI + Gemini + Whisper STT + Edge TTS
├── N.O.V.A. Client — wake word detection + voice interaction
└── Cloudflare Tunnel — HTTPS access for Alexa + external web

Consumers:
├── Voice (local mic on Mac Studio)
├── Web UI (http://mac-studio.local:8080 or https://nova.yourdomain.com)
└── Alexa (via Cloudflare Tunnel)
```

## Directory Structure

```
~/.nova/
├── app/                    # git repo (code, updates here)
├── config/
│   ├── .env                # secrets (GEMINI_API_KEY, NOVA_API_KEY, etc.)
│   ├── client.env          # client config
│   └── cloudflared.yml     # tunnel config
├── data/
│   ├── nova-brain/         # Obsidian vault → iCloud Drive (syncs across devices)
│   ├── voiceprint.json     # voice ID data
│   └── .agilitytask/       # AgilityTask credentials
├── venv/                   # Python virtual environment
├── logs/                   # backend.log, client.log, tunnel.log
└── secrets/                # GCP service account (if needed)
```

## iCloud Sync (nova-brain)

The installer automatically places `nova-brain` in iCloud Drive:

```
~/Library/Mobile Documents/com~apple~CloudDocs/nova-brain/
```

A symlink connects it to `~/.nova/data/nova-brain`. Open the vault in Obsidian from any Apple device to view/edit N.O.V.A.'s knowledge graph.

### Manual iCloud setup (existing install)

```bash
# Move vault to iCloud
mv ~/.nova/data/nova-brain ~/Library/Mobile\ Documents/com~apple~CloudDocs/nova-brain

# Symlink back
ln -sf ~/Library/Mobile\ Documents/com~apple~CloudDocs/nova-brain ~/.nova/data/nova-brain
```

## Configuration

### Required

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google Gemini API key ([get one](https://aistudio.google.com/apikey)) |

### Auto-generated

| Variable | Description |
|----------|-------------|
| `NOVA_API_KEY` | Random key for external (non-LAN) access — generated at install |
| `NOVA_HOME` | Path to ~/.nova |

### Optional

| Variable | Description |
|----------|-------------|
| `GOOGLE_CLIENT_ID` | OAuth2 for Calendar/Gmail |
| `GOOGLE_CLIENT_SECRET` | OAuth2 secret |
| `GOOGLE_REFRESH_TOKEN` | OAuth2 refresh token |
| `HOME_ASSISTANT_URL` | Home Assistant instance URL |
| `HOME_ASSISTANT_TOKEN` | Home Assistant API token |
| `ALEXA_SKILL_ID` | Alexa skill ID for verification |

## Security

- **LAN requests** → direct access, no auth required
- **External requests** (via tunnel) → `NOVA_API_KEY` required as `Authorization: Bearer <key>`
- **Alexa** → `/alexa` endpoint always open (verified by Skill ID)
- **Cloudflare Tunnel** → only exposes necessary routes, not `/api/settings` or `/ws/client`

## Cloudflare Tunnel Setup

If you skipped tunnel during install, run the installer again or set up manually:

```bash
# Login to Cloudflare
cloudflared tunnel login

# Create tunnel
cloudflared tunnel create nova

# Add DNS route
cloudflared tunnel route dns nova nova.yourdomain.com

# Edit config
nano ~/.nova/config/cloudflared.yml

# Start tunnel
nova restart
```

### Alexa Lambda

Update the `JARVIS_BACKEND_URL` environment variable in your Alexa Lambda to point to your tunnel URL:

```
https://nova.yourdomain.com
```

## Updating

```bash
nova update
```

This pulls the latest code, installs new dependencies, and restarts services. Your data (nova-brain, voiceprint, .env, credentials) is never touched by updates.

## Troubleshooting

```bash
# Check service status
nova status

# View logs
nova logs           # backend
nova logs client    # voice client
nova logs tunnel    # cloudflare tunnel

# Restart a stuck service
nova restart

# Health check
curl http://localhost:8080/health

# Verify tunnel
curl https://nova.yourdomain.com/health
```

## Uninstall

```bash
nova uninstall
```

This stops services, removes launchd plists, and optionally removes all data.
