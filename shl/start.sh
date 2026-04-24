#!/usr/bin/env bash
# Start the Streamlit app in the background, write pid file.
# Usage: ./shl/start.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VENV_DIR=".venv"
APP_ENTRY="${KRX_APP_ENTRY:-app/main.py}"
PORT="${KRX_PORT:-8501}"
HOST="${KRX_HOST:-0.0.0.0}"
LOG_DIR="${KRX_LOG_DIR:-logs}"
PID_FILE="${KRX_PID_FILE:-.krx.pid}"

if [ ! -d "$VENV_DIR" ]; then
  echo "[start] ERROR: $VENV_DIR not found — run install_qa.sh or install_prod.sh first" >&2
  exit 1
fi
if [ ! -f "$APP_ENTRY" ]; then
  echo "[start] ERROR: $APP_ENTRY not found" >&2
  exit 1
fi

if [ -f "$PID_FILE" ]; then
  existing_pid=$(cat "$PID_FILE")
  if kill -0 "$existing_pid" 2>/dev/null; then
    echo "[start] already running (pid=$existing_pid) — run stop.sh first" >&2
    exit 1
  fi
  rm -f "$PID_FILE"
fi

mkdir -p "$LOG_DIR"

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# Offline/air-gapped requirement: no telemetry, no CDN fetches.
export STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

echo "[start] launching streamlit on $HOST:$PORT ..."
nohup streamlit run "$APP_ENTRY" \
  --server.address "$HOST" \
  --server.port "$PORT" \
  --server.headless true \
  >> "$LOG_DIR/app.log" 2>&1 &

echo $! > "$PID_FILE"
echo "[start] pid=$(cat "$PID_FILE"), logs=$LOG_DIR/app.log"
