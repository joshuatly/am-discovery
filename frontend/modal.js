/* =========================================================
   AM Discovery — Album detail modal
   ========================================================= */

"use strict";

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
      ? API.get(`/api/releases/${storeAdamId}/lookup?storefront=${state.metadataStorefront}`)
      : null;
    const myLookupPromise = shouldCompareMY
      ? API.get(`/api/releases/${storeAdamId}/lookup?storefront=${home}`)
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
    sfBadge.innerHTML = `${sfChipHtml(album._metaSf)} metadata`;
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

    if (album.artist) {
      const mbBtn = el("a", "btn-header-action", "MusicBrainz ↗");
      mbBtn.href = `https://musicbrainz.org/search?query=${encodeURIComponent(album.artist)}&type=artist`;
      mbBtn.target = "_blank";
      mbBtn.rel = "noopener";
      headerActions.appendChild(mbBtn);
    }

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
    diffBanner.innerHTML = `<span class="diff-warn-icon">⚠</span> Track titles differ between ${sfChipHtml(album._metaSf)} and ${sfChipHtml(homeForDiff)}`;
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
    descEl = el("p", "modal-desc");
    descEl.innerHTML = sanitizeHtml(album.description);
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
  sfResultContainer.style.display = "none";
  sfResultContainer.style.width = "100%";
  sfResultContainer.style.fontSize = "14px";
  sfResultContainer.style.lineHeight = "1.5";

  let cliBtns = null;
  let harmonyBtns = null;
  let harmonyUpc = album.upc || null;

  const makeHarmonyBtn = (storefront) => {
    const btn = el("a", "btn-cli-sf", storefront.toUpperCase());
    const amUrl = `https://music.apple.com/${storefront}/album/${album.store_adam_id}`;
    const params = new URLSearchParams({ url: amUrl });
    params.set("gtin", harmonyUpc || "");
    const regions = (state.configuredStorefronts || []).map(s => s.toUpperCase()).join(",");
    params.set("region", regions);
    params.set("musicbrainz", "");
    params.set("deezer", "");
    params.set("itunes", "");
    params.set("spotify", "");
    params.set("tidal", "");
    btn.href = `https://harmony.pulsewidth.org.uk/release?${params.toString()}`;
    btn.target = "_blank";
    btn.rel = "noopener";
    return btn;
  };

  const makeCliBtn = (storefront) => {
    const btn = el("button", "btn-cli-sf", storefront.toUpperCase());
    btn.addEventListener("click", async () => {
      btn.textContent = "…";
      btn.disabled = true;
      try {
        const status = await submitCliSchedulerJob(storefront, album.store_adam_id);
        if (status === 201) {
          btn.textContent = `✓ ${storefront.toUpperCase()}`;
          btn.className = "btn-cli-sf cli-sf-success";
        } else if (status === 400) {
          btn.textContent = `✗ ${storefront.toUpperCase()}`;
          btn.className = "btn-cli-sf cli-sf-error";
          btn.disabled = false;
        } else {
          btn.textContent = `! ${storefront.toUpperCase()}`;
          btn.className = "btn-cli-sf cli-sf-unreachable";
          btn.disabled = false;
        }
      } catch {
        btn.textContent = `! ${storefront.toUpperCase()}`;
        btn.className = "btn-cli-sf cli-sf-unreachable";
        btn.disabled = false;
      }
    });
    return btn;
  };

  sfCheckBtn.addEventListener("click", async () => {
    sfCheckBtn.textContent = "Checking...";
    sfCheckBtn.disabled = true;
    try {
      const res = await API.get(`/api/releases/${album.store_adam_id}/check_storefronts`);
      sfCheckBtn.textContent = `Available in ${res.available.length} / ${res.available.length + res.unavailable.length}`;

      sfResultContainer.innerHTML = "";
      sfResultContainer.style.display = "";

      if (res.available.length > 0) {
        const row = el("div", "sf-result-row");
        row.appendChild(el("span", "sf-result-label", "Available"));
        const chips = el("div", "sf-result-chips");
        res.available.forEach(sf => {
          const a = el("a", `sf-chip ${sf}`, sf.toUpperCase());
          applysfChipColor(a, sf);
          a.href = `https://music.apple.com/${sf}/album/${album.store_adam_id}`;
          a.target = "_blank";
          a.rel = "noopener";
          chips.appendChild(a);
        });
        row.appendChild(chips);
        sfResultContainer.appendChild(row);

        if (state.cliSchedulerEnabled && cliBtns) {
          cliBtns.innerHTML = "";
          res.available.forEach(sf => cliBtns.appendChild(makeCliBtn(sf)));
        }
        if (harmonyBtns) {
          harmonyBtns.innerHTML = "";
          res.available.forEach(sf => harmonyBtns.appendChild(makeHarmonyBtn(sf)));
        }
      }

      if (res.unavailable.length > 0) {
        const row = el("div", "sf-result-row");
        row.appendChild(el("span", "sf-result-label", "Unavailable"));
        const chips = el("div", "sf-result-chips");
        res.unavailable.forEach(sf => chips.appendChild(el("span", "sf-chip sf-chip-dim", sf.toUpperCase())));
        row.appendChild(chips);
        sfResultContainer.appendChild(row);
      }

    } catch {
      sfCheckBtn.textContent = "Check Failed";
      sfCheckBtn.disabled = false;
    }
  });
  actions.appendChild(sfCheckBtn);
  actions.appendChild(sfResultContainer);

  if (state.cliSchedulerEnabled) {
    const initialSfs = [];
    if (state.metadataStorefront) initialSfs.push(state.metadataStorefront);
    if (state.homeStorefront && state.homeStorefront !== state.metadataStorefront) initialSfs.push(state.homeStorefront);
    if (!initialSfs.length && state.homeStorefront) initialSfs.push(state.homeStorefront);
    const cliSection = el("div", "cli-scheduler-section");
    const cliLabel = el("span", "cli-scheduler-label", "CLI Scheduler");
    cliBtns = el("div", "cli-scheduler-btns");
    initialSfs.forEach(sf => cliBtns.appendChild(makeCliBtn(sf)));
    cliSection.appendChild(cliLabel);
    cliSection.appendChild(cliBtns);
    actions.appendChild(cliSection);
  }

  // --- MusicBrainz check row ---
  const mbSection = el("div", "cli-scheduler-section");
  const mbLabel = el("span", "cli-scheduler-label", "MusicBrainz");
  const mbResult = el("span", "mb-result");
  const mbCheckBtn = el("button", "btn-cli-sf", "Check");
  mbCheckBtn.addEventListener("click", async () => {
    mbCheckBtn.textContent = "…";
    mbCheckBtn.disabled = true;
    try {
      const res = await API.get(`/api/releases/${album.store_adam_id}/musicbrainz`);
      if (res.found && res.releases && res.releases.length) {
        mbResult.innerHTML = "";
        const methodNote = res.method === "title_artist" ? el("span", "mb-method-note", "~") : null;
        if (methodNote) {
          methodNote.title = "Matched by title + artist (no barcode) — verify before using";
          mbResult.appendChild(methodNote);
        }
        res.releases.forEach((r, i) => {
          if (i > 0) mbResult.appendChild(document.createTextNode(" · "));
          const link = el("a", "mb-release-link", r.title || "Release");
          link.href = r.url;
          link.target = "_blank";
          link.rel = "noopener";
          mbResult.appendChild(link);
        });
        mbCheckBtn.textContent = "✓";
        mbCheckBtn.className = "btn-cli-sf cli-sf-success";
      } else if (res.upc || res.error === undefined) {
        mbResult.textContent = "Not found";
        mbCheckBtn.textContent = "✗";
        mbCheckBtn.className = "btn-cli-sf cli-sf-error";
      } else {
        mbResult.textContent = "Not found";
        mbCheckBtn.textContent = "✗";
        mbCheckBtn.className = "btn-cli-sf cli-sf-error";
      }
      // Update Harmony buttons with UPC from response
      if (res.upc && !harmonyUpc) {
        harmonyUpc = res.upc;
        if (harmonyBtns) {
          const currentSfs = Array.from(harmonyBtns.children).map(b => b.textContent.toLowerCase());
          harmonyBtns.innerHTML = "";
          currentSfs.forEach(sf => harmonyBtns.appendChild(makeHarmonyBtn(sf)));
        }
      }
    } catch {
      mbCheckBtn.textContent = "!";
      mbCheckBtn.className = "btn-cli-sf cli-sf-unreachable";
      mbCheckBtn.disabled = false;
    }
  });
  mbSection.appendChild(mbLabel);
  mbSection.appendChild(mbCheckBtn);
  mbSection.appendChild(mbResult);
  actions.appendChild(mbSection);

  // --- Harmony seed row ---
  const harmonyInitialSfs = [];
  if (state.metadataStorefront) harmonyInitialSfs.push(state.metadataStorefront);
  if (state.homeStorefront && state.homeStorefront !== state.metadataStorefront) harmonyInitialSfs.push(state.homeStorefront);
  if (!harmonyInitialSfs.length && state.homeStorefront) harmonyInitialSfs.push(state.homeStorefront);
  const harmonySection = el("div", "cli-scheduler-section");
  const harmonyLabel = el("span", "cli-scheduler-label", "Harmony");
  harmonyBtns = el("div", "cli-scheduler-btns");
  harmonyInitialSfs.forEach(sf => harmonyBtns.appendChild(makeHarmonyBtn(sf)));
  harmonySection.appendChild(harmonyLabel);
  harmonySection.appendChild(harmonyBtns);
  actions.appendChild(harmonySection);

  const discoverBtn = el("button", "btn-discover-similar", "✨ You Might Also Like");
  discoverBtn.title = "Find albums Apple Music suggests alongside this one";
  actions.appendChild(discoverBtn);

  details.appendChild(actions);

  // Tracklist
  if (tracks.length) {
    const tl = el("div", "tracklist");
    const tlHead = el("div", "tracklist-header");
    if (hasDiff) {
      tlHead.innerHTML = `${sfChipHtml(album._metaSf, "font-size:10px;vertical-align:middle;")} &nbsp;Tracklist — ${tracks.length} track${tracks.length !== 1 ? "s" : ""}`;
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
    myTlHead.innerHTML = `${sfChipHtml(homeForDiff, "font-size:10px;vertical-align:middle;")} &nbsp;Tracklist — ${myTracks.length} track${myTracks.length !== 1 ? "s" : ""}`;
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

  // Discover Similar — "You Might Also Like" grid rendered inline after tracklist
  const discoverSection = el("div", "discover-results-section");
  details.appendChild(discoverSection);

  discoverBtn.addEventListener("click", async () => {
    discoverBtn.disabled = true;
    const originalLabel = discoverBtn.textContent;
    discoverBtn.textContent = "Loading…";
    discoverSection.innerHTML = "";
    try {
      const sf = state.metadataStorefront || "us";
      const resp = await API.get(`/api/releases/${album.store_adam_id}/you-might-also-like?storefront=${sf}&limit=10`);
      const results = (resp && resp.results) || [];
      const header = el("h3", "", "You Might Also Like");
      discoverSection.appendChild(header);
      if (!results.length) {
        discoverSection.appendChild(el("div", "discover-empty", "No suggestions found"));
      } else {
        const grid = el("div", "discover-grid");
        results.forEach(a => grid.appendChild(albumCard(a)));
        discoverSection.appendChild(grid);
      }
    } catch (err) {
      const msg = err && String(err.message || "").includes("429")
        ? "Rate limited — try again in a minute"
        : "Failed to load suggestions";
      discoverSection.appendChild(el("div", "discover-empty", msg));
    } finally {
      discoverBtn.disabled = false;
      discoverBtn.textContent = originalLabel;
    }
  });

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
