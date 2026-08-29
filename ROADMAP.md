# Roadmap

Plans and direction for Camera Dashboard. Status here is intentional, not a promise of dates.

**User ideas and requests are welcome.** Open a [GitHub Issue](https://github.com/commander-apemanx/camera-dashboard/issues) (feature request or discussion). Useful reports include what you want, why, and roughly how many cameras / what hardware you run.

---

## Honest status (alpha)

This is a **very young, single-maintainer** project. Treat it like **alpha software**, not something you point at anything you actually rely on for security or critical monitoring.

Today that means, in practice:

| Reality | What to expect |
|---------|----------------|
| Early repo | Few commits, little external adoption yet, no mature test suite or heavy issue/PR history |
| **CPU-bound detection** | YOLOv8 on CPU is expensive. The README already flags that **four full HD streams is heavy** — prefer camera **sub-streams** (e.g. Hikvision channel `102`) instead of main streams. On a decent NVR-grade Unraid CPU this is manageable; otherwise expect fan noise and dropped frames |
| **Credentials on disk** | Camera usernames/passwords sit in plaintext `data/cameras.json` (gitignored, **not encrypted at rest**). Fine on a trusted LAN; not something to expose further |
| **No dashboard auth** | The UI and streams are open to whoever can reach the port. Do **not** expose port **5000** to the internet without a reverse proxy (and your existing access control) in front. Prefer keeping it on the LAN or behind the same gate as your other services — not a raw port-forward |
| **Hard cap of 4 cameras** | Fine if that matches your setup; a real limitation if you want to scale later (see near-term roadmap) |

If you need a battle-tested NVR/detection stack today, use something mature (e.g. Frigate). This project stays a focused live dashboard + detection helper while it grows.

---

## Current (v1.x)

- Up to **4** cameras in a 2×2 live grid
- RTSP / ONVIF add flow with live probe
- YOLOv8 person detection, detection terminal, optional snapshots
- Docker Compose package (GHCR) and local `./start.sh` package
- GNU GPLv3

---

## Near term

These items exist specifically because of the limitations above.

### More cameras (selectable, up to 32)

Today the hard limit is four. The goal is a **configurable camera count** — choose how many you need, up to **32**.

Likely work:

- Replace the fixed 2×2 grid with a layout that scales (e.g. 3×3, 4×4, or auto)
- Per-install max (or UI selector) instead of a single compile-time `MAX_CAMERAS = 4`
- Keep multi-stream MJPEG stable under higher load (slot reuse, lower preview FPS, sub-stream defaults)
- Document CPU/RAM expectations as camera count grows

### Local encryption

Protect sensitive data **on disk** when the app stores it locally (addressing plaintext `cameras.json`):

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

Tracked issues: [#1 cameras](https://github.com/commander-apemanx/camera-dashboard/issues/1) · [#2 encryption](https://github.com/commander-apemanx/camera-dashboard/issues/2) · [#3 security](https://github.com/commander-apemanx/camera-dashboard/issues/3) · [Milestone](https://github.com/commander-apemanx/camera-dashboard/milestone/1)

License remains **GNU GPLv3** — see [LICENSE](LICENSE).
