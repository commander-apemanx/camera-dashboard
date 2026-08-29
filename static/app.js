(() => {
  const grid = document.getElementById("cameraGrid");
  const terminal = document.getElementById("terminal");
  const addPanel = document.getElementById("addPanel");
  const addForm = document.getElementById("addForm");
  const formStatus = document.getElementById("formStatus");
  const btnToggleAdd = document.getElementById("btnToggleAdd");
  const btnCancelAdd = document.getElementById("btnCancelAdd");
  const btnClearLog = document.getElementById("btnClearLog");
  const btnTest = document.getElementById("btnTest");
  const btnAdd = document.getElementById("btnAdd");
  const detectorBadge = document.getElementById("detectorBadge");
  const camCount = document.getElementById("camCount");
  const protocolSelect = document.getElementById("protocolSelect");
  const portInput = document.getElementById("portInput");
  const pathLabel = document.getElementById("pathLabel");
  const pathInput = document.getElementById("pathInput");
  const protocolHint = document.getElementById("protocolHint");
  const snapshotDelay = document.getElementById("snapshotDelay");
  const snapshotEnabled = document.getElementById("snapshotEnabled");
  const btnSaveDelay = document.getElementById("btnSaveDelay");
  const delayControl = document.querySelector(".delay-control");
  const settingsPanel = document.getElementById("settingsPanel");
  const btnSettings = document.getElementById("btnSettings");
  const btnCloseSettings = document.getElementById("btnCloseSettings");
  const btnLogout = document.getElementById("btnLogout");
  const btnLockVault = document.getElementById("btnLockVault");
  const unlockUntilReboot = document.getElementById("unlockUntilReboot");
  const securityStatus = document.getElementById("securityStatus");
  const vaultBadge = document.getElementById("vaultBadge");
  const changePasswordForm = document.getElementById("changePasswordForm");
  const cpStatus = document.getElementById("cpStatus");

  const MAX = 4;
  let camerasTimer = null;
  let healthTimer = null;

  function goLogin() {
    if (camerasTimer) clearInterval(camerasTimer);
    if (healthTimer) clearInterval(healthTimer);
    camerasTimer = null;
    healthTimer = null;
    // Stop MJPEG requests so they do not hit a locking/locked server.
    document.querySelectorAll("img[data-stream]").forEach((img) => {
      img.removeAttribute("src");
    });
    window.location.replace("/login");
  }

  async function apiFetch(url, opts) {
    const res = await fetch(url, opts);
    if (res.status === 401) {
      const data = await res.clone().json().catch(() => ({}));
      if (data.setup_required || data.error === "setup_required") {
        window.location.replace("/setup");
      } else {
        // Includes vault_locked after process restart with a stale cookie.
        goLogin();
      }
      throw new Error("auth");
    }
    return res;
  }
  /** @type {Map<string, object>} cameraId -> last camera meta */
  const known = new Map();
  /** slot index -> cameraId (or null) */
  let slotIds = [null, null, null, null];

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function log(message, type = "sys") {
    const empty = terminal.querySelector(".empty-hint");
    if (empty) empty.remove();
    const line = document.createElement("div");
    line.className = `line ${type}`;
    const ts = new Date().toLocaleTimeString();
    line.innerHTML = `<span class="ts">[${ts}]</span> <span class="msg">${escapeHtml(message)}</span>`;
    terminal.prepend(line);
    while (terminal.children.length > 300) terminal.removeChild(terminal.lastChild);
  }

  function logDetection(ev) {
    const empty = terminal.querySelector(".empty-hint");
    if (empty) empty.remove();
    const line = document.createElement("div");
    line.className = "line det";
    let extra = "";
    if (ev.snapshot) {
      extra = ` · <a class="snap-link" href="/Data/${encodeURIComponent(ev.snapshot)}" target="_blank" rel="noopener">${escapeHtml(ev.snapshot)}</a>`;
    }
    line.innerHTML =
      `<span class="ts">[${escapeHtml(ev.timestamp)}]</span> ` +
      `<span class="cam">${escapeHtml(ev.camera_name)}</span> · ` +
      `<span class="msg">${escapeHtml(ev.message)}</span>${extra}`;
    terminal.prepend(line);
    while (terminal.children.length > 300) terminal.removeChild(terminal.lastChild);
  }

  function applySettingsUI(data) {
    if (!data) return;
    if (data.snapshot_delay_sec != null) {
      snapshotDelay.value = String(data.snapshot_delay_sec);
    }
    if (typeof data.snapshot_enabled === "boolean") {
      snapshotEnabled.checked = data.snapshot_enabled;
      delayControl.classList.toggle("disabled-photos", !data.snapshot_enabled);
      snapshotDelay.disabled = !data.snapshot_enabled;
    }
    if (typeof data.unlock_until_reboot === "boolean" && unlockUntilReboot) {
      unlockUntilReboot.checked = data.unlock_until_reboot;
    }
    if (vaultBadge) {
      if (data.vault_unlocked) {
        vaultBadge.textContent = "Vault unlocked";
        vaultBadge.className = "badge ok";
      } else {
        vaultBadge.textContent = "Vault locked";
        vaultBadge.className = "badge danger";
      }
    }
  }

  async function loadSettings() {
    try {
      const res = await apiFetch("/api/settings");
      const data = await res.json();
      applySettingsUI(data);
    } catch (_) {
      /* ignore */
    }
  }

  async function savePhotoSettings(partial) {
    btnSaveDelay.disabled = true;
    snapshotEnabled.disabled = true;
    try {
      const body = {
        snapshot_delay_sec: Number(snapshotDelay.value),
        snapshot_enabled: !!snapshotEnabled.checked,
        ...partial,
      };
      const res = await apiFetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        log(`Photo settings FAIL: ${data.error || data.message || "invalid"}`);
        await loadSettings();
        return;
      }
      applySettingsUI(data.settings);
      const on = data.settings.snapshot_enabled ? "ON" : "OFF";
      log(`Photo save ${on} · delay ${data.settings.snapshot_delay_sec}s`);
    } catch (_) {
      log("Photo settings FAIL: network error");
    } finally {
      btnSaveDelay.disabled = false;
      snapshotEnabled.disabled = false;
    }
  }

  async function saveUnlockSetting() {
    if (!unlockUntilReboot) return;
    securityStatus.textContent = "Saving…";
    securityStatus.className = "form-status pending";
    try {
      const res = await apiFetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ unlock_until_reboot: !!unlockUntilReboot.checked }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        securityStatus.textContent = data.error || "Failed";
        securityStatus.className = "form-status err";
        await loadSettings();
        return;
      }
      applySettingsUI(data.settings);
      securityStatus.textContent = data.settings.unlock_until_reboot
        ? "Unlock until reboot ON"
        : "Unlock until reboot OFF";
      securityStatus.className = "form-status ok";
      log(
        data.settings.unlock_until_reboot
          ? "Unlock until reboot enabled"
          : "Unlock until reboot disabled — logout will lock the vault"
      );
    } catch (_) {
      securityStatus.textContent = "Network error";
      securityStatus.className = "form-status err";
    }
  }

  function setFormStatus(message, kind) {
    formStatus.textContent = message || "";
    formStatus.className = "form-status" + (kind ? ` ${kind}` : "");
  }

  function setDetectorBadge(ready, error) {
    if (ready) {
      detectorBadge.textContent = "YOLO ready";
      detectorBadge.className = "badge ok";
    } else if (error) {
      detectorBadge.textContent = "Detector error";
      detectorBadge.className = "badge danger";
      detectorBadge.title = error;
    } else {
      detectorBadge.textContent = "Detector loading…";
      detectorBadge.className = "badge warn";
    }
  }

  function emptySlotHtml(idx) {
    return `<div>Empty slot ${idx + 1}<br/><span style="opacity:.7">Add a camera stream</span></div>`;
  }

  function ensureSlots() {
    if (grid.children.length === MAX) return;
    grid.innerHTML = "";
    for (let i = 0; i < MAX; i++) {
      const el = document.createElement("article");
      el.className = "slot empty";
      el.dataset.slot = String(i);
      el.innerHTML = emptySlotHtml(i);
      grid.appendChild(el);
    }
  }

  function bindRemove(el, camId) {
    const btn = el.querySelector("[data-del]");
    if (!btn) return;
    btn.onclick = async () => {
      if (!confirm("Remove this camera stream?")) return;
      const res = await apiFetch(`/api/cameras/${camId}`, { method: "DELETE" });
      if (res.ok) {
        log(`Removed camera ${camId}`);
        await refreshCameras(true);
      } else {
        log("Failed to remove camera", "sys");
      }
    };
  }

  function fillSlot(slotEl, cam) {
    const status = cam.status || "stopped";
    const proto = (cam.protocol || "rtsp").toUpperCase();
    slotEl.className = "slot";
    slotEl.dataset.camId = cam.id;
    slotEl.innerHTML = `
      <div class="slot-head">
        <div class="slot-title">
          <span class="dot ${escapeHtml(status)}"></span>
          ${escapeHtml(cam.name)}
          <span class="proto-tag">${escapeHtml(proto)}</span>
        </div>
        <div class="slot-meta">
          <span data-meta="status">${escapeHtml(status)}</span>
          <span data-meta="fps">${Number(cam.fps || 0).toFixed(1)} fps</span>
          <button class="btn tiny danger" data-del="${escapeHtml(cam.id)}" type="button" title="Remove">✕</button>
        </div>
      </div>
      <div class="slot-body">
        <img data-stream="1" src="/stream/${encodeURIComponent(cam.id)}" alt="${escapeHtml(cam.name)}" draggable="false" />
      </div>
      <div class="slot-foot">
        <span class="ip" data-meta="ip">${escapeHtml(cam.ip)}:${escapeHtml(String(cam.port))}${cam.protocol === "rtsp" ? escapeHtml(cam.path || "") : " · ONVIF"}</span>
        <span class="person-pill" data-meta="persons">persons: ${cam.person_count || 0}</span>
      </div>
    `;
    bindRemove(slotEl, cam.id);
    const img = slotEl.querySelector("[data-stream]");
    if (img) {
      img.addEventListener("error", () => {
        const id = cam.id;
        setTimeout(() => {
          if (slotEl.dataset.camId !== id) return;
          img.src = `/stream/${encodeURIComponent(id)}?t=${Date.now()}`;
        }, 1500);
      });
    }
  }

  function updateSlotMeta(slotEl, cam) {
    const status = cam.status || "stopped";
    const dot = slotEl.querySelector(".dot");
    if (dot) dot.className = `dot ${status}`;
    const st = slotEl.querySelector('[data-meta="status"]');
    if (st) st.textContent = status;
    const fps = slotEl.querySelector('[data-meta="fps"]');
    if (fps) fps.textContent = `${Number(cam.fps || 0).toFixed(1)} fps`;
    const persons = slotEl.querySelector('[data-meta="persons"]');
    if (persons) persons.textContent = `persons: ${cam.person_count || 0}`;
    // NEVER touch img.src — that was killing multi-stream MJPEG
  }

  function clearSlot(slotEl, idx) {
    slotEl.className = "slot empty";
    delete slotEl.dataset.camId;
    slotEl.innerHTML = emptySlotHtml(idx);
  }

  /**
   * Stable grid: only rebuild a slot when its camera id changes.
   * Prevents MJPEG reconnect thrash that broke 2nd+ streams.
   */
  function syncGrid(cameras) {
    ensureSlots();
    camCount.textContent = `${cameras.length} / ${MAX} cameras`;
    btnToggleAdd.disabled = cameras.length >= MAX;
    if (cameras.length >= MAX) addPanel.classList.add("hidden");

    const nextIds = cameras.map((c) => c.id);
    while (nextIds.length < MAX) nextIds.push(null);

    // Detect order: keep existing ids in their slots when possible
    const newSlotIds = [null, null, null, null];
    const used = new Set();

    // 1) keep cameras that already occupy a slot
    for (let i = 0; i < MAX; i++) {
      const prev = slotIds[i];
      if (prev && nextIds.includes(prev)) {
        newSlotIds[i] = prev;
        used.add(prev);
      }
    }
    // 2) place remaining cameras into free slots (left to right)
    for (const id of nextIds) {
      if (!id || used.has(id)) continue;
      const free = newSlotIds.indexOf(null);
      if (free === -1) break;
      newSlotIds[free] = id;
      used.add(id);
    }

    const byId = new Map(cameras.map((c) => [c.id, c]));

    for (let i = 0; i < MAX; i++) {
      const slotEl = grid.children[i];
      const id = newSlotIds[i];
      const prevId = slotIds[i];

      if (!id) {
        if (prevId || !slotEl.classList.contains("empty")) clearSlot(slotEl, i);
        continue;
      }

      const cam = byId.get(id);
      if (!cam) continue;

      if (id !== prevId || slotEl.dataset.camId !== id) {
        fillSlot(slotEl, cam);
      } else {
        updateSlotMeta(slotEl, cam);
      }
      known.set(id, cam);
    }

    // drop unknown
    for (const id of [...known.keys()]) {
      if (!nextIds.includes(id)) known.delete(id);
    }

    slotIds = newSlotIds;
  }

  async function refreshCameras() {
    try {
      const res = await apiFetch("/api/cameras");
      if (!res.ok) throw new Error("bad status");
      const cameras = await res.json();
      if (!Array.isArray(cameras)) throw new Error("invalid payload");
      syncGrid(cameras);
    } catch (_) {
      // keep UI stable on transient errors
    }
  }

  async function refreshHealth() {
    try {
      const res = await apiFetch("/api/health");
      const data = await res.json();
      setDetectorBadge(data.detector_ready, data.detector_error);
      if (vaultBadge) {
        if (data.vault_unlocked) {
          vaultBadge.textContent = "Vault unlocked";
          vaultBadge.className = "badge ok";
        } else {
          vaultBadge.textContent = "Vault locked";
          vaultBadge.className = "badge danger";
        }
      }
    } catch (_) {
      setDetectorBadge(false, "unreachable");
    }
  }

  async function loadDetections() {
    try {
      const res = await apiFetch("/api/detections?limit=100");
      const list = await res.json();
      if (!list.length) {
        terminal.innerHTML = `<div class="empty-hint">Waiting for person detections…</div>`;
        return;
      }
      terminal.innerHTML = "";
      [...list].reverse().forEach(logDetection);
    } catch (_) {
      terminal.innerHTML = `<div class="empty-hint">Waiting for person detections…</div>`;
    }
  }

  function formBody() {
    const fd = new FormData(addForm);
    const protocol = String(fd.get("protocol") || "rtsp");
    return {
      protocol,
      name: String(fd.get("name") || ""),
      ip: String(fd.get("ip") || "").trim(),
      port: Number(fd.get("port") || (protocol === "onvif" ? 80 : 554)),
      username: String(fd.get("username") || ""),
      password: String(fd.get("password") || ""),
      path: String(fd.get("path") || ""),
    };
  }

  function onProtocolChange() {
    const p = protocolSelect.value;
    if (p === "onvif") {
      portInput.value = portInput.value === "554" || !portInput.value ? "80" : portInput.value;
      pathLabel.classList.add("hidden-field");
      pathInput.disabled = true;
      protocolHint.innerHTML =
        "ONVIF discovers the RTSP URL automatically. Default port <code>80</code> (also tries 8080, 8000, 8899). " +
        "Enter camera IP + credentials, then Test or Add.";
    } else {
      portInput.value = portInput.value === "80" || !portInput.value ? "554" : portInput.value;
      pathLabel.classList.remove("hidden-field");
      pathInput.disabled = false;
      protocolHint.innerHTML =
        "RTSP URL: <code>rtsp://user:pass@ip:port/path</code>. " +
        "Examples: <code>/stream1</code>, Hikvision <code>/Streaming/Channels/101</code>, " +
        "Dahua <code>/cam/realmonitor?channel=1&amp;subtype=0</code>.";
    }
  }

  function setBusy(busy) {
    btnAdd.disabled = busy;
    btnTest.disabled = busy;
    btnAdd.textContent = busy ? "Working…" : "Add Stream";
    btnTest.textContent = busy ? "Testing…" : "Test Connection";
  }

  btnToggleAdd.addEventListener("click", () => {
    addPanel.classList.toggle("hidden");
    setFormStatus("", "");
  });

  btnCancelAdd.addEventListener("click", () => {
    addPanel.classList.add("hidden");
    setFormStatus("", "");
    addForm.reset();
    protocolSelect.value = "rtsp";
    onProtocolChange();
  });

  btnClearLog.addEventListener("click", () => {
    terminal.innerHTML = `<div class="empty-hint">Log cleared. Waiting for person detections…</div>`;
  });

  protocolSelect.addEventListener("change", onProtocolChange);

  btnTest.addEventListener("click", async () => {
    setFormStatus("Testing connection…", "pending");
    setBusy(true);
    const body = formBody();
    try {
      const res = await apiFetch("/api/cameras/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (data.success || data.ok) {
        setFormStatus(`✓ SUCCESS (${body.protocol.toUpperCase()}): ${data.message}`, "ok");
        log(`Test OK [${body.protocol}] ${body.ip}: ${data.message}`);
      } else {
        const err = data.error || data.message || "Connection failed";
        setFormStatus(`✗ FAIL (${body.protocol.toUpperCase()}): ${err}`, "err");
        log(`Test FAIL [${body.protocol}] ${body.ip}: ${err}`);
      }
    } catch (_) {
      setFormStatus("✗ FAIL: Network error talking to dashboard", "err");
    } finally {
      setBusy(false);
    }
  });

  addForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    setFormStatus("Adding & verifying stream…", "pending");
    setBusy(true);
    const body = formBody();

    try {
      const res = await apiFetch("/api/cameras", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();

      if (!res.ok || !data.success) {
        const err = data.error || data.message || "Failed to add camera";
        setFormStatus(`✗ FAIL (${body.protocol.toUpperCase()}): ${err}`, "err");
        log(`Add FAIL [${body.protocol}] ${body.ip}: ${err}`);
        return;
      }

      setFormStatus(`✓ SUCCESS (${body.protocol.toUpperCase()}): ${data.message}`, "ok");
      log(`Add OK [${body.protocol}] ${body.name || body.ip}: ${data.message}`);
      addForm.reset();
      protocolSelect.value = "rtsp";
      onProtocolChange();
      await refreshCameras();
      // keep panel open briefly so user sees success, then close
      setTimeout(() => {
        if (formStatus.classList.contains("ok")) {
          addPanel.classList.add("hidden");
          setFormStatus("", "");
        }
      }, 1600);
    } catch (_) {
      setFormStatus("✗ FAIL: Network error talking to dashboard", "err");
    } finally {
      setBusy(false);
    }
  });

  try {
    if (typeof io !== "function") {
      throw new Error("socket.io missing");
    }
    const socket = io({ transports: ["websocket", "polling"] });
    socket.on("connect", () => log("Connected to notification channel"));
    socket.on("disconnect", () => log("Disconnected from notification channel"));
    socket.on("detection", (ev) => logDetection(ev));
    socket.on("status", (st) => {
      if (st && typeof st.detector_ready === "boolean") {
        setDetectorBadge(st.detector_ready, st.detector_error || null);
      }
      if (st && st.settings) applySettingsUI(st.settings);
    });
    socket.on("settings", (st) => applySettingsUI(st));
  } catch (_) {
    log("Live notifications unavailable — dashboard still works");
  }

  btnSaveDelay.addEventListener("click", () => savePhotoSettings());
  snapshotEnabled.addEventListener("change", () => {
    savePhotoSettings({ snapshot_enabled: !!snapshotEnabled.checked });
  });
  snapshotDelay.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      savePhotoSettings();
    }
  });

  if (btnSettings && settingsPanel) {
    btnSettings.addEventListener("click", () => {
      settingsPanel.classList.toggle("hidden");
      addPanel.classList.add("hidden");
    });
  }
  if (btnCloseSettings && settingsPanel) {
    btnCloseSettings.addEventListener("click", () => settingsPanel.classList.add("hidden"));
  }
  if (unlockUntilReboot) {
    unlockUntilReboot.addEventListener("change", () => saveUnlockSetting());
  }
  if (btnLogout) {
    btnLogout.addEventListener("click", async () => {
      try {
        await fetch("/api/auth/logout", { method: "POST" });
      } catch (_) {
        /* ignore */
      }
      goLogin();
    });
  }
  if (btnLockVault) {
    btnLockVault.addEventListener("click", async () => {
      if (!confirm("Lock the vault and stop camera streams until the next login?")) return;
      btnLockVault.disabled = true;
      // Stop polling/streams before teardown so the UI cannot race the lock.
      if (camerasTimer) clearInterval(camerasTimer);
      if (healthTimer) clearInterval(healthTimer);
      camerasTimer = null;
      healthTimer = null;
      document.querySelectorAll("img[data-stream]").forEach((img) => {
        img.removeAttribute("src");
      });
      try {
        await fetch("/api/auth/lock", { method: "POST" });
      } catch (_) {
        /* still leave the dashboard */
      }
      window.location.replace("/login");
    });
  }
  if (changePasswordForm) {
    changePasswordForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const current_password = document.getElementById("cpCurrent").value;
      const new_password = document.getElementById("cpNew").value;
      const confirm_password = document.getElementById("cpConfirm").value;
      cpStatus.textContent = "Updating…";
      cpStatus.className = "form-status pending";
      try {
        const res = await apiFetch("/api/auth/change-password", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ current_password, new_password, confirm_password }),
        });
        const data = await res.json();
        if (!res.ok || !data.ok) {
          cpStatus.textContent = data.error || "Failed";
          cpStatus.className = "form-status err";
          return;
        }
        cpStatus.textContent = "Password updated";
        cpStatus.className = "form-status ok";
        changePasswordForm.reset();
        log("Dashboard password updated — camera secrets re-encrypted");
      } catch (_) {
        cpStatus.textContent = "Network error";
        cpStatus.className = "form-status err";
      }
    });
  }

  // Auth-aware fetch for add/test/remove
  const _fetch = window.fetch.bind(window);
  // bindRemove / form handlers still use fetch — patch via apiFetch where we already did

  terminal.innerHTML = `<div class="empty-hint">Waiting for person detections…</div>`;
  onProtocolChange();
  ensureSlots();
  loadSettings();
  refreshCameras();
  refreshHealth();
  loadDetections();
  camerasTimer = setInterval(refreshCameras, 3000);
  healthTimer = setInterval(refreshHealth, 5000);

  log("Dashboard ready — vault unlocks camera credentials");
})();
