#!/usr/bin/env bash
# Run this ON the Unraid server (SSH), from the project folder.
# Builds a local image only — does not push anywhere.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

IMAGE_NAME="${IMAGE_NAME:-camera-dashboard:local}"

echo "[*] Project: $ROOT"
echo "[*] Building image: $IMAGE_NAME"
echo "    (first build downloads PyTorch/Ultralytics wheels — can take a while)"
echo

docker build -t "$IMAGE_NAME" -f Dockerfile .

echo
echo "[OK] Image ready: $IMAGE_NAME"
echo
echo "Next (from $ROOT):"
echo "  A) docker compose up -d"
echo "     (first time you can also: docker compose up -d --build)"
echo "  B) Unraid Docker UI + unraid/my-CameraDashboard.xml"
echo "  See UNRAID-INSTALL.md"
echo "  Web UI: http://<UNRAID-IP>:5000"
