#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════╗
# ║  NOVA Installer — Mac Home Server Setup                ║
# ║  Neural Operative Voice Assistant                           ║
# ╚══════════════════════════════════════════════════════════════╝
set -euo pipefail

# ── Config ──
NOVA_HOME="$HOME/.nova"
NOVA_APP="$NOVA_HOME/app"
NOVA_VENV="$NOVA_HOME/venv"
NOVA_DATA="$NOVA_HOME/data"
NOVA_CONFIG="$NOVA_HOME/config"
NOVA_LOGS="$NOVA_HOME/logs"
NOVA_SECRETS="$NOVA_HOME/secrets"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON=""

# ── Colors ──
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()  { echo -e "  ${CYAN}INFO${NC}  $1"; }
ok()    { echo -e "  ${GREEN}OK${NC}    $1"; }
warn()  { echo -e "  ${YELLOW}WARN${NC}  $1"; }
fail()  { echo -e "  ${RED}FAIL${NC}  $1"; exit 1; }

# ══════════════════════════════════════════════════════════════
# Phase 1: Preflight
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}║       NOVA INSTALLER v1.0       ║${NC}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════╝${NC}"
echo ""

# macOS check
[[ "$(uname)" == "Darwin" ]] || fail "This installer is for macOS only."

# Homebrew
if ! command -v brew &>/dev/null; then
  info "Installing Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi
ok "Homebrew"

# Python 3.11+
for py in python3.11 python3.12 python3.13 python3; do
  if command -v "$py" &>/dev/null; then
    ver=$("$py" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    major="${ver%%.*}"
    minor="${ver#*.}"
    if [[ "$major" -ge 3 && "$minor" -ge 11 ]]; then
      PYTHON="$(command -v "$py")"
      break
    fi
  fi
done

if [[ -z "$PYTHON" ]]; then
  info "Installing Python 3.11 via Homebrew..."
  brew install python@3.11
  PYTHON="$(brew --prefix python@3.11)/bin/python3.11"
fi
ok "Python: $($PYTHON --version) at $PYTHON"

# ══════════════════════════════════════════════════════════════
# Phase 2: System Dependencies
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}Installing system dependencies...${NC}"

BREW_DEPS=(portaudio tesseract)
for dep in "${BREW_DEPS[@]}"; do
  if brew list "$dep" &>/dev/null; then
    ok "$dep (already installed)"
  else
    info "Installing $dep..."
    brew install "$dep"
    ok "$dep"
  fi
done

# Cloudflared
if command -v cloudflared &>/dev/null; then
  ok "cloudflared (already installed)"
else
  info "Installing cloudflared..."
  brew install cloudflare/cloudflare/cloudflared
  ok "cloudflared"
fi

# ══════════════════════════════════════════════════════════════
# Phase 3: Directory Structure
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}Setting up directories...${NC}"

mkdir -p "$NOVA_HOME" "$NOVA_DATA" "$NOVA_CONFIG" "$NOVA_LOGS" "$NOVA_SECRETS"

# nova-brain: use iCloud if available, fallback to local
ICLOUD_DIR="$HOME/Library/Mobile Documents/com~apple~CloudDocs"
ICLOUD_BRAIN="$ICLOUD_DIR/nova-brain"

if [[ -d "$ICLOUD_DIR" ]]; then
  mkdir -p "$ICLOUD_BRAIN"
  # Point NOVA_DATA/nova-brain to iCloud
  if [[ -d "$NOVA_DATA/nova-brain" && ! -L "$NOVA_DATA/nova-brain" ]]; then
    # Migrate existing local data to iCloud
    if [[ "$(ls -A "$NOVA_DATA/nova-brain" 2>/dev/null)" ]]; then
      cp -Rn "$NOVA_DATA/nova-brain/"* "$ICLOUD_BRAIN/" 2>/dev/null || true
      info "Migrated existing nova-brain to iCloud"
    fi
    rm -rf "$NOVA_DATA/nova-brain"
  fi
  if [[ ! -L "$NOVA_DATA/nova-brain" ]]; then
    ln -sf "$ICLOUD_BRAIN" "$NOVA_DATA/nova-brain"
  fi
  ok "nova-brain → iCloud Drive (syncs across all Apple devices)"
else
  mkdir -p "$NOVA_DATA/nova-brain"
  ok "nova-brain → local ($NOVA_DATA/nova-brain)"
fi

# Link or copy app
if [[ "$SCRIPT_DIR" != "$NOVA_APP" ]]; then
  if [[ -L "$NOVA_APP" ]]; then
    rm "$NOVA_APP"
  elif [[ -d "$NOVA_APP" ]]; then
    # Existing app dir — pull updates
    cd "$NOVA_APP" && git pull origin main 2>/dev/null || true
  fi

  if [[ ! -d "$NOVA_APP" ]]; then
    ln -sf "$SCRIPT_DIR" "$NOVA_APP"
    ok "App linked: $SCRIPT_DIR -> $NOVA_APP"
  fi
else
  ok "App already at $NOVA_APP"
fi

# Migrate nova-brain data to persistent location
if [[ -d "$NOVA_APP/backend/nova-brain" && ! -L "$NOVA_APP/backend/nova-brain" ]]; then
  if [[ "$(ls -A "$NOVA_APP/backend/nova-brain" 2>/dev/null)" ]]; then
    # Has content — copy to data dir if data dir is empty
    if [[ ! "$(ls -A "$NOVA_DATA/nova-brain" 2>/dev/null | grep -v '.obsidian')" ]]; then
      cp -R "$NOVA_APP/backend/nova-brain/"* "$NOVA_DATA/nova-brain/" 2>/dev/null || true
      info "Migrated nova-brain to persistent storage"
    fi
  fi
  rm -rf "$NOVA_APP/backend/nova-brain"
fi

# Symlink nova-brain
if [[ ! -L "$NOVA_APP/backend/nova-brain" ]]; then
  ln -sf "$NOVA_DATA/nova-brain" "$NOVA_APP/backend/nova-brain"
fi
ok "nova-brain → $NOVA_DATA/nova-brain"

# Migrate .agilitytask if present
if [[ -d "$NOVA_APP/.agilitytask" && ! -L "$NOVA_APP/.agilitytask" ]]; then
  cp -R "$NOVA_APP/.agilitytask/"* "$NOVA_DATA/.agilitytask/" 2>/dev/null || true
  rm -rf "$NOVA_APP/.agilitytask"
fi
mkdir -p "$NOVA_DATA/.agilitytask"
if [[ ! -L "$NOVA_APP/.agilitytask" ]]; then
  ln -sf "$NOVA_DATA/.agilitytask" "$NOVA_APP/.agilitytask"
fi

ok "Directory structure ready"

# ══════════════════════════════════════════════════════════════
# Phase 4: Python Virtual Environment
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}Setting up Python environment...${NC}"

if [[ ! -d "$NOVA_VENV" ]]; then
  info "Creating virtual environment..."
  "$PYTHON" -m venv "$NOVA_VENV"
fi

info "Installing backend dependencies..."
"$NOVA_VENV/bin/pip" install -q --upgrade pip
# PyAudio needs special flags on Apple Silicon
export LDFLAGS="-L$(brew --prefix portaudio)/lib"
export CFLAGS="-I$(brew --prefix portaudio)/include"
"$NOVA_VENV/bin/pip" install -q -r "$NOVA_APP/backend/requirements.txt"

info "Installing client dependencies..."
"$NOVA_VENV/bin/pip" install -q -r "$NOVA_APP/client/requirements.txt"

ok "Python environment ready ($("$NOVA_VENV/bin/python" --version))"

# ══════════════════════════════════════════════════════════════
# Phase 5: Configuration (.env)
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}Configuring NOVA...${NC}"

ENV_FILE="$NOVA_CONFIG/.env"

if [[ -f "$ENV_FILE" ]]; then
  ok ".env already configured"
else
  info "Let's configure NOVA (you can edit $ENV_FILE later)"
  echo ""

  # Gemini API Key (required)
  read -p "  GEMINI_API_KEY (required): " gemini_key
  if [[ -z "$gemini_key" ]]; then
    fail "GEMINI_API_KEY is required. Get one at https://aistudio.google.com/apikey"
  fi

  # Generate random API key for external access
  nova_api_key="nova_$(openssl rand -hex 16)"

  cat > "$ENV_FILE" <<ENVEOF
# NOVA Configuration — generated by installer
GEMINI_API_KEY=$gemini_key

# NOVA Home Server
NOVA_HOME=$NOVA_HOME
NOVA_API_KEY=$nova_api_key

# Logging
LOG_LEVEL=INFO
ALLOWED_ORIGINS=*

# Google OAuth (Calendar/Gmail) — optional
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REFRESH_TOKEN=

# Home Assistant — optional
HOME_ASSISTANT_URL=
HOME_ASSISTANT_TOKEN=

# Alexa — optional
ALEXA_SKILL_ID=
ENVEOF

  ok ".env created"
  info "API key for external access: $nova_api_key"
  info "Save this key — you'll need it for Alexa or external clients"
fi

# Symlink .env to backend
if [[ ! -L "$NOVA_APP/backend/.env" ]]; then
  ln -sf "$ENV_FILE" "$NOVA_APP/backend/.env"
fi

# ══════════════════════════════════════════════════════════════
# Phase 6: Cloudflare Tunnel (optional)
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}Cloudflare Tunnel Setup${NC}"
echo ""
read -p "  Set up Cloudflare Tunnel for external access (Alexa, web)? (y/N) " setup_tunnel

if [[ "$setup_tunnel" == "y" || "$setup_tunnel" == "Y" ]]; then
  if [[ ! -f "$HOME/.cloudflared/cert.pem" ]]; then
    info "Opening browser for Cloudflare login..."
    cloudflared tunnel login
  fi

  # Create tunnel
  read -p "  Tunnel name (default: nova): " tunnel_name
  tunnel_name="${tunnel_name:-nova}"

  if cloudflared tunnel list 2>/dev/null | grep -q "$tunnel_name"; then
    ok "Tunnel '$tunnel_name' already exists"
    tunnel_uuid=$(cloudflared tunnel list 2>/dev/null | grep "$tunnel_name" | awk '{print $1}')
  else
    info "Creating tunnel '$tunnel_name'..."
    tunnel_output=$(cloudflared tunnel create "$tunnel_name" 2>&1)
    tunnel_uuid=$(echo "$tunnel_output" | grep -oE '[0-9a-f-]{36}' | head -1)
    ok "Tunnel created: $tunnel_uuid"
  fi

  read -p "  Hostname (e.g., nova.yourdomain.com): " tunnel_hostname
  if [[ -z "$tunnel_hostname" ]]; then
    warn "No hostname provided — tunnel config not generated"
    warn "You can set it up later by editing $NOVA_CONFIG/cloudflared.yml"
  else
    # Create DNS route
    cloudflared tunnel route dns "$tunnel_name" "$tunnel_hostname" 2>/dev/null || true

    # Generate config from template
    sed \
      -e "s|__TUNNEL_UUID__|$tunnel_uuid|g" \
      -e "s|__HOME__|$HOME|g" \
      -e "s|__TUNNEL_HOSTNAME__|$tunnel_hostname|g" \
      "$NOVA_APP/deploy/cloudflare/config.yml.template" > "$NOVA_CONFIG/cloudflared.yml"

    ok "Tunnel config: $NOVA_CONFIG/cloudflared.yml"
    ok "DNS route: $tunnel_hostname -> tunnel"
  fi
else
  info "Skipping tunnel setup. NOVA will be LAN-only."
  info "Run this installer again to set up the tunnel later."
fi

# ══════════════════════════════════════════════════════════════
# Phase 7: launchd Services
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}Installing system services...${NC}"

mkdir -p "$LAUNCH_DIR"

install_plist() {
  local name="$1"
  local src="$NOVA_APP/deploy/launchd/${name}.plist"
  local dst="$LAUNCH_DIR/${name}.plist"

  if [[ ! -f "$src" ]]; then
    warn "Plist not found: $src"
    return
  fi

  # Replace placeholders with absolute paths
  sed \
    -e "s|__NOVA_VENV__|$NOVA_VENV|g" \
    -e "s|__NOVA_APP__|$NOVA_APP|g" \
    -e "s|__NOVA_HOME__|$NOVA_HOME|g" \
    "$src" > "$dst"

  ok "$name installed"
}

install_plist "com.nova.backend"
install_plist "com.nova.client"

# Only install tunnel plist if configured
if [[ -f "$NOVA_CONFIG/cloudflared.yml" ]]; then
  install_plist "com.nova.tunnel"
else
  info "Tunnel plist skipped (not configured)"
fi

# ══════════════════════════════════════════════════════════════
# Phase 8: Install nova CLI
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}Installing nova CLI...${NC}"

if [[ -w /usr/local/bin ]] || sudo -n true 2>/dev/null; then
  ln -sf "$NOVA_APP/nova-ctl.sh" /usr/local/bin/nova 2>/dev/null || \
    sudo ln -sf "$NOVA_APP/nova-ctl.sh" /usr/local/bin/nova
  ok "nova CLI → /usr/local/bin/nova"
else
  warn "Cannot write to /usr/local/bin. Run: sudo ln -sf $NOVA_APP/nova-ctl.sh /usr/local/bin/nova"
fi

# ══════════════════════════════════════════════════════════════
# Phase 9: Start & Verify
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}Starting NOVA...${NC}"

GUI_DOMAIN="gui/$(id -u)"

for label in com.nova.backend com.nova.client; do
  plist="$LAUNCH_DIR/${label}.plist"
  [[ -f "$plist" ]] && launchctl bootstrap "$GUI_DOMAIN" "$plist" 2>/dev/null || true
done

if [[ -f "$LAUNCH_DIR/com.nova.tunnel.plist" ]]; then
  launchctl bootstrap "$GUI_DOMAIN" "$LAUNCH_DIR/com.nova.tunnel.plist" 2>/dev/null || true
fi

# Wait for backend
echo -ne "  Waiting for backend..."
for i in $(seq 1 15); do
  if curl -sf http://localhost:8080/health -o /dev/null 2>/dev/null; then
    echo ""
    ok "Backend is running!"
    break
  fi
  echo -n "."
  sleep 2
done

if ! curl -sf http://localhost:8080/health -o /dev/null 2>/dev/null; then
  echo ""
  warn "Backend not responding yet. Check logs: tail -f $NOVA_LOGS/backend.error.log"
fi

# ══════════════════════════════════════════════════════════════
# Done!
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║      NOVA INSTALL COMPLETE       ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}Local:${NC}    http://localhost:8080"

if [[ -f "$NOVA_CONFIG/cloudflared.yml" ]]; then
  tunnel_host=$(grep 'hostname:' "$NOVA_CONFIG/cloudflared.yml" 2>/dev/null | head -1 | awk '{print $2}')
  [[ -n "$tunnel_host" ]] && echo -e "  ${BOLD}External:${NC} https://${tunnel_host}"
fi

echo ""
echo -e "  ${BOLD}Commands:${NC}"
echo "    nova status     — check services"
echo "    nova logs       — view backend logs"
echo "    nova restart    — restart all"
echo "    nova update     — pull & restart"
echo "    nova stop       — stop everything"
echo ""
echo -e "  ${BOLD}Say \"Jarvis\" to start a voice conversation.${NC}"
echo ""
