/**
 * Shared JSDOM bootstrap for all frontend test suites.
 *
 * Require this module at the top of each test file. It registers
 * beforeAll / afterAll / beforeEach hooks in the calling suite's
 * scope and exports a `ctx` object whose `appWindow` property is
 * populated once the beforeAll hook has run.
 *
 * Usage:
 *   const ctx = require("./setup-jsdom");
 *   // inside a test: ctx.appWindow.someFunction(...)
 */

"use strict";

const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const ctx = {};

beforeAll(() => {
  // Minimal HTML that satisfies the DOM references in app.js
  const html = `<!DOCTYPE html>
<html>
<head></head>
<body>
  <nav id="sidebar">
    <button id="sidebar-expand-btn"></button>
    <a class="nav-link" data-page="releases" href="#/">New</a>
    <a class="nav-link" data-page="all" href="#/all">All</a>
    <a class="nav-link" data-page="watchlist" href="#/watchlist">Watchlist</a>
    <a class="nav-link" data-page="settings" href="#/settings">Settings</a>
    <button id="sidebar-src-badge"></button>
    <div id="meta-source-chips"></div>
  </nav>
  <div id="sidebar-backdrop"></div>
  <main id="main-content"></main>
  <div id="status-card">
    <div id="status-dot"></div>
    <div class="status-info"><div id="status-last-run"></div></div>
  </div>
  <button id="btn-refresh"></button>
  <div id="modal-overlay">
    <button id="modal-close"></button>
    <div id="modal-body"></div>
  </div>
</body>
</html>`;

  const dom = new JSDOM(html, {
    runScripts: "dangerously",
    url: "http://localhost",
    pretendToBeVisual: true,
  });

  ctx.appWindow = dom.window;

  // jsdom doesn't implement scrollIntoView (requires real layout engine).
  ctx.appWindow.HTMLElement.prototype.scrollIntoView = jest.fn();

  // Provide a fetch stub so module-level code doesn't throw on init.
  ctx.appWindow.fetch = jest.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve({ items: [], total: 0 }) })
  );

  // Inject all JS modules in dependency order so function declarations land on window
  const jsFiles = [
    "utils.js",
    "components.js",
    "state.js",
    "status.js",
    "modal.js",
    "page-releases.js",
    "page-artist.js",
    "page-watchlist.js",
    "page-settings.js",
    "app.js",
  ];
  for (const file of jsFiles) {
    const code = fs.readFileSync(path.join(__dirname, "..", file), "utf8");
    const script = ctx.appWindow.document.createElement("script");
    script.textContent = code;
    ctx.appWindow.document.head.appendChild(script);
  }

  // Expose const-declared objects for testing.
  // (const at script top-level is NOT a window property, but IS accessible
  //  from other scripts in the same page's global scope.)
  const exposeScript = ctx.appWindow.document.createElement("script");
  exposeScript.textContent = `
    window.__test_state               = state;
    window.__test_FORMAT_LABELS       = FORMAT_LABELS;
    window.__test_RELEASE_TYPE_LABELS = RELEASE_TYPE_LABELS;
    window.__test_RELEASE_TYPE_ORDER  = RELEASE_TYPE_ORDER;
    window.__test_API                 = API;
    window.__test_el                  = el;
    window.__test_dollar              = $;
    window.__test_refreshStatus       = refreshStatus;
    window.__test_renderSettings      = renderSettings;
    window.__test_COLLECTION_STATUS_LABELS = COLLECTION_STATUS_LABELS;
    window.__test_COLLECTION_TRANSITIONS   = COLLECTION_TRANSITIONS;
    window.__test_renderArtist             = renderArtist;
    window.__test_renderNewReleases        = renderNewReleases;
    window.__test_renderAllReleases        = renderAllReleases;
    window.__test_renderWatchlist          = renderWatchlist;
    window.__test_WatchlistPrefs           = WatchlistPrefs;
    window.__test_ReleasesPrefs            = ReleasesPrefs;
    window.__test_paginateList             = paginateList;
    window.__test_WATCHLIST_PAGE_SIZE      = WATCHLIST_PAGE_SIZE;
    window.__test_submitCliSchedulerJob    = submitCliSchedulerJob;
    window.__test_albumCard                = albumCard;
    window.__test_artistCard               = artistCard;
    window.__test_buildPagination          = buildPagination;
    window.__test_sanitizeHtml             = sanitizeHtml;
    window.__test_renderNotificationEvents = renderNotificationEvents;
    window.__test_openNotificationEventModal = openNotificationEventModal;
  `;
  ctx.appWindow.document.head.appendChild(exposeScript);
});

afterAll(() => {
  ctx.appWindow.close();
});

beforeEach(() => {
  // Reset fetch mock between tests
  ctx.appWindow.fetch.mockClear();
  // Reset watchedIds cache so each test gets a clean slate
  ctx.appWindow.__test_state.watchedIdsLoaded = false;
});

module.exports = ctx;
