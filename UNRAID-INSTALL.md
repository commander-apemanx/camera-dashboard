# Camera Dashboard — Unraid README & install

This file is the Unraid README: what the package is, which files matter, and how to install it on **your own Unraid server**.

The Docker image is built **on the Unraid host**.  
**Nothing is pushed** to Docker Hub or any other registry.

Web UI after install: `http://<UNRAID-IP>:5000`

---

## README (Unraid package)

### What this is

A four-camera RTSP/ONVIF dashboard with YOLOv8 person detection, a live detection log, and optional JPEG snapshots.

It is meant to stay private on your LAN. You copy the project to Unraid, build `camera-dashboard:local`, and start it with Docker Compose (recommended) or the Unraid Docker UI.

### Files that matter on Unraid

| File | Purpose |
|------|---------|
| `Dockerfile` | Builds the local image `camera-dashboard:local` |
| `docker-compose.yml` | Recommended run method: host network + volume mounts |
| `docker/build-on-unraid.sh` | One-shot `docker build` from SSH |
| `docker/entrypoint.sh` | Starts the app inside the container |
| `unraid/my-CameraDashboard.xml` | Optional Unraid **Add Container** template |
| `app.py` | Application |
| `requirements.txt` | Python dependencies (installed **at image build**) |
| `yolov8n.pt` | YOLO weights (optional in the copy; speeds first start) |
| `static/`, `templates/` | Web UI |

Do **not** copy a PC `.venv` folder to Unraid. The image installs its own packages.

### Persistent data (bind mounts)

These live on the Unraid share, not inside the image:

| Host path | Container path | Contents |
|-----------|----------------|----------|
| `/mnt/user/appdata/camera-dashboard/data` | `/app/data` | `cameras.json`, `settings.json`, `.secret_key` |
| `/mnt/user/appdata/camera-dashboard/Data` | `/app/Data` | Person-detection photos |

`data` and `Data` are different folders (Linux is case-sensitive). Create them with SSH/`mkdir`, not Windows Explorer over SMB, or they can collapse into one folder.

Camera passwords stay in `data/cameras.json` on the share. Do not bake credentials into the image.

### What you should see after a good install

- Container name: `camera-dashboard`
- Image: `camera-dashboard:local`
- Port: **5000** on the Unraid host (host networking)
- UI loads at `http://<UNRAID-IP>:5000`
- `curl -s http://127.0.0.1:5000/api/health` from Unraid returns `"ok": true`

First start can take a minute while YOLO loads. The compose healthcheck allows up to two minutes before it is considered unhealthy.

---

## Install on Unraid

Pick **one** run method after the copy + build. Compose (Method A) is the one to use unless you already live in the Unraid Docker template UI.

### Requirements

- Unraid with **Docker** enabled
- SSH or the Unraid web terminal
- Several GB free for the image (PyTorch/YOLO; often ~3–6 GB)
- Cameras reachable from the Unraid host (`ping` the camera IPs from Unraid)
- Port **5000** free on Unraid (or change `PORT` everywhere)

Optional: **Compose Manager** plugin from Community Applications if you prefer a UI over SSH for compose.

---

### Step 1 — Copy the project to Unraid

Target folder:

```text
/mnt/user/appdata/camera-dashboard/
```

**From a Linux/Mac PC (SCP):**

```bash
ssh root@UNRAID-IP "mkdir -p /mnt/user/appdata/camera-dashboard"
scp -r "/path/to/Camera Dashboard/." root@UNRAID-IP:/mnt/user/appdata/camera-dashboard/
```

**Or** copy via the Unraid `appdata` SMB share in your file manager.

Recommended layout after copy:

```text
/mnt/user/appdata/camera-dashboard/
  app.py
  Dockerfile
  docker-compose.yml
  requirements.txt
  yolov8n.pt          (optional, speeds first start)
  start.sh
  static/
  templates/
  docker/
  unraid/
  data/               (config — created if missing)
  Data/               (photos — created if missing)
```

Create the runtime folders from the Unraid terminal:

```bash
mkdir -p /mnt/user/appdata/camera-dashboard/data
mkdir -p /mnt/user/appdata/camera-dashboard/Data
chmod +x /mnt/user/appdata/camera-dashboard/docker/build-on-unraid.sh \
         /mnt/user/appdata/camera-dashboard/docker/entrypoint.sh \
         /mnt/user/appdata/camera-dashboard/start.sh
```

If you already have a working `data/cameras.json` from a PC install, copy that file into the Unraid `data/` folder.

---

### Step 2 — Get the Docker image (pick one)

#### Option A — Pull the published package (recommended)

No local build. Uses GitHub Container Registry:

```bash
ssh root@UNRAID-IP
cd /mnt/user/appdata/camera-dashboard
# ensure docker-compose.yml is the published one from this repo
docker compose pull
```

Image: `ghcr.io/commander-apemanx/camera-dashboard:latest` (or set `CAMERA_DASHBOARD_TAG=v1.0.2`).

#### Option B — Build the local image on Unraid

```bash
ssh root@UNRAID-IP
cd /mnt/user/appdata/camera-dashboard
./docker/build-on-unraid.sh
# or:
docker compose -f docker-compose.build.yml build
```

The first build downloads Python wheels and can take a long time. When it finishes:

```bash
docker images | grep camera-dashboard
```

You should see either `ghcr.io/commander-apemanx/camera-dashboard` or `camera-dashboard:local`.

`docker-compose.yml` sets `pull_policy: never` so Compose will **not** try to download this name from Docker Hub.

---

### Step 3 — Run (choose one method)

#### Method A — Docker Compose (recommended)

From the project folder on Unraid:

```bash
cd /mnt/user/appdata/camera-dashboard
docker compose up -d          # pulls ghcr.io/commander-apemanx/camera-dashboard
docker compose logs -f
```

Build on the host instead of pulling:

```bash
docker compose -f docker-compose.build.yml up -d --build
```

If Unraid only has the old binary:

```bash
docker-compose up -d
```

Stop / restart:

```bash
cd /mnt/user/appdata/camera-dashboard
docker compose down
docker compose up -d
```

Compose defaults (`docker-compose.yml`):

- Image: `ghcr.io/commander-apemanx/camera-dashboard:latest`
- Network: **host** (container uses the Unraid LAN stack — this is what RTSP needs)
- Port: **5000**
- Volumes: `./data` → `/app/data`, `./Data` → `/app/Data`
- Restart: `unless-stopped`
- Logs rotated at 10 MB × 3 files

Open:

```text
http://UNRAID-IP:5000
```

---

#### Method B — Unraid Compose Manager plugin

1. Install **Compose Manager** from Community Applications (if needed).
2. Create a stack / project whose **compose directory** is:

   ```text
   /mnt/user/appdata/camera-dashboard
   ```

   Relative volume paths in `docker-compose.yml` (`./data`, `./Data`) only work if that directory is the compose project folder. Do not point the plugin at a different empty folder and paste the YAML there without also copying the Dockerfile and source.

3. Build once (SSH `./docker/build-on-unraid.sh`, or the plugin **Compose Up** with build).
4. Start the stack. UI: `http://UNRAID-IP:5000`.

---

#### Method C — Unraid Docker UI + template XML

1. Finish **Step 2** (image must exist).
2. Install the template:

```bash
mkdir -p /boot/config/plugins/dockerMan/templates-user
cp /mnt/user/appdata/camera-dashboard/unraid/my-CameraDashboard.xml \
   /boot/config/plugins/dockerMan/templates-user/
```

3. Unraid Web UI → **Docker** → **Add Container**
4. Template dropdown → **CameraDashboard** (sometimes listed as `my-CameraDashboard`)
5. Confirm:

| Setting | Value |
|---------|--------|
| Repository | `camera-dashboard:local` |
| Network Type | `Host` |
| App Config | `/mnt/user/appdata/camera-dashboard/data` → `/app/data` |
| Detection Photos | `/mnt/user/appdata/camera-dashboard/Data` → `/app/Data` |
| PORT | `5000` |
| TZ | e.g. `Europe/Amsterdam` |

6. Apply / Start
7. Open `http://UNRAID-IP:5000`

If the template does not appear: **Add Container** manually with repository `camera-dashboard:local`, network **Host**, and the two path binds above. Do not set a Docker Hub registry.

---

#### Method D — Plain `docker run`

```bash
docker run -d \
  --name camera-dashboard \
  --network host \
  --restart unless-stopped \
  --init \
  -e HOST=0.0.0.0 \
  -e PORT=5000 \
  -e TZ=Europe/Amsterdam \
  -e OPENCV_FFMPEG_CAPTURE_OPTIONS='rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|max_delay;500000|stimeout;5000000' \
  -v /mnt/user/appdata/camera-dashboard/data:/app/data \
  -v /mnt/user/appdata/camera-dashboard/Data:/app/Data \
  camera-dashboard:local
```

---

### Step 4 — Use the dashboard

1. Open `http://UNRAID-IP:5000` from a browser on your LAN.
2. Wait until the badge shows **YOLO ready** (first boot can take a while).
3. **+ Add Camera Stream** — RTSP or ONVIF — then **Test Connection** / **Add Stream**.
4. Toggle **Save photos** and **Delay** if you want detection JPEGs.
5. **Detection Photos** (`/photos`) lists files in `Data/`.

On disk:

```text
/mnt/user/appdata/camera-dashboard/Data/          photos
/mnt/user/appdata/camera-dashboard/data/cameras.json
/mnt/user/appdata/camera-dashboard/data/settings.json
```

---

## Network notes (cameras)

### Why host network?

Unraid and LAN IP cameras work most reliably with:

```yaml
network_mode: host
```

The container then uses Unraid’s network, so `192.168.x.x` RTSP URLs work the same as they do from the Unraid terminal.

With host mode, Compose `ports:` mappings are ignored. `PORT=5000` is the real listen port.

### Bridge mode

Only if you cannot use host networking. In `docker-compose.yml`:

1. Remove `network_mode: host`
2. Uncomment / add:

```yaml
ports:
  - "5000:5000"
```

3. `docker compose up -d`

On a flat home LAN this is often still fine. Host mode is still the default for a reason.

### Camera URL tips

- RTSP is usually port `554`
- ONVIF HTTP is often `80` or `8080`
- If Unraid CPU is high, add the camera **sub-stream** (example: Hikvision `/Streaming/Channels/102`) instead of the main 1080p/1440p stream

---

## Updating after code changes

Copy changed files to `/mnt/user/appdata/camera-dashboard/`, then:

```bash
cd /mnt/user/appdata/camera-dashboard
docker compose build --no-cache
docker compose up -d
```

Or:

```bash
./docker/build-on-unraid.sh
docker compose up -d
```

`data/` and `Data/` are bind mounts and are **not** wiped by a rebuild.

---

## Backup

Backup at least:

```text
/mnt/user/appdata/camera-dashboard/data
/mnt/user/appdata/camera-dashboard/Data
```

Also keep a copy of the project source if you want to rebuild later without the original PC folder.

---

## Uninstall

```bash
cd /mnt/user/appdata/camera-dashboard
docker compose down
docker rmi camera-dashboard:local
```

If you used Method C (template UI): Docker tab → stop / remove the container, then remove the image.

Delete appdata only if you also want config and photos gone:

```bash
rm -rf /mnt/user/appdata/camera-dashboard
```

---

## Troubleshooting

| Problem | What to try |
|---------|-------------|
| Page not loading | `docker ps`, `docker logs camera-dashboard`, confirm port 5000 is free (`ss -ltnp \| grep 5000`) |
| `pull access denied` / compose tries Docker Hub | Image must be local. Rebuild, keep `pull_policy: never`, do not add a registry URL |
| `pull_policy` rejected by old Compose | Delete that line in `docker-compose.yml` and run `docker compose up -d --build` |
| Build fails / no space | Free Unraid docker image disk (often the cache pool) |
| Cameras work on a PC but not in the container | Use **host** network; `ping` the camera IP from Unraid |
| RTSP fail | Path, user, password; try ONVIF; cameras must allow TCP RTSP |
| YOLO never ready | `docker logs camera-dashboard` — first load is slow; image must include/build weights |
| Photos not saving | Toggle **Save photos** ON; `Data/` must exist and be writable |
| `data` and `Data` mixed together | Recreate both with `mkdir` over SSH; SMB from Windows can smash case |
| Template missing | Copy XML to `/boot/config/plugins/dockerMan/templates-user/` and refresh Docker |

Logs:

```bash
docker logs -f camera-dashboard
# or
docker compose -f /mnt/user/appdata/camera-dashboard/docker-compose.yml logs -f
```

Health:

```bash
curl -s http://127.0.0.1:5000/api/health
```

A healthy process looks like:

```json
{"ok": true, "detector_ready": true, "camera_count": 0}
```

`detector_ready` may stay `false` for a short time after start.

---

## Security (home / LAN)

- Docker binds `0.0.0.0:5000` so phones/PCs on the LAN can open the UI via the Unraid IP.
- Camera passwords sit in `data/cameras.json` on the appdata share — limit who can read that share.
- Do not forward port 5000 from the internet without a reverse proxy and authentication.
- This setup is intentionally **not** published to any Docker repository.

---

## Quick checklist

1. Copy project → `/mnt/user/appdata/camera-dashboard/`
2. `mkdir -p data Data` and `chmod +x docker/*.sh`
3. `./docker/build-on-unraid.sh`  (or `docker compose up -d --build`)
4. `docker compose up -d`
5. Open `http://UNRAID-IP:5000`
6. Wait for **YOLO ready**, then add cameras
