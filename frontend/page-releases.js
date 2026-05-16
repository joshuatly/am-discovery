/* =========================================================
   AM Discovery — New Releases and All Albums pages
   ========================================================= */

"use strict";

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
// Page: New Releases
// ---------------------------------------------------------------------------
async function renderNewReleases(main, page = 1, query = "", storefront = "", watchedOnly = false, sort = state.currentSort) {
  state.currentPage = page;
  state.currentQuery = query;
  state.currentStorefront = storefront;
  state.currentWatchedOnly = watchedOnly;
  state.currentSort = sort;

  // Load config once
  if (state.configuredStorefronts === null || state.discoveryStorefronts === null) {
    try {
      const cfg = await API.get("/api/system/config");
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

  // Controls: filters (left) + search (right)
  const controls = el("div", "page-controls");
  const filtersDiv = el("div", "page-controls-filters");
  const searchDiv = el("div", "page-controls-search");
  const inp = el("input", "search-input");
  inp.type = "text";
  inp.placeholder = "Search title or artist…";
  inp.value = query;
  inp.id = "releases-search";
  inp.addEventListener("input", debounce(e => {
    renderNewReleases(main, 1, e.target.value.trim(), state.currentStorefront);
  }, 350));
  searchDiv.appendChild(inp);
  controls.appendChild(filtersDiv);
  controls.appendChild(searchDiv);
  wrap.appendChild(controls);

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

  const sfRow = el("div", "filter-row");
  sfRow.appendChild(el("span", "filter-row-label", "Region"));
  sfRow.appendChild(filterBar);
  filtersDiv.appendChild(sfRow);

  // Sort bar
  const sortBar = el("div", "type-filter-bar");
  [["release_date", "Release Date"], ["first_seen", "First Seen"]].forEach(([code, label]) => {
    const btn = el("button", "type-filter-btn" + (sort === code ? " active" : ""), label);
    btn.addEventListener("click", () => {
      ReleasesPrefs.setSort(code);
      renderNewReleases(main, 1, state.currentQuery, state.currentStorefront, state.currentWatchedOnly, code);
    });
    sortBar.appendChild(btn);
  });
  const sortRow = el("div", "filter-row");
  sortRow.appendChild(el("span", "filter-row-label", "Sort"));
  sortRow.appendChild(sortBar);
  filtersDiv.appendChild(sortRow);

  // Fetch
  await loadWatchedIds();
  let data;
  try {
    const qp = new URLSearchParams({ page, per_page: state.perPage, view: "new" });
    if (watchedOnly) qp.set("watched", "true");
    if (query) qp.set("q", query);
    if (storefront) qp.set("storefront", storefront);
    if (sort !== "release_date") qp.set("sort", sort);
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
    gridWrap.appendChild(buildPagination(page, totalPages, p => renderNewReleases(main, p, state.currentQuery, state.currentStorefront, state.currentWatchedOnly, sort)));
  }
}

// ---------------------------------------------------------------------------
// Page: All Albums
// ---------------------------------------------------------------------------
async function renderAllReleases(main, page = 1, query = "", storefront = "", watchedOnly = false, typeFilter = "", sort = state.currentSort) {
  state.currentSort = sort;
  main.innerHTML = "";
  const wrap = el("div", "page-enter");
  wrap.appendChild(buildHeader("📀 All Albums", "Every album in your local database"));

  const controls = el("div", "page-controls");
  const filtersDiv = el("div", "page-controls-filters");
  const searchDiv = el("div", "page-controls-search");
  const inp = el("input", "search-input");
  inp.type = "text";
  inp.placeholder = "Search title or artist…";
  inp.value = query;
  inp.addEventListener("input", debounce(e => {
    renderAllReleases(main, 1, e.target.value.trim(), storefront, watchedOnly, typeFilter);
  }, 350));
  searchDiv.appendChild(inp);
  controls.appendChild(filtersDiv);
  controls.appendChild(searchDiv);
  wrap.appendChild(controls);

  if (state.configuredStorefronts === null) {
    try {
      const cfg = await API.get("/api/system/config");
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
    btn.addEventListener("click", () => renderAllReleases(main, 1, query, code, watchedOnly, typeFilter));
    filterBar.appendChild(btn);
  });

  // Watched-only toggle
  const watchedToggle = el("button", `sf-filter-btn watched-toggle${watchedOnly ? " active" : ""}`, "Watched");
  watchedToggle.title = "Show only albums from watched artists";
  watchedToggle.addEventListener("click", () => renderAllReleases(main, 1, query, storefront, !watchedOnly, typeFilter));
  filterBar.appendChild(watchedToggle);

  const sfRow = el("div", "filter-row");
  sfRow.appendChild(el("span", "filter-row-label", "Region"));
  sfRow.appendChild(filterBar);
  filtersDiv.appendChild(sfRow);

  const typeFilterBar = el("div", "type-filter-bar");
  [["All", ""], ...RELEASE_TYPE_ORDER.map(k => [RELEASE_TYPE_LABELS[k], k])].forEach(([label, code]) => {
    const btn = el("button", "type-filter-btn" + (typeFilter === code ? " active" : ""));
    btn.textContent = label;
    btn.addEventListener("click", () => {
      state.allReleasesTypeFilter = code;
      renderAllReleases(main, 1, query, storefront, watchedOnly, code, sort);
    });
    typeFilterBar.appendChild(btn);
  });
  const typeRow = el("div", "filter-row");
  typeRow.appendChild(el("span", "filter-row-label", "Type"));
  typeRow.appendChild(typeFilterBar);
  filtersDiv.appendChild(typeRow);

  // Sort bar
  const sortBar = el("div", "type-filter-bar");
  [["release_date", "Release Date"], ["first_seen", "First Seen"]].forEach(([code, label]) => {
    const btn = el("button", "type-filter-btn" + (sort === code ? " active" : ""), label);
    btn.addEventListener("click", () => {
      ReleasesPrefs.setSort(code);
      renderAllReleases(main, 1, query, storefront, watchedOnly, typeFilter, code);
    });
    sortBar.appendChild(btn);
  });
  const sortRow = el("div", "filter-row");
  sortRow.appendChild(el("span", "filter-row-label", "Sort"));
  sortRow.appendChild(sortBar);
  filtersDiv.appendChild(sortRow);

  const gridWrap = el("div");
  gridWrap.appendChild(skeletonGrid(12));
  wrap.appendChild(gridWrap);
  main.appendChild(wrap);

  await loadWatchedIds();
  let data;
  try {
    const qp = new URLSearchParams({ page, per_page: state.perPage });
    if (watchedOnly) qp.set("watched", "true");
    if (query) qp.set("q", query);
    if (storefront) qp.set("storefront", storefront);
    if (typeFilter) qp.set("release_type", typeFilter);
    if (sort !== "release_date") qp.set("sort", sort);
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
    gridWrap.appendChild(buildPagination(page, totalPages, p => renderAllReleases(main, p, query, storefront, watchedOnly, typeFilter, sort)));
  }
}
