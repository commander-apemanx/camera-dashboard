#!/usr/bin/env bash
set -euo pipefail

cd /app

mkdir -p /app/data /app/Data

export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-5000}"
export OPENCV_FFMPEG_CAPTURE_OPTIONS="${OPENCV_FFMPEG_CAPTURE_OPTIONS:-rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|max_delay;500000|stimeout;5000000}"

echo "========================================"
echo "  Camera Dashboard (Docker)"
echo "  http://${HOST}:${PORT}"
echo "  data   -> /app/data"
echo "  photos -> /app/Data"
echo "========================================"

exec python /app/app.py
