# Camera Dashboard
<img width="692" height="190" alt="image" src="https://github.com/user-attachments/assets/836c80d2-402c-479e-84a2-a4b443624af3" />

<img width="725" height="152" alt="image" src="https://github.com/user-attachments/assets/89333a77-6a79-4505-8a55-34a80eb83918" />

<img width="274" height="98" alt="image" src="https://github.com/user-attachments/assets/37f53e5a-7886-4230-9926-0eee22286c8d" />

<img width="727" height="214" alt="image" src="https://github.com/user-attachments/assets/0d8b8ba8-35ef-4e42-9c1b-245b4d07d67e" />



Four-camera **RTSP / ONVIF** dashboard with **YOLOv8 person detection**, a live detection terminal, and optional snapshot saving.

Runs on a home Linux box or **Unraid**. Two published packages are available on each release:

| Package | What it is | Install |
|---------|------------|---------|
| **Docker Compose** | Pre-built image on GHCR | `docker compose up -d` with `docker-compose.yml` |
| **Local `.sh`** | Source tarball + `./start.sh` | Download release asset, extract, run `./start.sh` |

Image: `ghcr.io/commander-apemanx/camera-dashboard`  
Releases: https://github.com/commander-apemanx/camera-dashboard/releases

Open **http://127.0.0.1:5000** (local) or **http://UNRAID-IP:5000** (Docker / Unraid).

**Roadmap:** [ROADMAP.md](ROADMAP.md) — alpha status + plans for up to 32 cameras, GPU detection (NVIDIA/AMD/Intel), local encryption, and security. [Issues](https://github.com/commander-apemanx/camera-dashboard/issues) welcome.

---

## Features

- 2×2 live grid (stable MJPEG slots — streams are not rebuilt on every status poll)
- Add cameras via **RTSP** or **ONVIF** (live probe before save)
- Person boxes via YOLOv8n
- Detection log in the side terminal and in server logs
- Optional detection photos under `Data/`, gallery at `/photos`
- Max **4** cameras (see roadmap for selectable / up to 32)

---

## Requirements

- Linux (or Unraid with Docker)
- Python 3.10+ for `./start.sh`, **or** Docker for compose
- Network access to your cameras
- First image/app start needs `yolov8n.pt` (~6 MB; included in this folder when present, otherwise downloaded)

---

## Package 1 — Docker Compose (published image)

Pulls `ghcr.io/commander-apemanx/camera-dashboard` — no local image build.

```bash
mkdir -p camera-dashboard/data camera-dashboard/Data
cd camera-dashboard
curl -fsSL -o docker-compose.yml \
  https://raw.githubusercontent.com/commander-apemanx/camera-dashboard/main/docker-compose.yml
docker compose up -d
docker compose logs -f
```

Pin a release tag:

```bash
CAMERA_DASHBOARD_TAG=v1.0.2 docker compose up -d
```

UI: **http://127.0.0.1:5000** or **http://UNRAID-IP:5000**

Stop / restart:

```bash
docker compose down
docker compose up -d
```

| Setting | Value |
|---------|--------|
| Image | `ghcr.io/commander-apemanx/camera-dashboard:latest` (or a `v*` tag) |
| Network | **host** (best for LAN cameras) |
| Port | `5000` |
| Config volume | `./data` → `/app/data` |
| Photos volume | `./Data` → `/app/Data` |

To **build locally** instead of pulling: `docker compose -f docker-compose.build.yml up -d --build`

### Environment

| Variable | Default | Meaning |
|----------|---------|---------|
| `HOST` | `0.0.0.0` in Docker, `127.0.0.1` in `./start.sh` | Bind address |
| `PORT` | `5000` | Listen port |
| `TZ` | `Europe/Amsterdam` | Container timezone (photo timestamps) |
| `OPENCV_FFMPEG_CAPTURE_OPTIONS` | TCP RTSP + low-latency flags | FFmpeg capture options |
| `SECRET_KEY` | auto-written to `data/.secret_key` | Flask secret |
| `CAMERA_DASHBOARD_TAG` | `latest` | Image tag for Compose |

---

## Package 2 — Local run (`./start.sh`)

### From a release asset (recommended)

1. Open [Releases](https://github.com/commander-apemanx/camera-dashboard/releases)
2. Download `camera-dashboard-vX.Y.Z-local.tar.gz`
3. Extract and start:

```bash
tar -xzf camera-dashboard-v1.0.2-local.tar.gz
cd camera-dashboard-v1.0.2-local
chmod +x start.sh
./start.sh
```

### From a git clone

```bash
git clone https://github.com/commander-apemanx/camera-dashboard.git
cd camera-dashboard
chmod +x start.sh
./start.sh
```

Open **http://127.0.0.1:5000**

Optional bind:

```bash
HOST=127.0.0.1 PORT=5000 ./start.sh
```

`./start.sh` creates `.venv` and installs Python deps only when `requirements.txt` changes.

---

## Add cameras

Use **+ Add Camera Stream**. A camera is saved only if a live frame can be read.

### RTSP

| Field    | Example                    |
|----------|----------------------------|
| IP       | `192.168.1.64`             |
| Port     | `554`                      |
| Username | `admin`                    |
| Password | your camera password       |
| Path     | `/stream1`                 |

Built URL: `rtsp://user:pass@ip:port/path`

### ONVIF

| Field    | Example        |
|----------|----------------|
| IP       | `192.168.1.64` |
| Port     | `80` (or 8080) |
| Username | `admin`        |
| Password | camera pass    |

ONVIF discovers the RTSP URI, then the same live probe runs.

**Test Connection** and **Add Stream** both show ✓ SUCCESS or ✗ FAIL.

---

## Data on disk

| Path | Contents |
|------|----------|
| `data/cameras.json` | Camera config (includes passwords — **gitignored**, keep private) |
| `data/cameras.example.json` | Empty starter file you can copy to `cameras.json` |
| `data/settings.json` | Photo save on/off and delay |
| `Data/` | Person-detection JPEGs (gitignored) |

Those two folder names differ only by case. Create them from a Linux/Unraid terminal, not from Windows Explorer.

Do not commit `data/cameras.json`. It holds camera passwords.

---

## Unraid

Full Unraid guide: **[UNRAID-INSTALL.md](UNRAID-INSTALL.md)**

**Fast path (published Docker package):**

```bash
mkdir -p /mnt/user/appdata/camera-dashboard/{data,Data}
cd /mnt/user/appdata/camera-dashboard
curl -fsSL -o docker-compose.yml \
  https://raw.githubusercontent.com/commander-apemanx/camera-dashboard/main/docker-compose.yml
docker compose up -d
# UI: http://UNRAID-IP:5000
```

| File | Role |
|------|------|
| `docker-compose.yml` | Pull published GHCR image |
| `docker-compose.build.yml` | Build image on the Unraid host |
| `Dockerfile` | Image definition |
| `docker/build-on-unraid.sh` | Local build helper |
| `docker/entrypoint.sh` | Container start |
| `unraid/my-CameraDashboard.xml` | Unraid **Add Container** template |

---

## Notes

- Local `./start.sh` binds to **localhost** (`127.0.0.1`) by default.
- Docker / Unraid binds to **`0.0.0.0:5000`** so other devices on the LAN can open the UI.
- Do not publish port 5000 to the public internet without a reverse proxy and auth.
- Person detection uses CPU. Four HD main-streams is heavy; a camera **sub-stream** (e.g. Hikvision channel `102`) is easier on the server.
- Passwords are stored in `data/cameras.json`.

---

## License

This project is licensed under the **GNU General Public License v3.0**. See [LICENSE](LICENSE).
