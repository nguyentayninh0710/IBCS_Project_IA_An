// workouts.js — Workouts grid + auth guard (requires login) + search + client-side pagination
(function () {
  "use strict";

  // ======================
  // Auth guard + utilities
  // ======================
  const API_BASE = document.body?.getAttribute("data-api-base")?.trim()
    || `${location.protocol}//${location.hostname}:8000`;

  const ROUTES = {
    login: `${API_BASE}/api/auth/login`,
    refresh: `${API_BASE}/api/auth/refresh`,
    me: `${API_BASE}/api/me`,
    logout: `${API_BASE}/api/auth/logout`,
  };

  const LS = {
    access: "auth.access_token",
    accessExp: "auth.access_expires_at",
    refresh: "auth.refresh_token",
    refreshExp: "auth.refresh_expires_at",
    me: "auth.me",
  };
  const EXP_LEEWAY = 30;

  const $ = (s) => document.querySelector(s);
  const epochNow = () => Math.floor(Date.now() / 1000);
  const getAT = () => localStorage.getItem(LS.access) || "";
  const getRT = () => localStorage.getItem(LS.refresh) || "";
  const isAccessExpired = () => {
    const exp = Number(localStorage.getItem(LS.accessExp) || 0);
    return !exp || epochNow() >= (exp - EXP_LEEWAY);
  };
  const isRefreshExpired = () => {
    const exp = Number(localStorage.getItem(LS.refreshExp) || 0);
    return !exp || epochNow() >= (exp - EXP_LEEWAY);
  };
  const clearTokens = () => {
    localStorage.removeItem(LS.access);
    localStorage.removeItem(LS.accessExp);
    localStorage.removeItem(LS.refresh);
    localStorage.removeItem(LS.refreshExp);
    // Giữ LS.me để hiện tạm tên user nếu muốn, hoặc bỏ comment để xoá:
    // localStorage.removeItem(LS.me);
  };

  let refreshing = null;

  async function refreshAccessToken() {
    if (refreshing) return refreshing;
    const rt = getRT();
    if (!rt) throw new Error("No refresh token");

    refreshing = (async () => {
      const res = await fetch(ROUTES.refresh, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify({ refresh_token: rt }),
        cache: "no-store",
      });
      const data = await (async () => { try { return await res.json(); } catch { return null; } })();
      refreshing = null;
      if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);

      localStorage.setItem(LS.access, data.access_token);
      localStorage.setItem(LS.accessExp, String(data.access_expires_at));
      localStorage.setItem(LS.refresh, data.refresh_token);
      localStorage.setItem(LS.refreshExp, String(data.refresh_expires_at));
      return true;
    })();

    return refreshing;
  }

  async function ensureAccessToken() {
    if (!isAccessExpired()) return;
    if (isRefreshExpired()) throw new Error("Session expired.");
    await refreshAccessToken();
  }

  async function apiFetch(url, options = {}, { auth = "access", retryOn401 = true } = {}) {
    const base = new Headers({ Accept: "application/json" });
    const user = new Headers(options.headers || {});
    const headers = new Headers([...base, ...user]);

    const opts = { method: "GET", ...options, headers, cache: "no-store" };
    if (opts.body && !(opts.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }

    if (auth === "access") {
      await ensureAccessToken();
      const at = getAT();
      if (at) headers.set("Authorization", `Bearer ${at}`);
    }

    let res = await fetch(url, opts);

    if (res.status === 401 && auth === "access" && retryOn401) {
      try {
        if (!isRefreshExpired()) {
          await refreshAccessToken();
          const retryHeaders = new Headers({ Accept: "application/json" });
          const at2 = getAT();
          if (at2) retryHeaders.set("Authorization", `Bearer ${at2}`);
          res = await fetch(url, { method: opts.method, body: opts.body, headers: retryHeaders, cache: "no-store" });
        }
      } catch { /* ignore */ }
    }

    const ct = res.headers.get("content-type") || "";
    const data = ct.includes("application/json") ? await res.json().catch(() => null) : null;
    if (!res.ok) throw new Error(data?.detail || data?.message || `HTTP ${res.status}`);
    return data;
  }

  async function loadMeOrRedirect() {
    try {
      if (!getRT() || isRefreshExpired()) {
        location.href = "./login.html";
        return;
      }
      // Vẽ tạm tên user từ cache nếu có
      const cached = (() => { try { return JSON.parse(localStorage.getItem(LS.me) || "{}"); } catch { return {}; } })();
      if (cached?.username || cached?.email || cached?.full_name) paintUser(cached);

      // Lấy me từ API (chuẩn nhất)
      const me = await apiFetch(ROUTES.me, { method: "GET" }, { auth: "access" });
      localStorage.setItem(LS.me, JSON.stringify(me || {}));
      paintUser(me);
    } catch {
      clearTokens();
      location.href = "./login.html";
    }
  }

  function paintUser(me) {
    const greet = $("#greetName");
    if (greet) {
      const name = me?.full_name || me?.username || me?.email || "User";
      greet.textContent = `${name}`;
    }
  }

  async function doLogout(e) {
    e?.preventDefault?.();
    try {
      const at = getAT();
      if (at) {
        await fetch(ROUTES.logout, { method: "POST", headers: { "Authorization": `Bearer ${at}` } });
      }
    } catch { /* ignore */ }
    clearTokens();
    location.href = "./login.html";
  }

  // Khởi chạy guard + logout wiring
  document.addEventListener("DOMContentLoaded", () => {
    const logoutBtn = document.getElementById("logoutBtn");
    if (logoutBtn) logoutBtn.addEventListener("click", doLogout);
    loadMeOrRedirect();
  });

  // =========================
  // Workouts listing (secure)
  // =========================

  // ---------- DEMO DATA ----------
  const DEMO_DATA = [
    // Giữ nguyên demo nếu cần bật bằng ?demo=1
    { workout_id: 1, name: "Morning Cardio Blast", type: "cardio", intensity: "medium", estimated_minutes: 15, level: "beginner", created_by: 101, created_by_name: "Coach Anna" },
    { workout_id: 2, name: "Full-Body Strength A", type: "strength", intensity: "high", estimated_minutes: 20, level: "intermediate", created_by: 102, created_by_name: "Coach Ben" },
    { workout_id: 3, name: "Mixed Circuit Lite", type: "mixed", intensity: "low", estimated_minutes: 10, level: "beginner", created_by: 101, created_by_name: "Coach Anna" },
  ];

  // Ưu tiên /api/workouts
  const ENDPOINTS = [`${API_BASE}/api/workouts`, `${API_BASE}/workouts`];
  const FORCE_DEMO = new URLSearchParams(location.search).get("demo") === "1";
  const EX_PAGE = document.body?.getAttribute("data-exercises-url")?.trim() || "exercises.html";

  // ------------------ STATE ------------------
  let ALL = [];
  let FILTERED = [];
  let currentPage = 1;
  const pageSize = 9;

  // ------------------ ELTS ------------------
  const grid = document.getElementById("grid");
  const pager = document.getElementById("pager");
  const searchInput = document.getElementById("searchInput");
  const searchBtn = document.getElementById("searchBtn");
  const emptyState = document.getElementById("emptyState");

  // ------------------ HELPERS & RENDER ------------------
  function svgIcon() {
    return `<svg class="gym-svg" viewBox="0 0 24 24" fill="currentColor"><path d="M7 20h2l1-3h4l1 3h2l-1.2-3.6A2 2 0 0 0 14 15h-4a2 2 0 0 0-1.8 1.4L7 20zM5 9h14v2H5V9zm2-5h2v3H7V4zm8 0h2v3h-2V4z"/></svg>`;
  }
  function iconForType(type) {
    const common = `class="gym-svg" viewBox="0 0 64 64" stroke="currentColor" fill="none" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"`;
    const cardio = `<svg ${common}><path d="M46 12c-4-1-8 1-10 5-2-4-6-6-10-5-6 2-10 10-6 18 3 7 12 13 16 16 4-3 13-9 16-16 4-8 0-16-6-18z"/><path d="M12 33h10l4-8 6 14 4-8h16"/></svg>`;
    const strength = `<svg ${common}><line x1="8" y1="32" x2="56" y2="32"/><rect x="10" y="24" width="6" height="16"/><rect x="48" y="24" width="6" height="16"/><rect x="18" y="26" width="6" height="12"/><rect x="40" y="26" width="6" height="12"/></svg>`;
    const mixed = `<svg ${common}><path d="M22 26a10 10 0 0120 0"/><path d="M16 40a16 14 0 1032 0 16 14 0 10-32 0z"/><path d="M26 24h12"/></svg>`;
    switch ((type || "").toLowerCase()) { case "cardio": return cardio; case "strength": return strength; default: return mixed; }
  }
  const text = v => (v ?? "").toString();
  const escapeHtml = s => s.replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[ch]));
  const creatorName = w => w.created_by_name || (w.created_by ? `User #${w.created_by}` : "—");
  function normalizeItem(it) {
    return {
      workout_id: it.workout_id ?? it.id ?? it.workoutId,
      name: it.name,
      type: it.type,
      intensity: it.intensity,
      estimated_minutes: it.estimated_minutes ?? it.estimatedMinutes,
      level: it.level,
      created_by: it.created_by ?? it.createdBy,
      created_by_name: it.created_by_name ?? it.createdByName
    };
  }

  function renderGrid() {
    const total = FILTERED.length;
    const start = (currentPage - 1) * pageSize;
    const pageItems = FILTERED.slice(start, start + pageSize);

    grid.innerHTML = "";
    if (pageItems.length === 0) {
      grid.classList.add("d-none");
      emptyState?.classList.remove("d-none");
    } else {
      grid.classList.remove("d-none");
      emptyState?.classList.add("d-none");
      const frag = document.createDocumentFragment();
      pageItems.forEach(w => {
        const col = document.createElement("div");
        col.className = "col-12 col-md-6 col-lg-4";
        col.innerHTML = `
          <a class="text-decoration-none text-dark d-block h-100"
             href="${EX_PAGE}?workout_id=${encodeURIComponent(w.workout_id)}&name=${encodeURIComponent(w.name)}">
            <div class="workout-card h-100">
              <div class="workout-thumb">${iconForType(w.type)}</div>
              <div class="workout-meta">
                <dl class="mb-0">
                  <dt>NAME</dt><dd>${escapeHtml(text(w.name))}</dd>
                  <dt>CREATED BY</dt><dd>${escapeHtml(text(creatorName(w)))}</dd>
                  <dt>TYPE</dt><dd class="text-capitalize">${escapeHtml(text(w.type))}</dd>
                  <dt>LEVEL</dt><dd class="text-capitalize">${escapeHtml(text(w.level))}</dd>
                  <dt>INTENSITY</dt><dd class="text-capitalize">${escapeHtml(text(w.intensity))}</dd>
                </dl>
              </div>
            </div>
          </a>`;
        frag.appendChild(col);
      });
      grid.appendChild(frag);
    }
    renderPager(total);
  }

  function renderPager(total) {
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    currentPage = Math.min(currentPage, totalPages);
    const btn = (l, p, d = false, a = false) => `<button class="page-btn ${a ? "active" : ""}" data-page="${p}" ${d ? "disabled" : ""}>${l}</button>`;
    let html = "";
    html += btn("≪", 1, currentPage === 1);
    html += btn("‹", Math.max(1, currentPage - 1), currentPage === 1);
    const win = 2, from = Math.max(1, currentPage - win), to = Math.min(totalPages, currentPage + win);
    for (let p = from; p <= to; p++) html += btn(`${p}`, p, false, p === currentPage);
    html += btn("›", Math.min(totalPages, currentPage + 1), currentPage === totalPages);
    html += btn("≫", totalPages, currentPage === totalPages);
    pager.innerHTML = html;
    pager.querySelectorAll(".page-btn").forEach(b => {
      b.addEventListener("click", () => {
        const to = parseInt(b.getAttribute("data-page"), 10);
        if (!Number.isNaN(to) && to !== currentPage) { currentPage = to; renderGrid(); }
      });
    });
  }

  function applySearch() {
    const q = (searchInput?.value || "").trim().toLowerCase();
    FILTERED = !q ? [...ALL] :
      ALL.filter(w => [w.name, w.type, w.level, w.intensity, creatorName(w)]
        .map(v => (v ?? "").toString().toLowerCase()).join(" ").includes(q));
    currentPage = 1; renderGrid();
  }

  // ------------------ DATA ------------------
  async function fetchWorkouts() {
    // YÊU CẦU ĐĂNG NHẬP: dùng apiFetch (Authorization + refresh tự động)
    if (FORCE_DEMO) { useDemo(); return; }

    let json = null;
    for (const url of ENDPOINTS) {
      try {
        json = await apiFetch(url, { method: "GET" }, { auth: "access" });
        if (json) break;
      } catch {
        // thử endpoint tiếp theo
      }
    }

    if (!json) { useDemo(); return; }
    const items = Array.isArray(json) ? json : (json.items ?? []);
    ALL = items.map(normalizeItem);
    if (ALL.length === 0) { useDemo(); return; }
    FILTERED = [...ALL];
    renderGrid();
  }

  function useDemo() {
    ALL = DEMO_DATA.map(normalizeItem);
    FILTERED = [...ALL];
    renderGrid();
  }

  // ------------------ INIT ------------------
  document.addEventListener("DOMContentLoaded", () => {
    searchInput?.addEventListener("input", applySearch);
    searchBtn?.addEventListener("click", applySearch);
    // fetch sau khi guard đã chạy loadMeOrRedirect (ở trên cùng)
    // Tuy hai listener đều trên DOMContentLoaded, guard sẽ redirect sớm nếu chưa login.
    fetchWorkouts();
  });

})();
