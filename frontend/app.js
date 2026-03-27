/* =========================================================
   AM Discovery — Single-Page App
   ========================================================= */

"use strict";

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------
const API = {
  async get(path) {
    const r = await fetch(path);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  },
  async post(path, body) {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    return r.json();
  },
  async put(path, body) {
    const r = await fetch(path, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    return r.json();
  },
  async del(path) {
    const r = await fetch(path, { method: "DELETE" });
    return r.json();
  },
  async patch(path, body) {
    const r = await fetch(path, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    return r.json();
  },
};

// ---------------------------------------------------------------------------
// Utility helpers
// ---------------------------------------------------------------------------
const $ = id => document.getElementById(id);
const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
};

function formatDate(d) {
  if (!d || d === "Unknown") return "—";
  if (/^\d{4}-00-00/.test(d)) return d.slice(0, 4);
  try {
    return new Date(d + "T00:00:00Z").toLocaleDateString("en-GB", { year: "numeric", month: "short", day: "numeric" });
  } catch { return d; }
}

function isFutureDate(d) {
  if (!d || /^\d{4}-00-00/.test(d)) return false;
  try {
    return new Date(d + "T00:00:00Z") > new Date();
  } catch { return false; }
}

function timeAgo(isoStr) {
  if (!isoStr) return "never";
  const ts = typeof isoStr === "number" ? isoStr * 1000 : new Date(isoStr + "Z").getTime();
  const diff = Date.now() - ts;
  const m = Math.floor(diff / 60000);
  if (m < 1)  return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function formatDuration(ms) {
  if (!ms) return "";
  const s = Math.round(ms / 1000);
  const m = Math.floor(s / 60);
  return `${m}:${(s % 60).toString().padStart(2, "0")}`;
}

const RELEASE_TYPE_LABELS = {
  "main-albums":        "Albums",
  "compilation-albums": "Compilations",
  "live-albums":        "Live Albums",
  "singles-eps":        "Singles & EPs",
};
const RELEASE_TYPE_ORDER = ["main-albums", "singles-eps", "compilation-albums", "live-albums"];

const FORMAT_LABELS = {
  "lossy-stereo":    "AAC",
  "lossless":        "Lossless",
  "hi-res-lossless": "Hi-Res Lossless",
  "atmos":           "Dolby Atmos",
  "spatial":         "Spatial Audio",
  "adm":             "Apple Digital Masters",
};

function formatBadges(formats) {
  if (!formats || !formats.length) return null;
  const wrap = el("div", "format-badges");
  for (const key of formats) {
    const label = FORMAT_LABELS[key];
    if (!label) continue;
    const span = el("span", `format-badge ${key}`, label);
    wrap.appendChild(span);
  }
  return wrap.childElementCount ? wrap : null;
}

function artworkEl(artworkUrl, cls) {
  if (artworkUrl) {
    const img = el("img", cls || "album-artwork");
    img.src = artworkUrl;
    img.alt = "";
    img.loading = "lazy";
    img.onerror = () => { img.replaceWith(placeholderEl(cls)); };
    return img;
  }
  return placeholderEl(cls);
}

function placeholderEl(cls) {
  const d = el("div",
    cls === "album-artwork"       ? "album-artwork-placeholder" :
    cls === "modal-artwork"       ? "modal-artwork-placeholder" :
    cls === "modal-artwork-thumb" ? "modal-artwork-thumb-placeholder" :
    "album-artwork-placeholder"
  );
  d.textContent = "♫";
  return d;
}

function sfChips(storefronts) {
  const div = el("div", "sf-chips");
  (storefronts || []).forEach(sf => {
    const c = el("span", `sf-chip ${sf.toLowerCase()}`);
    c.textContent = sf.toUpperCase();
    div.appendChild(c);
  });
  return div;
}

function skeletonGrid(n = 12) {
  const grid = el("div", "loading-grid");
  for (let i = 0; i < n; i++) {
    const card = el("div", "skeleton-card");
    card.innerHTML = `<div class="skeleton-art"></div><div class="skeleton-line"></div><div class="skeleton-line short"></div>`;
    grid.appendChild(card);
  }
  return grid;
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const state = {
  watchedIds: new Set(),
  currentPage: 1,
  currentTotal: 0,
  currentQuery: "",
  currentStorefront: "",
  perPage: 48,
  configuredStorefronts: null,
  discoveryStorefronts: null,
  metadataStorefront: localStorage.getItem("metadataStorefront") || "",
  alwaysIncludeMY: localStorage.getItem("alwaysIncludeMY") === "true",
  homeStorefront: "",
  artistViewMode: "chrono",   // "chrono" | "grouped"
  artistTypeFilter: "",       // "" = all, else a release_type value
};

// ---------------------------------------------------------------------------
// Status bar
// ---------------------------------------------------------------------------
async function refreshStatus() {
  try {
    const s = await API.get("/api/status");
    const dot = $("status-dot");
    const val = $("status-last-run");
    const roomErrors = s.room_errors || [];
    if (s.is_running) {
      dot.className = "status-dot spin";
      val.textContent = "Scanning…";
    } else if (roomErrors.length > 0) {
      dot.className = "status-dot warn";
      val.textContent = s.last_run ? timeAgo(s.last_run.ran_at) : "never";
    } else {
      dot.className = "status-dot ok";
      val.textContent = s.last_run ? timeAgo(s.last_run.ran_at) : "never";
    }
    let warn = $("status-room-errors");
    if (roomErrors.length > 0) {
      if (!warn) {
        warn = document.createElement("div");
        warn.id = "status-room-errors";
        warn.className = "status-room-errors";
        $("status-card").insertAdjacentElement("afterend", warn);
      }
      const sfList = roomErrors.map(sf => sf.toUpperCase()).join(", ");
      warn.textContent = `⚠ Room fetch failed: ${sfList}`;
    } else if (warn) {
      warn.remove();
    }
  } catch {}
}

async function triggerRefresh() {
  const btn = $("btn-refresh");
  btn.disabled = true;
  btn.classList.add("spinning");
  const dot = $("status-dot");
  dot.className = "status-dot spin";
  $("status-last-run").textContent = "Scanning…";
  try {
    await API.post("/api/refresh", {});
  } catch {}
  // Poll until done
  const poll = setInterval(async () => {
    try {
      const s = await API.get("/api/status");
      if (!s.is_running) {
        clearInterval(poll);
        btn.disabled = false;
        btn.classList.remove("spinning");
        await refreshStatus();
        // Reload current page
        route(location.hash || "#/");
      }
    } catch {}
  }, 2000);
}

// ---------------------------------------------------------------------------
// Metadata source widget
// ---------------------------------------------------------------------------
function updateArtistExtLink() {
  const extLink = document.querySelector(".artist-ext-link");
  if (!extLink) return;
  const base = extLink.dataset.baseUrl;
  const sf = state.metadataStorefront;
  extLink.href = sf
    ? base.replace(/music\.apple\.com\/[a-z]{2}\//, `music.apple.com/${sf}/`)
    : base;
}

// ---------------------------------------------------------------------------
function updateFetchArtistBtn() {
  const fetchBtn = document.querySelector(".btn-fetch-artist");
  if (!fetchBtn || fetchBtn.disabled) return;
  const sf = state.metadataStorefront;
  fetchBtn.textContent = sf ? `↓ Fetch from ${sf.toUpperCase()}` : "↓ Fetch All";
}

function updateSrcBadge() {
  const badge = $("sidebar-src-badge");
  if (!badge) return;
  const sf = state.metadataStorefront;
  const home = state.homeStorefront;
  const showHome = state.alwaysIncludeMY && sf && home && sf !== home;
  if (sf && showHome) {
    badge.innerHTML = `${sf.toUpperCase()}<span class="badge-home">+${home.toUpperCase()}</span>`;
  } else {
    badge.textContent = sf ? sf.toUpperCase() : "—";
  }
  badge.className = `sidebar-src-badge${sf ? ` ${sf}` : ""}`;
}

function renderMetaSourceWidget() {
  const chips = $("meta-source-chips");
  if (!chips) return;
  chips.innerHTML = "";
  updateSrcBadge();

  const storefronts = state.configuredStorefronts || [];

  // "Off" option
  const offBtn = el("button", `meta-src-btn${!state.metadataStorefront ? " active" : ""}`, "Off");
  offBtn.title = "Use cached metadata";
  offBtn.addEventListener("click", () => {
    state.metadataStorefront = "";
    localStorage.setItem("metadataStorefront", "");
    renderMetaSourceWidget();
    updateFetchArtistBtn();
    updateArtistExtLink();
  });
  chips.appendChild(offBtn);

  storefronts.forEach(sf => {
    const isActive = state.metadataStorefront === sf;
    const btn = el("button", `meta-src-btn ${sf}${isActive ? " active" : ""}`, sf.toUpperCase());
    btn.title = `Fetch metadata from ${sf.toUpperCase()} storefront`;
    btn.addEventListener("click", () => {
      state.metadataStorefront = sf;
      localStorage.setItem("metadataStorefront", sf);
      renderMetaSourceWidget();
      updateFetchArtistBtn();
      updateArtistExtLink();
    });
    chips.appendChild(btn);
  });

  // "+HOME" comparison toggle — only shown when a non-home storefront is selected
  const home = state.homeStorefront;
  if (home && state.metadataStorefront && state.metadataStorefront !== home) {
    const label = `+${home.toUpperCase()}`;
    const myToggle = el("button", `meta-src-btn my-toggle${state.alwaysIncludeMY ? " active" : ""}`, label);
    myToggle.title = state.alwaysIncludeMY
      ? `Also fetching ${home.toUpperCase()} for tracklist comparison (click to disable)`
      : `Also fetch ${home.toUpperCase()} storefront to compare tracklists`;
    myToggle.addEventListener("click", () => {
      state.alwaysIncludeMY = !state.alwaysIncludeMY;
      if (state.alwaysIncludeMY) {
        localStorage.setItem("alwaysIncludeMY", "true");
      } else {
        localStorage.removeItem("alwaysIncludeMY");
      }
      renderMetaSourceWidget();
    });
    chips.appendChild(myToggle);
  }
}

async function initMetaSourceWidget() {
  if (state.configuredStorefronts === null) {
    try {
      const cfg = await API.get("/api/config");
      state.configuredStorefronts = cfg.check_storefronts || [];
      state.homeStorefront = cfg.home_storefront || "my";
    } catch {
      state.configuredStorefronts = [];
      state.homeStorefront = "my";
    }
  }
  if (localStorage.getItem("metadataStorefront") === null) {
    state.metadataStorefront = state.homeStorefront;
    localStorage.setItem("metadataStorefront", state.homeStorefront);
  }
  renderMetaSourceWidget();
}

// ---------------------------------------------------------------------------
// Router
// ---------------------------------------------------------------------------
function route(hash) {
  hash = hash || "#/";
  const main = $("main-content");

  // Highlight nav
  document.querySelectorAll(".nav-link").forEach(a => {
    const page = a.dataset.page;
    const active =
      (page === "releases"  && (hash === "#/" || hash.startsWith("#/releases"))) ||
      (page === "all"       && hash === "#/all") ||
      (page === "watchlist" && hash === "#/watchlist") ||
      (page === "settings"  && hash === "#/settings");
    a.classList.toggle("active", active);
  });

  if (hash === "#/all") {
    renderAllReleases(main);
  } else if (hash === "#/watchlist") {
    renderWatchlist(main);
  } else if (hash === "#/settings") {
    renderSettings(main);
  } else if (hash.startsWith("#/artist/")) {
    const artistId = hash.slice("#/artist/".length);
    renderArtist(main, artistId);
  } else {
    renderNewReleases(main);
  }
}

// ---------------------------------------------------------------------------
// Watchlist helpers
// ---------------------------------------------------------------------------
async function loadWatchedIds() {
  try {
    const list = await API.get("/api/watchlist");
    state.watchedIds = new Set(list.map(a => a.artist_id));
  } catch {}
}

async function toggleWatch(artistId, name, artistUrl, preferredSource) {
  if (state.watchedIds.has(artistId)) {
    await API.del(`/api/watchlist/${artistId}`);
    state.watchedIds.delete(artistId);
  } else {
    const body = { artist_id: artistId, name, url: artistUrl };
    if (preferredSource) body.preferred_source = preferredSource;
    await API.post("/api/watchlist", body);
    state.watchedIds.add(artistId);
    // Fetch artist metadata (artwork, genre) immediately, then refresh current page
    const sf = preferredSource || state.metadataStorefront;
    const qp = sf ? `?storefront=${sf}` : "";
    API.post(`/api/artists/${artistId}/fetch${qp}`).then(() => route(location.hash)).catch(() => {});
  }
}

// ---------------------------------------------------------------------------
// Page: New Releases
// ---------------------------------------------------------------------------
async function renderNewReleases(main, page = 1, query = "", storefront = "", watchedOnly = false) {
  state.currentPage = page;
  state.currentQuery = query;
  state.currentStorefront = storefront;
  state.currentWatchedOnly = watchedOnly;

  // Load config once
  if (state.configuredStorefronts === null) {
    try {
      const cfg = await API.get("/api/config");
      state.configuredStorefronts = cfg.check_storefronts || [];
      state.discoveryStorefronts = cfg.check_storefronts || [];
    } catch {
      state.configuredStorefronts = [];
      state.discoveryStorefronts = [];
    }
  }

  const sfSubtitle = state.discoveryStorefronts.length
    ? "Latest albums discovered across " + state.discoveryStorefronts.map(s => s.toUpperCase()).join(" · ")
    : "Latest albums discovered";

  // Skeleton
  main.innerHTML = "";
  const wrap = el("div", "page-enter");
  wrap.appendChild(buildHeader("🎵 New Releases", sfSubtitle));

  // Search
  const searchBar = el("div", "search-bar");
  const inp = el("input", "search-input");
  inp.type = "text";
  inp.placeholder = "Search title or artist…";
  inp.value = query;
  inp.id = "releases-search";
  inp.addEventListener("input", debounce(e => {
    renderNewReleases(main, 1, e.target.value.trim(), state.currentStorefront);
  }, 350));
  searchBar.appendChild(inp);
  wrap.appendChild(searchBar);

  const gridWrap = el("div");
  gridWrap.appendChild(skeletonGrid(12));
  wrap.appendChild(gridWrap);
  main.appendChild(wrap);
  const filterBar = el("div", "sf-filter-bar");
  const sfButtons = [["All", ""], ...state.configuredStorefronts.map(sf => [sf.toUpperCase(), sf.toLowerCase()])];
  sfButtons.forEach(([label, code]) => {
    const btn = el("button", "sf-filter-btn" + (code ? ` ${code}` : "") + (storefront === code ? " active" : ""));
    btn.textContent = label;
    btn.addEventListener("click", () => renderNewReleases(main, 1, state.currentQuery, code, state.currentWatchedOnly));
    filterBar.appendChild(btn);
  });

  // Watched-only toggle
  const watchedToggle = el("button", `sf-filter-btn watched-toggle${watchedOnly ? " active" : ""}`, "Watched");
  watchedToggle.title = "Show only releases from watched artists";
  watchedToggle.addEventListener("click", () => renderNewReleases(main, 1, state.currentQuery, state.currentStorefront, !watchedOnly));
  filterBar.appendChild(watchedToggle);

  searchBar.after(filterBar);

  // Fetch
  await loadWatchedIds();
  let data;
  try {
    const qp = new URLSearchParams({ page, per_page: state.perPage, view: "new" });
    if (watchedOnly) qp.set("watched", "true");
    if (query) qp.set("q", query);
    if (storefront) qp.set("storefront", storefront);
    data = await API.get(`/api/releases?${qp}`);
  } catch {
    gridWrap.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><div class="empty-title">Could not load releases</div><div class="empty-desc">Is the server running?</div></div>`;
    return;
  }

  state.currentTotal = data.total;
  gridWrap.innerHTML = "";

  if (!data.items.length) {
    gridWrap.innerHTML = `<div class="empty-state"><div class="empty-icon">🔍</div><div class="empty-title">No results</div><div class="empty-desc">${query ? `No matches for "${query}"` : "Run a refresh to fetch new releases"}</div></div>`;
    return;
  }

  const grid = el("div", "album-grid");
  data.items.forEach(album => grid.appendChild(albumCard(album)));
  gridWrap.appendChild(grid);

  // Pagination
  const totalPages = Math.ceil(data.total / state.perPage);
  if (totalPages > 1) {
    gridWrap.appendChild(buildPagination(page, totalPages, p => renderNewReleases(main, p, state.currentQuery, state.currentStorefront, state.currentWatchedOnly)));
  }
}

// ---------------------------------------------------------------------------
// Page: All Albums
// ---------------------------------------------------------------------------
async function renderAllReleases(main, page = 1, query = "", storefront = "") {
  main.innerHTML = "";
  const wrap = el("div", "page-enter");
  wrap.appendChild(buildHeader("📀 All Albums", "Every album in your local database"));

  const searchBar = el("div", "search-bar");
  const inp = el("input", "search-input");
  inp.type = "text";
  inp.placeholder = "Search title or artist…";
  inp.value = query;
  inp.addEventListener("input", debounce(e => {
    renderAllReleases(main, 1, e.target.value.trim(), storefront);
  }, 350));
  searchBar.appendChild(inp);
  wrap.appendChild(searchBar);

  if (state.configuredStorefronts === null) {
    try {
      const cfg = await API.get("/api/config");
      state.configuredStorefronts = cfg.check_storefronts || [];
    } catch {
      state.configuredStorefronts = [];
    }
  }
  const filterBar = el("div", "sf-filter-bar");
  const sfButtons = [["All", ""], ...state.configuredStorefronts.map(sf => [sf.toUpperCase(), sf.toLowerCase()])];
  sfButtons.forEach(([label, code]) => {
    const btn = el("button", "sf-filter-btn" + (code ? ` ${code}` : "") + (storefront === code ? " active" : ""));
    btn.textContent = label;
    btn.addEventListener("click", () => renderAllReleases(main, 1, query, code));
    filterBar.appendChild(btn);
  });
  searchBar.after(filterBar);

  const gridWrap = el("div");
  gridWrap.appendChild(skeletonGrid(12));
  wrap.appendChild(gridWrap);
  main.appendChild(wrap);

  await loadWatchedIds();
  let data;
  try {
    const qp = new URLSearchParams({ page, per_page: state.perPage });
    if (query) qp.set("q", query);
    if (storefront) qp.set("storefront", storefront);
    data = await API.get(`/api/releases?${qp}`);
  } catch {
    gridWrap.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><div class="empty-title">Could not load</div></div>`;
    return;
  }

  gridWrap.innerHTML = "";
  if (!data.items.length) {
    gridWrap.innerHTML = `<div class="empty-state"><div class="empty-icon">📀</div><div class="empty-title">No albums yet</div><div class="empty-desc">Go to <a href="#/watchlist" style="color:var(--accent)">Artist Watchlist</a>, search for an artist, and fetch their releases from the artist page</div></div>`;
    return;
  }

  const grid = el("div", "album-grid");
  data.items.forEach(album => grid.appendChild(albumCard(album)));
  gridWrap.appendChild(grid);

  const totalPages = Math.ceil(data.total / state.perPage);
  if (totalPages > 1) {
    gridWrap.appendChild(buildPagination(page, totalPages, p => renderAllReleases(main, p, query, storefront)));
  }
}

// ---------------------------------------------------------------------------
// Artist release grid (chronological or grouped by type)
// ---------------------------------------------------------------------------
function renderArtistReleaseGrid(releases, container) {
  container.innerHTML = "";
  const filtered = state.artistTypeFilter
    ? releases.filter(r => r.release_type === state.artistTypeFilter)
    : releases;

  if (!filtered.length) {
    container.innerHTML = `<div class="empty-state"><div class="empty-icon">🎵</div><div class="empty-title">No releases</div></div>`;
    return;
  }

  if (state.artistViewMode === "grouped") {
    const groups = {};
    filtered.forEach(r => {
      const key = r.release_type || "__other";
      if (!groups[key]) groups[key] = [];
      groups[key].push(r);
    });
    const orderedKeys = [
      ...RELEASE_TYPE_ORDER.filter(k => groups[k]),
      ...Object.keys(groups).filter(k => !RELEASE_TYPE_ORDER.includes(k) && k !== "__other"),
      ...(groups["__other"] ? ["__other"] : []),
    ];
    orderedKeys.forEach(key => {
      const items = groups[key];
      const section = el("div", "release-section");
      const label = key === "__other" ? "Other" : (RELEASE_TYPE_LABELS[key] || key);
      const header = el("div", "release-section-header");
      header.innerHTML = `${label} <span class="release-section-count">${items.length}</span>`;
      section.appendChild(header);
      const grid = el("div", "album-grid");
      items.forEach(album => grid.appendChild(albumCard(album)));
      section.appendChild(grid);
      container.appendChild(section);
    });
  } else {
    const grid = el("div", "album-grid");
    filtered.forEach(album => grid.appendChild(albumCard(album)));
    container.appendChild(grid);
  }
}

// ---------------------------------------------------------------------------
// Page: Artist Detail
// ---------------------------------------------------------------------------
async function renderArtist(main, artistId) {
  main.innerHTML = "";
  const wrap = el("div", "page-enter");
  wrap.appendChild(skeletonGrid(6));
  main.appendChild(wrap);

  let data;
  try {
    data = await API.get(`/api/artists/${artistId}/releases`);
  } catch {
    wrap.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><div class="empty-title">Could not load artist</div></div>`;
    return;
  }
  if (!data || !Array.isArray(data.releases)) {
    wrap.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><div class="empty-title">Could not load artist</div></div>`;
    return;
  }

  // Use hint from watchlist search if the artist isn't in DB yet
  const hint = (state.artistHint?.id === artistId) ? state.artistHint : null;
  if (!data.artist_name        && hint?.name)        data.artist_name        = hint.name;
  if (!data.artist_url         && hint?.url)         data.artist_url         = hint.url;
  if (!data.artist_artwork_url && hint?.artwork_url) data.artist_artwork_url = hint.artwork_url;
  if (!data.artist_genre       && hint?.genre)       data.artist_genre       = hint.genre;

  await loadWatchedIds();
  wrap.innerHTML = "";

  // Header
  const header = el("div", "artist-header");
  const avatar = el("div", "artist-avatar");
  if (data.artist_artwork_url) {
    const img = el("img", "artist-avatar-img");
    img.src = data.artist_artwork_url;
    img.alt = "";
    img.onerror = () => { img.remove(); avatar.textContent = (data.artist_name || "?")[0].toUpperCase(); };
    avatar.appendChild(img);
  } else {
    avatar.textContent = (data.artist_name || "?")[0].toUpperCase();
  }
  header.appendChild(avatar);

  const meta = el("div", "artist-meta");
  const nameBig = el("h1", "artist-name-big", data.artist_name || "Unknown Artist");
  meta.appendChild(nameBig);

  if (data.artist_artwork_url && data.artist_genre) {
    const genreEl = el("div", "artist-genre", data.artist_genre);
    meta.appendChild(genreEl);
  }

  const links = el("div", "artist-links");
  if (data.artist_url) {
    const extLink = el("a", "artist-ext-link", "Open in Apple Music ↗");
    extLink.dataset.baseUrl = data.artist_url;
    const sf = state.metadataStorefront;
    extLink.href = sf
      ? data.artist_url.replace(/music\.apple\.com\/[a-z]{2}\//, `music.apple.com/${sf}/`)
      : data.artist_url;
    extLink.target = "_blank";
    extLink.rel = "noopener";
    links.appendChild(extLink);
  }

  const isWatched = state.watchedIds.has(artistId);
  const watchBtn = el("button", `btn-watch${isWatched ? " watching" : ""}`, isWatched ? "⭐ Watching" : "☆ Watch");

  // Preferred source selector — only visible when watched
  const srcWrap = el("div", "artist-src-wrap");
  srcWrap.style.cssText = `display:${isWatched ? "flex" : "none"};align-items:center;gap:6px;flex-wrap:wrap;`;
  const srcLabel = el("span", "artist-src-label", "Preferred source:");
  srcWrap.appendChild(srcLabel);
  const srcSelect = document.createElement("select");
  srcSelect.className = "src-select";

  function buildSrcOptions(currentPs) {
    srcSelect.innerHTML = "";
    const noneOpt = document.createElement("option");
    noneOpt.value = "";
    noneOpt.textContent = "None (uses home)";
    noneOpt.selected = !currentPs;
    srcSelect.appendChild(noneOpt);
    (state.configuredStorefronts || []).forEach(sf => {
      const opt = document.createElement("option");
      opt.value = sf;
      opt.textContent = sf.toUpperCase();
      opt.selected = currentPs === sf;
      srcSelect.appendChild(opt);
    });
  }

  buildSrcOptions(null); // placeholder until async load

  srcSelect.addEventListener("change", async () => {
    const val = srcSelect.value || null;
    await API.patch(`/api/watchlist/${artistId}`, { preferred_source: val });
  });

  srcWrap.appendChild(srcSelect);
  links.appendChild(srcWrap);

  // Collection status selector — only visible when watched
  const csWrap = el("div", "artist-src-wrap");
  csWrap.style.cssText = `display:${isWatched ? "flex" : "none"};align-items:center;gap:6px;flex-wrap:wrap;`;
  const csLabel = el("span", "artist-src-label", "Collection status:");
  csWrap.appendChild(csLabel);
  const csSelect = document.createElement("select");
  csSelect.className = "src-select";

  function buildCsOptions(currentCs) {
    csSelect.innerHTML = "";
    const current = currentCs || "new";
    // Show current status as the first (selected) option
    const currentOpt = document.createElement("option");
    currentOpt.value = current;
    currentOpt.textContent = COLLECTION_STATUS_LABELS[current] || current;
    currentOpt.selected = true;
    csSelect.appendChild(currentOpt);
    // Show valid transitions as additional options
    const transitions = COLLECTION_TRANSITIONS[current] || [];
    transitions.forEach(s => {
      const opt = document.createElement("option");
      opt.value = s;
      opt.textContent = COLLECTION_STATUS_LABELS[s];
      csSelect.appendChild(opt);
    });
    csSelect.disabled = transitions.length === 0;
  }

  buildCsOptions(null); // placeholder until async load

  csSelect.addEventListener("change", async () => {
    const newStatus = csSelect.value;
    const oldStatus = csSelect.querySelector("option")?.value;
    if (!newStatus || newStatus === oldStatus) return;
    try {
      await API.patch(`/api/watchlist/${artistId}`, { collection_status: newStatus });
      buildCsOptions(newStatus);
    } catch {
      alert("Failed to update status");
      buildCsOptions(oldStatus);
    }
  });

  csWrap.appendChild(csSelect);
  links.appendChild(csWrap);

  watchBtn.addEventListener("click", async () => {
    const ps = state.metadataStorefront || state.homeStorefront || null;
    await toggleWatch(artistId, data.artist_name, data.artist_url, ps);
    const nowWatched = state.watchedIds.has(artistId);
    watchBtn.textContent = nowWatched ? "⭐ Watching" : "☆ Watch";
    watchBtn.classList.toggle("watching", nowWatched);
    srcWrap.style.display = nowWatched ? "flex" : "none";
    csWrap.style.display = nowWatched ? "flex" : "none";
    if (nowWatched) {
      buildSrcOptions(ps);
      buildCsOptions("new");
    }
  });
  links.appendChild(watchBtn);

  if (isWatched) {
    // Load current preferred_source and collection_status, pre-select
    API.get("/api/watchlist").then(wl => {
      const entry = wl.find(a => a.artist_id === artistId);
      buildSrcOptions(entry?.preferred_source || null);
      buildCsOptions(entry?.collection_status || "new");
    }).catch(() => {});
  }

  const sfLabel = state.metadataStorefront ? state.metadataStorefront.toUpperCase() : "";
  const fetchBtn = el("button", "btn-fetch-artist", sfLabel ? `↓ Fetch from ${sfLabel}` : "↓ Fetch All");
  fetchBtn.title = "Fetch all releases for this artist and store tracklists";
  fetchBtn.addEventListener("click", async () => {
    fetchBtn.disabled = true;
    fetchBtn.textContent = "Fetching…";
    try {
      const sf = state.metadataStorefront;
      const qp = sf ? `?storefront=${sf}` : "";
      const res = await API.post(`/api/artists/${artistId}/fetch${qp}`, {});
      fetchBtn.textContent = `✓ ${res.fetched} fetched`;
      setTimeout(() => renderArtist(main, artistId), 800);
    } catch {
      fetchBtn.textContent = "Failed";
      fetchBtn.disabled = false;
    }
  });
  links.appendChild(fetchBtn);

  meta.appendChild(links);
  header.appendChild(meta);
  wrap.appendChild(header);

  // Stats
  const subtitle = el("p", "page-subtitle");
  const trackFetched = data.releases.filter(r => r.tracks_fetched).length;
  subtitle.textContent = `${data.releases.length} release${data.releases.length !== 1 ? "s" : ""} in database` +
    (trackFetched ? ` · ${trackFetched} with tracklist` : "");
  subtitle.style.marginBottom = "20px";
  wrap.appendChild(subtitle);

  if (!data.releases.length) {
    wrap.insertAdjacentHTML("beforeend", `<div class="empty-state"><div class="empty-icon">🎵</div><div class="empty-title">No releases found</div><div class="empty-desc">This artist's releases will appear here after a refresh</div></div>`);
    return;
  }

  data.releases.forEach(album => {
    album.watched = state.watchedIds.has(album.artist_id);
    if (data.artist_name) album.artist = data.artist_name;
  });

  // Toolbar: view toggle + type filter
  const toolbar = el("div", "artist-releases-toolbar");
  const gridContainer = el("div", "artist-grid-container");

  // View mode toggle
  const viewToggle = el("div", "view-toggle-bar");
  [["Chronological", "chrono"], ["By Type", "grouped"]].forEach(([label, mode]) => {
    const btn = el("button", `view-toggle-btn${state.artistViewMode === mode ? " active" : ""}`, label);
    btn.dataset.mode = mode;
    btn.addEventListener("click", () => {
      state.artistViewMode = mode;
      viewToggle.querySelectorAll(".view-toggle-btn").forEach(b =>
        b.classList.toggle("active", b.dataset.mode === mode));
      renderArtistReleaseGrid(data.releases, gridContainer);
    });
    viewToggle.appendChild(btn);
  });
  toolbar.appendChild(viewToggle);

  // Type filter — only shown when multiple types are present
  const typeSet = new Set(data.releases.map(r => r.release_type).filter(Boolean));
  if (typeSet.size > 1) {
    const typeFilter = el("div", "type-filter-bar");
    [["All", ""], ...RELEASE_TYPE_ORDER
      .filter(k => typeSet.has(k))
      .map(k => [RELEASE_TYPE_LABELS[k] || k, k])
    ].forEach(([label, code]) => {
      const btn = el("button", `type-filter-btn${state.artistTypeFilter === code ? " active" : ""}`, label);
      btn.dataset.type = code;
      btn.addEventListener("click", () => {
        state.artistTypeFilter = code;
        typeFilter.querySelectorAll(".type-filter-btn").forEach(b =>
          b.classList.toggle("active", b.dataset.type === code));
        renderArtistReleaseGrid(data.releases, gridContainer);
      });
      typeFilter.appendChild(btn);
    });
    toolbar.appendChild(typeFilter);
  }

  wrap.appendChild(toolbar);
  wrap.appendChild(gridContainer);
  renderArtistReleaseGrid(data.releases, gridContainer);
}

// ---------------------------------------------------------------------------
// Page: Watchlist
// ---------------------------------------------------------------------------
const COLLECTION_STATUS_LABELS = {
  new: "New",
  complete: "Complete",
  new_release: "New Release",
  in_progress: "In Progress",
};
const COLLECTION_TRANSITIONS = {
  new: ["complete", "in_progress"],
  complete: ["in_progress"],
  new_release: ["complete", "in_progress"],
  in_progress: ["complete"],
};

async function renderWatchlist(main, preferredSourceFilter = "", collectionStatusFilter = "") {
  main.innerHTML = "";
  const wrap = el("div", "page-enter");
  wrap.appendChild(buildHeader("⭐ Artist Watchlist", "Artists you're following"));
  main.appendChild(wrap);

  // Action bar: import/export
  const actionBar = el("div", "watchlist-action-bar");
  actionBar.style.cssText = "display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center;";

  const exportBtn = el("button", "btn-secondary", "Export");
  exportBtn.title = "Download watchlist as JSON";
  exportBtn.addEventListener("click", () => {
    window.location.href = "/api/watchlist/export";
  });
  actionBar.appendChild(exportBtn);

  const importBtn = el("button", "btn-secondary", "Import");
  importBtn.title = "Import watchlist from JSON file";
  importBtn.addEventListener("click", () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".json";
    input.addEventListener("change", async () => {
      if (!input.files.length) return;
      const file = input.files[0];
      const formData = new FormData();
      formData.append("file", file);
      try {
        const resp = await fetch("/api/watchlist/import", { method: "POST", body: formData });
        const result = await resp.json();
        if (result.ok) {
          renderWatchlist(main, preferredSourceFilter, collectionStatusFilter);
        } else {
          alert(result.error || "Import failed");
        }
      } catch {
        alert("Import failed");
      }
    });
    input.click();
  });
  actionBar.appendChild(importBtn);

  wrap.appendChild(actionBar);

  const qpParts = [];
  if (preferredSourceFilter) qpParts.push(`preferred_source=${preferredSourceFilter}`);
  if (collectionStatusFilter) qpParts.push(`collection_status=${collectionStatusFilter}`);
  const qp = qpParts.length ? `?${qpParts.join("&")}` : "";
  let list;
  try {
    list = await API.get(`/api/watchlist${qp}`);
  } catch {
    wrap.innerHTML += `<div class="empty-state"><div class="empty-icon">⚠️</div><div class="empty-title">Could not load watchlist</div></div>`;
    return;
  }

  // Also load full watchlist for IDs (unfiltered)
  try {
    const full = await API.get("/api/watchlist");
    state.watchedIds = new Set(full.map(a => a.artist_id));
  } catch {
    state.watchedIds = new Set(list.map(a => a.artist_id));
  }

  // Filter by preferred source
  if (state.configuredStorefronts === null) {
    try {
      const cfg = await API.get("/api/config");
      state.configuredStorefronts = cfg.check_storefronts || [];
    } catch {
      state.configuredStorefronts = [];
    }
  }
  const psFilterBar = el("div", "sf-filter-bar");
  const psButtons = [["All", ""], ...state.configuredStorefronts.map(sf => [sf.toUpperCase(), sf.toLowerCase()])];
  psButtons.forEach(([label, code]) => {
    const btn = el("button", "sf-filter-btn" + (code ? ` ${code}` : "") + (preferredSourceFilter === code ? " active" : ""));
    btn.textContent = label;
    btn.addEventListener("click", () => renderWatchlist(main, code, collectionStatusFilter));
    psFilterBar.appendChild(btn);
  });
  actionBar.appendChild(psFilterBar);

  // Collection status filter bar
  const csFilterBar = el("div", "cs-filter-bar");
  const csButtons = [["All", ""], ...Object.entries(COLLECTION_STATUS_LABELS)];
  csButtons.forEach(([label, code]) => {
    const cls = "cs-filter-btn" + (code ? ` status-${code}` : "") + (collectionStatusFilter === code ? " active" : "");
    const btn = el("button", cls);
    btn.textContent = label;
    btn.addEventListener("click", () => renderWatchlist(main, preferredSourceFilter, code));
    csFilterBar.appendChild(btn);
  });
  actionBar.appendChild(csFilterBar);

  // Search bar
  const searchBar = el("div", "search-bar");
  const searchInput = el("input", "search-input");
  searchInput.type = "text";
  searchInput.placeholder = "Search artists…";
  searchBar.appendChild(searchInput);
  wrap.appendChild(searchBar);

  // Results area: watched list + AM search suggestions
  const grid = el("div", "watchlist-grid");
  wrap.appendChild(grid);

  function makeWatchedCard(artist) {
    const card = el("div", "watchlist-card");
    card.dataset.artistId = artist.artist_id;

    const avatar = el("div", "watchlist-avatar");
    if (artist.artwork_url) {
      const img = el("img", "watchlist-avatar-img");
      img.src = artist.artwork_url;
      img.alt = "";
      img.loading = "lazy";
      img.onerror = () => { img.remove(); avatar.textContent = (artist.name || "?")[0].toUpperCase(); };
      avatar.appendChild(img);
    } else {
      avatar.textContent = (artist.name || "?")[0].toUpperCase();
    }
    card.appendChild(avatar);

    const info = el("div", "watchlist-info");
    const name = el("a", "watchlist-name", artist.name);
    name.title = artist.name;
    name.href = `#/artist/${artist.artist_id}`;
    name.addEventListener("click", e => {
      e.preventDefault();
      location.hash = `#/artist/${artist.artist_id}`;
    });
    info.appendChild(name);

    const _addedAt = typeof artist.added_at === "number"
      ? new Date(artist.added_at * 1000).toISOString().slice(0, 10)
      : artist.added_at?.slice(0, 10);
    const date = el("div", "watchlist-date", `Added ${formatDate(_addedAt)}`);
    if (artist.preferred_source) {
      const psBadge = el("span", `sf-chip ${artist.preferred_source}`);
      psBadge.textContent = artist.preferred_source.toUpperCase();
      psBadge.style.marginLeft = "6px";
      psBadge.style.fontSize = "9px";
      date.appendChild(psBadge);
    }
    // Collection status chip (read-only, change on artist detail page)
    const currentStatus = artist.collection_status || "new";
    const badge = el("span", `collection-status-badge status-${currentStatus}`);
    badge.textContent = COLLECTION_STATUS_LABELS[currentStatus] || currentStatus;
    badge.style.marginLeft = "6px";
    date.appendChild(badge);
    info.appendChild(date);
    card.appendChild(info);

    const unwatchBtn = el("button", "btn-unwatch", "Remove");
    unwatchBtn.addEventListener("click", async () => {
      await toggleWatch(artist.artist_id, artist.name, artist.url);
      state.watchedIds.delete(artist.artist_id);
      list = list.filter(a => a.artist_id !== artist.artist_id);
      card.remove();
      renderGrid(searchInput.value.trim());
    });
    card.appendChild(unwatchBtn);
    return card;
  }

  function makeSuggestionCard(artist) {
    const card = el("div", "watchlist-card watchlist-card--suggestion");
    card.dataset.artistId = artist.id;

    const avatar = el("div", "watchlist-avatar");
    if (artist.artwork_url) {
      const img = el("img", "watchlist-avatar-img");
      img.src = artist.artwork_url;
      img.alt = "";
      img.loading = "lazy";
      img.onerror = () => { img.remove(); avatar.textContent = (artist.name || "?")[0].toUpperCase(); };
      avatar.appendChild(img);
    } else {
      avatar.textContent = (artist.name || "?")[0].toUpperCase();
    }
    card.appendChild(avatar);

    const info = el("div", "watchlist-info");
    const name = el("a", "watchlist-name", artist.name);
    name.title = artist.name;
    name.href = `#/artist/${artist.id}`;
    name.addEventListener("click", e => {
      e.preventDefault();
      state.artistHint = { id: String(artist.id), name: artist.name, url: artist.url, artwork_url: artist.artwork_url, genre: artist.genre };
      location.hash = `#/artist/${artist.id}`;
    });
    info.appendChild(name);
    const sub = el("div", "watchlist-date", "Apple Music");
    info.appendChild(sub);
    card.appendChild(info);

    const watchBtn = el("button", "btn-watch", "Watch");
    watchBtn.addEventListener("click", async () => {
      const ps = state.metadataStorefront || state.homeStorefront || null;
      await toggleWatch(artist.id, artist.name, artist.url, ps);
      state.watchedIds.add(artist.id);
      list.push({ artist_id: artist.id, name: artist.name, url: artist.url, preferred_source: ps, added_at: new Date().toISOString(), collection_status: "new" });
      renderGrid(searchInput.value.trim());
    });
    card.appendChild(watchBtn);
    return card;
  }

  let _searchTimer = null;
  let _lastSuggestions = [];

  function renderGrid(q) {
    grid.innerHTML = "";

    const filtered = q
      ? list.filter(a => a.name.toLowerCase().includes(q.toLowerCase()))
      : list;

    filtered.forEach(a => grid.appendChild(makeWatchedCard(a)));

    // Show AM suggestions (already-watched ones excluded)
    const suggestions = _lastSuggestions.filter(a => !state.watchedIds.has(a.id));
    if (suggestions.length) {
      if (filtered.length) {
        const sep = el("div", "watchlist-separator", "Also on Apple Music");
        sep.style.cssText = "grid-column:1/-1;font-size:11px;color:var(--text-dim);text-transform:uppercase;letter-spacing:.06em;padding:4px 0;";
        grid.appendChild(sep);
      }
      suggestions.forEach(a => grid.appendChild(makeSuggestionCard(a)));
    }

    if (!grid.children.length) {
      if (q) {
        grid.innerHTML = `<div class="empty-state" style="grid-column:1/-1"><div class="empty-icon">🔍</div><div class="empty-title">No results for "${q}"</div></div>`;
      } else {
        grid.innerHTML = `<div class="empty-state" style="grid-column:1/-1"><div class="empty-icon">⭐</div><div class="empty-title">Watchlist is empty</div></div>`;
      }
    }
  }

  searchInput.addEventListener("input", () => {
    const q = searchInput.value.trim();
    _lastSuggestions = [];
    renderGrid(q);

    clearTimeout(_searchTimer);
    if (!q) return;
    _searchTimer = setTimeout(async () => {
      try {
        const sf = state.metadataStorefront || state.homeStorefront || "us";
        const data = await API.get(`/api/search/artists?term=${encodeURIComponent(q)}&limit=10&storefront=${sf}`);
        _lastSuggestions = data.results || [];
      } catch {
        _lastSuggestions = [];
      }
      renderGrid(q);
    }, 350);
  });

  renderGrid("");
}

// ---------------------------------------------------------------------------
// Page: Settings
// ---------------------------------------------------------------------------
async function renderSettings(main) {
  main.innerHTML = "";
  const wrap = el("div", "page-enter");
  wrap.appendChild(buildHeader("⚙️ Settings", "Configure application options"));
  main.appendChild(wrap);

  let cfg;
  try {
    cfg = await API.get("/api/config");
  } catch {
    wrap.innerHTML += `<div class="empty-state"><div class="empty-icon">⚠️</div><div class="empty-title">Could not load config</div></div>`;
    return;
  }

  const form = el("div", "settings-form");
  form.style.maxWidth = "600px";
  form.style.display = "flex";
  form.style.flexDirection = "column";
  form.style.gap = "20px";

  // Check Storefronts
  const sfsGroup = el("div");
  sfsGroup.style.display = "flex";
  sfsGroup.style.flexDirection = "column";
  sfsGroup.style.gap = "8px";
  const sfsLabel = el("label", "", "Check Storefronts (comma separated)");
  sfsLabel.style.fontWeight = "600";
  sfsGroup.appendChild(sfsLabel);
  const sfsInput = el("input", "search-input");
  sfsInput.type = "text";
  sfsInput.value = (cfg.check_storefronts || ["jp", "my", "us", "hk", "tw", "sg"]).join(", ");
  sfsGroup.appendChild(sfsInput);
  form.appendChild(sfsGroup);

  // Home Storefront
  const homeGroup = el("div");
  homeGroup.style.display = "flex";
  homeGroup.style.flexDirection = "column";
  homeGroup.style.gap = "8px";
  const homeLabel = el("label", "", "Home Storefront");
  homeLabel.style.fontWeight = "600";
  const homeDesc = el("p", "", "The storefront your Apple Music account is in. Used as the baseline for tracklist comparisons.");
  homeDesc.style.fontSize = "12px";
  homeDesc.style.color = "var(--text-dim)";
  homeDesc.style.margin = "0";
  homeGroup.appendChild(homeLabel);
  homeGroup.appendChild(homeDesc);
  const homeInput = el("input", "search-input");
  homeInput.type = "text";
  homeInput.value = cfg.home_storefront || "my";
  homeInput.placeholder = "e.g. my";
  homeInput.style.maxWidth = "120px";
  homeGroup.appendChild(homeInput);
  form.appendChild(homeGroup);

  // Poll Interval
  const pollGroup = el("div");
  pollGroup.style.display = "flex";
  pollGroup.style.flexDirection = "column";
  pollGroup.style.gap = "8px";
  const pollLabel = el("label", "", "New Release Poll Interval (days)");
  pollLabel.style.fontWeight = "600";
  pollGroup.appendChild(pollLabel);
  const pollInput = el("input", "search-input");
  pollInput.type = "number";
  pollInput.min = "1";
  pollInput.value = cfg.newrelease_poll_interval_days || 1;
  pollInput.style.maxWidth = "120px";
  pollGroup.appendChild(pollInput);
  form.appendChild(pollGroup);

  // Watchlist Poll Interval
  const wlPollGroup = el("div");
  wlPollGroup.style.display = "flex";
  wlPollGroup.style.flexDirection = "column";
  wlPollGroup.style.gap = "8px";
  const wlPollLabel = el("label", "", "Watchlist Poll Interval (minutes)");
  wlPollLabel.style.fontWeight = "600";
  const wlPollDesc = el("p", "", "How often to check watched artists for new releases.");
  wlPollDesc.style.fontSize = "12px";
  wlPollDesc.style.color = "var(--text-dim)";
  wlPollDesc.style.margin = "0";
  wlPollGroup.appendChild(wlPollLabel);
  wlPollGroup.appendChild(wlPollDesc);
  const wlPollInput = el("input", "search-input");
  wlPollInput.type = "number";
  wlPollInput.min = "1";
  wlPollInput.value = cfg.watchlist_poll_interval_minutes || 10;
  wlPollInput.style.maxWidth = "120px";
  wlPollGroup.appendChild(wlPollInput);
  form.appendChild(wlPollGroup);

  // Watchlist Poll Batch Size
  const wlBatchGroup = el("div");
  wlBatchGroup.style.display = "flex";
  wlBatchGroup.style.flexDirection = "column";
  wlBatchGroup.style.gap = "8px";
  const wlBatchLabel = el("label", "", "Watchlist Poll Batch Size");
  wlBatchLabel.style.fontWeight = "600";
  const wlBatchDesc = el("p", "", "Number of watched artists to refresh per poll cycle.");
  wlBatchDesc.style.fontSize = "12px";
  wlBatchDesc.style.color = "var(--text-dim)";
  wlBatchDesc.style.margin = "0";
  wlBatchGroup.appendChild(wlBatchLabel);
  wlBatchGroup.appendChild(wlBatchDesc);
  const wlBatchInput = el("input", "search-input");
  wlBatchInput.type = "number";
  wlBatchInput.min = "1";
  wlBatchInput.value = cfg.watchlist_poll_batch_size || 5;
  wlBatchInput.style.maxWidth = "120px";
  wlBatchGroup.appendChild(wlBatchInput);
  form.appendChild(wlBatchGroup);

  // Watchlist Refresh Interval
  const wlRefreshGroup = el("div");
  wlRefreshGroup.style.display = "flex";
  wlRefreshGroup.style.flexDirection = "column";
  wlRefreshGroup.style.gap = "8px";
  const wlRefreshLabel = el("label", "", "Watchlist Artist Refresh Interval (days)");
  wlRefreshLabel.style.fontWeight = "600";
  const wlRefreshDesc = el("p", "", "Days before a watched artist's catalog is considered stale and re-fetched.");
  wlRefreshDesc.style.fontSize = "12px";
  wlRefreshDesc.style.color = "var(--text-dim)";
  wlRefreshDesc.style.margin = "0";
  wlRefreshGroup.appendChild(wlRefreshLabel);
  wlRefreshGroup.appendChild(wlRefreshDesc);
  const wlRefreshInput = el("input", "search-input");
  wlRefreshInput.type = "number";
  wlRefreshInput.min = "1";
  wlRefreshInput.value = cfg.watchlist_refresh_interval_days || 7;
  wlRefreshInput.style.maxWidth = "120px";
  wlRefreshGroup.appendChild(wlRefreshInput);
  form.appendChild(wlRefreshGroup);

  // CORS Proxy
  const proxyGroup = el("div");
  proxyGroup.style.display = "flex";
  proxyGroup.style.flexDirection = "column";
  proxyGroup.style.gap = "8px";
  const proxyLabel = el("label", "", "CORS Proxy");
  proxyLabel.style.fontWeight = "600";
  const proxyDesc = el("p", "", "Optional URL prefix to proxy outgoing Apple Music requests through. Leave blank to disable.");
  proxyDesc.style.fontSize = "12px";
  proxyDesc.style.color = "var(--text-dim)";
  proxyDesc.style.margin = "0";
  proxyGroup.appendChild(proxyLabel);
  proxyGroup.appendChild(proxyDesc);
  const proxyInput = el("input", "search-input");
  proxyInput.type = "text";
  proxyInput.value = cfg.cors_proxy || "";
  proxyInput.placeholder = "e.g. https://proxy.example.com/";
  proxyGroup.appendChild(proxyInput);
  form.appendChild(proxyGroup);

  const errorMsg = el("div", "");
  errorMsg.style.color = "red";
  errorMsg.style.display = "none";
  form.appendChild(errorMsg);

  const saveBtn = el("button", "btn-primary", "Save Config");
  saveBtn.style.alignSelf = "flex-start";
  saveBtn.addEventListener("click", async () => {
    errorMsg.style.display = "none";
    saveBtn.textContent = "Saving...";
    saveBtn.disabled = true;

    try {
      const parsedSfs = sfsInput.value.split(",").map(s => s.trim().toLowerCase()).filter(s => s);
      const parsedHome = homeInput.value.trim().toLowerCase();
      const parsedPoll = parseInt(pollInput.value, 10);
      const parsedWlPoll = parseInt(wlPollInput.value, 10);
      const parsedWlBatch = parseInt(wlBatchInput.value, 10);
      const parsedWlRefresh = parseInt(wlRefreshInput.value, 10);
      const parsedProxy = proxyInput.value.trim();
      const newCfg = {
        ...cfg,
        check_storefronts: parsedSfs,
        home_storefront: parsedHome || "my",
        newrelease_poll_interval_days: isNaN(parsedPoll) ? 1 : parsedPoll,
        watchlist_poll_interval_minutes: isNaN(parsedWlPoll) ? 10 : parsedWlPoll,
        watchlist_poll_batch_size: isNaN(parsedWlBatch) ? 5 : parsedWlBatch,
        watchlist_refresh_interval_days: isNaN(parsedWlRefresh) ? 7 : parsedWlRefresh,
        cors_proxy: parsedProxy,
      };

      await API.put("/api/config", newCfg);

      // Update in-memory state so widget/modal reflect new values immediately
      state.configuredStorefronts = parsedSfs;
      state.homeStorefront = newCfg.home_storefront;
      renderMetaSourceWidget();

      saveBtn.textContent = "Saved!";
      setTimeout(() => {
        saveBtn.textContent = "Save Config";
        saveBtn.disabled = false;
      }, 2000);
    } catch (e) {
      errorMsg.textContent = "Error saving config. Ensure JSON is valid.";
      errorMsg.style.display = "block";
      saveBtn.textContent = "Save Config";
      saveBtn.disabled = false;
    }
  });
  form.appendChild(saveBtn);
  wrap.appendChild(form);
}


// ---------------------------------------------------------------------------
// Artist links helper — renders multiple linked artist names or falls back
// to a single artist name/link when artists_json is not available.
// ---------------------------------------------------------------------------
function makeArtistLinks(album, cls, onNav) {
  const wrap = el("span", cls);
  const artists = album.artists_json;
  if (Array.isArray(artists) && artists.length) {
    wrap.classList.add("multi");
    artists.forEach((a, i) => {
      if (i > 0) wrap.appendChild(document.createTextNode(", "));
      const span = el("span", "artist-link", a.name || "—");
      if (a.id) {
        span.addEventListener("click", e => {
          e.stopPropagation();
          state.artistHint = { id: String(a.id), name: a.name, url: a.url, artwork_url: a.artwork_url, genre: a.genre };
          if (onNav) onNav();
          location.hash = `#/artist/${a.id}`;
        });
      }
      wrap.appendChild(span);
    });
    wrap.title = album.artist || "";
  } else {
    wrap.textContent = album.artist || "—";
    wrap.title = album.artist || "";
    if (album.artist_id) {
      wrap.addEventListener("click", e => {
        e.stopPropagation();
        if (onNav) onNav();
        location.hash = `#/artist/${album.artist_id}`;
      });
    }
  }
  return wrap;
}

// ---------------------------------------------------------------------------
// Album card
// ---------------------------------------------------------------------------
function albumCard(album) {
  const card = el("div", `album-card${album.watched ? " watched" : ""}`);
  card.dataset.id = album.store_adam_id;

  if (album.watched) {
    const badge = el("span", "watched-badge", "⭐");
    card.appendChild(badge);
  }

  card.appendChild(artworkEl(album.artwork_url, "album-artwork"));

  const info = el("div", "album-info");

  const title = el("div", "album-title", album.title || "—");
  title.title = album.title || "";
  info.appendChild(title);

  info.appendChild(makeArtistLinks(album, "album-artist"));

  if (album.genre) {
    const genre = el("div", "release-date", album.genre);
    genre.style.color = "var(--text-dim)";
    info.appendChild(genre);
  }

  const meta = el("div", "album-meta");
  const dateEl = el("span", `release-date${isFutureDate(album.release_date) ? " future" : ""}`, formatDate(album.release_date));
  meta.appendChild(dateEl);

  if (album.release_type) {
    const TYPE_SHORT = {
      "main-albums":        "Album",
      "compilation-albums": "Comp.",
      "live-albums":        "Live",
      "singles-eps":        "Single/EP",
    };
    const chip = el("span", `release-type-chip rt-${album.release_type}`, TYPE_SHORT[album.release_type] || album.release_type);
    meta.appendChild(chip);
  }

  const sf = sfChips(album.storefronts);
  meta.appendChild(sf);
  info.appendChild(meta);
  card.appendChild(info);

  card.addEventListener("click", () => openModal(album.store_adam_id));

  return card;
}

// ---------------------------------------------------------------------------
// Album Detail Modal
// ---------------------------------------------------------------------------
async function openModal(storeAdamId) {
  const overlay = $("modal-overlay");
  const body = $("modal-body");
  overlay.style.display = "flex";
  body.innerHTML = `<div style="padding:32px;text-align:center;color:var(--text-dim)">Loading…</div>`;

  let album;
  let myAlbumData = null;
  try {
    const home = state.homeStorefront;
    const shouldCompareMY = state.alwaysIncludeMY
      && home
      && state.metadataStorefront
      && state.metadataStorefront !== home;

    const dbPromise = API.get(`/api/releases/${storeAdamId}`);
    const lookupPromise = state.metadataStorefront
      ? API.get(`/api/lookup/${storeAdamId}?storefront=${state.metadataStorefront}`)
      : null;
    const myLookupPromise = shouldCompareMY
      ? API.get(`/api/lookup/${storeAdamId}?storefront=${home}`)
      : null;

    album = await dbPromise;

    if (lookupPromise) {
      try {
        const fresh = await lookupPromise;
        if (fresh.title)        album.title        = fresh.title;
        if (fresh.artist)       album.artist       = fresh.artist;
        if (fresh.artists?.length) album.artists_json = fresh.artists;
        if (fresh.artwork_url)  album.artwork_url  = fresh.artwork_url;
        if (fresh.genre)        album.genre        = fresh.genre;
        if (fresh.description)  album.description  = fresh.description;
        if (fresh.tracks?.length) album.tracks     = fresh.tracks;
        if (fresh.audio_formats?.length) album.audio_formats = fresh.audio_formats;
        album._metaSf = state.metadataStorefront;
      } catch {}
    }

    if (myLookupPromise) {
      try { myAlbumData = await myLookupPromise; } catch {}
    }
  } catch {
    body.innerHTML = `<div style="padding:32px;text-align:center">Failed to load</div>`;
    return;
  }

  body.innerHTML = "";

  // Modal header: thumbnail + title/artist info side-by-side
  const header = el("div", "modal-header");
  const thumb = artworkEl(album.artwork_url, "modal-artwork-thumb");
  if (album.artwork_url) {
    thumb.title = "Click to view full size";
    thumb.addEventListener("click", (e) => { e.stopPropagation(); showImageLightbox(album.artwork_url); });
  }
  header.appendChild(thumb);

  const headerInfo = el("div", "modal-header-info");
  const title = el("h2", "modal-title", album.title || "—");
  headerInfo.appendChild(title);

  if (album._metaSf) {
    const sfBadge = el("div", "modal-meta-sf-badge");
    sfBadge.innerHTML = `<span class="sf-chip ${album._metaSf}">${album._metaSf.toUpperCase()}</span> metadata`;
    headerInfo.appendChild(sfBadge);
  }

  if (album.artist || (Array.isArray(album.artists_json) && album.artists_json.length)) {
    headerInfo.appendChild(makeArtistLinks(album, "modal-artist", closeModal));
  }

  if (album.artist_id) {
    const headerActions = el("div", "modal-header-actions");

    const artBtn = el("button", "btn-header-action", "View Artist →");
    artBtn.addEventListener("click", () => { closeModal(); location.hash = `#/artist/${album.artist_id}`; });
    headerActions.appendChild(artBtn);

    const isWatched = state.watchedIds.has(album.artist_id);
    const watchBtn = el("button", `btn-header-action${isWatched ? " watching" : ""}`, isWatched ? "⭐ Watching" : "☆ Watch");
    watchBtn.addEventListener("click", async () => {
      const ps = state.metadataStorefront || state.homeStorefront || null;
      await toggleWatch(album.artist_id, album.artist, album.artist_url, ps);
      const w = state.watchedIds.has(album.artist_id);
      watchBtn.textContent = w ? "⭐ Watching" : "☆ Watch";
      watchBtn.className = `btn-header-action${w ? " watching" : ""}`;
    });
    headerActions.appendChild(watchBtn);
    headerInfo.appendChild(headerActions);
  }

  header.appendChild(headerInfo);
  body.appendChild(header);

  const details = el("div", "modal-details");

  // Compute diff early so the banner can appear before the tags
  const tracks = album.tracks || [];
  const myTracks = myAlbumData?.tracks || [];
  const hasDiff = tracks.length > 0 && myTracks.length > 0 && tracklistsDiffer(tracks, myTracks);
  const homeForDiff = state.homeStorefront || "my";

  if (hasDiff) {
    const diffBanner = el("div", "tracklist-diff-banner");
    const sfLabel = album._metaSf.toUpperCase();
    diffBanner.innerHTML = `<span class="diff-warn-icon">⚠</span> Track titles differ between <span class="sf-chip ${album._metaSf}">${sfLabel}</span> and <span class="sf-chip ${homeForDiff}">${homeForDiff.toUpperCase()}</span>`;
    details.appendChild(diffBanner);
  }

  // Tags
  const tags = el("div", "modal-tags");
  if (album.release_date) {
    const t = el("span", `modal-tag${isFutureDate(album.release_date) ? " future" : ""}`, `📅 ${formatDate(album.release_date)}`);
    tags.appendChild(t);
  }
  if (album.track_count) {
    const t = el("span", "modal-tag", `🎵 ${album.track_count} tracks`);
    tags.appendChild(t);
  }
  if (album.genre) {
    const t = el("span", "modal-tag", album.genre);
    tags.appendChild(t);
  }
  if (album.release_type) {
    const TYPE_LABELS = {
      "main-albums":        "Album",
      "compilation-albums": "Compilation",
      "live-albums":        "Live Album",
      "singles-eps":        "Single / EP",
    };
    const t = el("span", `modal-tag rt-modal rt-${album.release_type}`, TYPE_LABELS[album.release_type] || album.release_type);
    tags.appendChild(t);
  }
  if (album.storefronts?.length) {
    tags.appendChild(sfChips(album.storefronts));
  }
  details.appendChild(tags);

  const badges = formatBadges(album.audio_formats);
  if (badges) details.appendChild(badges);

  let descExpandBtn = null;
  let descEl = null;
  if (album.description) {
    descEl = el("p", "modal-desc", album.description);
    const expandBtn = el("button", "modal-desc-expand", "Show more");
    expandBtn.style.display = "none";
    expandBtn.addEventListener("click", () => {
      const expanded = descEl.classList.toggle("expanded");
      expandBtn.textContent = expanded ? "Show less" : "Show more";
    });
    details.appendChild(descEl);
    details.appendChild(expandBtn);
    descExpandBtn = expandBtn;
  }

  // Actions
  const actions = el("div", "modal-actions");

  const amLink = el("a", "btn-primary");
  amLink.href = album.url;
  amLink.target = "_blank";
  amLink.rel = "noopener";
  amLink.textContent = "Open in Apple Music ↗";
  actions.appendChild(amLink);

  const sfCheckBtn = el("button", "btn-secondary", "Check Storefronts");
  const sfResultContainer = el("div", "sf-check-results");
  sfResultContainer.style.marginTop = "16px";
  sfResultContainer.style.fontSize = "14px";
  sfResultContainer.style.lineHeight = "1.5";

  sfCheckBtn.addEventListener("click", async () => {
    sfCheckBtn.textContent = "Checking...";
    sfCheckBtn.disabled = true;
    try {
      const res = await API.get(`/api/releases/${album.store_adam_id}/check_storefronts`);
      sfCheckBtn.textContent = `Available in ${res.available.length} / ${res.available.length + res.unavailable.length}`;
      
      sfResultContainer.innerHTML = "";
      
      if (res.available.length > 0) {
        const availDiv = el("div");
        availDiv.textContent = "Available: ";
        res.available.forEach(sf => {
          const a = el("a");
          a.href = `https://music.apple.com/${sf}/album/${album.store_adam_id}`;
          a.target = "_blank";
          a.rel = "noopener";
          a.style.marginRight = "8px";
          a.style.color = "inherit";
          a.style.textDecoration = "underline";
          a.textContent = sf.toUpperCase();
          availDiv.appendChild(a);
        });
        sfResultContainer.appendChild(availDiv);
      }
      
      if (res.unavailable.length > 0) {
        const unavailDiv = el("div");
        unavailDiv.style.color = "var(--text-dim)";
        unavailDiv.textContent = "Unavailable: " + res.unavailable.map(s => s.toUpperCase()).join(", ");
        sfResultContainer.appendChild(unavailDiv);
      }
      
    } catch {
      sfCheckBtn.textContent = "Check Failed";
      sfCheckBtn.disabled = false;
    }
  });
  actions.appendChild(sfCheckBtn);

  details.appendChild(actions);
  details.appendChild(sfResultContainer);

  // Tracklist
  if (tracks.length) {
    const tl = el("div", "tracklist");
    const tlHead = el("div", "tracklist-header");
    if (hasDiff) {
      tlHead.innerHTML = `<span class="sf-chip ${album._metaSf}" style="font-size:10px;vertical-align:middle">${album._metaSf.toUpperCase()}</span> &nbsp;Tracklist — ${tracks.length} track${tracks.length !== 1 ? "s" : ""}`;
    } else {
      tlHead.textContent = `Tracklist — ${tracks.length} track${tracks.length !== 1 ? "s" : ""}`;
    }
    tl.appendChild(tlHead);
    tracks.forEach((t, i) => {
      const myTrack = myTracks[i];
      const rowDiffers = hasDiff && myTrack && t.title !== myTrack.title;
      const row = el("div", `track-row${rowDiffers ? " track-differs" : ""}`);
      const num = el("span", "track-num", String(t.track_number ?? i + 1));
      const title = el("span", "track-title", t.title || "—");
      const dur = el("span", "track-dur", formatDuration(t.duration_ms));
      row.appendChild(num);
      row.appendChild(title);
      row.appendChild(dur);
      tl.appendChild(row);
    });
    details.appendChild(tl);
  } else if (album._metaSf && album.artist_id) {
    // Live-fetched but no tracks found — show note
    const note = el("p", "tracklist-empty", "No tracklist available from this storefront.");
    details.appendChild(note);
  }

  if (hasDiff && myTracks.length) {
    const myTl = el("div", "tracklist");
    const myTlHead = el("div", "tracklist-header tracklist-header-my");
    myTlHead.innerHTML = `<span class="sf-chip ${homeForDiff}" style="font-size:10px;vertical-align:middle">${homeForDiff.toUpperCase()}</span> &nbsp;Tracklist — ${myTracks.length} track${myTracks.length !== 1 ? "s" : ""}`;
    myTl.appendChild(myTlHead);
    myTracks.forEach((t, i) => {
      const mainTrack = tracks[i];
      const rowDiffers = mainTrack && t.title !== mainTrack.title;
      const row = el("div", `track-row${rowDiffers ? " track-differs-my" : ""}`);
      const num = el("span", "track-num", String(t.track_number ?? i + 1));
      const title = el("span", "track-title", t.title || "—");
      const dur = el("span", "track-dur", formatDuration(t.duration_ms));
      row.appendChild(num);
      row.appendChild(title);
      row.appendChild(dur);
      myTl.appendChild(row);
    });
    details.appendChild(myTl);
  }

  body.appendChild(details);

  // Show the expand button only if the description actually overflows 3 lines
  if (descExpandBtn && descEl) {
    requestAnimationFrame(() => {
      if (descEl.scrollHeight > descEl.clientHeight + 2) {
        descExpandBtn.style.display = "";
      }
    });
  }
}

function closeModal() {
  $("modal-overlay").style.display = "none";
}

function showImageLightbox(url) {
  const box = el("div", "image-lightbox");
  const img = document.createElement("img");
  img.src = url;
  img.alt = "";
  box.appendChild(img);
  box.addEventListener("click", () => box.remove());
  document.body.appendChild(box);
}

// ---------------------------------------------------------------------------
// Utility components
// ---------------------------------------------------------------------------
function buildHeader(title, subtitle) {
  const header = el("div", "page-header");
  const h = el("h1", "page-title", title);
  header.appendChild(h);
  if (subtitle) {
    header.appendChild(el("p", "page-subtitle", subtitle));
  }
  return header;
}

function buildPagination(current, total, onPage) {
  const wrap = el("div", "pagination");

  const prev = el("button", "page-btn", "← Prev");
  prev.disabled = current <= 1;
  prev.addEventListener("click", () => onPage(current - 1));
  wrap.appendChild(prev);

  // Show up to 5 page buttons
  const start = Math.max(1, current - 2);
  const end = Math.min(total, start + 4);
  for (let p = start; p <= end; p++) {
    const btn = el("button", `page-btn${p === current ? " active" : ""}`, String(p));
    btn.addEventListener("click", () => onPage(p));
    wrap.appendChild(btn);
  }

  const info = el("span", "page-info", `Page ${current} of ${total}`);
  wrap.appendChild(info);

  const next = el("button", "page-btn", "Next →");
  next.disabled = current >= total;
  next.addEventListener("click", () => onPage(current + 1));
  wrap.appendChild(next);

  return wrap;
}

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

function tracklistsDiffer(a, b) {
  if (a.length !== b.length) return true;
  return a.some((t, i) => t.title !== b[i]?.title);
}

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
  // Routing
  window.addEventListener("hashchange", () => route(location.hash));

  // Refresh button
  $("btn-refresh").addEventListener("click", triggerRefresh);

  // Modal close
  $("modal-close").addEventListener("click", closeModal);
  $("modal-overlay").addEventListener("click", e => {
    if (e.target === $("modal-overlay")) closeModal();
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") closeModal();
  });

  // Metadata source widget
  initMetaSourceWidget();

  // Sidebar expand/collapse for small screens
  function expandSidebar() {
    $("sidebar").classList.add("expanded");
    $("sidebar-backdrop").classList.add("active");
  }
  function collapseSidebar() {
    $("sidebar").classList.remove("expanded");
    $("sidebar-backdrop").classList.remove("active");
  }
  $("sidebar-expand-btn").addEventListener("click", () => {
    $("sidebar").classList.contains("expanded") ? collapseSidebar() : expandSidebar();
  });
  $("sidebar-src-badge").addEventListener("click", expandSidebar);
  $("status-card").addEventListener("click", expandSidebar);
  $("sidebar-backdrop").addEventListener("click", collapseSidebar);

  // Initial status poll
  refreshStatus();
  setInterval(refreshStatus, 10000);

  // Initial route
  route(location.hash || "#/");
});
