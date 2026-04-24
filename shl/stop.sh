#!/usr/bin/env bash
# Stop the Streamlit app started by start.sh.
# Usage: ./shl/stop.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PID_FILE="${KRX_PID_FILE:-.krx.pid}"
STOP_TIMEOUT="${KRX_STOP_TIMEOUT:-15}"

if [ ! -f "$PID_FILE" ]; then
  echo "[stop] no pid file ($PID_FILE) — nothing to stop"
  exit 0
fi

pid=$(cat "$PID_FILE")
if ! kill -0 "$pid" 2>/dev/null; then
  echo "[stop] pid $pid not running — cleaning up stale pid file"
  rm -f "$PID_FILE"
  exit 0
fi

echo "[stop] sending SIGTERM to pid $pid ..."
kill "$pid"

# Wait up to STOP_TIMEOUT seconds for graceful shutdown.
waited=0
while kill -0 "$pid" 2>/dev/null; do
  if [ "$waited" -ge "$STOP_TIMEOUT" ]; then
    echo "[stop] timeout — sending SIGKILL"
    kill -9 "$pid" 2>/dev/null || true
    break
  fi
  sleep 1
  waited=$((waited + 1))
done

rm -f "$PID_FILE"
echo "[stop] done."
