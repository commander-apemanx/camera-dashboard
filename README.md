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

On first visit you are sent to **Setup** / **Login**: create a dashboard password, then sign in to unlock the camera vault.

**Roadmap:** [ROADMAP.md](ROADMAP.md) — alpha status + plans for up to 32 cameras, GPU detection (NVIDIA/AMD/Intel), Areas pages, and more. [Issues](https://github.com/commander-apemanx/camera-dashboard/issues) welcome.

---

## Features

- 2×2 live grid (stable MJPEG slots — streams are not rebuilt on every status poll)
- Add cameras via **RTSP** or **ONVIF** (live probe before save)
- Person boxes via YOLOv8n
- Detection log in the side terminal and in server logs
- Optional detection photos under `Data/`, gallery at `/photos`
- Max **4** cameras (see roadmap for selectable / up to 32)
- **Login page** and encrypted camera credentials (see [Security](#security--login))

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

Open **http://127.0.0.1:5000** — first run opens **Setup** to create your dashboard password.

Optional bind:

```bash
HOST=127.0.0.1 PORT=5000 ./start.sh
```

`./start.sh` creates `.venv` and installs Python deps only when `requirements.txt` changes.

---

## Security & login

The dashboard is password-protected. Camera credentials are **encrypted at rest** — there is **no Docker/env master key**. Your dashboard login password unlocks the vault.

### First run (Setup)

1. Start the app and open the UI  
2. You are redirected to **`/setup`**  
3. Choose a dashboard password (at least 8 characters) and confirm it  
4. That creates `data/auth.json` (password hash + vault salt) and unlocks the vault  

### Later visits (Login)

1. Open the UI → **`/login`**  
2. Enter your dashboard password  
3. The vault unlocks, camera secrets are decrypted in memory, and streams can start  

### What is protected

| Item | How it is stored |
|------|------------------|
| Dashboard password | Argon2 hash in `data/auth.json` (never plaintext) |
| Camera passwords | Encrypted (`password_enc`) in `data/cameras.json` |
| RTSP URLs on disk | Stored **without** `user:pass@` — credentials are injected only in memory after unlock |

Legacy plaintext `cameras.json` from older installs is migrated to encrypted form on first unlock.

### Settings (in the UI)

Open **Settings** on the dashboard:

- **Unlock until reboot** — log out ends your browser session, but the vault can stay unlocked so streams keep running until the app/container restarts  
- **Lock vault now** — wipe secrets from memory, stop streams, return to the login page  
- **Change dashboard password** — re-encrypts all camera secrets under the new password  

### Still important

- Do **not** expose port 5000 to the public internet without a reverse proxy (and preferably TLS)  
- Someone who knows the dashboard password can unlock the vault  
- While unlocked, camera passwords exist in process memory (required for RTSP)  
- Host/root compromise can still read memory — encryption protects **files on disk**, not a fully compromised server  

---

## Add cameras

Sign in first, then use **+ Add Camera Stream**. A camera is saved only if a live frame can be read.

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
| `data/auth.json` | Dashboard password hash + vault salt (**gitignored**) |
| `data/cameras.json` | Camera config with **encrypted** passwords (`password_enc`) — gitignored |
| `data/cameras.example.json` | Empty starter file |
| `data/settings.json` | Photo save on/off, delay, unlock-until-reboot |
| `data/.secret_key` | Flask session secret (gitignored) |
| `Data/` | Person-detection JPEGs (gitignored) |

Those two folder names (`data` / `Data`) differ only by case. Create them from a Linux/Unraid terminal, not from Windows Explorer.

Do not commit `data/auth.json` or `data/cameras.json`. Camera passwords are encrypted on disk, but the files are still private to your install.

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
- Do not publish port 5000 to the public internet without a reverse proxy; the app now has its own login, but that is not a substitute for edge TLS/access control.
- Person detection uses CPU. Four HD main-streams is heavy; a camera **sub-stream** (e.g. Hikvision channel `102`) is easier on the server.
- Camera passwords are **encrypted at rest** and unlocked with the dashboard login password (see [Security & login](#security--login)).

---

## License

This project is licensed under the **GNU General Public License v3.0**. See [LICENSE](LICENSE).
