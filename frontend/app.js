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
  const diff = Date.now() - new Date(isoStr + "Z").getTime();
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
  const d = el("div", cls === "album-artwork" ? "album-artwork-placeholder" : (cls === "modal-artwork" ? "modal-artwork-placeholder" : "album-artwork-placeholder"));
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
  metadataStorefront: localStorage.getItem("metadataStorefront") || "",
  alwaysIncludeMY: localStorage.getItem("alwaysIncludeMY") === "true",
  homeStorefront: "",
};

// ---------------------------------------------------------------------------
// Status bar
// ---------------------------------------------------------------------------
async function refreshStatus() {
  try {
    const s = await API.get("/api/status");
    const dot = $("status-dot");
    const val = $("status-last-run");
    if (s.is_running) {
      dot.className = "status-dot spin";
      val.textContent = "Scanning…";
    } else {
      dot.className = "status-dot ok";
      val.textContent = s.last_run ? timeAgo(s.last_run.ran_at) : "never";
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
function updateFetchArtistBtn() {
  const fetchBtn = document.querySelector(".btn-fetch-artist");
  if (!fetchBtn || fetchBtn.disabled) return;
  const sf = state.metadataStorefront;
  fetchBtn.textContent = sf ? `↓ Fetch from ${sf.toUpperCase()}` : "↓ Fetch All";
}

function renderMetaSourceWidget() {
  const chips = $("meta-source-chips");
  if (!chips) return;
  chips.innerHTML = "";

  const storefronts = state.configuredStorefronts || [];

  // "Off" option
  const offBtn = el("button", `meta-src-btn${!state.metadataStorefront ? " active" : ""}`, "Off");
  offBtn.title = "Use cached metadata";
  offBtn.addEventListener("click", () => {
    state.metadataStorefront = "";
    localStorage.setItem("metadataStorefront", "");
    renderMetaSourceWidget();
    updateFetchArtistBtn();
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

async function toggleWatch(artistId, name, artistUrl) {
  if (state.watchedIds.has(artistId)) {
    await API.del(`/api/watchlist/${artistId}`);
    state.watchedIds.delete(artistId);
  } else {
    await API.post("/api/watchlist", { artist_id: artistId, name, url: artistUrl });
    state.watchedIds.add(artistId);
  }
}

// ---------------------------------------------------------------------------
// Page: New Releases
// ---------------------------------------------------------------------------
async function renderNewReleases(main, page = 1, query = "", storefront = "") {
  state.currentPage = page;
  state.currentQuery = query;
  state.currentStorefront = storefront;

  // Skeleton
  main.innerHTML = "";
  const wrap = el("div", "page-enter");
  wrap.appendChild(buildHeader("🎵 New Releases", "Latest albums discovered across HK · JP · MY · TW"));

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

  // Load config once, then insert the filter bar
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
    btn.addEventListener("click", () => renderNewReleases(main, 1, state.currentQuery, code));
    filterBar.appendChild(btn);
  });
  searchBar.after(filterBar);

  // Fetch
  await loadWatchedIds();
  let data;
  try {
    const qp = new URLSearchParams({ page, per_page: state.perPage });
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
    gridWrap.appendChild(buildPagination(page, totalPages, p => renderNewReleases(main, p, state.currentQuery, state.currentStorefront)));
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
    gridWrap.innerHTML = `<div class="empty-state"><div class="empty-icon">📀</div><div class="empty-title">No albums yet</div><div class="empty-desc">Run a refresh to populate the database</div></div>`;
    return;
  }

  const grid = el("div", "album-grid");
  data.items.forEach(album => grid.appendChild(albumCard(album, true)));
  gridWrap.appendChild(grid);

  const totalPages = Math.ceil(data.total / state.perPage);
  if (totalPages > 1) {
    gridWrap.appendChild(buildPagination(page, totalPages, p => renderAllReleases(main, p, query, storefront)));
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

  await loadWatchedIds();
  wrap.innerHTML = "";

  // Header
  const header = el("div", "artist-header");
  const avatar = el("div", "artist-avatar");
  avatar.textContent = (data.artist_name || "?")[0].toUpperCase();
  header.appendChild(avatar);

  const meta = el("div", "artist-meta");
  const nameBig = el("h1", "artist-name-big", data.artist_name || "Unknown Artist");
  meta.appendChild(nameBig);

  const links = el("div", "artist-links");
  if (data.artist_url) {
    const extLink = el("a", "artist-ext-link", "Open in Apple Music ↗");
    extLink.href = data.artist_url;
    extLink.target = "_blank";
    extLink.rel = "noopener";
    links.appendChild(extLink);
  }

  const isWatched = state.watchedIds.has(artistId);
  const watchBtn = el("button", `btn-watch${isWatched ? " watching" : ""}`, isWatched ? "⭐ Watching" : "☆ Watch");
  watchBtn.addEventListener("click", async () => {
    await toggleWatch(artistId, data.artist_name, data.artist_url);
    watchBtn.textContent = state.watchedIds.has(artistId) ? "⭐ Watching" : "☆ Watch";
    watchBtn.classList.toggle("watching", state.watchedIds.has(artistId));
  });
  links.appendChild(watchBtn);

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
    wrap.innerHTML += `<div class="empty-state"><div class="empty-icon">🎵</div><div class="empty-title">No releases found</div><div class="empty-desc">This artist's releases will appear here after a refresh</div></div>`;
    return;
  }

  const grid = el("div", "album-grid");
  data.releases.forEach(album => {
    album.watched = state.watchedIds.has(album.artist_id);
    if (data.artist_name) album.artist = data.artist_name;
    grid.appendChild(albumCard(album));
  });
  wrap.appendChild(grid);
}

// ---------------------------------------------------------------------------
// Page: Watchlist
// ---------------------------------------------------------------------------
async function renderWatchlist(main) {
  main.innerHTML = "";
  const wrap = el("div", "page-enter");
  wrap.appendChild(buildHeader("⭐ Watchlist", "Artists you're following"));
  main.appendChild(wrap);

  let list;
  try {
    list = await API.get("/api/watchlist");
  } catch {
    wrap.innerHTML += `<div class="empty-state"><div class="empty-icon">⚠️</div><div class="empty-title">Could not load watchlist</div></div>`;
    return;
  }

  if (!list.length) {
    wrap.innerHTML += `<div class="empty-state"><div class="empty-icon">⭐</div><div class="empty-title">No artists watched yet</div><div class="empty-desc">Click an artist's name on the New Releases page, then press Watch</div></div>`;
    return;
  }

  state.watchedIds = new Set(list.map(a => a.artist_id));

  const grid = el("div", "watchlist-grid");
  list.forEach(artist => {
    const card = el("div", "watchlist-card");

    const avatar = el("div", "watchlist-avatar");
    avatar.textContent = (artist.name || "?")[0].toUpperCase();
    card.appendChild(avatar);

    const info = el("div", "watchlist-info");
    const name = el("a", "watchlist-name", artist.name);
    name.href = `#/artist/${artist.artist_id}`;
    name.addEventListener("click", e => {
      e.preventDefault();
      location.hash = `#/artist/${artist.artist_id}`;
    });
    info.appendChild(name);

    const date = el("div", "watchlist-date", `Added ${formatDate(artist.added_at?.slice(0, 10))}`);
    info.appendChild(date);
    card.appendChild(info);

    const unwatchBtn = el("button", "btn-unwatch", "Remove");
    unwatchBtn.addEventListener("click", async () => {
      await toggleWatch(artist.artist_id, artist.name, artist.url);
      card.remove();
      if (!grid.children.length) {
        grid.innerHTML = `<div class="empty-state" style="grid-column:1/-1"><div class="empty-icon">⭐</div><div class="empty-title">Watchlist is empty</div></div>`;
      }
    });
    card.appendChild(unwatchBtn);
    grid.appendChild(card);
  });
  wrap.appendChild(grid);
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
  const pollLabel = el("label", "", "Poll Interval (minutes)");
  pollLabel.style.fontWeight = "600";
  pollGroup.appendChild(pollLabel);
  const pollInput = el("input", "search-input");
  pollInput.type = "number";
  pollInput.value = cfg.poll_interval_minutes || 60;
  pollGroup.appendChild(pollInput);
  form.appendChild(pollGroup);

  // Rooms
  const roomsGroup = el("div");
  roomsGroup.style.display = "flex";
  roomsGroup.style.flexDirection = "column";
  roomsGroup.style.gap = "8px";
  const roomsLabel = el("label", "", "Rooms Configuration (JSON)");
  roomsLabel.style.fontWeight = "600";
  roomsGroup.appendChild(roomsLabel);
  const roomsInput = el("textarea", "search-input");
  roomsInput.style.fontFamily = "monospace";
  roomsInput.style.minHeight = "200px";
  roomsInput.style.resize = "vertical";
  roomsInput.value = JSON.stringify(cfg.rooms || {}, null, 2);
  roomsGroup.appendChild(roomsInput);
  form.appendChild(roomsGroup);

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
      const parsedRooms = JSON.parse(roomsInput.value);

      const newCfg = {
        ...cfg,
        check_storefronts: parsedSfs,
        home_storefront: parsedHome || "my",
        poll_interval_minutes: isNaN(parsedPoll) ? 60 : parsedPoll,
        rooms: parsedRooms
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
// Album card
// ---------------------------------------------------------------------------
function albumCard(album, showGenre = false) {
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

  const artist = el("span", "album-artist", album.artist || "—");
  artist.title = album.artist || "";
  if (album.artist_id) {
    artist.addEventListener("click", e => {
      e.stopPropagation();
      location.hash = `#/artist/${album.artist_id}`;
    });
  }
  info.appendChild(artist);

  if (showGenre && album.genre) {
    const genre = el("div", "release-date", album.genre);
    genre.style.color = "var(--text-dim)";
    info.appendChild(genre);
  }

  const meta = el("div", "album-meta");
  const dateEl = el("span", `release-date${isFutureDate(album.release_date) ? " future" : ""}`, formatDate(album.release_date));
  meta.appendChild(dateEl);

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

  // Artwork
  body.appendChild(artworkEl(album.artwork_url, "modal-artwork"));

  const details = el("div", "modal-details");

  const title = el("h2", "modal-title", album.title || "—");
  details.appendChild(title);

  if (album._metaSf) {
    const sfBadge = el("div", "modal-meta-sf-badge");
    sfBadge.innerHTML = `<span class="sf-chip ${album._metaSf}">${album._metaSf.toUpperCase()}</span> metadata`;
    details.appendChild(sfBadge);
  }

  if (album.artist) {
    const artist = el("span", "modal-artist", album.artist);
    if (album.artist_id) {
      artist.addEventListener("click", () => {
        closeModal();
        location.hash = `#/artist/${album.artist_id}`;
      });
    }
    details.appendChild(artist);
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
  if (album.storefronts?.length) {
    tags.appendChild(sfChips(album.storefronts));
  }
  details.appendChild(tags);

  const badges = formatBadges(album.audio_formats);
  if (badges) details.appendChild(badges);

  if (album.description) {
    const desc = el("p", "modal-desc", album.description);
    details.appendChild(desc);
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

  if (album.artist_id) {
    const artBtn = el("button", "btn-secondary", "View Artist →");
    artBtn.addEventListener("click", () => {
      closeModal();
      location.hash = `#/artist/${album.artist_id}`;
    });
    actions.appendChild(artBtn);
  }

  // Watch button in modal
  const isWatched = state.watchedIds.has(album.artist_id);
  const watchBtn = el("button", `btn-secondary${isWatched ? " watching" : ""}`, isWatched ? "⭐ Watching" : "☆ Watch Artist");
  if (album.artist_id) {
    watchBtn.addEventListener("click", async () => {
      await toggleWatch(album.artist_id, album.artist, album.artist_url);
      const w = state.watchedIds.has(album.artist_id);
      watchBtn.textContent = w ? "⭐ Watching" : "☆ Watch Artist";
    });
    actions.appendChild(watchBtn);
  }

  details.appendChild(actions);
  details.appendChild(sfResultContainer);

  // Tracklist
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
}

function closeModal() {
  $("modal-overlay").style.display = "none";
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

  // Initial status poll
  refreshStatus();
  setInterval(refreshStatus, 10000);

  // Initial route
  route(location.hash || "#/");
});
