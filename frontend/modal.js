/* =========================================================
   AM Discovery — Album detail modal
   ========================================================= */

"use strict";

// ---------------------------------------------------------------------------
// Album Detail Modal
// ---------------------------------------------------------------------------
// Bumped on every open/close. A load that finishes after the modal was closed
// or re-pointed at another album (e.g. hopping through "You Might Also Like")
// sees a stale token and bails instead of painting over the newer content.
let _modalSeq = 0;

function modalMessage(text) {
  $("modal-body").innerHTML = "";
  const msg = el("div", "modal-message", text);
  msg.style.padding = "32px";
  msg.style.textAlign = "center";
  $("modal-body").appendChild(msg);
}

// Opens the album detail modal. Resolves to the album shown, or null when the
// load failed or was superseded. Normally reached via the #/album/<id> route
// (see app.js) rather than called directly.
async function openModal(storeAdamId) {
  const seq = ++_modalSeq;
  const stale = () => seq !== _modalSeq;
  const overlay = $("modal-overlay");
  const body = $("modal-body");
  overlay.style.display = "flex";
  body.innerHTML = `<div style="padding:32px;text-align:center;color:var(--text-dim)">Loading…</div>`;

  // A deep link can open the modal before the storefront config has loaded;
  // wait for it so the lookups use the configured storefronts, not "us".
  if (state.configReady) {
    try { await state.configReady; } catch {}
    if (stale()) return null;
  }

  let album;
  // Live comparisons against the primary (metadata storefront) lookup, in
  // display order: the watched artist's preferred storefront, then +HOME.
  // [{ sf, data }] — storefronts whose lookup failed are left out.
  const comparisons = [];
  // Preferred storefront of the first credited watched artist that has one
  // (from the DB row, or the live lookup for albums not in the DB).
  let preferredSf = null;
  // The /lookup response the tracklist came from. "Show info" and Release Info
  // render from it (and from the comparison lookups), so they never re-query.
  let info = null;
  // One /lookup request per storefront for this modal: every caller (initial
  // load, Release Info chips, lazy tracklist load) shares these promises.
  const lookups = new Map();
  const getLookup = (sf) => {
    if (!lookups.has(sf)) {
      const p = API.get(`/api/releases/${storeAdamId}/lookup?storefront=${sf}`);
      lookups.set(sf, p);
      p.catch(() => lookups.delete(sf));  // allow a retry after a failure
    }
    return lookups.get(sf);
  };
  try {
    const home = state.homeStorefront;
    // Metadata source "Off" = no live Apple Music calls at all, so the
    // preferred storefront isn't fetched either (it's still highlighted).
    const metaSf = state.metadataStorefront;
    const shouldCompareHome = state.alwaysIncludeMY && home && metaSf && metaSf !== home;
    const lookupSf = metaSf || home || "us";

    const dbPromise = API.get(`/api/releases/${storeAdamId}`);
    const lookupPromise = metaSf ? getLookup(metaSf) : null;
    const homeLookupPromise = shouldCompareHome ? getLookup(home) : null;
    let prefLookupPromise = null;
    // Kick off the preferred-storefront comparison as soon as it's known.
    const startPreferred = (ps) => {
      preferredSf = ps ? String(ps).toLowerCase() : null;
      if (metaSf && preferredSf && preferredSf !== metaSf) prefLookupPromise = getLookup(preferredSf);
    };

    try {
      album = await dbPromise;
      startPreferred(album.preferred_source);
    } catch {
      if (stale()) return null;
      // Album not in local DB (e.g. a "You Might Also Like" suggestion that
      // was never discovered through room polling). Fall back to a fresh
      // Apple Music lookup so the modal still renders (via the shared cache,
      // so it reuses lookupPromise whenever that targets the same storefront).
      try {
        const fresh = await getLookup(lookupSf);
        info = fresh;
        startPreferred(fresh.preferred_source);
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
          _notIndexed: true,
        };
      } catch (err) {
        if (stale()) return null;
        const notFound = String((err && err.message) || "").includes("404");
        modalMessage(notFound ? "Album not found" : "Failed to load");
        return null;
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
        album._metaSf = metaSf;
        info = fresh;
      } catch {}
    }

    const compareSfs = [prefLookupPromise && preferredSf, homeLookupPromise && home].filter(Boolean);
    for (const sf of new Set(compareSfs)) {
      try { comparisons.push({ sf, data: await getLookup(sf) }); } catch {}
    }
  } catch {
    if (stale()) return null;
    modalMessage("Failed to load");
    return null;
  }
  if (stale()) return null;

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
    let badge = `${sfChipHtml(album._metaSf, "", preferredSf)} metadata`;
    if (preferredSf === album._metaSf) {
      badge += " · preferred source";
    } else if (preferredSf && state.metadataStorefront) {
      const missing = !comparisons.some(c => c.sf === preferredSf);
      badge += ` · ${sfChipHtml(preferredSf, "", preferredSf)} preferred source${missing ? " (not available)" : ""}`;
    }
    sfBadge.innerHTML = badge;
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

  // Compute diff early so the banner can appear before the tags. Each
  // comparison storefront is diffed against the primary (metadata) tracklist;
  // storefronts with identical tracklists are grouped and shown once.
  let tracks = album.tracks || [];
  const primarySf = album._metaSf || null;
  const diffGroups = primarySf ? groupTracklistComparisons(tracks, comparisons) : [];
  const hasDiff = diffGroups.length > 0;

  if (hasDiff) details.appendChild(buildTracklistDiffBanner(primarySf, diffGroups, preferredSf));

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
    tags.appendChild(sfChips(album.storefronts, preferredSf));
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
    return markPreferredSf(btn, storefront, preferredSf);
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
      markPreferredSf(btn, storefront, preferredSf);  // className resets above drop it
    });
    return markPreferredSf(btn, storefront, preferredSf);
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

  // CLI Scheduler / Harmony start with: metadata storefront, the watched
  // artist's preferred storefront, then home ("Check Storefronts" replaces them).
  const actionSfs = [...new Set([state.metadataStorefront, preferredSf, state.homeStorefront].filter(Boolean))];

  if (state.cliSchedulerEnabled) {
    const initialSfs = actionSfs;
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
      const res = await API.get(musicBrainzCheckUrl(album));
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
  const harmonyInitialSfs = actionSfs;
  const harmonySection = el("div", "cli-scheduler-section");
  const harmonyLabel = el("span", "cli-scheduler-label", "Harmony");
  harmonyBtns = el("div", "cli-scheduler-btns");
  harmonyInitialSfs.forEach(sf => harmonyBtns.appendChild(makeHarmonyBtn(sf)));
  harmonySection.appendChild(harmonyLabel);
  harmonySection.appendChild(harmonyBtns);
  actions.appendChild(harmonySection);

  details.appendChild(actions);

  // Release Info — collapsible (persistent preference), one chip per storefront.
  // Defaults to the user's metadata storefront; storefronts already fetched
  // switch instantly, others are fetched once through the shared cache.
  const knownLookups = new Map();
  if (info) knownLookups.set(album._metaSf, info);
  comparisons.forEach(c => knownLookups.set(c.sf, c.data));
  const infoSfs = [album._metaSf, preferredSf, ...knownLookups.keys(), ...(album.storefronts || [])];
  const releaseInfo = buildReleaseInfoSection({
    album,
    storefronts: [...new Set(infoSfs.filter(Boolean).map(s => s.toLowerCase()))],
    known: knownLookups,
    selected: info?.title ? album._metaSf : null,
    getLookup,
    preferredSf,
  });
  details.appendChild(releaseInfo.el);

  // Tracklist with per-track "Show info" (track dates, ISRCs, lyrics, …).
  // Built from the lookup response(s) already fetched above; only when no
  // lookup ran at all (metadata source Off, or it failed) does the button
  // fetch — once. The toggle is per album: every modal opens collapsed.
  const trackSection = el("div", "track-section");
  details.appendChild(trackSection);
  const infoBtn = el("button", "btn-track-info");
  infoBtn.type = "button";
  infoBtn.title = "Track dates, ISRCs, lyrics, composers";
  let showInfo = false;

  const renderTrackSection = () => {
    trackSection.innerHTML = "";
    infoBtn.disabled = false;
    const meta = mergeNonNull(album, info);
    if (tracks.length) {
      const tl = buildTracklist(tracks, {
        compareLists: hasDiff ? diffGroups.map(g => g.data.tracks) : null,
        diffClass: "track-differs",
        diffColor: hasDiff ? sfColor(primarySf) : null,
        headerSf: hasDiff ? primarySf : null,
        preferredSf,
        albumDate: meta.release_date,
        albumArtist: meta.artist,
      });
      tl.querySelector(".tracklist-header").appendChild(infoBtn);
      trackSection.appendChild(tl);
      diffGroups.forEach(g => {
        trackSection.appendChild(buildTracklist(g.data.tracks, {
          compareTracks: tracks,
          diffClass: "track-differs",
          diffColor: sfColor(g.sfs[0]),
          headerSf: g.sfs,
          headerClass: "tracklist-header-compare",
          preferredSf,
          albumDate: g.data.release_date || meta.release_date,
          albumArtist: g.data.artist || meta.artist,
        }));
      });
      setTrackInfoVisible(trackSection, infoBtn, showInfo);
      infoBtn.onclick = () => {
        showInfo = !showInfo;
        setTrackInfoVisible(trackSection, infoBtn, showInfo);
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
          info = await getLookup(sf);
          tracks = info.tracks || [];
          album._metaSf = sf;
          showInfo = true;
          renderTrackSection();
          knownLookups.set(sf, info);
          releaseInfo.select(sf);
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

  return album;
}

// The MusicBrainz route reads barcode/title/artist from the DB row. Albums
// that were never stored (deep link, "You Might Also Like") send the values
// fetched live from Apple Music instead.
function musicBrainzCheckUrl(album) {
  const base = `/api/releases/${album.store_adam_id}/musicbrainz`;
  if (!album._notIndexed) return base;
  const params = new URLSearchParams();
  if (album.upc) params.set("upc", album.upc);
  if (album.title) params.set("title", album.title);
  if (album.artist) params.set("artist", album.artist);
  const qs = params.toString();
  return qs ? `${base}?${qs}` : base;
}

// Hides the modal overlay. Purely visual — the album route's URL/history
// handling lives in closeAlbumModal (app.js), which ends up calling this.
function closeModal() {
  _modalSeq++;
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
