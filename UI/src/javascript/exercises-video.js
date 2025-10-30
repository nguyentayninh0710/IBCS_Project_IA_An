// exercises-video.js — show one exercise video (from querystring or API)
(() => {
  "use strict";

  const API_BASE = document.body?.getAttribute("data-api-base")?.trim()
    || `${location.protocol}//${location.hostname}:8000`;

  const qs = new URLSearchParams(location.search);
  const exerciseId = qs.get("exercise_id");
  const passed = {
    name: qs.get("name"),
    category: qs.get("category"),
    unit: qs.get("unit"),
    difficulty: qs.get("difficulty"),
    body_area: qs.get("body_area"),
    description: qs.get("description"),
    video: qs.get("video"),
  };

  // Elements
  const pageTitle = document.getElementById("pageTitle");
  const subTitle = document.getElementById("subTitle");
  const videoWrap = document.getElementById("videoWrap");
  const noVideo = document.getElementById("noVideo");
  const badgeDifficulty = document.getElementById("badgeDifficulty");
  const badgeUnit = document.getElementById("badgeUnit");
  const descText = document.getElementById("descText");
  const openInYouTube = document.getElementById("openInYouTube");

  const bodyAreaItems = Array.from(document.querySelectorAll(".body-area-list li"));

  function setBodyArea(area) {
    bodyAreaItems.forEach(li => {
      const key = li.getAttribute("data-area");
      if (!area) { li.classList.remove("active"); return; }
      if (area === "full_body") { li.classList.add("active"); return; }
      li.classList.toggle("active", key === area);
    });
  }

  function toEmbedUrl(url) {
    if (!url) return "";
    try {
      const u = new URL(url);
      if (u.hostname.includes("youtube.com")) {
        const vid = u.searchParams.get("v");
        const base = `https://www.youtube.com/embed/${vid || ""}`;
        const si = u.searchParams.get("si");
        return si ? `${base}?si=${encodeURIComponent(si)}` : base;
      }
      if (u.hostname === "youtu.be") {
        const id = u.pathname.replace("/", "");
        return `https://www.youtube.com/embed/${id}`;
      }
      return url;
    } catch { return url; }
  }

  function renderVideo(url) {
    if (!url) { noVideo.classList.remove("d-none"); return; }
    const embed = toEmbedUrl(url);
    const iframe = document.createElement("iframe");
    iframe.width = "560"; iframe.height = "315";
    iframe.src = embed; iframe.title = "YouTube video player";
    iframe.frameBorder = "0";
    iframe.setAttribute("allow","accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share");
    iframe.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
    iframe.allowFullscreen = true;

    videoWrap.innerHTML = "";
    videoWrap.appendChild(iframe);

    openInYouTube.disabled = false;
    openInYouTube.onclick = () => window.open(url, "_blank", "noopener");
  }

  function fillHeader(category, name) {
    pageTitle.textContent = "Exercise Video";
    subTitle.textContent = `${category || "—"} › ${name || "—"}`;
  }
  function fillBadges(difficulty, unit) {
    badgeDifficulty.textContent = `Difficulty: ${difficulty || "—"}`;
    badgeUnit.textContent = `Unit: ${unit || "—"}`;
  }
  function fillDesc(text) {
    descText.textContent = text && text.trim() ? text : "No description.";
  }

  async function fetchExerciseById(id) {
    const urls = [`${API_BASE}/api/exercises/${id}`, `${API_BASE}/exercises/${id}`];
    for (const url of urls) {
      try { const res = await fetch(url); if (res.ok) return await res.json(); } catch {}
    }
    return null;
  }

  async function init() {
    let data = { ...passed };

    // If missing info but we have ID, fetch
    const needFetch = (!!exerciseId) && (!data.name || !data.category || !data.unit ||
                                        !data.difficulty || !data.body_area || !data.video);
    if (needFetch) {
      const fetched = await fetchExerciseById(exerciseId);
      if (fetched) {
        data = {
          name: data.name ?? fetched.name,
          category: data.category ?? fetched.category,
          unit: data.unit ?? fetched.unit,
          difficulty: data.difficulty ?? fetched.difficulty,
          body_area: data.body_area ?? fetched.body_area,
          description: data.description ?? fetched.description,
          video: data.video ?? fetched.video_url,
        };
      }
    }

    fillHeader(data.category, data.name);
    setBodyArea(data.body_area);
    fillBadges(data.difficulty, data.unit);
    fillDesc(data.description);
    renderVideo(data.video);
  }

  init();
})();
