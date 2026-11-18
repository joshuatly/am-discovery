"use strict";

// ---------------------------------------------------------------------------
// Album route (#/album/<id>) — deep links, background page, close/back
// behaviour, albums that aren't in the local DB.
//
// Each test boots a fresh window at a chosen URL (cold deep links need an
// empty history and no page rendered yet), so this suite builds its own JSDOM
// instead of sharing the one from setup-jsdom.js.
// ---------------------------------------------------------------------------

const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const JS_FILES = [
  "utils.js", "components.js", "state.js", "status.js", "modal.js",
  "page-releases.js", "page-artist.js", "page-watchlist.js", "page-settings.js",
  "page-settings-notifications.js", "page-admin.js", "app.js",
];
const SOURCES = JS_FILES.map(f => fs.readFileSync(path.join(__dirname, "..", f), "utf8"));

const HTML = `<!DOCTYPE html><html><head></head><body>
  <nav id="sidebar">
    <button id="sidebar-expand-btn"></button>
    <a class="nav-link" data-page="releases" href="#/">New</a>
    <a class="nav-link" data-page="all" href="#/all">All</a>
    <a class="nav-link" data-page="watchlist" href="#/watchlist">Watchlist</a>
    <a class="nav-link" id="nav-admin" data-page="admin" href="#/admin">Admin</a>
    <a class="nav-link" data-page="settings" href="#/settings">Settings</a>
    <button id="sidebar-src-badge"></button>
    <div id="meta-source-chips"></div>
  </nav>
  <div id="sidebar-backdrop"></div>
  <main id="main-content"></main>
  <div id="status-card"><div id="status-dot"></div><div class="status-info"><div id="status-last-run"></div></div></div>
  <button id="btn-refresh"></button>
  <div id="modal-overlay" style="display:none">
    <button id="modal-close"></button>
    <div id="modal-body"></div>
  </div>
</body></html>`;

const ALBUMS = {
  "111": { store_adam_id: "111", title: "First Album", artist: "Artist A", artist_id: "ART1", storefronts: ["jp"], tracks: [], audio_formats: [], artists_json: [] },
  "222": { store_adam_id: "222", title: "Second Album", artist: "Artist B", artist_id: "ART2", storefronts: ["jp"], tracks: [], audio_formats: [], artists_json: [] },
};
const LIVE = { title: "Live Only", artist: "Live Artist", artist_id: "ART9", upc: "4988000", tracks: [], audio_formats: [] };

function jsonResponse(body, status = 200) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) });
}

// Fake backend. `overrides` maps an exact path (query string ignored) to a
// handler returning a fetch response promise, checked before the defaults.
function makeFetch(overrides = {}) {
  return jest.fn(url => {
    const handler = overrides[url.split("?")[0]];
    if (handler) return handler(url);
    if (url === "/api/system/config") {
      return jsonResponse({ check_storefronts: ["jp", "my"], home_storefront: "my", mb_scan_enabled: true });
    }
    let m = url.match(/^\/api\/releases\/([^/?]+)\/lookup\?storefront=(\w+)/);
    if (m) return m[1] === "LIVE1" ? jsonResponse({ ...LIVE }) : jsonResponse({ error: "Not found" }, 404);
    m = url.match(/^\/api\/releases\/([^/?]+)$/);
    if (m) return ALBUMS[m[1]] ? jsonResponse({ ...ALBUMS[m[1]] }) : jsonResponse({ error: "Not found" }, 404);
    if (url.includes("/musicbrainz")) return jsonResponse({ found: false, upc: null });
    return jsonResponse({ items: [], total: 0, releases: [], artists: [] });
  });
}

const tick = (ms = 15) => new Promise(r => setTimeout(r, ms));
async function settle() { for (let i = 0; i < 4; i++) await tick(); }

let w;

// Boots the app at `hash`. localStorage is cleared so the metadata storefront
// comes from config (home "my"), as for a first-time visitor.
async function boot(hash = "", overrides = {}) {
  const dom = new JSDOM(HTML, { runScripts: "dangerously", url: `http://localhost/${hash}`, pretendToBeVisual: true });
  w = dom.window;
  w.HTMLElement.prototype.scrollIntoView = jest.fn();
  w.scrollTo = jest.fn();
  w.localStorage.clear();
  w.fetch = makeFetch(overrides);
  w.setInterval = jest.fn();  // no status polling during tests
  for (const code of SOURCES) {
    const s = w.document.createElement("script");
    s.textContent = code;
    w.document.head.appendChild(s);
  }
  const expose = w.document.createElement("script");
  expose.textContent = "window.__test_state = state;";
  w.document.head.appendChild(expose);
  await settle();
  return w;
}

async function go(hash) {
  w.location.hash = hash;
  await settle();
}

const overlayOpen = () => w.document.getElementById("modal-overlay").style.display === "flex";
const modalTitle = () => w.document.querySelector("#modal-body .modal-title")?.textContent;
const activeNav = () => w.document.querySelector(".nav-link.active")?.dataset.page;
const fetched = re => w.fetch.mock.calls.map(c => c[0]).filter(u => re.test(u));

afterEach(() => { if (w) w.close(); w = null; });

describe("albumIdFromHash", () => {
  beforeEach(() => boot());

  test("parses album routes", () => {
    expect(w.albumIdFromHash("#/album/123")).toBe("123");
    expect(w.albumIdFromHash("#/album/123/")).toBe("123");
    expect(w.albumIdFromHash("#/album/a%2Fb")).toBe("a/b");
  });

  test("ignores other routes", () => {
    expect(w.albumIdFromHash("#/")).toBeNull();
    expect(w.albumIdFromHash("#/all")).toBeNull();
    expect(w.albumIdFromHash("#/album/")).toBeNull();
    expect(w.albumIdFromHash("#/album/1/extra")).toBeNull();
    expect(w.albumIdFromHash("")).toBeNull();
  });
});

describe("cold deep link", () => {
  test("renders New Releases behind the modal and opens the album", async () => {
    await boot("#/album/111");
    expect(overlayOpen()).toBe(true);
    expect(modalTitle()).toBe("First Album");
    expect(activeNav()).toBe("releases");
    expect(w.document.title).toBe("First Album — AM Discovery");
    expect(w.history.state.amAlbum).toEqual({ bg: "#/", depth: 0, cold: true });
  });

  test("closing goes to the home page without adding a history entry", async () => {
    await boot("#/album/111");
    const len = w.history.length;
    w.document.getElementById("modal-close").click();
    await settle();
    expect(w.location.hash).toBe("#/");
    expect(overlayOpen()).toBe(false);
    expect(w.history.length).toBe(len);
    expect(w.document.title).toBe("New Releases — AM Discovery");
  });

  test("closing after hopping to a second album still lands on home", async () => {
    await boot("#/album/111");
    await go("#/album/222");
    expect(modalTitle()).toBe("Second Album");
    expect(w.history.state.amAlbum).toEqual({ bg: "#/", depth: 1, cold: true });
    w.document.getElementById("modal-close").click();
    await settle();
    expect(w.location.hash).toBe("#/");
    expect(overlayOpen()).toBe(false);
  });
});

describe("album opened from a page in the app", () => {
  test("keeps the page behind it untouched and returns to it on close", async () => {
    await boot("#/all");
    const marker = w.document.createElement("span");
    marker.id = "page-marker";
    w.document.getElementById("main-content").appendChild(marker);

    await go("#/album/111");
    expect(overlayOpen()).toBe(true);
    expect(activeNav()).toBe("all");
    expect(w.history.state.amAlbum).toEqual({ bg: "#/all", depth: 1, cold: false });

    w.document.getElementById("modal-close").click();
    await settle();
    expect(w.location.hash).toBe("#/all");
    expect(overlayOpen()).toBe(false);
    // Not re-rendered: the marker we planted is still in the page.
    expect(w.document.getElementById("page-marker")).not.toBeNull();
    expect(w.document.title).toBe("All Albums — AM Discovery");
  });

  test("X after hopping A → B closes the whole modal", async () => {
    await boot("#/all");
    await go("#/album/111");
    await go("#/album/222");
    expect(w.history.state.amAlbum.depth).toBe(2);
    w.document.getElementById("modal-close").click();
    await settle();
    expect(w.location.hash).toBe("#/all");
    expect(overlayOpen()).toBe(false);
  });

  test("browser Back steps B → A → page", async () => {
    await boot("#/all");
    await go("#/album/111");
    await go("#/album/222");
    w.history.back();
    await settle();
    expect(w.location.hash).toBe("#/album/111");
    expect(modalTitle()).toBe("First Album");
    w.history.back();
    await settle();
    expect(w.location.hash).toBe("#/all");
    expect(overlayOpen()).toBe(false);
  });

  test("Escape and backdrop click close the album", async () => {
    await boot("#/all");
    await go("#/album/111");
    w.document.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape" }));
    await settle();
    expect(w.location.hash).toBe("#/all");
    expect(overlayOpen()).toBe(false);

    await go("#/album/111");
    w.document.getElementById("modal-overlay").click();
    await settle();
    expect(w.location.hash).toBe("#/all");
    expect(overlayOpen()).toBe(false);
  });

  test("View Artist then Back reopens the album over its original page", async () => {
    await boot("#/all");
    await go("#/album/111");
    const viewArtist = [...w.document.querySelectorAll("#modal-body .btn-header-action")]
      .find(a => a.textContent.startsWith("View Artist"));
    viewArtist.click();
    await settle();
    expect(w.location.hash).toBe("#/artist/ART1");
    expect(overlayOpen()).toBe(false);
    expect(activeNav()).toBeUndefined();

    w.history.back();
    await settle();
    expect(w.location.hash).toBe("#/album/111");
    expect(overlayOpen()).toBe(true);
    expect(activeNav()).toBe("all");  // background re-rendered as All Albums

    w.document.getElementById("modal-close").click();
    await settle();
    expect(w.location.hash).toBe("#/all");
    expect(overlayOpen()).toBe(false);
  });
});

describe("closeAlbumModal outside the album route", () => {
  test("just hides the overlay (notification event editor)", async () => {
    await boot("#/settings");
    const len = w.history.length;
    w.document.getElementById("modal-overlay").style.display = "flex";
    w.closeAlbumModal();
    await settle();
    expect(overlayOpen()).toBe(false);
    expect(w.location.hash).toBe("#/settings");
    expect(w.history.length).toBe(len);
  });
});

describe("albums not in the local database", () => {
  test("waits for config and looks up the home storefront", async () => {
    await boot("#/album/LIVE1");
    expect(modalTitle()).toBe("Live Only");
    expect(fetched(/\/api\/releases\/LIVE1\/lookup/)).toEqual(
      expect.arrayContaining(["/api/releases/LIVE1/lookup?storefront=my"]),
    );
    expect(fetched(/storefront=us/)).toEqual([]);
  });

  test("MusicBrainz check passes the live barcode/title/artist", async () => {
    await boot("#/album/LIVE1");
    const mbBtn = [...w.document.querySelectorAll("#modal-body .cli-scheduler-section")]
      .find(s => s.textContent.startsWith("MusicBrainz"))
      .querySelector("button");
    mbBtn.click();
    await settle();
    const [url] = fetched(/\/musicbrainz/);
    expect(url).toBe("/api/releases/LIVE1/musicbrainz?upc=4988000&title=Live+Only&artist=Live+Artist");
  });

  test("an unknown ID shows 'Album not found'", async () => {
    await boot("#/album/NOPE");
    expect(overlayOpen()).toBe(true);
    expect(w.document.querySelector("#modal-body .modal-message").textContent).toBe("Album not found");
  });

  test("a server error shows 'Failed to load'", async () => {
    await boot("#/album/BROKEN", {
      "/api/releases/BROKEN/lookup": () => jsonResponse({ error: "boom" }, 500),
    });
    expect(w.document.querySelector("#modal-body .modal-message").textContent).toBe("Failed to load");
  });
});

describe("musicBrainzCheckUrl", () => {
  beforeEach(() => boot());

  test("indexed albums use the plain route", () => {
    expect(w.musicBrainzCheckUrl({ store_adam_id: "1", upc: "9", title: "T", artist: "A" }))
      .toBe("/api/releases/1/musicbrainz");
  });

  test("unindexed albums append only the values they have", () => {
    expect(w.musicBrainzCheckUrl({ store_adam_id: "1", title: "T & U", _notIndexed: true }))
      .toBe("/api/releases/1/musicbrainz?title=T+%26+U");
    expect(w.musicBrainzCheckUrl({ store_adam_id: "1", _notIndexed: true }))
      .toBe("/api/releases/1/musicbrainz");
  });
});

describe("openModal superseded loads", () => {
  test("a slow earlier load does not overwrite the newer album", async () => {
    let releaseSlow;
    await boot("#/all", {
      "/api/releases/111": () => new Promise(r => { releaseSlow = () => r({ ok: true, status: 200, json: () => Promise.resolve({ ...ALBUMS["111"] }) }); }),
    });
    const first = w.openModal("111");
    await tick();
    const second = w.openModal("222");
    await second;
    expect(modalTitle()).toBe("Second Album");
    releaseSlow();
    expect(await first).toBeNull();
    expect(modalTitle()).toBe("Second Album");
  });

  test("closing while loading leaves the overlay closed", async () => {
    let releaseSlow;
    await boot("#/all", {
      "/api/releases/111": () => new Promise(r => { releaseSlow = () => r({ ok: true, status: 200, json: () => Promise.resolve({ ...ALBUMS["111"] }) }); }),
    });
    const p = w.openModal("111");
    await tick();
    w.closeModal();
    releaseSlow();
    expect(await p).toBeNull();
    expect(overlayOpen()).toBe(false);
  });
});

describe("album links", () => {
  beforeEach(() => boot("#/all"));

  test("album cards carry a real link to the album route", () => {
    const card = w.albumCard({ store_adam_id: "111", title: "First Album", artist: "Artist A", storefronts: [] });
    const link = card.querySelector("a.album-card-link");
    expect(link).not.toBeNull();
    expect(link.getAttribute("href")).toBe("#/album/111");
    expect(link.getAttribute("aria-label")).toBe("First Album — Artist A");
  });

  test("clicking a card badge opens the album", async () => {
    const card = w.albumCard({ store_adam_id: "111", title: "First Album", watched: true, storefronts: [] });
    w.document.body.appendChild(card);
    card.querySelector(".watched-badge").click();
    await settle();
    expect(w.location.hash).toBe("#/album/111");
    card.remove();
  });

  test("clicking an artist name on a card goes to the artist, not the album", async () => {
    const card = w.albumCard({
      store_adam_id: "111", title: "First Album", storefronts: [],
      artists_json: [{ id: "ART1", name: "Artist A" }],
    });
    w.document.body.appendChild(card);
    card.querySelector(".artist-link").click();
    await settle();
    expect(w.location.hash).toBe("#/artist/ART1");
    card.remove();
  });

  test("admin release card links its artwork and Open button to the album route", () => {
    const card = w.adminReleaseCard({ store_adam_id: "111", title: "First Album", artist_name: "A" }, () => {});
    expect(card.querySelector("a.admin-release-art-link").getAttribute("href")).toBe("#/album/111");
    const open = [...card.querySelectorAll("a.btn-secondary")].find(a => a.textContent === "Open");
    expect(open.getAttribute("href")).toBe("#/album/111");
  });
});
