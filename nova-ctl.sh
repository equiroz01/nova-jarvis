#!/usr/bin/env bash
# nova-ctl — N.O.V.A. service management CLI
set -euo pipefail

NOVA_HOME="${NOVA_HOME:-$HOME/.nova}"
NOVA_APP="$NOVA_HOME/app"
NOVA_VENV="$NOVA_HOME/venv"
NOVA_LOGS="$NOVA_HOME/logs"
NOVA_CONFIG="$NOVA_HOME/config"

BACKEND_LABEL="com.nova.backend"
CLIENT_LABEL="com.nova.client"
TUNNEL_LABEL="com.nova.tunnel"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
GUI_DOMAIN="gui/$(id -u)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; CYAN='\033[0;36m'; NC='\033[0m'; BOLD='\033[1m'

_is_loaded() { launchctl print "$GUI_DOMAIN/$1" &>/dev/null; }

_status_icon() {
  if _is_loaded "$1"; then echo -e "${GREEN}RUNNING${NC}"
  else echo -e "${RED}STOPPED${NC}"; fi
}

cmd_start() {
  echo -e "${CYAN}Starting N.O.V.A. services...${NC}"
  mkdir -p "$NOVA_LOGS"
  for label in $BACKEND_LABEL $CLIENT_LABEL $TUNNEL_LABEL; do
    plist="$LAUNCH_DIR/${label}.plist"
    if [[ ! -f "$plist" ]]; then
      echo -e "  ${YELLOW}SKIP${NC} $label — plist not installed"
      continue
    fi
    if _is_loaded "$label"; then
      echo -e "  ${GREEN}OK${NC}   $label (already running)"
    else
      launchctl bootstrap "$GUI_DOMAIN" "$plist" 2>/dev/null || true
      echo -e "  ${GREEN}OK${NC}   $label started"
    fi
  done
  sleep 2
  cmd_status
}

cmd_stop() {
  echo -e "${CYAN}Stopping N.O.V.A. services...${NC}"
  for label in $TUNNEL_LABEL $CLIENT_LABEL $BACKEND_LABEL; do
    if _is_loaded "$label"; then
      launchctl bootout "$GUI_DOMAIN/$label" 2>/dev/null || true
      echo -e "  ${RED}STOP${NC} $label"
    else
      echo -e "  ${YELLOW}SKIP${NC} $label (not running)"
    fi
  done
}

cmd_restart() {
  cmd_stop
  sleep 2
  cmd_start
}

cmd_status() {
  echo ""
  echo -e "${BOLD}N.O.V.A. Status${NC}"
  echo -e "────────────────────────────────────"
  echo -e "  Backend   $(_status_icon $BACKEND_LABEL)"
  echo -e "  Client    $(_status_icon $CLIENT_LABEL)"
  echo -e "  Tunnel    $(_status_icon $TUNNEL_LABEL)"
  echo ""

  # Health check
  if curl -sf http://localhost:8080/health -o /dev/null 2>/dev/null; then
    echo -e "  Health    ${GREEN}OK${NC} (http://localhost:8080)"
  else
    echo -e "  Health    ${RED}UNREACHABLE${NC}"
  fi

  # Tunnel URL
  if [[ -f "$NOVA_CONFIG/cloudflared.yml" ]]; then
    tunnel_host=$(grep 'hostname:' "$NOVA_CONFIG/cloudflared.yml" 2>/dev/null | head -1 | awk '{print $2}')
    if [[ -n "$tunnel_host" ]]; then
      echo -e "  Tunnel    ${CYAN}https://${tunnel_host}${NC}"
    fi
  fi

  echo -e "  Logs      $NOVA_LOGS/"
  echo ""
}

cmd_logs() {
  local service="${1:-backend}"
  local logfile="$NOVA_LOGS/${service}.log"
  if [[ ! -f "$logfile" ]]; then
    echo "No log file: $logfile"
    echo "Available: $(ls "$NOVA_LOGS"/*.log 2>/dev/null | xargs -I{} basename {} | tr '\n' ' ')"
    return 1
  fi
  tail -f "$logfile"
}

cmd_update() {
  echo -e "${CYAN}Updating N.O.V.A....${NC}"
  cd "$NOVA_APP"

  git fetch origin main 2>/dev/null
  local_rev=$(git rev-parse HEAD)
  remote_rev=$(git rev-parse origin/main 2>/dev/null || echo "")

  if [[ "$local_rev" == "$remote_rev" ]]; then
    echo -e "  ${GREEN}Already up to date.${NC}"
    return
  fi

  echo -e "  Pulling latest changes..."
  git pull origin main

  echo -e "  Installing dependencies..."
  "$NOVA_VENV/bin/pip" install -q -r backend/requirements.txt
  "$NOVA_VENV/bin/pip" install -q -r client/requirements.txt

  echo -e "  Restarting services..."
  cmd_restart

  echo -e "${GREEN}Update complete.${NC}"
}

cmd_tunnel() {
  if [[ -f "$NOVA_CONFIG/cloudflared.yml" ]]; then
    tunnel_host=$(grep 'hostname:' "$NOVA_CONFIG/cloudflared.yml" 2>/dev/null | head -1 | awk '{print $2}')
    if [[ -n "$tunnel_host" ]]; then
      echo "https://${tunnel_host}"
      return
    fi
  fi
  echo "Tunnel not configured. Run install.sh to set it up."
}

cmd_uninstall() {
  echo -e "${RED}${BOLD}Uninstalling N.O.V.A.${NC}"
  echo ""
  read -p "This will stop services and remove launchd plists. Continue? (y/N) " confirm
  [[ "$confirm" != "y" && "$confirm" != "Y" ]] && exit 0

  cmd_stop

  for label in $BACKEND_LABEL $CLIENT_LABEL $TUNNEL_LABEL; do
    rm -f "$LAUNCH_DIR/${label}.plist"
  done
  echo -e "  ${GREEN}OK${NC} launchd plists removed"

  rm -f /usr/local/bin/nova 2>/dev/null || true
  echo -e "  ${GREEN}OK${NC} nova CLI symlink removed"

  echo ""
  read -p "Also remove ~/.nova (data, venv, logs)? (y/N) " confirm_data
  if [[ "$confirm_data" == "y" || "$confirm_data" == "Y" ]]; then
    rm -rf "$NOVA_HOME"
    echo -e "  ${GREEN}OK${NC} ~/.nova removed"
  else
    echo -e "  ${YELLOW}KEPT${NC} ~/.nova (data preserved)"
  fi

  echo ""
  echo -e "${GREEN}N.O.V.A. uninstalled.${NC}"
}

cmd_help() {
  echo ""
  echo -e "${BOLD}nova${NC} — N.O.V.A. service management"
  echo ""
  echo "Usage: nova <command>"
  echo ""
  echo "Commands:"
  echo "  start       Start all services (backend, client, tunnel)"
  echo "  stop        Stop all services"
  echo "  restart     Restart all services"
  echo "  status      Show service status and health"
  echo "  logs [svc]  Tail logs (backend|client|tunnel, default: backend)"
  echo "  update      Pull latest code and restart"
  echo "  tunnel      Show Cloudflare Tunnel URL"
  echo "  uninstall   Remove services and optionally all data"
  echo ""
}

# ── Main ──
case "${1:-help}" in
  start)     cmd_start ;;
  stop)      cmd_stop ;;
  restart)   cmd_restart ;;
  status)    cmd_status ;;
  logs)      cmd_logs "${2:-backend}" ;;
  update)    cmd_update ;;
  tunnel)    cmd_tunnel ;;
  uninstall) cmd_uninstall ;;
  help|*)    cmd_help ;;
esac
