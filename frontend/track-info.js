/* =========================================================
   AM Discovery — Album modal: tracklist, track info, Release Info
   ========================================================= */

"use strict";

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

/**
 * Body of the Release Info section for one storefront's data: summary notes
 * (modal-tag pills) + label/copyright/UPC grid. Null when there's nothing to show.
 */
function buildAlbumInfoBody(meta, tracks) {
  const panel = el("div", "aip-content");
  const notes = el("div", "aip-notes");
  const addNote = (text, highlight = false) =>
    notes.appendChild(el("span", `modal-tag aip-note${highlight ? " aip-highlight" : ""}`, text));
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
  return notes.childNodes.length || rows.length ? panel : null;
}

/**
 * Collapsible "Release Info" section with clickable storefront chips.
 *
 * - `storefronts`: chip order (the user's metadata storefront first).
 * - `known`: Map storefront → /lookup response already fetched by the modal;
 *   those switch instantly. Other storefronts go through `getLookup(sf)`
 *   (the modal's per-album cache) — at most one request each.
 * - `selected`: initial storefront, or null to show only the DB row (`album`).
 * Collapsed/expanded is a persistent user preference (ReleaseInfoPrefs).
 * Returns { el, select(sf) } so the modal can switch it after a lazy load.
 */
function buildReleaseInfoSection({ album, storefronts, known, selected, getLookup }) {
  const section = el("div", "album-info-panel");
  const head = el("div", "aip-head");
  const toggle = el("button", "aip-toggle");
  toggle.type = "button";
  const chevron = el("span", "aip-chevron", "▾");
  toggle.appendChild(chevron);
  toggle.appendChild(el("span", "aip-title", "Release Info"));
  head.appendChild(toggle);
  const chips = el("div", "aip-sfs");
  head.appendChild(chips);
  const body = el("div", "aip-body");
  section.appendChild(head);
  section.appendChild(body);

  const setCollapsed = (collapsed) => {
    section.classList.toggle("collapsed", collapsed);
    chevron.textContent = collapsed ? "▸" : "▾";
    toggle.setAttribute("aria-expanded", String(!collapsed));
    toggle.title = collapsed ? "Show release info" : "Hide release info";
  };
  setCollapsed(ReleaseInfoPrefs.isCollapsed());
  toggle.addEventListener("click", () => {
    const collapsed = !section.classList.contains("collapsed");
    ReleaseInfoPrefs.setCollapsed(collapsed);
    setCollapsed(collapsed);
  });

  let current = null;
  const status = (text) => {
    body.innerHTML = "";
    body.appendChild(el("p", "aip-status", text));
  };
  const show = (data) => {
    body.innerHTML = "";
    const content = data
      ? buildAlbumInfoBody(mergeNonNull(album, data), data.tracks || [])
      : buildAlbumInfoBody(album, album.tracks || []);
    if (content) body.appendChild(content);
    else status("No release info available.");
  };

  const chipFor = {};
  const select = (sf) => {
    current = sf;
    Object.entries(chipFor).forEach(([code, c]) => {
      c.classList.toggle("selected", code === sf);
      c.setAttribute("aria-pressed", String(code === sf));
    });
    if (!sf) return show(null);
    if (known.has(sf)) {
      const data = known.get(sf);
      return data && data.title ? show(data) : status(`No release info from the ${sf.toUpperCase()} storefront.`);
    }
    status(`Loading ${sf.toUpperCase()}…`);
    chipFor[sf]?.classList.add("loading");
    getLookup(sf).then((data) => {
      known.set(sf, data);
      chipFor[sf]?.classList.remove("loading");
      if (current === sf) select(sf);
    }).catch(() => {
      chipFor[sf]?.classList.remove("loading");
      if (current === sf) status(`Couldn't load release info for ${sf.toUpperCase()}.`);
    });
  };

  storefronts.forEach((sf) => {
    const c = el("button", `sf-chip ${sf} aip-sf-chip`, sf.toUpperCase());
    c.type = "button";
    c.title = `Release info from the ${sf.toUpperCase()} storefront`;
    applysfChipColor(c, sf);
    c.addEventListener("click", () => { if (sf !== current) select(sf); });
    chipFor[sf] = c;
    chips.appendChild(c);
  });

  select(selected);
  return { el: section, select };
}
