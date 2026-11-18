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
  // The /lookup response the tracklist came from. "Show info" renders from it
  // (and from myAlbumData), so revealing track info never re-queries.
  let info = null;
  try {
    const home = state.homeStorefront;
    const shouldCompareMY = state.alwaysIncludeMY
      && home
      && state.metadataStorefront
      && state.metadataStorefront !== home;
    const lookupSf = state.metadataStorefront || home || "us";

    const dbPromise = API.get(`/api/releases/${storeAdamId}`);
    const lookupPromise = state.metadataStorefront
      ? API.get(`/api/releases/${storeAdamId}/lookup?storefront=${state.metadataStorefront}`)
      : null;
    const myLookupPromise = shouldCompareMY
      ? API.get(`/api/releases/${storeAdamId}/lookup?storefront=${home}`)
      : null;

    try {
      album = await dbPromise;
    } catch {
      // Album not in local DB (e.g. a "You Might Also Like" suggestion that
      // was never discovered through room polling). Fall back to a fresh
      // Apple Music lookup so the modal still renders. lookupPromise already
      // targets lookupSf whenever it exists — reuse it rather than re-fetching.
      try {
        const fresh = await (lookupPromise
          || API.get(`/api/releases/${storeAdamId}/lookup?storefront=${lookupSf}`));
        info = fresh;
        album = {
          store_adam_id: storeAdamId,
          title: fresh.title,
          artist: fresh.artist,
          artists_json: fresh.artists || [],
          artist_id: fresh.artist_id,
          artist_url: fresh.artist_url,
          url: fresh.url || `https://music.apple.com/${lookupSf}/album/${storeAdamId}`,
          artwork_url: fresh.artwork_url,
          release_date: fresh.release_date,
          track_count: fresh.track_count,
          music_video_count: fresh.music_video_count || 0,
          genre: fresh.genre,
          description: fresh.description,
          tracks: fresh.tracks || [],
          audio_formats: fresh.audio_formats || [],
          storefronts: [lookupSf],
          upc: fresh.upc || null,
          release_type: fresh.release_type || null,
          _metaSf: lookupSf,
        };
      } catch {
        body.innerHTML = `<div style="padding:32px;text-align:center">Failed to load</div>`;
        return;
      }
    }

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
        if (fresh.music_video_count != null) album.music_video_count = fresh.music_video_count;
        if (fresh.audio_formats?.length) album.audio_formats = fresh.audio_formats;
        album._metaSf = state.metadataStorefront;
        info = fresh;
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

    const artBtn = routeLink(`#/artist/${album.artist_id}`, "btn-header-action", "View Artist →", closeModal);
    headerActions.appendChild(artBtn);

    if (album.artist) {
      const mbBtn = el("a", "btn-header-action", "MusicBrainz ↗");
      mbBtn.href = album.artist_musicbrainz_id
        ? `https://musicbrainz.org/artist/${album.artist_musicbrainz_id}`
        : `https://musicbrainz.org/search?query=${encodeURIComponent(album.artist)}&type=artist`;
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
  let tracks = album.tracks || [];
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
    const mvCount = album.music_video_count || 0;
    const songCount = album.track_count - mvCount;
    const countLabel = mvCount > 0 ? `${songCount}+${mvCount}` : `${album.track_count}`;
    const t = el("span", "modal-tag", `🎵 ${countLabel} tracks`);
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
    params.set("category", "preferred");
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

  details.appendChild(actions);

  // Tracklist + "Show info" (track dates, ISRCs, lyrics, label, …). Built from
  // the lookup response(s) already fetched above; only when no lookup ran at
  // all (metadata source Off, or it failed) does the button fetch — once.
  const trackSection = el("div", "track-section");
  details.appendChild(trackSection);
  const infoBtn = el("button", "btn-track-info");
  infoBtn.type = "button";
  infoBtn.title = "Track dates, ISRCs, lyrics, label and copyright";

  const renderTrackSection = () => {
    trackSection.innerHTML = "";
    infoBtn.disabled = false;
    if (tracks.length) {
      const meta = mergeNonNull(album, info);
      trackSection.appendChild(buildAlbumInfoPanel(meta, tracks, album._metaSf));
      const tl = buildTracklist(tracks, {
        compareTracks: hasDiff ? myTracks : null,
        diffClass: "track-differs",
        headerSf: hasDiff ? album._metaSf : null,
        albumDate: meta.release_date,
        albumArtist: meta.artist,
      });
      tl.querySelector(".tracklist-header").appendChild(infoBtn);
      trackSection.appendChild(tl);
      if (hasDiff) {
        trackSection.appendChild(buildTracklist(myTracks, {
          compareTracks: tracks,
          diffClass: "track-differs-my",
          headerSf: homeForDiff,
          headerClass: "tracklist-header-my",
          albumDate: myAlbumData.release_date || meta.release_date,
          albumArtist: myAlbumData.artist || meta.artist,
        }));
      }
      setTrackInfoVisible(trackSection, infoBtn, state.showTrackInfo);
      infoBtn.onclick = () => {
        state.showTrackInfo = !state.showTrackInfo;
        setTrackInfoVisible(trackSection, infoBtn, state.showTrackInfo);
      };
    } else if (info) {
      // A lookup ran but returned no tracks — don't offer to repeat it.
      trackSection.appendChild(el("p", "tracklist-empty", "No tracklist available from this storefront."));
    } else {
      const tl = el("div", "tracklist");
      const head = el("div", "tracklist-header");
      head.appendChild(el("span", "tracklist-header-label", "Tracklist"));
      head.appendChild(infoBtn);
      tl.appendChild(head);
      trackSection.appendChild(tl);
      setTrackInfoVisible(trackSection, infoBtn, false);
      infoBtn.onclick = async () => {
        infoBtn.disabled = true;
        infoBtn.textContent = "Loading…";
        const sf = state.homeStorefront || "us";
        try {
          info = await API.get(`/api/releases/${album.store_adam_id}/lookup?storefront=${sf}`);
          tracks = info.tracks || [];
          album._metaSf = sf;
          state.showTrackInfo = true;
          renderTrackSection();
        } catch {
          infoBtn.disabled = false;
          infoBtn.textContent = "ⓘ Retry";
        }
      };
    }
  };
  renderTrackSection();

  // Discover Similar — ✨ button + "You Might Also Like" grid, rendered at the
  // bottom of the modal (after the tracklist section).
  const discoverSection = el("div", "discover-results-section");
  const discoverHeading = el("div", "discover-similar-heading");
  const discoverH = el("h3", "", "You Might Also Like");
  const discoverBtn = el("button", "btn-discover-similar", "✨ Discover Similar");
  discoverBtn.title = "Find albums Apple Music suggests alongside this one";
  discoverHeading.appendChild(discoverH);
  discoverHeading.appendChild(discoverBtn);
  discoverSection.appendChild(discoverHeading);
  const discoverBody = el("div", "discover-similar-body");
  discoverSection.appendChild(discoverBody);
  details.appendChild(discoverSection);

  discoverBtn.addEventListener("click", async () => {
    discoverBtn.disabled = true;
    const originalLabel = discoverBtn.textContent;
    discoverBtn.textContent = "Discovering…";
    discoverBody.innerHTML = "";
    try {
      const sf = state.metadataStorefront || "us";
      const resp = await API.get(`/api/releases/${album.store_adam_id}/you-might-also-like?storefront=${sf}&limit=10`);
      const results = (resp && resp.results) || [];
      if (!results.length) {
        discoverBody.appendChild(el("div", "discover-empty", "No suggestions found"));
      } else {
        const grid = el("div", "discover-grid");
        results.forEach(a => grid.appendChild(albumCard(a)));
        discoverBody.appendChild(grid);
      }
    } catch (err) {
      const msg = err && String(err.message || "").includes("429")
        ? "Rate limited — try again in a minute"
        : "Failed to load suggestions";
      discoverBody.appendChild(el("div", "discover-empty", msg));
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

// ---------------------------------------------------------------------------
// Tracklist + track info ("Show info")
// ---------------------------------------------------------------------------
// Everything here renders from the source-agnostic /lookup shape. Every field
// is optional — whatever a metadata source doesn't provide is left out.

/** Copy of `base` with every non-null value from `extra` laid over it. */
function mergeNonNull(base, extra) {
  const out = { ...base };
  for (const [k, v] of Object.entries(extra || {})) {
    if (v != null && k !== "tracks") out[k] = v;
  }
  return out;
}

function plural(n, word) {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

function trackCountLabel(tracks) {
  const mv = tracks.filter(t => t.is_music_video).length;
  const songs = tracks.length - mv;
  return mv > 0 ? `${plural(songs, "track")} + ${plural(mv, "video")}` : plural(tracks.length, "track");
}

function setTrackInfoVisible(container, btn, on) {
  container.classList.toggle("show-track-info", on);
  btn.classList.toggle("active", on);
  btn.setAttribute("aria-pressed", String(on));
  btn.textContent = on ? "ⓘ Hide info" : "ⓘ Show info";
}

/** Secondary line under a track title; hidden by CSS unless info is shown. */
function trackInfoLine(t, albumDate, albumArtist) {
  const line = el("div", "track-info-line");
  if (t.release_date) {
    const rel = trackDateRelation(t.release_date, albumDate);
    const cls = rel === "before" ? " ti-early" : rel === "after" ? " ti-late" : "";
    const d = el("span", `ti-date${cls}`, formatDate(t.release_date));
    d.title = rel === "before" ? "Released before the album"
      : rel === "after" ? "Released after the album date" : "Track date";
    line.appendChild(d);
  }
  if ("has_lyrics" in t || "has_synced_lyrics" in t) {
    const any = t.has_lyrics || t.has_synced_lyrics;
    const label = t.has_synced_lyrics ? "Synced lyrics" : any ? "Lyrics" : "No lyrics";
    line.appendChild(el("span", `ti-lyrics${any ? "" : " ti-none"}`, label));
  }
  if (t.content_rating === "explicit") line.appendChild(el("span", "ti-explicit", "Explicit"));
  if (t.isrc) {
    const isrc = el("span", "ti-isrc", t.isrc);
    isrc.title = "ISRC";
    line.appendChild(isrc);
  }
  if (t.audio_locale) {
    const loc = el("span", "ti-meta", t.audio_locale);
    loc.title = "Audio locale";
    line.appendChild(loc);
  }
  if (t.artist && albumArtist && t.artist !== albumArtist) {
    line.appendChild(el("span", "ti-meta", t.artist));
  }
  if (t.composer) {
    const c = el("span", "ti-meta ti-composer", `✎ ${t.composer}`);
    c.title = `Composer: ${t.composer}`;
    line.appendChild(c);
  }
  return line.childNodes.length ? line : null;
}

/**
 * Numbered tracklist. `compareTracks` (same index) marks rows whose titles
 * differ with `diffClass`; `headerSf` prefixes the header with a storefront chip.
 */
function buildTracklist(tracks, opts = {}) {
  const { compareTracks = null, diffClass = "", headerSf = null, headerClass = "", albumDate = null, albumArtist = null } = opts;
  const tl = el("div", "tracklist");
  const head = el("div", `tracklist-header${headerClass ? ` ${headerClass}` : ""}`);
  const label = el("span", "tracklist-header-label");
  if (headerSf) {
    label.innerHTML = `${sfChipHtml(headerSf, "font-size:10px;vertical-align:middle;")} &nbsp;Tracklist — ${trackCountLabel(tracks)}`;
  } else {
    label.textContent = `Tracklist — ${trackCountLabel(tracks)}`;
  }
  head.appendChild(label);
  tl.appendChild(head);

  tracks.forEach((t, i) => {
    const other = compareTracks?.[i];
    const differs = other && t.title !== other.title;
    const row = el("div", `track-row${differs ? ` ${diffClass}` : ""}`);
    row.appendChild(el("span", "track-num", String(t.track_number ?? i + 1)));
    const titleCell = el("span", "track-title-cell");
    titleCell.appendChild(el("span", "track-title", t.title || "—"));
    if (t.is_music_video) titleCell.appendChild(el("span", "track-mv-badge", "MV"));
    row.appendChild(titleCell);
    row.appendChild(el("span", "track-dur", formatDuration(t.duration_ms)));
    const infoLine = trackInfoLine(t, albumDate, albumArtist);
    if (infoLine) row.appendChild(infoLine);
    tl.appendChild(row);
  });
  return tl;
}

/** Album-level "Release Info" panel; hidden by CSS unless info is shown. */
function buildAlbumInfoPanel(meta, tracks, sf) {
  const panel = el("div", "album-info-panel");
  const head = el("div", "aip-head");
  head.appendChild(el("span", "aip-title", "Release Info"));
  if (sf) head.insertAdjacentHTML("beforeend", sfChipHtml(sf));
  panel.appendChild(head);

  const notes = el("div", "aip-notes");
  const addNote = (text, highlight = false) => notes.appendChild(el("div", `aip-note${highlight ? " aip-highlight" : ""}`, text));
  const sum = summarizeTrackInfo(tracks, meta.release_date);
  if (sum.dated && meta.release_date && sum.total > 0) {
    if (sum.prereleased === sum.total) {
      addNote(sum.total === 1
        ? "This track was released before this release"
        : `All ${sum.total} tracks were released before this album — no new music`, true);
    } else if (sum.prereleased) {
      addNote(`${sum.prereleased} of ${plural(sum.total, "track")} released before the album · earliest ${formatDate(sum.earliestDate)}`, true);
    } else {
      addNote(sum.total === 1 ? "New track with this release" : `All ${sum.total} tracks are new with this release`);
    }
  }
  if (sum.lyricsKnown && sum.total > 0) {
    addNote(sum.lyrics
      ? `Lyrics on ${sum.lyrics} of ${plural(sum.total, "track")}${sum.synced ? ` · ${sum.synced} synced` : ""}`
      : "No lyrics on any track");
  }
  if (meta.is_complete === false) {
    addNote(`Incomplete — ${tracks.length} of ${meta.track_count ?? "?"} tracks available in this storefront`, true);
  }
  if (notes.childNodes.length) panel.appendChild(notes);

  const flags = [meta.is_compilation && "Compilation", meta.is_single && "Single"].filter(Boolean).join(" · ");
  const rating = { explicit: "Explicit", clean: "Clean" }[meta.content_rating];
  const rows = [
    ["Released", meta.release_date ? formatDate(meta.release_date) : null],
    ["Label", meta.record_label],
    ["Copyright", meta.copyright],
    ["UPC", meta.upc],
    ["Flagged as", flags || null],
    ["Rating", rating || null],
  ].filter(([, v]) => v);
  if (rows.length) {
    const grid = el("dl", "aip-grid");
    rows.forEach(([k, v]) => {
      grid.appendChild(el("dt", "", k));
      grid.appendChild(el("dd", k === "UPC" ? "aip-mono" : "", v));
    });
    panel.appendChild(grid);
  }
  return panel;
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
