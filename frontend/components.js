/* =========================================================
   AM Discovery — UI components, artwork, storefronts, cards
   ========================================================= */

"use strict";

function formatBadges(formats) {
  if (!formats || !formats.length) return null;
  const wrap = el("div", "format-badges");
  for (const key of formats) {
    const label = FORMAT_LABELS[key];
    if (!label) continue;
    const span = el("span", `format-badge ${key}`, label);
    wrap.appendChild(span);
  }
  return wrap.childElementCount ? wrap : null;
}

function artworkEl(artworkUrl, cls) {
  if (artworkUrl) {
    const img = el("img", cls || "album-artwork");
    img.src = artworkUrl;
    img.alt = "";
    img.loading = "lazy";
    img.onerror = () => { img.replaceWith(placeholderEl(cls)); };
    return img;
  }
  return placeholderEl(cls);
}

function placeholderEl(cls) {
  const d = el("div",
    cls === "album-artwork"       ? "album-artwork-placeholder" :
    cls === "modal-artwork"       ? "modal-artwork-placeholder" :
    cls === "modal-artwork-thumb" ? "modal-artwork-thumb-placeholder" :
    "album-artwork-placeholder"
  );
  d.textContent = "♫";
  return d;
}

// Storefronts with hardcoded CSS colors — all others get a palette color
const SF_CSS_KNOWN = new Set(["hk", "jp", "my", "tw", "sg"]);
const SF_PALETTE = [
  { bg: "rgba(180,100,255,0.2)", fg: "#b464ff" }, // purple
  { bg: "rgba(255,140,0,0.2)",   fg: "#ff8c00" }, // orange
  { bg: "rgba(0,200,200,0.2)",   fg: "#00c8c8" }, // cyan
  { bg: "rgba(255,100,180,0.2)", fg: "#ff64b4" }, // pink
  { bg: "rgba(100,220,150,0.2)", fg: "#64dc96" }, // mint
  { bg: "rgba(255,180,100,0.2)", fg: "#ffb464" }, // peach
  { bg: "rgba(150,100,255,0.2)", fg: "#9664ff" }, // violet
  { bg: "rgba(0,180,255,0.2)",   fg: "#00b4ff" }, // sky
  { bg: "rgba(255,60,60,0.2)",   fg: "#ff3c3c" }, // red
  { bg: "rgba(180,220,60,0.2)",  fg: "#b4dc3c" }, // lime
  { bg: "rgba(255,120,180,0.2)", fg: "#ff78b4" }, // rose
  { bg: "rgba(60,180,255,0.2)",  fg: "#3cb4ff" }, // azure
];

function sfPaletteColor(sf) {
  const code = sf.toLowerCase();
  let hash = 0;
  for (let i = 0; i < code.length; i++) hash = (hash * 31 + code.charCodeAt(i)) & 0xffff;
  return SF_PALETTE[hash % SF_PALETTE.length];
}

// Returns an inline style string for storefronts not covered by CSS
function sfChipInlineStyle(sf) {
  if (SF_CSS_KNOWN.has(sf.toLowerCase())) return "";
  const { bg, fg } = sfPaletteColor(sf);
  return `background:${bg};color:${fg};`;
}

// Applies dynamic palette color to a chip element if needed
function applysfChipColor(el, sf) {
  const style = sfChipInlineStyle(sf);
  if (style) el.style.cssText += style;
}

// Applies palette color to a meta-src-btn for unknown storefronts (active state only)
function applyMetaSrcBtnColor(btn, sf, isActive) {
  if (SF_CSS_KNOWN.has(sf.toLowerCase()) || !isActive) return;
  const { bg, fg } = sfPaletteColor(sf);
  btn.style.color = fg;
  btn.style.background = bg;
  btn.style.borderColor = bg.replace("0.2)", "0.4)");
}

// Returns full <span class="sf-chip ..."> HTML for use in innerHTML, with optional extra style
function sfChipHtml(sf, extraStyle = "") {
  const inlineStyle = sfChipInlineStyle(sf) + extraStyle;
  const styleAttr = inlineStyle ? ` style="${inlineStyle}"` : "";
  return `<span class="sf-chip ${sf.toLowerCase()}"${styleAttr}>${sf.toUpperCase()}</span>`;
}

function sfChips(storefronts) {
  const div = el("div", "sf-chips");
  (storefronts || []).forEach(sf => {
    const c = el("span", `sf-chip ${sf.toLowerCase()}`);
    applysfChipColor(c, sf);
    c.textContent = sf.toUpperCase();
    div.appendChild(c);
  });
  return div;
}

function skeletonGrid(n = 12) {
  const grid = el("div", "loading-grid");
  for (let i = 0; i < n; i++) {
    const card = el("div", "skeleton-card");
    card.innerHTML = `<div class="skeleton-art"></div><div class="skeleton-line"></div><div class="skeleton-line short"></div>`;
    grid.appendChild(card);
  }
  return grid;
}

// ---------------------------------------------------------------------------
// Utility components
// ---------------------------------------------------------------------------
function buildHeader(title, subtitle) {
  const header = el("div", "page-header");
  const h = el("h1", "page-title", title);
  header.appendChild(h);
  if (subtitle) {
    header.appendChild(el("p", "page-subtitle", subtitle));
  }
  return header;
}

function buildPagination(current, total, onPage) {
  const wrap = el("div", "pagination");

  const scrollTop = () => window.scrollTo(0, 0);

  const prev = el("button", "page-btn", "← Prev");
  prev.disabled = current <= 1;
  prev.addEventListener("click", () => { scrollTop(); onPage(current - 1); });
  wrap.appendChild(prev);

  // Show up to 5 page buttons
  const start = Math.max(1, current - 2);
  const end = Math.min(total, start + 4);
  for (let p = start; p <= end; p++) {
    const btn = el("button", `page-btn${p === current ? " active" : ""}`, String(p));
    btn.addEventListener("click", () => { scrollTop(); onPage(p); });
    wrap.appendChild(btn);
  }

  const info = el("span", "page-info", `Page ${current} of ${total}`);
  wrap.appendChild(info);

  const next = el("button", "page-btn", "Next →");
  next.disabled = current >= total;
  next.addEventListener("click", () => { scrollTop(); onPage(current + 1); });
  wrap.appendChild(next);

  return wrap;
}

// ---------------------------------------------------------------------------
// Artist links helper — renders multiple linked artist names or falls back
// to a single artist name/link when artists_json is not available.
// ---------------------------------------------------------------------------
function makeArtistLinks(album, cls, onNav) {
  const wrap = el("span", cls);
  const artists = album.artists_json;
  if (Array.isArray(artists) && artists.length) {
    wrap.classList.add("multi");
    artists.forEach((a, i) => {
      if (i > 0) wrap.appendChild(document.createTextNode(", "));
      const span = el("span", "artist-link", a.name || "—");
      if (a.id) {
        span.addEventListener("click", e => {
          e.stopPropagation();
          state.artistHint = { id: String(a.id), name: a.name, url: a.url, artwork_url: a.artwork_url, genre: a.genre };
          if (onNav) onNav();
          location.hash = `#/artist/${a.id}`;
        });
      }
      wrap.appendChild(span);
    });
    wrap.title = album.artist || "";
  } else {
    wrap.textContent = album.artist || "—";
    wrap.title = album.artist || "";
    if (album.artist_id) {
      wrap.addEventListener("click", e => {
        e.stopPropagation();
        if (onNav) onNav();
        location.hash = `#/artist/${album.artist_id}`;
      });
    }
  }
  return wrap;
}

// ---------------------------------------------------------------------------
// Album card
// ---------------------------------------------------------------------------
function albumCard(album) {
  const card = el("div", `album-card${album.watched ? " watched" : ""}`);
  card.dataset.id = album.store_adam_id;

  if (album.watched) {
    const badge = el("span", "watched-badge", "⭐");
    card.appendChild(badge);
  }

  const artWrap = el("div", "album-art-wrap");
  artWrap.appendChild(artworkEl(album.artwork_url, "album-artwork"));
  if (album.track_count) {
    const tc = el("span", "track-count-chip", `${album.track_count}`);
    artWrap.appendChild(tc);
  }
  card.appendChild(artWrap);

  const info = el("div", "album-info");

  const title = el("div", "album-title", album.title || "—");
  title.title = album.title || "";
  info.appendChild(title);

  info.appendChild(makeArtistLinks(album, "album-artist"));

  if (album.genre) {
    const genre = el("div", "release-date", album.genre);
    genre.style.color = "var(--text-dim)";
    info.appendChild(genre);
  }

  const meta = el("div", "album-meta");
  const dateEl = el("span", `release-date${isFutureDate(album.release_date) ? " future" : ""}`, formatDate(album.release_date));
  meta.appendChild(dateEl);

  if (album.release_type) {
    const TYPE_SHORT = {
      "main-albums":        "Album",
      "compilation-albums": "Comp.",
      "live-albums":        "Live",
      "singles-eps":        "Single/EP",
    };
    const chip = el("span", `release-type-chip rt-${album.release_type}`, TYPE_SHORT[album.release_type] || album.release_type);
    meta.appendChild(chip);
  }

  const sf = sfChips(album.storefronts);
  meta.appendChild(sf);
  info.appendChild(meta);
  card.appendChild(info);

  card.addEventListener("click", () => openModal(album.store_adam_id));

  return card;
}

// ---------------------------------------------------------------------------
// Artist card (circular artwork, navigates to in-app artist page)
// ---------------------------------------------------------------------------
function artistCard(artist) {
  const card = el("div", "artist-card");
  if (artist.id) card.dataset.id = artist.id;

  card.appendChild(artworkEl(artist.artwork_url, "album-artwork"));

  const name = el("div", "artist-card-name", artist.name || "—");
  name.title = artist.name || "";
  card.appendChild(name);

  if (artist.genre) {
    card.appendChild(el("div", "artist-card-genre", artist.genre));
  }

  card.addEventListener("click", () => {
    if (artist.id) location.hash = `#/artist/${artist.id}`;
  });

  return card;
}
