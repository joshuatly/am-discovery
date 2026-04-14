/* =========================================================
   AM Discovery — Artist Watchlist page
   ========================================================= */

"use strict";

// Pure helper: slice a list for the given page and page size.
// Returns { items, page (clamped), totalPages, total }.
function paginateList(list, page, pageSize) {
  const total = list.length;
  const totalPages = Math.ceil(total / pageSize) || 1;
  const safePage = Math.max(0, Math.min(page, totalPages - 1));
  return { items: list.slice(safePage * pageSize, (safePage + 1) * pageSize), page: safePage, totalPages, total };
}

const WATCHLIST_PAGE_SIZE = 48;

async function renderWatchlist(main, preferredSourceFilter = "", collectionStatusFilter = "", sortFilter = "name", initialPage = 0) {
  main.innerHTML = "";
  const wrap = el("div", "page-enter");
  wrap.appendChild(buildHeader("⭐ Artist Watchlist", "Artists you're following"));
  main.appendChild(wrap);

  const controls = el("div", "page-controls");
  const filtersDiv = el("div", "page-controls-filters");
  const searchDiv = el("div", "page-controls-search");
  const searchInput = el("input", "search-input");
  searchInput.type = "text";
  searchInput.placeholder = "Search artists…";
  const amSearchLabel = el("label", "am-search-label");
  const amSearchCheck = el("input");
  amSearchCheck.type = "checkbox";
  amSearchLabel.appendChild(amSearchCheck);
  amSearchLabel.appendChild(document.createTextNode(" Also search Apple Music"));
  searchDiv.appendChild(searchInput);
  searchDiv.appendChild(amSearchLabel);
  controls.appendChild(filtersDiv);
  controls.appendChild(searchDiv);
  wrap.appendChild(controls);

  const qpParts = [];
  if (preferredSourceFilter) qpParts.push(`preferred_source=${preferredSourceFilter}`);
  if (collectionStatusFilter) qpParts.push(`collection_status=${collectionStatusFilter}`);
  if (sortFilter && sortFilter !== "name") qpParts.push(`sort=${sortFilter}`);
  const qp = qpParts.length ? `?${qpParts.join("&")}` : "";
  let list;
  try {
    list = await API.get(`/api/watchlist${qp}`);
  } catch {
    wrap.innerHTML += `<div class="empty-state"><div class="empty-icon">⚠️</div><div class="empty-title">Could not load watchlist</div></div>`;
    return;
  }

  // Sync watchedIds from the unfiltered list result (watchlist page always has full data)
  state.watchedIds = new Set(list.map(a => a.artist_id));
  state.watchedIdsLoaded = true;

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
    btn.addEventListener("click", () => renderWatchlist(main, code, collectionStatusFilter, sortFilter));
    psFilterBar.appendChild(btn);
  });
  const psRow = el("div", "filter-row");
  psRow.appendChild(el("span", "filter-row-label", "Country"));
  psRow.appendChild(psFilterBar);
  filtersDiv.appendChild(psRow);

  // Collection status filter bar
  const csFilterBar = el("div", "cs-filter-bar");
  const csButtons = [["", "All"], ...Object.entries(COLLECTION_STATUS_LABELS)];
  csButtons.forEach(([code, label]) => {
    const cls = "cs-filter-btn" + (code ? ` status-${code}` : "") + (collectionStatusFilter === code ? " active" : "");
    const btn = el("button", cls);
    btn.textContent = label;
    btn.addEventListener("click", () => renderWatchlist(main, preferredSourceFilter, code, sortFilter));
    csFilterBar.appendChild(btn);
  });
  const csRow = el("div", "filter-row");
  csRow.appendChild(el("span", "filter-row-label", "Status"));
  csRow.appendChild(csFilterBar);
  filtersDiv.appendChild(csRow);

  // Sort filter bar
  const sortFilterBar = el("div", "cs-filter-bar sort-filter-bar");
  const sortOptions = [["name", "Name"], ["added", "Added"], ["recent_release", "Recent Release"], ["recent_album", "Recent Album"]];
  sortOptions.forEach(([code, label]) => {
    const btn = el("button", "cs-filter-btn sort-filter-btn" + (sortFilter === code ? " active" : ""));
    btn.textContent = label;
    btn.addEventListener("click", () => {
      WatchlistPrefs.setSortFilter(code);
      renderWatchlist(main, preferredSourceFilter, collectionStatusFilter, code);
    });
    sortFilterBar.appendChild(btn);
  });
  const sortRow = el("div", "filter-row");
  sortRow.appendChild(el("span", "filter-row-label", "Sort"));
  sortRow.appendChild(sortFilterBar);
  filtersDiv.appendChild(sortRow);

  // Results area: watched list + AM search suggestions
  const grid = el("div", "watchlist-grid");
  const alphaIndexContainer = el("div", "alpha-index-container");
  const pageLayout = el("div", "watchlist-page-layout");
  const gridWrap = el("div", "watchlist-grid-wrap");
  gridWrap.appendChild(grid);
  pageLayout.appendChild(gridWrap);
  pageLayout.appendChild(alphaIndexContainer);
  wrap.appendChild(pageLayout);

  function makeWatchedCard(artist) {
    const card = el("div", "watchlist-card");
    card.dataset.artistId = artist.artist_id;
    const _displayFirst = ((artist.alt_name || artist.name || "?")[0]).toUpperCase();
    card.dataset.displayLetter = /[A-Z]/.test(_displayFirst) ? _displayFirst : "#";

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

    if (artist.alt_name) {
      const altNameEl = el("div", "watchlist-alt-name");
      altNameEl.textContent = artist.alt_name;
      info.appendChild(altNameEl);
    }

    let dateText = "";
    if (sortFilter === "added") {
      const _addedAt = typeof artist.added_at === "number"
        ? new Date(artist.added_at * 1000).toISOString().slice(0, 10)
        : artist.added_at?.slice(0, 10);
      dateText = `Added ${formatDate(_addedAt)}`;
    } else if (sortFilter === "recent_release") {
      dateText = artist.latest_release_date
        ? `Latest: ${formatDate(artist.latest_release_date.slice(0, 10))}`
        : "No releases";
    } else if (sortFilter === "recent_album") {
      dateText = artist.latest_album_date
        ? `Latest: ${formatDate(artist.latest_album_date.slice(0, 10))}`
        : "No releases";
    }
    const date = el("div", "watchlist-date", dateText);
    if (artist.preferred_source) {
      const psBadge = el("span", `sf-chip ${artist.preferred_source}`);
      applysfChipColor(psBadge, artist.preferred_source);
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
    unwatchBtn.style.display = "none";
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
      state.artistHint = { id: String(artist.id), name: artist.name, url: artist.url, artwork_url: artist.artwork_url, genre: artist.genre, born_or_formed: artist.born_or_formed, origin: artist.origin, artist_bio: artist.artist_bio, is_group: artist.is_group };
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
  let _searchAbort = null;
  let _lastSuggestions = [];
  let _localSuggestions = [];
  let _rateLimitedUntil = 0;
  let _currentPage = 0;

  function renderGrid(q, page = 0) {
    grid.innerHTML = "";

    const qLower = q.toLowerCase();
    const filtered = q
      ? list.filter(a =>
          (a.alt_name && a.alt_name.toLowerCase().includes(qLower)) ||
          a.name.toLowerCase().includes(qLower) ||
          (a.artist_bio && a.artist_bio.toLowerCase().includes(qLower))
        )
      : list;

    // Only paginate when not searching (search results are small enough to show all)
    const usePagination = !q;
    const { items: pageItems, page: safePage, totalPages } = usePagination
      ? paginateList(filtered, page, WATCHLIST_PAGE_SIZE)
      : { items: filtered, page: 0, totalPages: 1, total: filtered.length };
    _currentPage = safePage;
    state.watchlistPage = safePage;

    pageItems.forEach(a => grid.appendChild(makeWatchedCard(a)));

    // Show local DB suggestions (non-watchlist artists from local search)
    const localSuggestions = _localSuggestions.filter(a => !state.watchedIds.has(a.id));
    if (localSuggestions.length) {
      if (pageItems.length) {
        const sep = el("div", "watchlist-separator", "Local Library");
        sep.style.cssText = "grid-column:1/-1;font-size:11px;color:var(--text-dim);text-transform:uppercase;letter-spacing:.06em;padding:4px 0;";
        grid.appendChild(sep);
      }
      localSuggestions.forEach(a => grid.appendChild(makeSuggestionCard(a)));
    }

    // Show AM suggestions (only when Apple Music search is enabled, already-watched excluded)
    const amSuggestions = _lastSuggestions.filter(a => !state.watchedIds.has(a.id));
    if (amSuggestions.length) {
      if (pageItems.length || localSuggestions.length) {
        const sep = el("div", "watchlist-separator", "Also on Apple Music");
        sep.style.cssText = "grid-column:1/-1;font-size:11px;color:var(--text-dim);text-transform:uppercase;letter-spacing:.06em;padding:4px 0;";
        grid.appendChild(sep);
      }
      amSuggestions.forEach(a => grid.appendChild(makeSuggestionCard(a)));
    }

    if (!grid.children.length) {
      if (q) {
        grid.innerHTML = `<div class="empty-state" style="grid-column:1/-1"><div class="empty-icon">🔍</div><div class="empty-title">No results for "${q}"</div></div>`;
      } else {
        grid.innerHTML = `<div class="empty-state" style="grid-column:1/-1"><div class="empty-icon">⭐</div><div class="empty-title">Watchlist is empty</div></div>`;
      }
    }

    if (usePagination && totalPages > 1) {
      grid.appendChild(buildPagination(_currentPage + 1, totalPages, p => renderGrid(q, p - 1)));
    }

    // Build A-Z index (only when sorted by name with no active search and multiple pages)
    alphaIndexContainer.innerHTML = "";
    if (!q && sortFilter === "name" && filtered.length > WATCHLIST_PAGE_SIZE) {
      const alphaIndex = el("div", "alpha-index");
      const letters = ["#", ..."ABCDEFGHIJKLMNOPQRSTUVWXYZ"];
      const letterFirstPage = {};
      const letterLastPage = {};
      filtered.forEach((artist, i) => {
        const displayName = (artist.alt_name || artist.name || "?");
        const firstChar = displayName[0].toUpperCase();
        const letter = /[A-Z]/.test(firstChar) ? firstChar : "#";
        const page = Math.floor(i / WATCHLIST_PAGE_SIZE);
        if (!(letter in letterFirstPage)) letterFirstPage[letter] = page;
        letterLastPage[letter] = page;
      });
      letters.forEach(letter => {
        const btn = el("button", "alpha-index-btn");
        btn.textContent = letter;
        if (letter in letterFirstPage) {
          btn.classList.add("has-artists");
          const targetPage = letterFirstPage[letter];
          // Highlight whenever the current page falls within this letter's page range.
          if (safePage >= targetPage && safePage <= letterLastPage[letter]) btn.classList.add("current");
          btn.addEventListener("click", () => {
            renderGrid("", targetPage);
            requestAnimationFrame(() => {
              const cards = grid.querySelectorAll(".watchlist-card");
              for (const card of cards) {
                if (card.dataset.displayLetter === letter) {
                  card.scrollIntoView({ behavior: "smooth", block: "start" });
                  break;
                }
              }
            });
          });
        } else {
          btn.disabled = true;
        }
        alphaIndex.appendChild(btn);
      });
      alphaIndexContainer.appendChild(alphaIndex);
    }
  }

  async function runSearch(q) {
    if (Date.now() < _rateLimitedUntil) return;
    const abort = new AbortController();
    _searchAbort = abort;
    try {
      // Always search local DB first
      const localR = await fetch(`/api/search/artists/local?term=${encodeURIComponent(q)}&limit=25`, { signal: abort.signal });
      if (localR.ok) {
        const localData = await localR.json();
        _localSuggestions = (localData.results || [])
          .filter(a => !a.watched)
          .map(a => ({ id: a.artist_id, name: a.name, artwork_url: a.artwork_url, url: a.url, genre: a.genre, born_or_formed: a.born_or_formed, origin: a.origin, artist_bio: a.artist_bio, is_group: a.is_group }));
      }

      // Only search Apple Music when the checkbox is checked
      if (amSearchCheck.checked) {
        const sf = state.metadataStorefront || state.homeStorefront || "us";
        const r = await fetch(`/api/search/artists?term=${encodeURIComponent(q)}&limit=10&storefront=${sf}`, { signal: abort.signal });
        if (r.status === 429) {
          _rateLimitedUntil = Date.now() + 10000;
          _lastSuggestions = [];
          renderGrid(q);
          const notice = el("div", "empty-state", "");
          notice.style.cssText = "grid-column:1/-1";
          notice.innerHTML = `<div class="empty-icon">⏳</div><div class="empty-title">Rate limited</div><div class="empty-desc">Apple Music search is temporarily unavailable. Try again in a moment.</div>`;
          grid.appendChild(notice);
          return;
        }
        if (r.ok) {
          const data = await r.json();
          _lastSuggestions = data.results || [];
        }
      }
    } catch (e) {
      if (e.name !== "AbortError") { _localSuggestions = []; _lastSuggestions = []; }
      else return;
    }
    renderGrid(q);
  }

  searchInput.addEventListener("input", () => {
    const q = searchInput.value.trim();
    _lastSuggestions = [];
    _localSuggestions = [];
    renderGrid(q);

    clearTimeout(_searchTimer);
    if (_searchAbort) { _searchAbort.abort(); _searchAbort = null; }
    if (!q) return;

    const backoffMs = _rateLimitedUntil - Date.now();
    const delay = backoffMs > 0 ? backoffMs : 350;
    _searchTimer = setTimeout(() => runSearch(q), delay);
  });

  amSearchCheck.addEventListener("change", () => {
    const q = searchInput.value.trim();
    if (!amSearchCheck.checked) {
      _lastSuggestions = [];
      renderGrid(q);
    } else if (q) {
      clearTimeout(_searchTimer);
      if (_searchAbort) { _searchAbort.abort(); _searchAbort = null; }
      _searchTimer = setTimeout(() => runSearch(q), 350);
    }
  });

  renderGrid("", initialPage);
}
