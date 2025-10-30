// ======================================
// signup.js – Bootstrap Sign Up to FastAPI backend
// Expected endpoint:
//   POST /api/auth/register -> { message: "...", user_id? }
// You can rename if your backend differs.
// ======================================

(() => {
  "use strict";

  // ---------- Config ----------
  const bodyEl = document.body;
  const OVERRIDE = bodyEl?.getAttribute("data-api-base")?.trim();
  const API_BASE = OVERRIDE || `${location.protocol}//${location.hostname}:8000`;

  const ROUTES = {
    register: `${API_BASE}/api/auth/register`
  };

  // ---------- DOM ----------
  const $ = (s) => document.querySelector(s);

  const form = $("#signupForm");
  const btn  = $("#signupBtn");

  const fullNameEl  = $("#fullName");
  const emailEl     = $("#email");
  const pwdEl       = $("#password");
  const confirmEl   = $("#confirmPwd");
  const termsEl     = $("#terms");

  // Footer year
  const yearEl = $("#year");
  if (yearEl) yearEl.textContent = new Date().getFullYear();

  // Toggle password fields
  const togglePwd = $("#togglePwd");
  const toggleConfirm = $("#toggleConfirm");

  function setPwdVisible(input, btnEl, visible) {
    if (!input || !btnEl) return;
    input.type = visible ? "text" : "password";
    btnEl.innerHTML = `<i class="bi ${visible ? "bi-eye-slash" : "bi-eye"}"></i>`;
    btnEl.setAttribute("aria-label", visible ? "Hide password" : "Show password");
    btnEl.setAttribute("aria-pressed", String(visible));
  }
  if (togglePwd && pwdEl) {
    togglePwd.addEventListener("click", () => setPwdVisible(pwdEl, togglePwd, pwdEl.type === "password"));
    setPwdVisible(pwdEl, togglePwd, false);
  }
  if (toggleConfirm && confirmEl) {
    toggleConfirm.addEventListener("click", () => setPwdVisible(confirmEl, toggleConfirm, confirmEl.type === "password"));
    setPwdVisible(confirmEl, toggleConfirm, false);
  }

  // ---------- Alert helpers ----------
  function ensureAlertHost() {
    let host = $("#signup-alert-host");
    if (!host) {
      host = document.createElement("div");
      host.id = "signup-alert-host";
      form?.insertBefore(host, form.firstChild);
    }
    return host;
  }
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[ch]));
  }
  function showAlert(message, type = "danger") {
    const host = ensureAlertHost();
    host.innerHTML = `
      <div class="alert alert-${type} d-flex align-items-start" role="alert">
        <i class="bi ${type === "success" ? "bi-check-circle" : "bi-exclamation-triangle"} me-2"></i>
        <div>${escapeHtml(message)}</div>
      </div>`;
  }
  function clearAlert() {
    const host = $("#signup-alert-host");
    if (host) host.innerHTML = "";
  }

  // ---------- UI helpers ----------
  function setLoading(loading) {
    if (!btn || !form) return;
    const btnText = btn.querySelector(".btn-text");
    const spinner = btn.querySelector(".spinner-border");
    btn.disabled = loading;
    btn.setAttribute("aria-disabled", String(loading));
    form.setAttribute("aria-busy", String(loading));
    if (spinner) spinner.classList.toggle("d-none", !loading);
    if (btnText) btnText.classList.toggle("d-none", loading);
  }

  function setFieldInvalid(input, invalid, message) {
    if (!input) return;
    input.classList.toggle("is-invalid", invalid);
    const fb = input.parentElement?.querySelector(".invalid-feedback") || input.nextElementSibling;
    if (fb && fb.classList && fb.classList.contains("invalid-feedback") && message) {
      fb.textContent = message;
    }
  }

  function validEmail(v) {
    // đơn giản & đủ dùng
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
    // Nếu backend strict hơn, hãy đồng bộ regex tại đây.
  }

  // ---------- Submit ----------
  async function handleSubmit(e) {
    e.preventDefault();
    clearAlert();

    // Native constraint check
    if (!form.checkValidity()) {
      e.stopPropagation();
      form.classList.add("was-validated");
      return;
    }

    // Extra checks
    const fullName = (fullNameEl?.value || "").trim();
    const email = (emailEl?.value || "").trim();
    const password = pwdEl?.value || "";
    const confirm = confirmEl?.value || "";
    const accepted = !!termsEl?.checked;

    // Email validate
    if (!validEmail(email)) {
      setFieldInvalid(emailEl, true, "Please enter a valid email address.");
      return;
    } else {
      setFieldInvalid(emailEl, false);
    }

    // Password length
    if ((password || "").length < 6) {
      setFieldInvalid(pwdEl, true, "Password must be at least 6 characters.");
      return;
    } else {
      setFieldInvalid(pwdEl, false);
    }

    // Match
    if (password !== confirm) {
      setFieldInvalid(confirmEl, true, "Passwords do not match.");
      return;
    } else {
      setFieldInvalid(confirmEl, false);
    }

    // Terms
    if (!accepted) {
      termsEl?.classList.add("is-invalid");
      return;
    } else {
      termsEl?.classList.remove("is-invalid");
    }

    // Payload theo backend của bạn.
    // Thường gặp:
    //   { full_name, email, password }
    // hoặc { username/email, password }
    const payload = { full_name: fullName, email, password };

    setLoading(true);
    try {
      const res = await fetch(ROUTES.register, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify(payload),
        cache: "no-store",
      });

      const data = await (async () => {
        try { return await res.json(); } catch { return null; }
      })();

      if (!res.ok) {
        const detail = data?.detail || data?.message || `HTTP ${res.status}`;
        if (/email.*exists|duplicate/i.test(detail)) {
          setFieldInvalid(emailEl, true, "Email already registered.");
        }
        throw new Error(detail);
      }

      // Thành công → điều hướng về Login
      showAlert("Account created successfully. Redirecting to login…", "success");
      setTimeout(() => { window.location.href = "./login.html"; }, 800);
      form.reset();
      form.classList.remove("was-validated");
      // Reset toggles
      if (pwdEl && togglePwd) {
        pwdEl.type = "password";
        togglePwd.innerHTML = `<i class="bi bi-eye"></i>`;
        togglePwd.setAttribute("aria-pressed", "false");
      }
      if (confirmEl && toggleConfirm) {
        confirmEl.type = "password";
        toggleConfirm.innerHTML = `<i class="bi bi-eye"></i>`;
        toggleConfirm.setAttribute("aria-pressed", "false");
      }
    } catch (err) {
      showAlert(String(err?.message || err || "Registration failed"));
    } finally {
      setLoading(false);
    }
  }

  if (form && btn) {
    form.addEventListener("submit", handleSubmit);
  }
})();
