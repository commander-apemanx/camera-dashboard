#!/usr/bin/env bash
# Build the local-run package tarball (./start.sh workflow).
# Usage: ./scripts/package-local.sh [version]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
  if git describe --tags --exact-match >/dev/null 2>&1; then
    VERSION="$(git describe --tags --exact-match)"
  else
    VERSION="$(git rev-parse --short HEAD)"
  fi
fi
VERSION="${VERSION#v}"
NAME="camera-dashboard-v${VERSION}-local"
OUT_DIR="${OUT_DIR:-$ROOT/dist}"
ARCHIVE="${OUT_DIR}/${NAME}.tar.gz"

mkdir -p "$OUT_DIR"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

STAGE="${TMP}/${NAME}"
mkdir -p "$STAGE/data" "$STAGE/Data" "$STAGE/docker" "$STAGE/static" "$STAGE/templates" "$STAGE/scripts"

copy_file() {
  local src="$1"
  local dst="$2"
  if [[ -e "$src" ]]; then
    cp -a "$src" "$dst"
  fi
}

copy_file app.py "$STAGE/"
copy_file auth_vault.py "$STAGE/"
copy_file requirements.txt "$STAGE/"
copy_file start.sh "$STAGE/"
copy_file LICENSE "$STAGE/"
copy_file README.md "$STAGE/"
copy_file UNRAID-INSTALL.md "$STAGE/"
copy_file Dockerfile "$STAGE/"
copy_file docker-compose.yml "$STAGE/"
copy_file docker-compose.build.yml "$STAGE/"
copy_file yolov8n.pt "$STAGE/"
copy_file data/.gitkeep "$STAGE/data/"
copy_file data/cameras.example.json "$STAGE/data/"
copy_file data/settings.json "$STAGE/data/"
copy_file Data/.gitkeep "$STAGE/Data/"
copy_file docker/entrypoint.sh "$STAGE/docker/"
copy_file docker/build-on-unraid.sh "$STAGE/docker/"
copy_file scripts/package-local.sh "$STAGE/scripts/"

cp -a static/. "$STAGE/static/"
cp -a templates/. "$STAGE/templates/"
if [[ -d unraid ]]; then
  mkdir -p "$STAGE/unraid"
  cp -a unraid/. "$STAGE/unraid/"
fi

chmod +x "$STAGE/start.sh" "$STAGE/docker/"*.sh "$STAGE/scripts/"*.sh 2>/dev/null || true

# Starter note inside the package
cat > "$STAGE/INSTALL.txt" <<EOF
Camera Dashboard — local package (v${VERSION})

1. Extract this archive
2. cd ${NAME}
3. chmod +x start.sh
4. ./start.sh
5. Open http://127.0.0.1:5000

Optional: copy data/cameras.example.json to data/cameras.json
(or add cameras in the UI).

Docker users: prefer the published image —
  ghcr.io/commander-apemanx/camera-dashboard:v${VERSION}
  with docker-compose.yml
EOF

tar -C "$TMP" -czf "$ARCHIVE" "$NAME"
ls -lh "$ARCHIVE" >&2
# stdout must be only the archive path (used by CI)
echo "$ARCHIVE"
