(() => {
  const mode = window.__AUTH_MODE__ || "login";
  const form = document.getElementById("authForm");
  const password = document.getElementById("password");
  const confirm = document.getElementById("confirm");
  const status = document.getElementById("authStatus");
  const submit = document.getElementById("authSubmit");

  function setStatus(msg, kind) {
    status.textContent = msg || "";
    status.className = "form-status" + (kind ? ` ${kind}` : "");
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const pwd = password.value || "";
    if (pwd.length < 8) {
      setStatus("Password must be at least 8 characters", "err");
      return;
    }
    if (mode === "setup" && pwd !== (confirm.value || "")) {
      setStatus("Passwords do not match", "err");
      return;
    }

    submit.disabled = true;
    setStatus(mode === "setup" ? "Creating vault…" : "Unlocking…", "pending");
    try {
      const url = mode === "setup" ? "/api/auth/setup" : "/api/auth/login";
      const body =
        mode === "setup"
          ? { password: pwd, confirm: confirm.value || "" }
          : { password: pwd };
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.ok) {
        setStatus(data.error || "Failed", "err");
        return;
      }
      setStatus("OK — opening dashboard…", "ok");
      window.location.href = "/";
    } catch (_) {
      setStatus("Network error", "err");
    } finally {
      submit.disabled = false;
    }
  });
})();
