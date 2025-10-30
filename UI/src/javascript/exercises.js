// exercises.js — List theo workout (nếu có ?workout_id=) + search + client-side pagination + DEMO fallback
(function () {
  "use strict";

  // -------- DEMO DATA (same schema as table exercises) --------
  const DEMO_DATA = [
    { exercise_id: 1, name: "Bodyweight Squat", category: "strength", unit: "reps", difficulty: "beginner", body_area: "lower", video_url: "", description: "Air squat focus on depth" },
    { exercise_id: 2, name: "Plank Hold", category: "mobility", unit: "seconds", difficulty: "beginner", body_area: "core", video_url: "", description: "" },
    { exercise_id: 3, name: "Jumping Jacks", category: "cardio", unit: "seconds", difficulty: "beginner", body_area: "full_body", video_url: "", description: "" },
    { exercise_id: 4, name: "Push-up", category: "strength", unit: "reps", difficulty: "intermediate", body_area: "upper", video_url: "", description: "" },
    { exercise_id: 5, name: "Glute Bridge", category: "strength", unit: "seconds", difficulty: "beginner", body_area: "lower", video_url: "", description: "" },
    { exercise_id: 6, name: "Mountain Climbers", category: "cardio", unit: "seconds", difficulty: "intermediate", body_area: "core", video_url: "", description: "" },
    { exercise_id: 7, name: "Lunges", category: "strength", unit: "reps", difficulty: "beginner", body_area: "lower", video_url: "", description: "" },
    { exercise_id: 8, name: "High Knees", category: "cardio", unit: "seconds", difficulty: "beginner", body_area: "full_body", video_url: "", description: "" },
    { exercise_id: 9, name: "Shoulder Taps", category: "mobility", unit: "reps", difficulty: "beginner", body_area: "upper", video_url: "", description: "" },
    { exercise_id: 10, name: "Side Plank", category: "mobility", unit: "seconds", difficulty: "intermediate", body_area: "core", video_url: "", description: "" },
  ];

  // ------------------ CONFIG ------------------
  const API_BASE = document.body?.getAttribute("data-api-base")?.trim()
    || `${location.protocol}//${location.hostname}:8000`;

  const qs = new URLSearchParams(location.search);
  const WORKOUT_ID = qs.get("workout_id");         // từ workout.js
  const WORKOUT_NAME = qs.get("name") || "";       // để hiển thị heading
  const FORCE_DEMO = qs.get("demo") === "1";

  // Nếu có workout_id: ưu tiên endpoint JOIN
  const ENDPOINTS = WORKOUT_ID
    ? [`${API_BASE}/api/workouts/${encodeURIComponent(WORKOUT_ID)}/exercises`]
    : [`${API_BASE}/api/exercises`, `${API_BASE}/exercises`]; // fallback khi mở trực tiếp exercises.html

  // ------------------ STATE ------------------
  let ALL = [];
  let FILTERED = [];
  let currentPage = 1;
  const pageSize = 8;

  // ------------------ ELTS ------------------
  const list = document.getElementById("list");
  const pager = document.getElementById("pager");
  const searchInput = document.getElementById("searchInput");
  const searchBtn = document.getElementById("searchBtn");
  const emptyState = document.getElementById("emptyState");
  const titleEl = document.getElementById("pageTitle");
  const subTitleEl = document.getElementById("subTitle");
  const backEl = document.getElementById("backLink");

  // === NEW: trang video (có thể override bằng data-exercise-video-url trên <body>)
  const VIDEO_PAGE = document.body?.getAttribute("data-exercise-video-url")?.trim()
    || "exercises-video.html";

  // ------------------ HELPERS ------------------
  const text = (v) => (v ?? "").toString();
  const escapeHtml = (s) =>
    s.replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[ch]));

  // NEW: build URL tới trang video kèm params
  function buildVideoHref(e) {
    const q = new URLSearchParams({
      exercise_id: String(e.exercise_id ?? ""),
      name: e.name ?? "",
      category: e.category ?? "",
      unit: e.unit ?? "",
      difficulty: e.difficulty ?? "",
      body_area: e.body_area ?? "",
      description: e.description ?? "",
      // nếu không có video_url, trang video sẽ fetch bằng exercise_id
      video: e.video_url ?? ""
    });
    return `${VIDEO_PAGE}?${q.toString()}`;
  }

  // Chuẩn hoá item: hỗ trợ cả schema exercises thuần và JOIN (workout_exercises + exercises)
  function normalizeItem(it) {
    return {
      // core fields (exercises)
      exercise_id: it.exercise_id ?? it.id ?? it.exerciseId,
      name: it.name,
      category: it.category,
      unit: it.unit,
      difficulty: it.difficulty,
      body_area: it.body_area ?? it.bodyArea,
      video_url: it.video_url ?? it.videoUrl,
      description: it.description,
      // JOIN fields (nếu có)
      workout_id: it.workout_id ?? null,
      seq_no: it.seq_no ?? null,
      target_reps: it.target_reps ?? null,
      target_seconds: it.target_seconds ?? null,
      rest_seconds: it.rest_seconds ?? null,
    };
  }

  function iconForCategory(cat) {
    const common = `class="gym-svg" viewBox="0 0 64 64" stroke="currentColor" fill="none" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"`;
    const cardio = `<svg ${common}><path d="M12 33h10l4-8 6 14 4-8h16"/></svg>`;
    const strength = `<svg ${common}><line x1="8" y1="32" x2="56" y2="32"/><rect x="10" y="24" width="6" height="16"/><rect x="48" y="24" width="6" height="16"/></svg>`;
    const mobility = `<svg ${common}><path d="M20 44c8-8 16-8 24 0M20 20c8 8 16 8 24 0"/></svg>`;
    switch ((cat || "").toLowerCase()) {
      case "cardio": return cardio;
      case "strength": return strength;
      default: return mobility;
    }
  }

  // ------------------ RENDER ------------------
  function renderHeader() {
    if (titleEl) titleEl.textContent = WORKOUT_ID ? "Workout Exercises" : "All Exercises";
    if (subTitleEl) {
      if (WORKOUT_ID) {
        const name = decodeURIComponent(WORKOUT_NAME || "");
        subTitleEl.textContent = name ? `Workout: ${name} (ID ${WORKOUT_ID})` : `Workout ID: ${WORKOUT_ID}`;
      } else {
        subTitleEl.textContent = "Browse the full exercise library";
      }
    }
    if (backEl && WORKOUT_ID) {
      backEl.classList.remove("d-none");
      const backHref = document.body?.getAttribute("data-workouts-url")?.trim() || "workout.html";
      backEl.setAttribute("href", backHref);
    }
  }

  function renderList() {
    const total = FILTERED.length;
    const start = (currentPage - 1) * pageSize;
    const pageItems = FILTERED.slice(start, start + pageSize);

    list.innerHTML = "";
    if (pageItems.length === 0) {
      list.classList.add("d-none");
      emptyState.classList.remove("d-none");
    } else {
      list.classList.remove("d-none");
      emptyState.classList.add("d-none");

      const frag = document.createDocumentFragment();
      pageItems.forEach(e => {
        const item = document.createElement("div");
        item.className = "exercise-card";

        const seqBadge = (e.seq_no != null)
          ? `<span class="badge bg-dark me-2">#${e.seq_no}</span>`
          : "";

        let targetLine = "";
        if (e.target_reps != null || e.target_seconds != null || e.rest_seconds != null) {
          const parts = [];
          if (e.target_reps != null) parts.push(`${e.target_reps} reps`);
          if (e.target_seconds != null) parts.push(`${e.target_seconds} sec`);
          if (e.rest_seconds != null) parts.push(`rest ${e.rest_seconds}s`);
          targetLine = `<dt>TARGET</dt><dd>${escapeHtml(parts.join(" · "))}</dd>`;
        }

        // NEW: luôn link tới trang video (kể cả khi video_url null — trang video sẽ tự fetch)
        const watchBtn = `<a class="btn btn-sm btn-dark mt-2" href="${buildVideoHref(e)}">Watch Video</a>`;

        item.innerHTML = `
          <div class="exercise-thumb">${iconForCategory(e.category)}</div>
          <div class="exercise-meta">
            <dl class="mb-0">
              <dt>NAME</dt>
              <dd>${seqBadge}${escapeHtml(text(e.name))}</dd>
              <dt>CATEGORY</dt><dd class="text-capitalize">${escapeHtml(text(e.category))}</dd>
              <dt>UNIT</dt><dd class="text-capitalize">${escapeHtml(text(e.unit))}</dd>
              <dt>DIFFICULTY</dt><dd class="text-capitalize">${escapeHtml(text(e.difficulty))}</dd>
              <dt>BODY AREA</dt><dd class="text-capitalize">${escapeHtml(text(e.body_area))}</dd>
              ${targetLine}
              ${watchBtn}
            </dl>
          </div>
        `;
        frag.appendChild(item);
      });
      list.appendChild(frag);
    }
    renderPager(total);
  }

  function renderPager(total) {
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    currentPage = Math.min(currentPage, totalPages);
    const btn = (l, p, d = false, a = false) =>
      `<button class="page-btn ${a ? "active" : ""}" data-page="${p}" ${d ? "disabled" : ""}>${l}</button>`;
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
        if (!Number.isNaN(to) && to !== currentPage) { currentPage = to; renderList(); }
      });
    });
  }

  function applySearch() {
    const q = (searchInput?.value || "").trim().toLowerCase();
    FILTERED = !q ? [...ALL] :
      ALL.filter(e => [
        e.name, e.category, e.unit, e.difficulty, e.body_area
      ].map(v => (v ?? "").toString().toLowerCase()).join(" ").includes(q));
    currentPage = 1;
    renderList();
  }

  // ------------------ DATA ------------------
  async function fetchData() {
    if (FORCE_DEMO) { useDemo(); return; }

    let json;
    for (const url of ENDPOINTS) {
      try {
        const res = await fetch(url);   // GET public list
        if (!res.ok) continue;
        json = await res.json();
        break;
      } catch { /* try next */ }
    }
    if (!json) { useDemo(); return; }

    // JOIN endpoint trả về mảng; /api/exercises cũng trả mảng
    const items = Array.isArray(json) ? json : (json.items ?? []);
    ALL = items.map(normalizeItem);
    if (WORKOUT_ID) {
      // đảm bảo sort theo seq_no tăng dần nếu data chưa sort
      ALL.sort((a, b) => (a.seq_no ?? 1) - (b.seq_no ?? 1));
    }
    if (ALL.length === 0) { useDemo(); return; }
    FILTERED = [...ALL];
    renderHeader();
    renderList();
  }

  function useDemo() {
    ALL = DEMO_DATA.map(normalizeItem);
    FILTERED = [...ALL];
    renderHeader();
    renderList();
  }

  // ------------------ INIT ------------------
  searchInput?.addEventListener("input", applySearch);
  searchBtn?.addEventListener("click", applySearch);
  renderHeader();
  fetchData();
})();
