#!/usr/bin/env bash
# Offline install — QA / prod (RHEL 8, air-gapped). Installs Python deps
# from local wheels only, then runs Alembic migrations against SQLite.
#
# Expects the release tarball to have been extracted so that:
#   - wheels/            pre-downloaded wheels (manylinux2014_x86_64, cp311)
#   - requirements.lock  fully pinned dependency list
#   - alembic/           DB migrations
#   - krx_parser/, app/  package sources
#
# Re-running is safe: pip install is idempotent. Pass KRX_FORCE=1 to wipe
# and recreate .venv from scratch (useful when pinning changed).
#
# Usage:   ./shl/install.sh
#   or:    KRX_FORCE=1 ./shl/install.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VENV_DIR=".venv"
PYTHON_BIN="${KRX_PYTHON:-python3.11}"
WHEELS_DIR="${KRX_WHEELS_DIR:-wheels}"
REQ_FILE="${KRX_REQ_FILE:-requirements.lock}"
FORCE="${KRX_FORCE:-0}"

echo "[install] project root: $ROOT"
echo "[install] python: $PYTHON_BIN"
echo "[install] wheels: $WHEELS_DIR"
echo "[install] reqs:   $REQ_FILE"

if [ ! -d "$WHEELS_DIR" ]; then
  echo "[install] ERROR: $WHEELS_DIR not found — must be shipped in the release tarball" >&2
  exit 1
fi
if [ ! -f "$REQ_FILE" ]; then
  echo "[install] ERROR: $REQ_FILE not found" >&2
  exit 1
fi

if [ -d "$VENV_DIR" ] && [ "$FORCE" = "1" ]; then
  echo "[install] KRX_FORCE=1 set — removing existing $VENV_DIR"
  rm -rf "$VENV_DIR"
fi

if [ ! -d "$VENV_DIR" ]; then
  echo "[install] creating $VENV_DIR ..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "[install] pip install (offline, --no-index) ..."
pip install --no-index --find-links="$WHEELS_DIR" --upgrade pip
pip install --no-index --find-links="$WHEELS_DIR" -r "$REQ_FILE"

mkdir -p data
echo "[install] running alembic migrations (SQLite: data/krx.db) ..."
if [ -d alembic ]; then
  alembic upgrade head
else
  echo "[install] (alembic dir not present — skipping migrations)"
fi

echo "[install] done."
