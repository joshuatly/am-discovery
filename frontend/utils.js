/* =========================================================
   AM Discovery — Utilities, API helpers, constants
   ========================================================= */

"use strict";

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------
const API = {
  async get(path) {
    const r = await fetch(path);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  },
  async post(path, body) {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    return r.json();
  },
  async put(path, body) {
    const r = await fetch(path, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    return r.json();
  },
  async del(path) {
    const r = await fetch(path, { method: "DELETE" });
    return r.json();
  },
  async patch(path, body) {
    const r = await fetch(path, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    return r.json();
  },
};

// ---------------------------------------------------------------------------
// Utility helpers
// ---------------------------------------------------------------------------
const $ = id => document.getElementById(id);
const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
};

// True when a click carries a modifier (or is a middle-click) that means the
// browser should handle the link itself — ⌘/Ctrl-click opens a background tab,
// Shift-click a new window, Alt-click downloads. In-app routers must not
// preventDefault() on these or the "open in new tab" gesture silently breaks.
function isModifiedClick(e) {
  return !!(e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || (e.button != null && e.button !== 0));
}

// Sanitize HTML from Apple Music bios — allow only safe inline formatting tags.
const SAFE_BIO_TAGS = new Set(["BR", "B", "I", "EM", "STRONG"]);
function sanitizeHtml(html) {
  const tmp = document.createElement("div");
  tmp.innerHTML = html;
  function clean(node) {
    const frag = document.createDocumentFragment();
    for (const child of [...node.childNodes]) {
      if (child.nodeType === Node.TEXT_NODE) {
        frag.appendChild(document.createTextNode(child.textContent));
      } else if (child.nodeType === Node.ELEMENT_NODE) {
        if (SAFE_BIO_TAGS.has(child.tagName)) {
          const safe = document.createElement(child.tagName);
          safe.appendChild(clean(child));
          frag.appendChild(safe);
        } else {
          frag.appendChild(clean(child));
        }
      }
    }
    return frag;
  }
  const out = document.createElement("div");
  out.appendChild(clean(tmp));
  return out.innerHTML;
}

// localStorage helpers for watchlist preferences
const WatchlistPrefs = {
  getSortFilter() {
    return localStorage.getItem("watchlist_sort") || "name";
  },
  setSortFilter(sort) {
    localStorage.setItem("watchlist_sort", sort);
  },
};

// localStorage helpers for releases sort preference
const ReleasesPrefs = {
  getSort() {
    return localStorage.getItem("releases_sort") || "release_date";
  },
  setSort(sort) {
    localStorage.setItem("releases_sort", sort);
  },
};

// Album modal "Release Info" collapsed/expanded — a persistent preference
// (unlike the per-album "Show info" track toggle).
const ReleaseInfoPrefs = {
  isCollapsed() {
    try { return localStorage.getItem("release_info_collapsed") === "1"; } catch { return false; }
  },
  setCollapsed(collapsed) {
    try { localStorage.setItem("release_info_collapsed", collapsed ? "1" : "0"); } catch {}
  },
};

function formatDate(d) {
  if (!d || d === "Unknown") return "—";
  if (/^\d{4}-00-00/.test(d)) return d.slice(0, 4);
  try {
    return new Date(d + "T00:00:00Z").toLocaleDateString("en-GB", { year: "numeric", month: "short", day: "numeric" });
  } catch { return d; }
}

function isFutureDate(d) {
  if (!d || /^\d{4}-00-00/.test(d)) return false;
  try {
    return new Date(d + "T00:00:00Z") > new Date();
  } catch { return false; }
}

function timeAgo(isoStr) {
  if (!isoStr) return "never";
  const ts = typeof isoStr === "number" ? isoStr * 1000 : new Date(isoStr + "Z").getTime();
  const diff = Date.now() - ts;
  const m = Math.floor(diff / 60000);
  if (m < 1)  return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function formatDuration(ms) {
  if (!ms) return "";
  const s = Math.round(ms / 1000);
  const m = Math.floor(s / 60);
  return `${m}:${(s % 60).toString().padStart(2, "0")}`;
}

const RELEASE_TYPE_LABELS = {
  "main-albums":        "Albums",
  "compilation-albums": "Compilations",
  "live-albums":        "Live Albums",
  "singles-eps":        "Singles & EPs",
};
const RELEASE_TYPE_ORDER = ["main-albums", "singles-eps", "compilation-albums", "live-albums"];

const FORMAT_LABELS = {
  "lossy-stereo":    "AAC",
  "lossless":        "Lossless",
  "hi-res-lossless": "Hi-Res Lossless",
  "atmos":           "Dolby Atmos",
  "spatial":         "Spatial Audio",
  "adm":             "Apple Digital Masters",
};

const COLLECTION_STATUS_LABELS = {
  new: "New",
  complete: "Complete",
  new_release: "New Release",
  in_progress: "In Progress",
};
const COLLECTION_TRANSITIONS = {
  new: ["complete", "in_progress"],
  complete: ["in_progress"],
  new_release: ["complete", "in_progress"],
  in_progress: ["complete"],
};

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

function tracklistsDiffer(a, b) {
  if (a.length !== b.length) return true;
  return a.some((t, i) => t.title !== b[i]?.title);
}

// ---------------------------------------------------------------------------
// Track info ("Show info" in the album modal)
// ---------------------------------------------------------------------------
// Pure helpers over the source-agnostic track shape returned by /lookup
// (release_date, has_lyrics, has_synced_lyrics, …). Any field may be missing
// for a given metadata source; missing data is ignored, never guessed.

/** "before" | "after" | "same" relative to the album date, or null if either is unknown. */
function trackDateRelation(trackDate, albumDate) {
  const t = (trackDate || "").slice(0, 10);
  const a = (albumDate || "").slice(0, 10);
  if (!t || !a) return null;
  if (t < a) return "before";
  if (t > a) return "after";
  return "same";
}

/**
 * Summarize songs (music videos excluded) for the album info panel:
 * how many were already out before the album (pre-released singles,
 * compilations of old material) and lyrics coverage.
 */
function summarizeTrackInfo(tracks, albumDate) {
  const songs = (tracks || []).filter(t => !t.is_music_video);
  const dated = songs.filter(t => t.release_date);
  const early = dated.filter(t => trackDateRelation(t.release_date, albumDate) === "before");
  const earliest = early.reduce((min, t) => (!min || t.release_date < min ? t.release_date : min), null);
  return {
    total: songs.length,
    dated: dated.length,
    prereleased: early.length,
    earliestDate: earliest ? earliest.slice(0, 10) : null,
    lyricsKnown: songs.some(t => "has_lyrics" in t || "has_synced_lyrics" in t),
    lyrics: songs.filter(t => t.has_lyrics || t.has_synced_lyrics).length,
    synced: songs.filter(t => t.has_synced_lyrics).length,
  };
}
