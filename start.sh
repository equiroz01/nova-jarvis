#!/bin/bash
# NOVA - Quick Start Script

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
ENV_FILE="$SCRIPT_DIR/.env"

echo "========================================="
echo "  NOVA - Starting Up"
echo "========================================="

# Check .env
if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: .env not found. Copy .env.example to .env and add your GEMINI_API_KEY"
  exit 1
fi

# Check if GEMINI_API_KEY is set
if grep -q "PEGA-TU-KEY-AQUI" "$ENV_FILE" 2>/dev/null; then
  echo "ERROR: Edit .env and replace PEGA-TU-KEY-AQUI with your Gemini API key"
  exit 1
fi

# Kill any existing instance
pkill -f "uvicorn app.main:app" 2>/dev/null || true
sleep 1

# Install dependencies if needed
if ! python3.11 -c "import fastapi" 2>/dev/null; then
  echo "Installing dependencies..."
  python3.11 -m pip install -r "$BACKEND_DIR/requirements.txt" -q
fi

# Copy .env to backend dir
cp "$ENV_FILE" "$BACKEND_DIR/.env"

# Export Google Cloud credentials if configured
GCLOUD_CREDS=$(grep "^GOOGLE_APPLICATION_CREDENTIALS=" "$ENV_FILE" 2>/dev/null | cut -d= -f2-)
if [ -n "$GCLOUD_CREDS" ] && [ -f "$GCLOUD_CREDS" ]; then
  export GOOGLE_APPLICATION_CREDENTIALS="$GCLOUD_CREDS"
  echo "GCP credentials loaded"
fi

# Set PYTHONPATH to avoid importing from other projects
export PYTHONPATH="$BACKEND_DIR"

echo ""
echo "Chat:     http://localhost:8080"
echo "Settings: http://localhost:8080/settings"
echo "Press Ctrl+C to stop"
echo "========================================="
echo ""

cd "$BACKEND_DIR"
exec python3.11 -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
