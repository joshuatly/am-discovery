/* =========================================================
   AM Discovery — Router and bootstrap
   ========================================================= */

"use strict";

// ---------------------------------------------------------------------------
// Router
// ---------------------------------------------------------------------------
// The paginated list pages remember where you were. Leaving one (to an artist
// page, say) stashes its scroll offset; coming back re-renders the same page
// number and filters and scrolls you back down to the tile you clicked.
const SCROLL_MEMORY_ROUTES = new Set(["#/", "#/all"]);
let _activeRoute = null;

// Scrolls back to the offset remembered for `hash` once `rendered` settles.
function restoreScroll(hash, rendered) {
  const y = state.scrollMemory[hash] || 0;
  const go = () => { window.scrollTo({ top: y, behavior: "auto" }); };
  Promise.resolve(rendered).then(go, go);
}

// Title + sidebar highlight for a page route (also used for the page that
// sits behind the album modal).
function applyPageChrome(hash) {
  document.querySelectorAll(".nav-link").forEach(a => {
    const page = a.dataset.page;
    const active =
      (page === "releases"  && (hash === "#/" || hash.startsWith("#/releases"))) ||
      (page === "all"       && hash === "#/all") ||
      (page === "watchlist" && hash === "#/watchlist") ||
      (page === "admin"     && hash.startsWith("#/admin")) ||
      (page === "settings"  && hash === "#/settings");
    a.classList.toggle("active", active);
  });

  if (hash === "#/all") document.title = "All Albums — AM Discovery";
  else if (hash === "#/watchlist") document.title = "Artist Watchlist — AM Discovery";
  else if (hash === "#/settings") document.title = "Settings — AM Discovery";
  else if (hash.startsWith("#/admin")) document.title = "MB Admin — AM Discovery";
  else if (hash.startsWith("#/artist/")) document.title = "Artist — AM Discovery";
  else document.title = "New Releases — AM Discovery";
}

function renderPage(hash) {
  const main = $("main-content");

  // Stash the outgoing page's offset before the render blows the DOM away.
  // Also covers re-rendering the current page in place (e.g. after a watch
  // toggle), which would otherwise restore a stale offset.
  if (_activeRoute && SCROLL_MEMORY_ROUTES.has(_activeRoute)) {
    state.scrollMemory[_activeRoute] = window.scrollY;
  }
  _activeRoute = hash;
  applyPageChrome(hash);

  if (hash === "#/all") {
    restoreScroll(hash, renderAllReleases(
      main,
      state.allReleasesPage,
      state.allReleasesQuery,
      state.allReleasesStorefront,
      state.allReleasesWatchedOnly,
      state.allReleasesTypeFilter,
    ));
  } else if (hash === "#/watchlist") {
    const sortFilter = WatchlistPrefs.getSortFilter();
    renderWatchlist(main, "", "", sortFilter, state.watchlistPage);
  } else if (hash === "#/settings") {
    renderSettings(main);
  } else if (hash.startsWith("#/admin")) {
    const tab = hash.slice("#/admin".length).replace(/^\//, "") || "";
    renderAdmin(main, tab || null);
  } else if (hash.startsWith("#/artist/")) {
    const artistId = hash.slice("#/artist/".length);
    renderArtist(main, artistId);
  } else {
    restoreScroll(hash, renderNewReleases(
      main,
      state.currentPage,
      state.currentQuery,
      state.currentStorefront,
      state.currentWatchedOnly,
    ));
  }
}

function route(hash) {
  hash = hash || "#/";
  const albumId = albumIdFromHash(hash);
  if (albumId) return routeAlbum(hash, albumId);

  if (_album) {
    // Leaving the album modal — X, Back, or a link inside it.
    _album = null;
    _closeTo = null;
    closeModal();
    // Back onto the page that was already rendered behind the modal: keep it
    // as-is (page, filters, scroll) instead of re-rendering.
    if (hash === _activeRoute) {
      applyPageChrome(hash);
      return;
    }
  }
  renderPage(hash);
}

// ---------------------------------------------------------------------------
// Album route — #/album/<store_adam_id>
// ---------------------------------------------------------------------------
// The album detail modal is a route of its own so it can be bookmarked, shared
// and opened in a new tab. It always renders over a page ("background"):
//   • opened from a page in the app → that page, left untouched
//   • opened cold (new tab, pasted URL, reload with no history) → New Releases
// Each album history entry records {bg, depth, cold} in history.state, so Back
// from an artist page re-renders the right background, and closing knows how
// far back the background entry is:
//   depth — album entries pushed since the background page (A=1, then B=2 …)
//   cold  — the chain began with a direct link, so no background entry exists
//           in history; its first album entry (depth 0) is swapped for it.
const ALBUM_ROUTE_RE = /^#\/album\/([^/?#]+)\/?$/;
let _album = null;    // { hash, bg, depth, cold } while an album route is showing
let _closeTo = null;  // background to swap in once a cold chain is unwound

function albumIdFromHash(hash) {
  const m = ALBUM_ROUTE_RE.exec(hash || "");
  if (!m) return null;
  try { return decodeURIComponent(m[1]); } catch { return null; }
}

function routeAlbum(hash, albumId) {
  const hs = history.state && typeof history.state === "object" ? history.state : {};
  let entry = hs.amAlbum;

  if (_closeTo !== null && entry && entry.cold && entry.depth === 0) {
    // Closing a deep-linked chain: we've stepped back to its first album,
    // which has no page behind it in history — replace it with the background.
    const to = _closeTo;
    _closeTo = null;
    location.replace(to);
    return Promise.resolve(null);
  }

  if (!entry) {
    if (_album) entry = { bg: _album.bg, depth: _album.depth + 1, cold: _album.cold };
    else if (_activeRoute) entry = { bg: _activeRoute, depth: 1, cold: false };
    else entry = { bg: "#/", depth: 0, cold: true };
    try { history.replaceState({ ...hs, amAlbum: entry }, ""); } catch {}
  }

  if (_activeRoute !== entry.bg) renderPage(entry.bg);
  else applyPageChrome(entry.bg);

  _album = { hash, bg: entry.bg, depth: entry.depth, cold: entry.cold };
  document.title = "Album — AM Discovery";
  return Promise.resolve(openModal(albumId)).then(album => {
    if (album && _album && _album.hash === hash) {
      document.title = `${album.title || "Album"} — AM Discovery`;
    }
    return album;
  });
}

// X / Esc / backdrop click. Always returns to the background page, however
// many albums were hopped through; the browser Back button still steps back
// one album at a time. Non-album uses of the overlay (the notification event
// editor) just close.
function closeAlbumModal() {
  if (!_album) {
    closeModal();
    return;
  }
  const { bg, depth, cold } = _album;
  closeModal();
  if (depth > 0) {
    if (cold) _closeTo = bg;
    history.go(-depth);
  } else {
    location.replace(bg);
  }
}

// ---------------------------------------------------------------------------
// Feature flags
// ---------------------------------------------------------------------------
// Fetched once at bootstrap (before the initial route) so the Admin nav link
// and #/admin route agree from the first paint. Settings saves keep it in
// sync afterwards (see page-settings.js).
async function applyMbScanFeatureFlag() {
  try {
    const cfg = await API.get("/api/system/config");
    state.mbScanEnabled = cfg.mb_scan_enabled !== false;
  } catch {
    state.mbScanEnabled = true;
  }
  const navAdmin = $("nav-admin");
  if (navAdmin) navAdmin.style.display = state.mbScanEnabled ? "" : "none";
}

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", async () => {
  // Routing
  window.addEventListener("hashchange", () => route(location.hash));
  // Re-route on nav click when the hash isn't changing (e.g. clicking "New
  // Releases" while already on that page) — otherwise hashchange does it, and
  // routing here too would double-render and clobber the stashed scroll offset.
  // Modified clicks are left alone so ⌘/Ctrl-click still opens a new tab.
  document.querySelectorAll(".nav-link").forEach(a => {
    a.addEventListener("click", e => {
      if (isModifiedClick(e)) return;
      const href = a.getAttribute("href");
      if ((location.hash || "#/") !== href) return;
      e.preventDefault();
      route(href);
    });
  });

  // Refresh button
  $("btn-refresh").addEventListener("click", triggerRefresh);

  // Modal close
  $("modal-close").addEventListener("click", closeAlbumModal);
  $("modal-overlay").addEventListener("click", e => {
    if (e.target === $("modal-overlay")) closeAlbumModal();
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && $("modal-overlay").style.display !== "none") closeAlbumModal();
  });

  // Metadata source widget. The album modal awaits this so a deep-linked
  // album looks up the configured storefronts rather than the "us" fallback.
  state.configReady = initMetaSourceWidget();

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

  // Gate the Admin nav link/route before the first render so a bookmarked
  // #/admin URL doesn't flash the page before redirecting away.
  await applyMbScanFeatureFlag();

  // Initial route
  route(location.hash || "#/");
});
