/* =========================================================
   AM Discovery — Admin (MusicBrainz seeding) page
   ========================================================= */

"use strict";

// ---------------------------------------------------------------------------
// Config bootstrap — populate both storefront fields together so navigating
// between pages never leaves one null (see CLAUDE.md frontend state gotcha).
// ---------------------------------------------------------------------------
async function ensureAdminConfig() {
  if (state.configuredStorefronts !== null && state.homeStorefront) return;
  try {
    const cfg = await API.get("/api/system/config");
    state.configuredStorefronts = cfg.check_storefronts || [];
    state.discoveryStorefronts = cfg.check_storefronts || [];
    state.homeStorefront = cfg.home_storefront || "my";
  } catch {
    if (state.configuredStorefronts === null) state.configuredStorefronts = [];
    if (state.discoveryStorefronts === null) state.discoveryStorefronts = [];
    if (!state.homeStorefront) state.homeStorefront = "my";
  }
}

// ---------------------------------------------------------------------------
// Page: Admin
// ---------------------------------------------------------------------------
async function renderAdmin(main, tab) {
  main.innerHTML = "";
  const wrap = el("div", "page-enter");
  wrap.appendChild(buildHeader("Admin", "Link artists and seed missing releases to MusicBrainz"));
  main.appendChild(wrap);

  await ensureAdminConfig();

  const activeTab = tab || state.adminTab || "artists";
  state.adminTab = activeTab;

  // Tab bar
  const tabBar = el("div", "admin-tabs");
  const tabs = [
    ["artists", "Artists"],
    ["releases", "Releases"],
  ];
  const content = el("div", "admin-content");
  tabs.forEach(([key, label]) => {
    const btn = el("button", "admin-tab" + (key === activeTab ? " active" : ""), label);
    btn.addEventListener("click", () => {
      state.adminTab = key;
      location.hash = `#/admin/${key}`;
    });
    tabBar.appendChild(btn);
  });
  wrap.appendChild(tabBar);
  wrap.appendChild(content);

  if (activeTab === "releases") {
    await renderAdminReleases(content);
  } else {
    await renderAdminArtists(content);
  }
}

// ---------------------------------------------------------------------------
// Artists tab
// ---------------------------------------------------------------------------
async function renderAdminArtists(container) {
  container.innerHTML = "";
  container.appendChild(skeletonGrid(4));

  let data;
  try {
    data = await API.get("/api/admin/artists");
  } catch {
    container.innerHTML = "";
    container.appendChild(adminEmpty("⚠️", "Could not load artists"));
    return;
  }

  container.innerHTML = "";

  // Toolbar — bulk "search all" across un-suggested artists.
  const toolbar = el("div", "admin-toolbar");
  const count = el("div", "admin-count", `${data.total} watchlist artist${data.total === 1 ? "" : "s"} without a MusicBrainz link`);
  toolbar.appendChild(count);
  const unsuggested = data.items.filter(a => !a.suggested_mbid && a.suggestion_status !== "denied").length;
  const searchAllBtn = el("button", "btn-secondary admin-search-all-btn", "Search all on MusicBrainz");
  if (!unsuggested) searchAllBtn.disabled = true;
  searchAllBtn.title = "Look up MusicBrainz for every artist that has no suggestion yet (≈1/sec)";
  searchAllBtn.addEventListener("click", async () => {
    searchAllBtn.disabled = true;
    try {
      await API.post("/api/admin/artists/search-all", {});
    } catch { /* fall through to polling */ }
    pollBulkSearch(container, searchAllBtn);
  });
  toolbar.appendChild(searchAllBtn);
  container.appendChild(toolbar);

  if (!data.items.length) {
    container.appendChild(adminEmpty("✓", "Every watched artist is linked to MusicBrainz"));
    return;
  }

  const list = el("div", "admin-artist-list");
  data.items.forEach(a => list.appendChild(adminArtistRow(a, () => renderAdminArtists(container))));
  container.appendChild(list);

  // If a bulk search is already in flight (e.g. started before navigating away
  // and back), resume showing its progress.
  try {
    const st = await API.get("/api/admin/artists/search-all/status");
    if (st.running) pollBulkSearch(container, searchAllBtn);
  } catch { /* ignore */ }
}

// Poll bulk-search progress, updating the button label, then re-render the tab.
function pollBulkSearch(container, btn) {
  btn.disabled = true;
  const tick = async () => {
    if (!container.isConnected) return; // user navigated away
    let st;
    try {
      st = await API.get("/api/admin/artists/search-all/status");
    } catch {
      btn.disabled = false;
      return;
    }
    if (st.running) {
      const total = st.total || "…";
      btn.textContent = `Searching ${st.done}/${total}…`;
      setTimeout(tick, 1500);
    } else {
      // Finished — reload the list so freshly-found suggestions appear.
      renderAdminArtists(container);
    }
  };
  tick();
}

function adminArtistRow(a, onChange) {
  const row = el("div", "admin-artist-row");

  // Left: avatar + identity + links (avatar mirrors the watchlist card).
  const identity = el("div", "admin-artist-identity");
  const avatar = el("div", "admin-artist-avatar");
  if (a.artwork_url) {
    const img = el("img", "admin-artist-avatar-img");
    img.src = a.artwork_url;
    img.alt = "";
    img.loading = "lazy";
    img.onerror = () => { img.remove(); avatar.textContent = (a.name || "?")[0].toUpperCase(); };
    avatar.appendChild(img);
  } else {
    avatar.textContent = (a.name || "?")[0].toUpperCase();
  }
  identity.appendChild(avatar);

  const left = el("div", "admin-artist-main");
  const name = el("div", "admin-artist-name", a.name || "—");
  left.appendChild(name);
  if (a.alt_name) left.appendChild(el("div", "admin-artist-alt", a.alt_name));

  const links = el("div", "admin-artist-links");
  const amLink = el("a", "admin-link", "Apple Music ↗");
  amLink.href = a.am_url;
  amLink.target = "_blank";
  amLink.rel = "noopener";
  links.appendChild(amLink);
  const discLink = el("a", "admin-link", "AM Discovery →");
  discLink.href = a.am_discovery_url;
  links.appendChild(discLink);
  left.appendChild(links);
  identity.appendChild(left);
  row.appendChild(identity);

  // Right: suggestion / actions
  const right = el("div", "admin-artist-actions");

  const feedback = el("div", "admin-feedback");

  const applyMbid = async (mbid) => {
    feedback.textContent = "Linking…";
    try {
      const res = await API.post(`/api/admin/artists/${a.artist_id}/approve`, mbid ? { musicbrainz_id: mbid } : {});
      if (res.ok) {
        onChange();
      } else {
        feedback.textContent = res.error || "Could not link";
      }
    } catch {
      feedback.textContent = "Could not link";
    }
  };

  if (a.suggested_mbid) {
    const sug = el("div", "admin-suggestion");
    const sugName = el("span", "admin-suggestion-name", a.suggested_name || a.suggested_mbid);
    sug.appendChild(sugName);
    if (a.score != null) sug.appendChild(el("span", "admin-suggestion-score", `${a.score}%`));
    // Type (Person / Group) and area help disambiguate same-named artists.
    const metaParts = [];
    if (a.suggested_type) metaParts.push(a.suggested_type);
    if (a.suggested_area) metaParts.push(a.suggested_area);
    if (metaParts.length) sug.appendChild(el("span", "admin-suggestion-tag", metaParts.join(" · ")));
    if (a.suggested_disambiguation) {
      sug.appendChild(el("span", "admin-suggestion-disambig", a.suggested_disambiguation));
    }
    const mbLink = el("a", "admin-link", "Verify on MusicBrainz ↗");
    mbLink.href = a.mb_url;
    mbLink.target = "_blank";
    mbLink.rel = "noopener";
    sug.appendChild(mbLink);
    right.appendChild(sug);

    const btns = el("div", "admin-btn-row");
    const approve = el("button", "btn-mb-approve", "Approve");
    approve.addEventListener("click", () => applyMbid(a.suggested_mbid));
    const deny = el("button", "btn-mb-deny", "Deny");
    deny.addEventListener("click", async () => {
      deny.disabled = true;
      await API.post(`/api/admin/artists/${a.artist_id}/deny`, {});
      onChange();
    });
    btns.appendChild(approve);
    btns.appendChild(deny);
    right.appendChild(btns);
  } else {
    const lookupBtn = el("button", "btn-secondary", a.suggestion_status === "denied" ? "Look up again" : "Look up on MusicBrainz");
    lookupBtn.addEventListener("click", async () => {
      lookupBtn.disabled = true;
      lookupBtn.textContent = "Searching…";
      try {
        const res = await API.post(`/api/admin/artists/${a.artist_id}/lookup`, {});
        if (res.error === "rate_limited") {
          feedback.textContent = "MusicBrainz rate limited — try again shortly";
          lookupBtn.disabled = false;
          lookupBtn.textContent = "Look up on MusicBrainz";
          return;
        }
        onChange();
      } catch {
        feedback.textContent = "Lookup failed";
        lookupBtn.disabled = false;
        lookupBtn.textContent = "Look up on MusicBrainz";
      }
    });
    right.appendChild(lookupBtn);
  }

  // Manual MBID entry — always available.
  const manual = el("div", "admin-manual");
  const input = el("input", "search-input admin-mbid-input");
  input.type = "text";
  input.placeholder = "Enter MBID manually";
  const linkBtn = el("button", "btn-secondary", "Link");
  linkBtn.addEventListener("click", () => {
    const v = input.value.trim();
    if (v) applyMbid(v);
  });
  manual.appendChild(input);
  manual.appendChild(linkBtn);
  right.appendChild(manual);
  right.appendChild(feedback);

  row.appendChild(right);
  return row;
}

// ---------------------------------------------------------------------------
// Releases tab
// ---------------------------------------------------------------------------
async function renderAdminReleases(container) {
  container.innerHTML = "";

  // Controls
  const controls = el("div", "admin-controls");
  const sortLabel = el("span", "admin-control-label", "SORT");
  controls.appendChild(sortLabel);
  const sorts = [
    ["release_date", "Release date"],
    ["release_type", "Type"],
    ["artist", "Artist"],
  ];
  const state_sort = state.adminReleaseSort || "release_date";
  sorts.forEach(([key, label]) => {
    const btn = el("button", "admin-pill" + (key === state_sort ? " active" : ""), label);
    btn.addEventListener("click", () => {
      state.adminReleaseSort = key;
      renderAdminReleases(container);
    });
    controls.appendChild(btn);
  });

  const groupBtn = el("button", "admin-pill" + (state.adminGroupByArtist ? " active" : ""), "Group by artist");
  groupBtn.addEventListener("click", () => {
    state.adminGroupByArtist = !state.adminGroupByArtist;
    renderAdminReleases(container);
  });
  controls.appendChild(groupBtn);

  const scanBtn = el("button", "btn-secondary admin-scan-btn", "Scan now");
  scanBtn.title = "Re-verify releases against MusicBrainz now (ignores the weekly per-artist limit)";
  scanBtn.addEventListener("click", async () => {
    scanBtn.disabled = true;
    scanBtn.textContent = "Scanning…";
    try {
      await API.post("/api/admin/scan", {});
    } catch { /* ignore */ }
    setTimeout(() => {
      scanBtn.disabled = false;
      scanBtn.textContent = "Scan now";
    }, 2000);
  });
  controls.appendChild(scanBtn);
  container.appendChild(controls);

  const listWrap = el("div", "");
  listWrap.appendChild(skeletonGrid(8));
  container.appendChild(listWrap);

  let data;
  try {
    data = await API.get(`/api/admin/releases?sort=${state_sort}`);
  } catch {
    listWrap.innerHTML = "";
    listWrap.appendChild(adminEmpty("⚠️", "Could not load releases"));
    return;
  }

  listWrap.innerHTML = "";
  const count = el("div", "admin-count", `${data.total} release${data.total === 1 ? "" : "s"} missing from MusicBrainz`);
  listWrap.appendChild(count);

  if (!data.items.length) {
    listWrap.appendChild(adminEmpty("✓", "No releases pending — everything is seeded or hidden"));
    return;
  }

  const rerender = () => renderAdminReleases(container);

  if (state.adminGroupByArtist) {
    const groups = {};
    data.items.forEach(r => {
      const key = r.artist_name || "—";
      (groups[key] = groups[key] || []).push(r);
    });
    Object.keys(groups).sort((a, b) => a.localeCompare(b)).forEach(artistName => {
      const g = groups[artistName];
      const header = el("div", "admin-group-header");
      header.appendChild(el("span", "admin-group-name", artistName));
      header.appendChild(el("span", "admin-group-count", `${g.length}`));
      const mbid = g[0].artist_musicbrainz_id;
      if (mbid) {
        const mbLink = el("a", "admin-link", "MusicBrainz ↗");
        mbLink.href = `https://musicbrainz.org/artist/${mbid}`;
        mbLink.target = "_blank";
        mbLink.rel = "noopener";
        header.appendChild(mbLink);
      }
      listWrap.appendChild(header);
      const grid = el("div", "admin-release-grid");
      g.forEach(r => grid.appendChild(adminReleaseCard(r, rerender)));
      listWrap.appendChild(grid);
    });
  } else {
    const grid = el("div", "admin-release-grid");
    data.items.forEach(r => grid.appendChild(adminReleaseCard(r, rerender)));
    listWrap.appendChild(grid);
  }
}

function adminReleaseCard(r, onChange) {
  const card = el("div", "admin-release-card");

  const art = artworkEl(r.artwork_url, "admin-release-art");
  art.style.cursor = "pointer";
  art.addEventListener("click", () => openModal(r.store_adam_id));
  card.appendChild(art);

  const info = el("div", "admin-release-info");
  const title = el("div", "admin-release-title", r.title || "—");
  title.title = r.title || "";
  info.appendChild(title);
  if (!state.adminGroupByArtist) {
    info.appendChild(el("div", "admin-release-artist", r.artist_name || r.artist || "—"));
  }

  const meta = el("div", "admin-release-meta");
  meta.appendChild(el("span", `release-date${isFutureDate(r.release_date) ? " future" : ""}`, formatDate(r.release_date)));
  if (r.release_type) {
    meta.appendChild(el("span", `release-type-chip rt-${r.release_type}`, r.release_type));
  }
  const pref = r.preferred_source || state.homeStorefront;
  if (pref) {
    const chip = el("span", `sf-chip ${pref.toLowerCase()}`);
    applysfChipColor(chip, pref);
    chip.textContent = pref.toUpperCase();
    meta.appendChild(chip);
  }
  info.appendChild(meta);

  // Actions
  const actions = el("div", "admin-release-actions");
  const seedSf = r.preferred_source || state.homeStorefront || "us";
  const harmony = el("a", "btn-cli-sf", `Harmony ${seedSf.toUpperCase()}`);
  harmony.href = buildHarmonyUrl(r.store_adam_id, seedSf, r.upc, state.configuredStorefronts || []);
  harmony.target = "_blank";
  harmony.rel = "noopener";
  actions.appendChild(harmony);

  const openBtn = el("button", "btn-secondary", "Open");
  openBtn.addEventListener("click", () => openModal(r.store_adam_id));
  actions.appendChild(openBtn);

  const hideBtn = el("button", "btn-secondary admin-hide-btn", "Hide");
  hideBtn.title = "Hide from this list";
  hideBtn.addEventListener("click", async () => {
    hideBtn.disabled = true;
    try {
      await API.post(`/api/admin/releases/${r.store_adam_id}/hide`, {});
      onChange();
    } catch {
      hideBtn.disabled = false;
    }
  });
  actions.appendChild(hideBtn);

  info.appendChild(actions);
  card.appendChild(info);
  return card;
}

// ---------------------------------------------------------------------------
// Shared
// ---------------------------------------------------------------------------
function adminEmpty(icon, title) {
  const box = el("div", "empty-state");
  box.innerHTML = `<div class="empty-icon">${icon}</div><div class="empty-title">${sanitizeHtml(title)}</div>`;
  return box;
}
