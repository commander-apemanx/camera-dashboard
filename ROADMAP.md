# Roadmap

Plans and direction for Camera Dashboard. Status here is intentional, not a promise of dates.

**User ideas and requests are welcome.** Open a [GitHub Issue](https://github.com/commander-apemanx/camera-dashboard/issues) (feature request or discussion). Useful reports include what you want, why, and roughly how many cameras / what hardware you run.

---

## Honest status (alpha)

This is a **very young, single-maintainer** project. Treat it like **alpha software**, not something you point at anything you actually rely on for security or critical monitoring.

| Reality today | What to expect | How we plan to address it |
|---------------|----------------|---------------------------|
| Early repo | Few commits, little adoption yet, no mature tests or heavy issue/PR history | Grow carefully; add automated tests and CI as features land; keep docs honest |
| **CPU-bound detection** | YOLOv8 on CPU is expensive. Four full HD streams is heavy — prefer **sub-streams** (e.g. Hikvision `102`). Modest CPUs → fan noise / dropped frames | **GPU detection** (NVIDIA, AMD, Intel); default/recommend sub-streams; lighter detect cadence |
| **Credentials on disk** | Passwords in plaintext `data/cameras.json` (gitignored, **not encrypted at rest**) | **Local encryption** at rest + documented key/backup flow |
| **No dashboard auth** | Anyone who can reach the port sees UI + streams. Do not expose `:5000` raw to the internet | **Optional login / sessions**; safer bind defaults; reverse-proxy + TLS guidance |
| **Hard cap of 4 cameras** | Fine for small setups; blocks scale | **Selectable count, up to 32**, with scalable grid and load guidance |

If you need a battle-tested NVR/detection stack *today*, use something mature (e.g. Frigate). This project stays a focused live dashboard + detection helper while these gaps close.

---

## Current (v1.x)

- Up to **4** cameras in a 2×2 live grid
- RTSP / ONVIF add flow with live probe
- YOLOv8 person detection (**CPU only** today), detection terminal, optional snapshots
- Docker Compose package (GHCR) and local `./start.sh` package
- GNU GPLv3

---

## Near term — addressing known issues

### 1. More cameras (selectable, up to 32)

**Addresses:** hard 4-camera cap.

- Configurable / selectable camera count (not a fixed `MAX_CAMERAS = 4`)
- Scalable layouts (3×3, 4×4, or auto) instead of only 2×2
- Stable multi-stream behavior under load (slot reuse, lower preview FPS)
- Document CPU/RAM/GPU expectations as count grows

### 2. GPU-accelerated detection (NVIDIA, AMD, Intel)

**Addresses:** CPU-bound detection, fan noise, dropped frames with multiple streams.

Goal: run person detection on a GPU when available, with CPU as fallback.

| Vendor | Direction (explore / support) |
|--------|-------------------------------|
| **NVIDIA** | CUDA / TensorRT (or Ultralytics CUDA device) — most common for Unraid + discrete GPU |
| **AMD** | ROCm / compatible PyTorch builds where practical |
| **Intel** | OpenVINO and/or Intel GPU / iGPU paths (including common Unraid N100/iGPU boxes) |

Also planned alongside GPU work:

- Auto-detect best device (`cuda` / ROCm / OpenVINO / CPU) with clear UI/log status
- Docker image variants or docs for GPU passthrough (NVIDIA Container Toolkit, etc.)
- Keep CPU-only path for machines without a usable GPU

### 3. Sub-streams and stream efficiency (default path)

**Addresses:** “four HD mainstreams is heavy” even before detection.

- Prefer / guide **camera sub-streams** for live view and detection
- Optional main-stream only when needed (e.g. snapshot quality)
- Tunable detect interval and preview FPS so many cameras stay usable

### 4. Local encryption

**Addresses:** plaintext credentials (and sensitive snapshots) on disk.

- Encrypt `data/cameras.json` at rest
- Encrypt or protect detection photos under `Data/` where practical
- Unlock / key setup for Docker and `./start.sh` (local only — no cloud KMS required)
- Backup and key-recovery docs so a lost key does not brick an install silently

### 5. Security-focused hardening

**Addresses:** no dashboard auth; unsafe to expose raw.

- Optional login / session before UI and MJPEG streams
- Safer defaults (bind address, headers, secrets)
- Review API surfaces (streams, settings, deletes)
- Document reverse proxy + TLS + “put this behind your existing access control”
- Keep credentials/keys out of images, logs, and git

### 6. Project maturity (tests, CI, reliability)

**Addresses:** young-repo / no visible tests risk.

- Automated tests for config, settings, and critical API paths
- CI on GitHub Actions (lint/tests; package publish already exists)
- Clearer “alpha → beta” criteria before calling anything production-ready for security use

---

## Later / explore

### Areas (multi-page organisation)

Organise cameras into named **Areas** — separate dashboard pages, each holding up to **4 cameras** (same 2×2 grid as today).

Examples: *Front garden*, *Driveway*, *Inside*, *Garage*.

Likely work:

- Create / rename / reorder Areas
- Assign cameras to an Area (a camera belongs to one Area page)
- Navigate between Area pages without rebuilding streams awkwardly
- Scales naturally with the “up to 32 cameras” goal (e.g. eight Areas × 4)

### Other

- Round-robin or lighter models when GPU is absent but camera count is high
- Encrypted config export / import
- Unraid-friendly GPU and encrypted-volume defaults
- Role separation (view-only vs admin) if auth lands

---

## Out of scope (for now)

- Cloud account / SaaS control plane
- Replacing a full NVR (Frigate, etc.) — this stays a focused live dashboard + detection helper

---

## How to contribute an idea

1. Search [existing issues](https://github.com/commander-apemanx/camera-dashboard/issues) first  
2. Open a new issue (`enhancement`, `security`, or similar)  
3. Say whether it helps **cameras / GPU / encryption / security / tests** so we can place it here  

### Tracked work

| Theme | Issue |
|-------|--------|
| Cameras up to 32 | [#1](https://github.com/commander-apemanx/camera-dashboard/issues/1) |
| Local encryption | [#2](https://github.com/commander-apemanx/camera-dashboard/issues/2) |
| Security hardening | [#3](https://github.com/commander-apemanx/camera-dashboard/issues/3) |
| GPU detection (NVIDIA / AMD / Intel) | [#4](https://github.com/commander-apemanx/camera-dashboard/issues/4) |
| Sub-streams / stream efficiency | [#5](https://github.com/commander-apemanx/camera-dashboard/issues/5) |
| Tests and CI | [#6](https://github.com/commander-apemanx/camera-dashboard/issues/6) |
| Areas (pages of 4 cameras) | [#7](https://github.com/commander-apemanx/camera-dashboard/issues/7) |
| Milestone | [Roadmap: scale, GPU, encryption, security](https://github.com/commander-apemanx/camera-dashboard/milestone/1) |

License remains **GNU GPLv3** — see [LICENSE](LICENSE).
