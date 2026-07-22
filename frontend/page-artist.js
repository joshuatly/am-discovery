/* =========================================================
   AM Discovery — Artist detail page
   ========================================================= */

"use strict";

// ---------------------------------------------------------------------------
// Page: Artist Detail
// ---------------------------------------------------------------------------
async function renderArtist(main, artistId) {
  main.innerHTML = "";
  const wrap = el("div", "page-enter artist-page");
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
  if (!data.artist_name          && hint?.name)          data.artist_name          = hint.name;
  if (!data.artist_url           && hint?.url)           data.artist_url           = hint.url;
  if (!data.artist_artwork_url   && hint?.artwork_url)   data.artist_artwork_url   = hint.artwork_url;
  if (!data.artist_genre         && hint?.genre)         data.artist_genre         = hint.genre;
  if (!data.artist_born_or_formed && hint?.born_or_formed) data.artist_born_or_formed = hint.born_or_formed;
  if (!data.artist_origin        && hint?.origin)        data.artist_origin        = hint.origin;
  if (!data.artist_bio           && hint?.artist_bio)    data.artist_bio           = hint.artist_bio;
  if (data.artist_is_group == null && hint?.is_group != null) data.artist_is_group = hint.is_group;

  await loadWatchedIds();
  if (data.artist_name) document.title = `${data.artist_name} — AM Discovery`;
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
  const metaInfo = el("div", "artist-meta-info");
  const nameBig = el("h1", "artist-name-big", data.artist_name || "Unknown Artist");
  metaInfo.appendChild(nameBig);

  if (data.artist_artwork_url && data.artist_genre) {
    const genreEl = el("div", "artist-genre", data.artist_genre);
    metaInfo.appendChild(genreEl);
  }

  const detailParts = [];
  if (data.artist_born_or_formed) {
    let bofStr = data.artist_born_or_formed;
    if (data.artist_is_group === true && !/^formed/i.test(bofStr)) bofStr = "Formed " + bofStr;
    else if (data.artist_is_group === false && !/^born/i.test(bofStr)) bofStr = "Born " + bofStr;
    detailParts.push(bofStr);
  }
  if (data.artist_origin) detailParts.push(data.artist_origin);
  if (detailParts.length) {
    const detailEl = el("div", "artist-detail", detailParts.join(" · "));
    metaInfo.appendChild(detailEl);
  }
  meta.appendChild(metaInfo);

  const links = el("div", "artist-links");

  // Row 1: primary actions
  const actionsRow = el("div", "artist-actions");

  if (data.artist_url) {
    const extLink = el("a", "artist-ext-link", "Open in Apple Music ↗");
    extLink.dataset.baseUrl = data.artist_url;
    const sf = state.metadataStorefront;
    extLink.href = sf
      ? data.artist_url.replace(/music\.apple\.com\/[a-z]{2}\//, `music.apple.com/${sf}/`)
      : data.artist_url;
    extLink.target = "_blank";
    extLink.rel = "noopener";
    actionsRow.appendChild(extLink);
  }

  // MusicBrainz link — direct if MBID stored, search fallback
  const mbLink = el("a", "artist-ext-link", "MusicBrainz ↗");
  if (data.artist_musicbrainz_id) {
    mbLink.href = `https://musicbrainz.org/artist/${data.artist_musicbrainz_id}`;
  } else if (data.artist_name) {
    mbLink.href = `https://musicbrainz.org/search?query=${encodeURIComponent(data.artist_name)}&type=artist`;
  }
  mbLink.target = "_blank";
  mbLink.rel = "noopener";
  actionsRow.appendChild(mbLink);

  const isWatched = state.watchedIds.has(artistId);
  const watchBtn = el("button", `btn-watch${isWatched ? " watching" : ""}`, isWatched ? "⭐ Watching" : "☆ Watch");

  const sfLabel = state.metadataStorefront ? state.metadataStorefront.toUpperCase() : "";
  const fetchBtn = el("button", "btn-fetch-artist", sfLabel ? `↓ Fetch from ${sfLabel}` : "↓ Fetch All");
  fetchBtn.title = "Fetch all releases for this artist and store tracklists";
  fetchBtn.addEventListener("click", async () => {
    fetchBtn.disabled = true;
    fetchBtn.textContent = "Fetching…";
    try {
      const sf = state.metadataStorefront;
      const qp = sf ? `?storefront=${sf}` : "";
      await API.post(`/api/artists/${artistId}/fetch${qp}`, {});
      fetchBtn.textContent = "✓ Fetching in background";
      setTimeout(() => renderArtist(main, artistId), 5000);
    } catch {
      fetchBtn.textContent = "Failed";
      fetchBtn.disabled = false;
    }
  });

  actionsRow.appendChild(watchBtn);
  actionsRow.appendChild(fetchBtn);
  links.appendChild(actionsRow);

  // Row 2: watch settings (only visible when watched)
  const settingsRow = el("div", "artist-settings");
  settingsRow.style.display = isWatched ? "flex" : "none";

  // Preferred source selector
  const srcWrap = el("div", "artist-src-wrap");
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
  settingsRow.appendChild(srcWrap);

  // Collection status selector
  const csWrap = el("div", "artist-src-wrap");
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
  settingsRow.appendChild(csWrap);

  // Alt name row (sibling of settingsRow in artist-links, so it doesn't affect settings width)
  const altNameWrap = el("div", "artist-src-wrap");
  const altNameLabel = el("span", "artist-src-label", "Alt name:");
  altNameWrap.appendChild(altNameLabel);

  const altNameDisplay = el("span", "artist-alt-name-display");
  let _currentAltName = null;

  function buildAltNameDisplay(currentAltName) {
    _currentAltName = currentAltName || null;
    altNameDisplay.innerHTML = "";
    const valueEl = el("span", "artist-alt-name-value");
    valueEl.textContent = currentAltName || "—";
    altNameDisplay.appendChild(valueEl);
    const editBtn = el("button", "btn-alt-name-edit", "Edit");
    editBtn.addEventListener("click", () => {
      altNameDisplay.innerHTML = "";
      const input = document.createElement("input");
      input.type = "text";
      input.maxLength = 200;
      input.className = "alt-name-input";
      input.value = _currentAltName || "";
      const saveBtn = el("button", "btn-alt-name-save", "Save");
      const cancelBtn = el("button", "btn-alt-name-cancel", "Cancel");
      saveBtn.addEventListener("click", async () => {
        const newVal = input.value.trim() || null;
        try {
          await API.patch(`/api/watchlist/${artistId}`, { alt_name: newVal });
          buildAltNameDisplay(newVal);
        } catch {
          alert("Failed to save alt name");
          buildAltNameDisplay(_currentAltName);
        }
      });
      cancelBtn.addEventListener("click", () => buildAltNameDisplay(_currentAltName));
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") saveBtn.click();
      });
      altNameDisplay.appendChild(input);
      altNameDisplay.appendChild(saveBtn);
      altNameDisplay.appendChild(cancelBtn);
      input.focus();
    });
    altNameDisplay.appendChild(editBtn);
  }

  buildAltNameDisplay(null); // placeholder until async load
  altNameWrap.appendChild(altNameDisplay);
  links.appendChild(settingsRow);
  altNameWrap.style.display = isWatched ? "flex" : "none";
  links.appendChild(altNameWrap);

  // MBID row (always visible — useful for any artist)
  const mbidWrap = el("div", "artist-src-wrap");
  const mbidLabel = el("span", "artist-src-label", "MBID:");
  mbidWrap.appendChild(mbidLabel);

  const mbidDisplay = el("span", "artist-alt-name-display");
  let _currentMbid = data.artist_musicbrainz_id || null;

  function buildMbidDisplay(currentMbid) {
    _currentMbid = currentMbid || null;
    mbidDisplay.innerHTML = "";
    if (_currentMbid) {
      const link = el("a", "artist-alt-name-value", _currentMbid);
      link.href = `https://musicbrainz.org/artist/${_currentMbid}`;
      link.target = "_blank";
      link.rel = "noopener";
      link.style.fontSize = "11px";
      mbidDisplay.appendChild(link);
      // Update the MusicBrainz link in actionsRow to use direct URL
      mbLink.href = `https://musicbrainz.org/artist/${_currentMbid}`;
    } else {
      const valueEl = el("span", "artist-alt-name-value", "—");
      mbidDisplay.appendChild(valueEl);
      // Reset MB link to search
      if (data.artist_name) {
        mbLink.href = `https://musicbrainz.org/search?query=${encodeURIComponent(data.artist_name)}&type=artist`;
      }
    }
    const editBtn = el("button", "btn-alt-name-edit", "Edit");
    editBtn.addEventListener("click", () => {
      mbidDisplay.innerHTML = "";
      const input = document.createElement("input");
      input.type = "text";
      input.maxLength = 200;
      input.className = "alt-name-input";
      input.placeholder = "MusicBrainz artist ID";
      input.value = _currentMbid || "";
      const saveBtn = el("button", "btn-alt-name-save", "Save");
      const cancelBtn = el("button", "btn-alt-name-cancel", "Cancel");
      saveBtn.addEventListener("click", async () => {
        const newVal = input.value.trim() || null;
        try {
          await API.patch(`/api/artists/${artistId}`, { musicbrainz_id: newVal });
          buildMbidDisplay(newVal);
        } catch {
          alert("Failed to save MBID");
          buildMbidDisplay(_currentMbid);
        }
      });
      cancelBtn.addEventListener("click", () => buildMbidDisplay(_currentMbid));
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") saveBtn.click();
      });
      mbidDisplay.appendChild(input);
      mbidDisplay.appendChild(saveBtn);
      mbidDisplay.appendChild(cancelBtn);
      input.focus();
    });
    mbidDisplay.appendChild(editBtn);
  }

  buildMbidDisplay(_currentMbid);
  mbidWrap.appendChild(mbidDisplay);
  links.appendChild(mbidWrap);

  watchBtn.addEventListener("click", async () => {
    const ps = state.metadataStorefront || state.homeStorefront || null;
    await toggleWatch(artistId, data.artist_name, data.artist_url, ps);
    const nowWatched = state.watchedIds.has(artistId);
    watchBtn.textContent = nowWatched ? "⭐ Watching" : "☆ Watch";
    watchBtn.classList.toggle("watching", nowWatched);
    settingsRow.style.display = nowWatched ? "flex" : "none";
    altNameWrap.style.display = nowWatched ? "flex" : "none";
    if (nowWatched) {
      buildSrcOptions(ps);
      buildCsOptions("new");
      buildAltNameDisplay(null);
    }
  });

  if (isWatched) {
    // Load current preferred_source, collection_status, and alt_name, pre-select
    API.get("/api/watchlist").then(wl => {
      const entry = wl.find(a => a.artist_id === artistId);
      buildSrcOptions(entry?.preferred_source || null);
      buildCsOptions(entry?.collection_status || "new");
      buildAltNameDisplay(entry?.alt_name || null);
    }).catch(() => {});
  }

  meta.appendChild(links);
  header.appendChild(meta);
  wrap.appendChild(header);

  if (data.artist_bio) {
    const bioWrap = el("div", "artist-bio-wrap");
    const bioEl = el("div", "artist-bio artist-bio--clamped");
    bioEl.innerHTML = sanitizeHtml(data.artist_bio);
    bioWrap.appendChild(bioEl);
    const bioToggle = el("a", "artist-bio-toggle", "Show more");
    bioToggle.href = "#";
    let bioExpanded = false;
    bioToggle.addEventListener("click", e => {
      e.preventDefault();
      bioExpanded = !bioExpanded;
      bioEl.classList.toggle("artist-bio--clamped", !bioExpanded);
      bioToggle.textContent = bioExpanded ? "Show less" : "Show more";
    });
    bioWrap.appendChild(bioToggle);
    wrap.appendChild(bioWrap);
  }

  // Stats
  const subtitle = el("p", "page-subtitle");
  const trackFetched = data.releases.filter(r => r.tracks_fetched).length;
  subtitle.textContent = `${data.releases.length} release${data.releases.length !== 1 ? "s" : ""} in database` +
    (trackFetched ? ` · ${trackFetched} with tracklist` : "");
  subtitle.style.marginBottom = "20px";
  wrap.appendChild(subtitle);

  if (!data.releases.length) {
    wrap.insertAdjacentHTML("beforeend", `<div class="empty-state"><div class="empty-icon">🎵</div><div class="empty-title">No releases found</div><div class="empty-desc">This artist's releases will appear here after a refresh</div></div>`);
    appendDiscoverSimilarSection(wrap, artistId);
    return;
  }

  data.releases.forEach(album => {
    album.watched = state.watchedIds.has(album.artist_id);
    if (data.artist_name) album.artist = data.artist_name;
  });

  // Releases flagged as missing from MusicBrainz. If this artist has none,
  // clear the (globally persisted) seed filter so its releases still show.
  const seedCount = data.releases.filter(
    r => r.mb_seed_status === "needs_seeding" && !r.hidden_from_seeding
  ).length;
  if (!seedCount) state.artistSeedFilter = false;

  // Toolbar: view toggle + type filter
  const toolbar = el("div", "artist-releases-toolbar");
  const gridContainer = el("div", "artist-grid-container");

  // Top row: view mode toggle + (optional) seed filter, side by side
  const topRow = el("div", "artist-toolbar-row");
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
  topRow.appendChild(viewToggle);

  // Seed filter — only when this artist has releases flagged for seeding.
  // Sits on the same row as the view toggle.
  if (seedCount) {
    const seedBtn = el(
      "button",
      `type-filter-btn seed-filter-btn${state.artistSeedFilter ? " active" : ""}`,
      `🌱 Needs seeding (${seedCount})`
    );
    seedBtn.title = "Show only releases missing from MusicBrainz";
    seedBtn.addEventListener("click", () => {
      state.artistSeedFilter = !state.artistSeedFilter;
      seedBtn.classList.toggle("active", state.artistSeedFilter);
      renderArtistReleaseGrid(data.releases, gridContainer);
    });
    topRow.appendChild(seedBtn);
  }

  toolbar.appendChild(topRow);

  // Type filter — shown whenever at least one type is present
  const typeSet = new Set(data.releases.map(r => r.release_type).filter(Boolean));
  if (typeSet.size >= 1) {
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

  appendDiscoverSimilarSection(wrap, artistId);
}

// ---------------------------------------------------------------------------
// Discover Similar — renders ✨ button + horizontal row of similar artists
// ---------------------------------------------------------------------------
function appendDiscoverSimilarSection(wrap, artistId) {
  const section = el("div", "discover-results-section discover-similar-artist-section");
  const heading = el("div", "discover-similar-heading");
  const h = el("h3", "", "Similar Artists");
  const btn = el("button", "btn-discover-similar", "✨ Discover Similar");
  btn.title = "Discover similar artists via Apple Music";
  heading.appendChild(h);
  heading.appendChild(btn);
  section.appendChild(heading);

  const body = el("div", "discover-similar-body");
  section.appendChild(body);
  wrap.appendChild(section);

  btn.addEventListener("click", async () => {
    btn.disabled = true;
    const originalLabel = btn.textContent;
    btn.textContent = "Discovering…";
    body.innerHTML = "";
    try {
      const sf = state.metadataStorefront || "us";
      const resp = await API.get(`/api/artists/${artistId}/similar?storefront=${sf}&limit=10`);
      const results = (resp && resp.results) || [];
      if (!results.length) {
        body.appendChild(el("div", "discover-empty", "No similar artists found"));
      } else {
        const row = el("div", "discover-grid-artists");
        results.forEach(a => row.appendChild(artistCard(a)));

        const wrapper = el("div", "discover-scroll-wrapper");
        const arrowL = el("button", "discover-scroll-arrow left", "\u2039");
        const arrowR = el("button", "discover-scroll-arrow right", "\u203A");
        arrowL.type = "button";
        arrowR.type = "button";
        wrapper.appendChild(arrowL);
        wrapper.appendChild(arrowR);
        wrapper.appendChild(row);
        body.appendChild(wrapper);

        const scrollAmt = 136 * 3;
        arrowL.addEventListener("click", () => row.scrollBy({ left: -scrollAmt, behavior: "smooth" }));
        arrowR.addEventListener("click", () => row.scrollBy({ left: scrollAmt, behavior: "smooth" }));
        const updateArrows = () => {
          const maxScroll = row.scrollWidth - row.clientWidth;
          wrapper.classList.toggle("can-scroll-left", row.scrollLeft > 2);
          wrapper.classList.toggle("can-scroll-right", maxScroll - row.scrollLeft > 2);
        };
        row.addEventListener("scroll", updateArrows, { passive: true });
        requestAnimationFrame(updateArrows);
      }
    } catch (err) {
      const msg = err && String(err.message || "").includes("429")
        ? "Rate limited — try again in a minute"
        : "Failed to load similar artists";
      body.appendChild(el("div", "discover-empty", msg));
    } finally {
      btn.disabled = false;
      btn.textContent = originalLabel;
    }
  });
}
