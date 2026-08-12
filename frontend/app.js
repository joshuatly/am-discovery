/* =========================================================
   AM Discovery — Router and bootstrap
   ========================================================= */

"use strict";

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
      (page === "admin"     && hash.startsWith("#/admin")) ||
      (page === "settings"  && hash === "#/settings");
    a.classList.toggle("active", active);
  });

  if (hash === "#/all") {
    document.title = "All Albums — AM Discovery";
    renderAllReleases(main, 1, "", "", false, state.allReleasesTypeFilter);
  } else if (hash === "#/watchlist") {
    document.title = "Artist Watchlist — AM Discovery";
    const sortFilter = WatchlistPrefs.getSortFilter();
    renderWatchlist(main, "", "", sortFilter, state.watchlistPage);
  } else if (hash === "#/settings") {
    document.title = "Settings — AM Discovery";
    renderSettings(main);
  } else if (hash.startsWith("#/admin")) {
    document.title = "Admin — AM Discovery";
    const tab = hash.slice("#/admin".length).replace(/^\//, "") || "";
    renderAdmin(main, tab || null);
  } else if (hash.startsWith("#/artist/")) {
    document.title = "Artist — AM Discovery";
    const artistId = hash.slice("#/artist/".length);
    renderArtist(main, artistId);
  } else {
    document.title = "New Releases — AM Discovery";
    renderNewReleases(main);
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
  // Re-route on nav click even when hash hasn't changed (e.g. clicking "New Releases" while already on that page)
  document.querySelectorAll(".nav-link").forEach(a => {
    a.addEventListener("click", () => route(a.getAttribute("href")));
  });

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

  // Gate the Admin nav link/route before the first render so a bookmarked
  // #/admin URL doesn't flash the page before redirecting away.
  await applyMbScanFeatureFlag();

  // Initial route
  route(location.hash || "#/");
});
