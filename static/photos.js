(() => {
  const list = document.getElementById("photoList");
  const empty = document.getElementById("emptyState");
  const countBadge = document.getElementById("photoCount");
  const statusLine = document.getElementById("statusLine");
  const filterInput = document.getElementById("filterInput");
  const btnRefresh = document.getElementById("btnRefresh");
  const lightbox = document.getElementById("lightbox");
  const lightboxImg = document.getElementById("lightboxImg");
  const lightboxCap = document.getElementById("lightboxCap");
  const lightboxClose = document.getElementById("lightboxClose");

  let photos = [];

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatSize(n) {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / (1024 * 1024)).toFixed(2)} MB`;
  }

  function filtered() {
    const q = (filterInput.value || "").trim().toLowerCase();
    if (!q) return photos;
    return photos.filter(
      (p) =>
        p.filename.toLowerCase().includes(q) ||
        (p.camera || "").toLowerCase().includes(q) ||
        (p.timestamp || "").toLowerCase().includes(q)
    );
  }

  function render() {
    const rows = filtered();
    countBadge.textContent = `${photos.length} photo${photos.length === 1 ? "" : "s"}`;
    statusLine.textContent = rows.length !== photos.length ? `Showing ${rows.length} of ${photos.length}` : "";

    if (!photos.length) {
      list.innerHTML = "";
      empty.classList.remove("hidden");
      return;
    }
    empty.classList.add("hidden");

    if (!rows.length) {
      list.innerHTML = `<div class="empty-photos">No photos match the filter.</div>`;
      return;
    }

    list.innerHTML = rows
      .map(
        (p) => `
      <article class="photo-card" data-file="${escapeHtml(p.filename)}">
        <button type="button" class="photo-thumb" data-open="${escapeHtml(p.url)}" data-cap="${escapeHtml(p.filename)}">
          <img src="${escapeHtml(p.url)}" alt="${escapeHtml(p.filename)}" loading="lazy" />
        </button>
        <div class="photo-meta">
          <div class="photo-name" title="${escapeHtml(p.filename)}">${escapeHtml(p.filename)}</div>
          <div class="photo-sub">
            <span>${escapeHtml(p.timestamp || "")}</span>
            <span>${escapeHtml(p.camera || "—")}</span>
            <span>${formatSize(p.size || 0)}</span>
          </div>
          <div class="photo-actions">
            <a class="btn tiny ghost" href="${escapeHtml(p.url)}" target="_blank" rel="noopener">Open</a>
            <a class="btn tiny ghost" href="${escapeHtml(p.url)}" download="${escapeHtml(p.filename)}">Download</a>
            <button type="button" class="btn tiny danger" data-del="${escapeHtml(p.filename)}">Delete</button>
          </div>
        </div>
      </article>`
      )
      .join("");

    list.querySelectorAll("[data-open]").forEach((btn) => {
      btn.addEventListener("click", () => {
        lightboxImg.src = btn.getAttribute("data-open");
        lightboxCap.textContent = btn.getAttribute("data-cap") || "";
        lightbox.classList.remove("hidden");
      });
    });

    list.querySelectorAll("[data-del]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const name = btn.getAttribute("data-del");
        if (!confirm(`Delete ${name}?`)) return;
        const res = await fetch(`/api/photos/${encodeURIComponent(name)}`, { method: "DELETE" });
        if (res.ok) {
          photos = photos.filter((p) => p.filename !== name);
          render();
        }
      });
    });
  }

  async function load() {
    statusLine.textContent = "Loading…";
    try {
      const res = await fetch("/api/photos");
      if (res.status === 401) {
        window.location.href = "/login";
        return;
      }
      const next = await res.json();
      if (!Array.isArray(next)) {
        statusLine.textContent = "Failed to load photos";
        return;
      }
      const unchanged =
        next.length === photos.length &&
        next.every(
          (p, i) =>
            photos[i] &&
            p.filename === photos[i].filename &&
            p.size === photos[i].size &&
            p.mtime === photos[i].mtime
        );
      if (unchanged) {
        if (!(filterInput.value || "").trim()) statusLine.textContent = "";
        return;
      }
      photos = next;
      render();
    } catch (_) {
      statusLine.textContent = "Failed to load photos";
    }
  }

  function closeLightbox() {
    lightbox.classList.add("hidden");
    lightboxImg.src = "";
  }

  btnRefresh.addEventListener("click", load);
  filterInput.addEventListener("input", render);
  lightboxClose.addEventListener("click", closeLightbox);
  lightbox.addEventListener("click", (e) => {
    if (e.target === lightbox) closeLightbox();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeLightbox();
  });

  load();
  setInterval(load, 10000);
})();
