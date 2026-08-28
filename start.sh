#!/usr/bin/env bash
# Camera Dashboard launcher (Linux)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-5000}"
VENV="$ROOT/.venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "========================================"
echo "  Camera Dashboard"
echo "  http://${HOST}:${PORT}"
echo "========================================"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Error: python3 not found. Install Python 3.10+."
  exit 1
fi

# System packages hint (OpenCV / torch wheels usually enough)
if [[ ! -d "$VENV" ]]; then
  echo "[*] Creating virtual environment…"
  "$PYTHON_BIN" -m venv "$VENV"
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"

REQ_STAMP="$VENV/.requirements.sha"
REQ_HASH="$(python -c "import hashlib, pathlib; print(hashlib.sha256(pathlib.Path(r'$ROOT/requirements.txt').read_bytes()).hexdigest())")"
if [[ "$(cat "$REQ_STAMP" 2>/dev/null || true)" != "$REQ_HASH" ]]; then
  echo "[*] Installing Python dependencies (first run may take a few minutes)…"
  pip install --upgrade pip wheel setuptools >/dev/null
  pip install -r "$ROOT/requirements.txt"
  printf '%s\n' "$REQ_HASH" > "$REQ_STAMP"
else
  echo "[*] Dependencies already installed."
fi

mkdir -p "$ROOT/data" "$ROOT/Data" "$ROOT/static" "$ROOT/templates"

export HOST PORT
export OPENCV_FFMPEG_CAPTURE_OPTIONS="${OPENCV_FFMPEG_CAPTURE_OPTIONS:-rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|max_delay;500000|stimeout;5000000}"

echo "[*] Starting server…"
echo "    Person detections also print in this terminal."
echo "    Press Ctrl+C to stop."
echo

exec python "$ROOT/app.py"
