// Wave-6 Phase F: login form handler.
// Loaded as an external <script src> so script-src 'self' is satisfied
// without unsafe-inline. Posts {username, password} to /api/auth/login;
// on success, navigates to "/" + (next-hash). On rate-limit / bad creds,
// shows an inline error.
(function () {
  "use strict";

  function $(id) { return document.getElementById(id); }

  function showError(msg) {
    var el = $("loginError");
    if (!el) return;
    el.textContent = msg;
    el.hidden = false;
  }

  function clearError() {
    var el = $("loginError");
    if (!el) return;
    el.textContent = "";
    el.hidden = true;
  }

  function nextHash() {
    var el = $("loginNext");
    var raw = (el && el.value) || "";
    // The server escaped the value, but it may include `#` or be
    // empty. Always navigate to "/" + raw so a missing or root hash
    // still lands the user on the SPA.
    if (!raw) return "/";
    if (raw.charAt(0) === "#") return "/" + raw;
    return "/#" + raw;
  }

  async function submit(ev) {
    ev.preventDefault();
    clearError();
    var btn = $("loginSubmit");
    var u = ($("loginUsername") || {}).value || "";
    var p = ($("loginPassword") || {}).value || "";
    if (!u.trim() || !p) {
      showError("Username and token are required.");
      return;
    }
    if (btn) btn.disabled = true;
    try {
      var res = await fetch("/api/auth/login", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: u.trim(), password: p }),
      });
      if (res.status === 429) {
        var ra = res.headers.get("Retry-After") || "60";
        showError("Too many attempts. Try again in " + ra + " seconds.");
        return;
      }
      if (!res.ok) {
        showError("Invalid credentials.");
        return;
      }
      // Successful login — Set-Cookie was applied by the response.
      window.location.assign(nextHash());
    } catch (err) {
      showError("Network error. Please retry.");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var form = $("loginForm");
    if (form) form.addEventListener("submit", submit);
  });
})();
