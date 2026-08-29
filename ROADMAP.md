# Roadmap

Plans and direction for Camera Dashboard. Status here is intentional, not a promise of dates.

**User ideas and requests are welcome.** Open a [GitHub Issue](https://github.com/commander-apemanx/camera-dashboard/issues) (feature request or discussion). Useful reports include what you want, why, and roughly how many cameras / what hardware you run.

---

## Current (v1.x)

- Up to **4** cameras in a 2×2 live grid
- RTSP / ONVIF add flow with live probe
- YOLOv8 person detection, detection terminal, optional snapshots
- Docker Compose package (GHCR) and local `./start.sh` package
- GNU GPLv3

---

## Near term

### More cameras (selectable, up to 32)

Today the hard limit is four. The goal is a **configurable camera count** — choose how many you need, up to **32**.

Likely work:

- Replace the fixed 2×2 grid with a layout that scales (e.g. 3×3, 4×4, or auto)
- Per-install max (or UI selector) instead of a single compile-time `MAX_CAMERAS = 4`
- Keep multi-stream MJPEG stable under higher load (slot reuse, lower preview FPS, sub-stream defaults)
- Document CPU/RAM expectations as camera count grows

### Local encryption

Protect sensitive data **on disk** when the app stores it locally:

- Encrypt `data/cameras.json` (credentials) at rest
- Encrypt or protect detection photos under `Data/` where practical
- Clear unlock / key setup flow for Docker and `./start.sh` (no cloud key service required)
- Document backup and key recovery so a lost key does not silently brick a install

### Security-focused hardening

Treat the dashboard as a **LAN security appliance**, not a casual toy UI:

- Optional login / session auth before the UI and streams
- Safer defaults for bind address, headers, and secret handling
- Review password storage and API surfaces (streams, settings, deletes)
- Guidance for reverse proxy + TLS when exposing beyond the home LAN
- Keep credentials and keys out of images, logs, and git (continue current gitignore discipline)

---

## Later / explore

- Round-robin or lighter detection to keep many cameras usable on modest CPUs
- Prefer camera sub-streams for live view; full stream only when needed
- Role-friendly Unraid / Docker defaults for encrypted data volumes
- Export / import of camera config (encrypted)

---

## Out of scope (for now)

- Cloud account / SaaS control plane
- Replacing a full NVR (Frigate, etc.) — this stays a focused live dashboard + detection helper

---

## How to contribute an idea

1. Search [existing issues](https://github.com/commander-apemanx/camera-dashboard/issues) first  
2. Open a new issue with label ideas like `enhancement` or `security`  
3. Say whether it helps **many cameras**, **encryption**, or **security** so we can place it on this roadmap  

License remains **GNU GPLv3** — see [LICENSE](LICENSE).
