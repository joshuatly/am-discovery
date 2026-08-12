/* =========================================================
   AM Discovery — Global state and watchlist helpers
   ========================================================= */

"use strict";

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const state = {
  watchedIds: new Set(),
  watchedIdsLoaded: false,
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
  artistSeedFilter: false,    // true = only releases that need MusicBrainz seeding
  allReleasesTypeFilter: "",  // "" = all, else a release_type value
  currentSort: ReleasesPrefs.getSort(),  // "release_date" | "first_seen"
  cliSchedulerEnabled: false, // true when cli_scheduler_url is configured
  watchlistPage: 0,           // remembered page index for watchlist (0-based)
  mbScanEnabled: true,        // true when mb_scan_enabled is configured; gates the Admin nav link/page
  adminTab: "releases",       // active admin tab: "artists" | "releases"
  adminReleaseSort: "release_date", // admin releases sort key
  adminReleaseCountry: "",    // admin releases country filter ("" = all), by preferred source
  adminGroupByArtist: false,  // group admin releases by artist
  adminReleasePage: 1,        // remembered page number for the admin releases tab
};

// ---------------------------------------------------------------------------
// Watchlist helpers
// ---------------------------------------------------------------------------
async function loadWatchedIds() {
  if (state.watchedIdsLoaded) return;
  try {
    const ids = await API.get("/api/watchlist/ids");
    state.watchedIds = new Set(ids);
    state.watchedIdsLoaded = true;
  } catch {}
}

async function submitCliSchedulerJob(storefront, albumId) {
  const r = await fetch("/api/system/cli-scheduler/submit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ storefront, album_id: albumId }),
  });
  return r.status;
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
