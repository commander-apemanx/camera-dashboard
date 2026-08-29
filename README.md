# Camera Dashboard
<img width="692" height="190" alt="image" src="https://github.com/user-attachments/assets/836c80d2-402c-479e-84a2-a4b443624af3" />

<img width="725" height="152" alt="image" src="https://github.com/user-attachments/assets/89333a77-6a79-4505-8a55-34a80eb83918" />

<img width="274" height="98" alt="image" src="https://github.com/user-attachments/assets/37f53e5a-7886-4230-9926-0eee22286c8d" />

<img width="727" height="214" alt="image" src="https://github.com/user-attachments/assets/0d8b8ba8-35ef-4e42-9c1b-245b4d07d67e" />



Private four-camera **RTSP / ONVIF** dashboard with **YOLOv8 person detection**, a live detection terminal, and optional snapshot saving.

Built to run on a home Linux box or an **Unraid** server. The Docker image is built locally — nothing is pushed to Docker Hub.

Open **http://127.0.0.1:5000** (local) or **http://UNRAID-IP:5000** (Docker / Unraid).

---

## Features

- 2×2 live grid (stable MJPEG slots — streams are not rebuilt on every status poll)
- Add cameras via **RTSP** or **ONVIF** (live probe before save)
- Person boxes via YOLOv8n
- Detection log in the side terminal and in server logs
- Optional detection photos under `Data/`, gallery at `/photos`
- Max **4** cameras

---

## Requirements

- Linux (or Unraid with Docker)
- Python 3.10+ for `./start.sh`, **or** Docker for compose
- Network access to your cameras
- First image/app start needs `yolov8n.pt` (~6 MB; included in this folder when present, otherwise downloaded)

---

## Quick start (Linux, no Docker)

```bash
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

## Docker Compose

From this project folder (Linux or Unraid):

```bash
# First run: build the local image, then start
docker compose up -d --build

docker compose logs -f
```

UI: **http://127.0.0.1:5000** on a PC, or **http://UNRAID-IP:5000** on Unraid.

Stop / restart:

```bash
docker compose down
docker compose up -d
```

Defaults in `docker-compose.yml`:

| Setting | Value |
|---------|--------|
| Image | `camera-dashboard:local` (built here, never pulled) |
| Network | **host** (best for LAN cameras) |
| Port | `5000` |
| Config volume | `./data` → `/app/data` |
| Photos volume | `./Data` → `/app/Data` |
| Restart | `unless-stopped` |

The compose file sets `pull_policy: never` so Docker will not look up `camera-dashboard` on Docker Hub.

### Environment

| Variable | Default | Meaning |
|----------|---------|---------|
| `HOST` | `0.0.0.0` in Docker, `127.0.0.1` in `./start.sh` | Bind address |
| `PORT` | `5000` | Listen port |
| `TZ` | `Europe/Amsterdam` | Container timezone (photo timestamps) |
| `OPENCV_FFMPEG_CAPTURE_OPTIONS` | TCP RTSP + low-latency flags | FFmpeg capture options |
| `SECRET_KEY` | auto-written to `data/.secret_key` | Flask secret |

---

## Unraid

This project is packaged for a **private Unraid server**. Full copy / build / template / plugin steps:

**[UNRAID-INSTALL.md](UNRAID-INSTALL.md)** — Unraid README + install guide

Short path:

```bash
# copy this folder to Unraid, then SSH:
cd /mnt/user/appdata/camera-dashboard
chmod +x docker/build-on-unraid.sh docker/entrypoint.sh start.sh
./docker/build-on-unraid.sh
docker compose up -d
# UI: http://UNRAID-IP:5000
```

| File | Role |
|------|------|
| `Dockerfile` | Local image build |
| `docker-compose.yml` | Host network + volume mounts |
| `docker/build-on-unraid.sh` | Build helper |
| `docker/entrypoint.sh` | Container start |
| `unraid/my-CameraDashboard.xml` | Unraid **Add Container** template |

---

## Notes

- Local `./start.sh` binds to **localhost** (`127.0.0.1`) by default.
- Docker / Unraid binds to **`0.0.0.0:5000`** so other devices on the LAN can open the UI.
- Do not publish port 5000 to the public internet without a reverse proxy and auth.
- Person detection uses CPU. Four HD main-streams is heavy; a camera **sub-stream** (e.g. Hikvision channel `102`) is easier on the server.
- Passwords are stored in `data/cameras.json`.
