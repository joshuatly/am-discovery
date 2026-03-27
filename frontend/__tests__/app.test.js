/**
 * Frontend tests for app.js utility functions.
 *
 * Strategy:
 * - Create a dedicated JSDOM instance with runScripts: 'dangerously' so that
 *   app.js's function declarations are visible as window properties regardless
 *   of the "use strict" directive in the source.
 * - All assertions go through appWindow.functionName, which is the window
 *   object of the isolated jsdom instance.
 */

const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

// ---------------------------------------------------------------------------
// Bootstrap: create a JSDOM instance with app.js injected as a script tag
// ---------------------------------------------------------------------------

let appWindow;

beforeAll(() => {
  // Minimal HTML that satisfies the DOM references in app.js
  const html = `<!DOCTYPE html>
<html>
<head></head>
<body>
  <nav>
    <a class="nav-link" data-page="releases" href="#/">New</a>
    <a class="nav-link" data-page="all" href="#/all">All</a>
    <a class="nav-link" data-page="watchlist" href="#/watchlist">Watchlist</a>
    <a class="nav-link" data-page="settings" href="#/settings">Settings</a>
  </nav>
  <main id="main-content"></main>
  <div id="status-card">
    <div id="status-dot"></div>
    <div class="status-info"><div id="status-last-run"></div></div>
  </div>
  <button id="btn-refresh"></button>
  <div id="meta-source-chips"></div>
</body>
</html>`;

  const dom = new JSDOM(html, {
    runScripts: "dangerously",
    url: "http://localhost",
    pretendToBeVisual: true,
  });

  appWindow = dom.window;

  // Provide a fetch stub so app.js module-level code doesn't throw
  appWindow.fetch = jest.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
  );

  // localStorage is provided by jsdom — no stub needed

  // Inject app.js as a script element so function declarations land on window
  const code = fs.readFileSync(path.join(__dirname, "../app.js"), "utf8");
  const script = appWindow.document.createElement("script");
  script.textContent = code;
  appWindow.document.head.appendChild(script);

  // Inject a second script to expose const-declared objects for testing.
  // (const at script top-level is NOT a window property, but IS accessible from
  //  other scripts in the same page's global scope.)
  const exposeScript = appWindow.document.createElement("script");
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
  `;
  appWindow.document.head.appendChild(exposeScript);
});

beforeEach(() => {
  // Reset fetch mock between tests
  appWindow.fetch.mockClear();
});

// ---------------------------------------------------------------------------
// formatDate
// ---------------------------------------------------------------------------

describe("formatDate", () => {
  test("returns em-dash for null", () => {
    expect(appWindow.formatDate(null)).toBe("—");
  });

  test("returns em-dash for undefined", () => {
    expect(appWindow.formatDate(undefined)).toBe("—");
  });

  test("returns em-dash for the string 'Unknown'", () => {
    expect(appWindow.formatDate("Unknown")).toBe("—");
  });

  test("returns em-dash for empty string", () => {
    expect(appWindow.formatDate("")).toBe("—");
  });

  test("returns year only for YYYY-00-00 format", () => {
    expect(appWindow.formatDate("2024-00-00")).toBe("2024");
  });

  test("returns year only for 1990-00-00", () => {
    expect(appWindow.formatDate("1990-00-00")).toBe("1990");
  });

  test("formats a valid ISO date and includes the year", () => {
    const result = appWindow.formatDate("2024-03-15");
    expect(result).toContain("2024");
  });

  test("formats another valid date with the correct year", () => {
    const result = appWindow.formatDate("2020-12-25");
    expect(result).toContain("2020");
  });

  test("returns a string for an unparseable date", () => {
    const result = appWindow.formatDate("not-a-date");
    expect(typeof result).toBe("string");
  });

  test("handles dates from the far past", () => {
    const result = appWindow.formatDate("1960-06-01");
    expect(result).toContain("1960");
  });
});

// ---------------------------------------------------------------------------
// isFutureDate
// ---------------------------------------------------------------------------

describe("isFutureDate", () => {
  test("returns false for null", () => {
    expect(appWindow.isFutureDate(null)).toBe(false);
  });

  test("returns false for undefined", () => {
    expect(appWindow.isFutureDate(undefined)).toBe(false);
  });

  test("returns false for empty string", () => {
    expect(appWindow.isFutureDate("")).toBe(false);
  });

  test("returns false for YYYY-00-00 format even in the far future", () => {
    expect(appWindow.isFutureDate("2099-00-00")).toBe(false);
  });

  test("returns true for a date far in the future", () => {
    expect(appWindow.isFutureDate("2099-12-31")).toBe(true);
  });

  test("returns false for a clearly past date", () => {
    expect(appWindow.isFutureDate("2000-01-01")).toBe(false);
  });

  test("returns false for an invalid date string", () => {
    const result = appWindow.isFutureDate("not-a-date");
    expect(typeof result).toBe("boolean");
  });

  test("returns false for yesterday", () => {
    const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
    expect(appWindow.isFutureDate(yesterday)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// timeAgo
// ---------------------------------------------------------------------------

describe("timeAgo", () => {
  test("returns 'never' for null", () => {
    expect(appWindow.timeAgo(null)).toBe("never");
  });

  test("returns 'never' for undefined", () => {
    expect(appWindow.timeAgo(undefined)).toBe("never");
  });

  test("returns 'just now' for a timestamp a few seconds ago (unix seconds)", () => {
    const nowSec = Math.floor(Date.now() / 1000);
    expect(appWindow.timeAgo(nowSec)).toBe("just now");
  });

  test("returns 'just now' for a timestamp 30 seconds ago", () => {
    const sec = Math.floor(Date.now() / 1000) - 30;
    expect(appWindow.timeAgo(sec)).toBe("just now");
  });

  test("returns 'Xm ago' for 30 minutes ago", () => {
    const sec = Math.floor(Date.now() / 1000) - 30 * 60;
    expect(appWindow.timeAgo(sec)).toBe("30m ago");
  });

  test("returns '1m ago' for exactly 60 seconds ago", () => {
    const sec = Math.floor(Date.now() / 1000) - 60;
    expect(appWindow.timeAgo(sec)).toBe("1m ago");
  });

  test("returns 'Xh ago' for 3 hours ago", () => {
    const sec = Math.floor(Date.now() / 1000) - 3 * 3600;
    expect(appWindow.timeAgo(sec)).toBe("3h ago");
  });

  test("returns '1h ago' for 60 minutes ago", () => {
    const sec = Math.floor(Date.now() / 1000) - 60 * 60;
    expect(appWindow.timeAgo(sec)).toBe("1h ago");
  });

  test("returns 'Xd ago' for 2 days ago", () => {
    const sec = Math.floor(Date.now() / 1000) - 2 * 24 * 3600;
    expect(appWindow.timeAgo(sec)).toBe("2d ago");
  });

  test("accepts an ISO string for recent time", () => {
    const isoStr = new Date(Date.now() - 100).toISOString().replace("Z", "");
    expect(appWindow.timeAgo(isoStr)).toBe("just now");
  });
});

// ---------------------------------------------------------------------------
// formatDuration
// ---------------------------------------------------------------------------

describe("formatDuration", () => {
  test("returns empty string for null", () => {
    expect(appWindow.formatDuration(null)).toBe("");
  });

  test("returns empty string for undefined", () => {
    expect(appWindow.formatDuration(undefined)).toBe("");
  });

  test("returns empty string for 0", () => {
    expect(appWindow.formatDuration(0)).toBe("");
  });

  test("formats 60000ms as '1:00'", () => {
    expect(appWindow.formatDuration(60000)).toBe("1:00");
  });

  test("formats 90000ms as '1:30'", () => {
    expect(appWindow.formatDuration(90000)).toBe("1:30");
  });

  test("pads seconds with leading zero: 65000ms → '1:05'", () => {
    expect(appWindow.formatDuration(65000)).toBe("1:05");
  });

  test("formats 30000ms as '0:30'", () => {
    expect(appWindow.formatDuration(30000)).toBe("0:30");
  });

  test("formats exactly 5 minutes", () => {
    expect(appWindow.formatDuration(300000)).toBe("5:00");
  });

  test("formats 3661000ms (61 minutes 1 second) as '61:01'", () => {
    expect(appWindow.formatDuration(3661000)).toBe("61:01");
  });

  test("formats 1000ms as '0:01'", () => {
    expect(appWindow.formatDuration(1000)).toBe("0:01");
  });
});

// ---------------------------------------------------------------------------
// el (DOM element factory)
// ---------------------------------------------------------------------------

describe("el (DOM element factory)", () => {
  test("creates a div with correct tagName", () => {
    expect(appWindow.__test_el("div").tagName).toBe("DIV");
  });

  test("creates a span element", () => {
    expect(appWindow.__test_el("span").tagName).toBe("SPAN");
  });

  test("sets className when provided", () => {
    expect(appWindow.__test_el("div", "my-class").className).toBe("my-class");
  });

  test("leaves className empty when null", () => {
    expect(appWindow.__test_el("div", null).className).toBe("");
  });

  test("sets textContent when provided", () => {
    expect(appWindow.__test_el("p", null, "hello").textContent).toBe("hello");
  });

  test("leaves textContent empty when null", () => {
    expect(appWindow.__test_el("div", "cls", null).textContent).toBe("");
  });

  test("sets both className and textContent together", () => {
    const e = appWindow.__test_el("button", "btn", "Click me");
    expect(e.className).toBe("btn");
    expect(e.textContent).toBe("Click me");
  });
});

// ---------------------------------------------------------------------------
// sfChips
// ---------------------------------------------------------------------------

describe("sfChips", () => {
  test("returns a div element", () => {
    expect(appWindow.sfChips([]).tagName).toBe("DIV");
  });

  test("has class sf-chips", () => {
    expect(appWindow.sfChips([]).className).toBe("sf-chips");
  });

  test("creates one chip per storefront", () => {
    expect(appWindow.sfChips(["us", "jp", "hk"]).children.length).toBe(3);
  });

  test("chip text is uppercased storefront code", () => {
    const chips = appWindow.sfChips(["us"]);
    expect(chips.children[0].textContent).toBe("US");
  });

  test("chip className includes sf-chip and storefront code", () => {
    const chips = appWindow.sfChips(["jp"]);
    expect(chips.children[0].className).toContain("sf-chip");
    expect(chips.children[0].className).toContain("jp");
  });

  test("handles empty array — no chips", () => {
    expect(appWindow.sfChips([]).children.length).toBe(0);
  });

  test("handles null — no chips", () => {
    expect(appWindow.sfChips(null).children.length).toBe(0);
  });

  test("handles undefined — no chips", () => {
    expect(appWindow.sfChips(undefined).children.length).toBe(0);
  });

  test("preserves order of storefronts", () => {
    const chips = appWindow.sfChips(["us", "jp", "hk"]);
    expect(chips.children[0].textContent).toBe("US");
    expect(chips.children[1].textContent).toBe("JP");
    expect(chips.children[2].textContent).toBe("HK");
  });
});

// ---------------------------------------------------------------------------
// skeletonGrid
// ---------------------------------------------------------------------------

describe("skeletonGrid", () => {
  test("returns div with class loading-grid", () => {
    expect(appWindow.skeletonGrid().className).toBe("loading-grid");
  });

  test("creates 12 skeleton cards by default", () => {
    expect(appWindow.skeletonGrid().children.length).toBe(12);
  });

  test("creates the specified number of cards", () => {
    expect(appWindow.skeletonGrid(6).children.length).toBe(6);
  });

  test("creates zero cards when n=0", () => {
    expect(appWindow.skeletonGrid(0).children.length).toBe(0);
  });

  test("each card has class skeleton-card", () => {
    const grid = appWindow.skeletonGrid(3);
    for (const card of grid.children) {
      expect(card.className).toBe("skeleton-card");
    }
  });

  test("each card contains skeleton-art child element", () => {
    const grid = appWindow.skeletonGrid(1);
    expect(grid.children[0].innerHTML).toContain("skeleton-art");
  });

  test("creates 1 card when n=1", () => {
    expect(appWindow.skeletonGrid(1).children.length).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// formatBadges
// ---------------------------------------------------------------------------

describe("formatBadges", () => {
  test("returns null for null", () => {
    expect(appWindow.formatBadges(null)).toBeNull();
  });

  test("returns null for undefined", () => {
    expect(appWindow.formatBadges(undefined)).toBeNull();
  });

  test("returns null for empty array", () => {
    expect(appWindow.formatBadges([])).toBeNull();
  });

  test("returns null when all formats are unknown", () => {
    expect(appWindow.formatBadges(["totally-unknown"])).toBeNull();
  });

  test("returns a div element for known format", () => {
    const result = appWindow.formatBadges(["lossless"]);
    expect(result).not.toBeNull();
    expect(result.tagName).toBe("DIV");
  });

  test("creates one badge per known format", () => {
    const result = appWindow.formatBadges(["lossless", "atmos"]);
    expect(result.children.length).toBe(2);
  });

  test("lossless badge text is 'Lossless'", () => {
    expect(appWindow.formatBadges(["lossless"]).children[0].textContent).toBe("Lossless");
  });

  test("lossy-stereo badge text is 'AAC'", () => {
    expect(appWindow.formatBadges(["lossy-stereo"]).children[0].textContent).toBe("AAC");
  });

  test("hi-res-lossless badge text is 'Hi-Res Lossless'", () => {
    expect(appWindow.formatBadges(["hi-res-lossless"]).children[0].textContent).toBe("Hi-Res Lossless");
  });

  test("atmos badge text is 'Dolby Atmos'", () => {
    expect(appWindow.formatBadges(["atmos"]).children[0].textContent).toBe("Dolby Atmos");
  });

  test("spatial badge text is 'Spatial Audio'", () => {
    expect(appWindow.formatBadges(["spatial"]).children[0].textContent).toBe("Spatial Audio");
  });

  test("adm badge text is 'Apple Digital Masters'", () => {
    expect(appWindow.formatBadges(["adm"]).children[0].textContent).toBe("Apple Digital Masters");
  });

  test("badge has class containing the format key", () => {
    const result = appWindow.formatBadges(["atmos"]);
    expect(result.children[0].className).toContain("atmos");
  });

  test("badge has class format-badge", () => {
    const result = appWindow.formatBadges(["lossless"]);
    expect(result.children[0].className).toContain("format-badge");
  });

  test("skips unknown formats but renders known ones in the same array", () => {
    const result = appWindow.formatBadges(["unknown", "lossless"]);
    expect(result).not.toBeNull();
    expect(result.children.length).toBe(1);
    expect(result.children[0].textContent).toBe("Lossless");
  });

  test("wrap div has class format-badges", () => {
    const result = appWindow.formatBadges(["lossless"]);
    expect(result.className).toBe("format-badges");
  });
});

// ---------------------------------------------------------------------------
// placeholderEl
// ---------------------------------------------------------------------------

describe("placeholderEl", () => {
  test("returns a div", () => {
    expect(appWindow.placeholderEl("album-artwork").tagName).toBe("DIV");
  });

  test("album-artwork class gives album-artwork-placeholder", () => {
    expect(appWindow.placeholderEl("album-artwork").className).toBe("album-artwork-placeholder");
  });

  test("modal-artwork class gives modal-artwork-placeholder", () => {
    expect(appWindow.placeholderEl("modal-artwork").className).toBe("modal-artwork-placeholder");
  });

  test("modal-artwork-thumb class gives modal-artwork-thumb-placeholder", () => {
    expect(appWindow.placeholderEl("modal-artwork-thumb").className).toBe("modal-artwork-thumb-placeholder");
  });

  test("any other class gives album-artwork-placeholder", () => {
    expect(appWindow.placeholderEl("something-else").className).toBe("album-artwork-placeholder");
  });

  test("text content is musical note", () => {
    expect(appWindow.placeholderEl("album-artwork").textContent).toBe("♫");
  });
});

// ---------------------------------------------------------------------------
// showImageLightbox
// ---------------------------------------------------------------------------

describe("showImageLightbox", () => {
  afterEach(() => {
    // Clean up any lightbox appended to body
    const boxes = appWindow.document.querySelectorAll(".image-lightbox");
    boxes.forEach(b => b.remove());
  });

  test("appends an .image-lightbox div to body", () => {
    appWindow.showImageLightbox("https://example.com/art.jpg");
    expect(appWindow.document.querySelector(".image-lightbox")).not.toBeNull();
  });

  test("lightbox contains an img with the given src", () => {
    appWindow.showImageLightbox("https://example.com/art.jpg");
    const img = appWindow.document.querySelector(".image-lightbox img");
    expect(img).not.toBeNull();
    expect(img.src).toContain("art.jpg");
  });

  test("clicking the lightbox removes it from the DOM", () => {
    appWindow.showImageLightbox("https://example.com/art.jpg");
    const box = appWindow.document.querySelector(".image-lightbox");
    box.click();
    expect(appWindow.document.querySelector(".image-lightbox")).toBeNull();
  });

  test("creates a new lightbox each call", () => {
    appWindow.showImageLightbox("https://example.com/a.jpg");
    appWindow.showImageLightbox("https://example.com/b.jpg");
    expect(appWindow.document.querySelectorAll(".image-lightbox").length).toBe(2);
  });
});

// ---------------------------------------------------------------------------
// FORMAT_LABELS constant
// ---------------------------------------------------------------------------

describe("FORMAT_LABELS", () => {
  test("lossy-stereo maps to AAC", () => {
    expect(appWindow.__test_FORMAT_LABELS["lossy-stereo"]).toBe("AAC");
  });

  test("lossless maps to Lossless", () => {
    expect(appWindow.__test_FORMAT_LABELS["lossless"]).toBe("Lossless");
  });

  test("hi-res-lossless maps to Hi-Res Lossless", () => {
    expect(appWindow.__test_FORMAT_LABELS["hi-res-lossless"]).toBe("Hi-Res Lossless");
  });

  test("atmos maps to Dolby Atmos", () => {
    expect(appWindow.__test_FORMAT_LABELS["atmos"]).toBe("Dolby Atmos");
  });

  test("spatial maps to Spatial Audio", () => {
    expect(appWindow.__test_FORMAT_LABELS["spatial"]).toBe("Spatial Audio");
  });

  test("adm maps to Apple Digital Masters", () => {
    expect(appWindow.__test_FORMAT_LABELS["adm"]).toBe("Apple Digital Masters");
  });
});

// ---------------------------------------------------------------------------
// RELEASE_TYPE_LABELS constant
// ---------------------------------------------------------------------------

describe("RELEASE_TYPE_LABELS", () => {
  test("main-albums → Albums", () => {
    expect(appWindow.__test_RELEASE_TYPE_LABELS["main-albums"]).toBe("Albums");
  });

  test("compilation-albums → Compilations", () => {
    expect(appWindow.__test_RELEASE_TYPE_LABELS["compilation-albums"]).toBe("Compilations");
  });

  test("live-albums → Live Albums", () => {
    expect(appWindow.__test_RELEASE_TYPE_LABELS["live-albums"]).toBe("Live Albums");
  });

  test("singles-eps → Singles & EPs", () => {
    expect(appWindow.__test_RELEASE_TYPE_LABELS["singles-eps"]).toBe("Singles & EPs");
  });
});

// ---------------------------------------------------------------------------
// RELEASE_TYPE_ORDER
// ---------------------------------------------------------------------------

describe("RELEASE_TYPE_ORDER", () => {
  test("is an Array", () => {
    expect(Array.isArray(appWindow.__test_RELEASE_TYPE_ORDER)).toBe(true);
  });

  test("has four entries", () => {
    expect(appWindow.__test_RELEASE_TYPE_ORDER.length).toBe(4);
  });

  test("main-albums is first", () => {
    expect(appWindow.__test_RELEASE_TYPE_ORDER[0]).toBe("main-albums");
  });

  test("contains singles-eps", () => {
    expect(appWindow.__test_RELEASE_TYPE_ORDER).toContain("singles-eps");
  });

  test("contains compilation-albums", () => {
    expect(appWindow.__test_RELEASE_TYPE_ORDER).toContain("compilation-albums");
  });

  test("contains live-albums", () => {
    expect(appWindow.__test_RELEASE_TYPE_ORDER).toContain("live-albums");
  });

  test("main-albums comes before singles-eps", () => {
    const order = appWindow.__test_RELEASE_TYPE_ORDER;
    expect(order.indexOf("main-albums")).toBeLessThan(order.indexOf("singles-eps"));
  });
});

// ---------------------------------------------------------------------------
// API helper (fetch integration)
// ---------------------------------------------------------------------------

describe("API helper", () => {
  test("API.get calls fetch with the path", async () => {
    appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ items: [] }),
    });
    const result = await appWindow.__test_API.get("/api/releases");
    expect(appWindow.fetch).toHaveBeenCalledWith("/api/releases");
    expect(result).toEqual({ items: [] });
  });

  test("API.get throws on non-ok response", async () => {
    appWindow.fetch.mockResolvedValueOnce({ ok: false, status: 404 });
    await expect(appWindow.__test_API.get("/api/missing")).rejects.toThrow("HTTP 404");
  });

  test("API.post sends POST with JSON body and Content-Type header", async () => {
    appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    const body = { artist_id: "ART1", name: "Test Artist" };
    await appWindow.__test_API.post("/api/watchlist", body);
    const [url, opts] = appWindow.fetch.mock.calls[0];
    expect(url).toBe("/api/watchlist");
    expect(opts.method).toBe("POST");
    expect(JSON.parse(opts.body)).toEqual(body);
    expect(opts.headers["Content-Type"]).toBe("application/json");
  });

  test("API.put sends PUT method with JSON body", async () => {
    appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    await appWindow.__test_API.put("/api/config", { newrelease_poll_interval_days: 1 });
    const [, opts] = appWindow.fetch.mock.calls[0];
    expect(opts.method).toBe("PUT");
  });

  test("API.del sends DELETE method", async () => {
    appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    await appWindow.__test_API.del("/api/watchlist/ART1");
    const [url, opts] = appWindow.fetch.mock.calls[0];
    expect(url).toBe("/api/watchlist/ART1");
    expect(opts.method).toBe("DELETE");
  });

  test("API.post returns parsed JSON", async () => {
    appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    const result = await appWindow.__test_API.post("/api/refresh", {});
    expect(result.ok).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// state object initial values
// ---------------------------------------------------------------------------

describe("state initial values", () => {
  test("watchedIds is a Set", () => {
    expect(appWindow.__test_state.watchedIds).toBeInstanceOf(appWindow.Set);
  });

  test("currentPage is 1", () => {
    expect(appWindow.__test_state.currentPage).toBe(1);
  });

  test("currentTotal is 0", () => {
    expect(appWindow.__test_state.currentTotal).toBe(0);
  });

  test("currentQuery is empty string", () => {
    expect(appWindow.__test_state.currentQuery).toBe("");
  });

  test("currentStorefront is empty string", () => {
    expect(appWindow.__test_state.currentStorefront).toBe("");
  });

  test("perPage is a positive number", () => {
    expect(appWindow.__test_state.perPage).toBeGreaterThan(0);
  });

  test("artistViewMode is 'chrono'", () => {
    expect(appWindow.__test_state.artistViewMode).toBe("chrono");
  });

  test("artistTypeFilter is empty string", () => {
    expect(appWindow.__test_state.artistTypeFilter).toBe("");
  });

  test("configuredStorefronts starts null", () => {
    expect(appWindow.__test_state.configuredStorefronts).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// API.patch
// ---------------------------------------------------------------------------

describe("API.patch", () => {
  test("sends PATCH method", async () => {
    appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    await appWindow.__test_API.patch("/api/watchlist/ART1", { preferred_source: "jp" });
    const [, opts] = appWindow.fetch.mock.calls[0];
    expect(opts.method).toBe("PATCH");
  });

  test("sends the correct URL", async () => {
    appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    await appWindow.__test_API.patch("/api/watchlist/ART1", { preferred_source: "jp" });
    const [url] = appWindow.fetch.mock.calls[0];
    expect(url).toBe("/api/watchlist/ART1");
  });

  test("sends Content-Type: application/json", async () => {
    appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    await appWindow.__test_API.patch("/api/watchlist/ART1", { preferred_source: "jp" });
    const [, opts] = appWindow.fetch.mock.calls[0];
    expect(opts.headers["Content-Type"]).toBe("application/json");
  });

  test("serialises body as JSON", async () => {
    appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    const body = { preferred_source: "us" };
    await appWindow.__test_API.patch("/api/watchlist/ART1", body);
    const [, opts] = appWindow.fetch.mock.calls[0];
    expect(JSON.parse(opts.body)).toEqual(body);
  });

  test("serialises null preferred_source correctly", async () => {
    appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    await appWindow.__test_API.patch("/api/watchlist/ART1", { preferred_source: null });
    const [, opts] = appWindow.fetch.mock.calls[0];
    expect(JSON.parse(opts.body)).toEqual({ preferred_source: null });
  });

  test("returns parsed JSON response", async () => {
    appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    const result = await appWindow.__test_API.patch("/api/watchlist/ART1", {});
    expect(result.ok).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// tracklistsDiffer
// ---------------------------------------------------------------------------

describe("tracklistsDiffer", () => {
  test("returns false for identical single-track lists", () => {
    const t = [{ title: "Song A" }];
    expect(appWindow.tracklistsDiffer(t, t)).toBe(false);
  });

  test("returns false for two equal lists", () => {
    const a = [{ title: "Song A" }, { title: "Song B" }];
    const b = [{ title: "Song A" }, { title: "Song B" }];
    expect(appWindow.tracklistsDiffer(a, b)).toBe(false);
  });

  test("returns true when lengths differ", () => {
    const a = [{ title: "Song A" }, { title: "Song B" }];
    const b = [{ title: "Song A" }];
    expect(appWindow.tracklistsDiffer(a, b)).toBe(true);
  });

  test("returns true when a track title differs", () => {
    const a = [{ title: "Song A" }, { title: "Song B" }];
    const b = [{ title: "Song A" }, { title: "Song C" }];
    expect(appWindow.tracklistsDiffer(a, b)).toBe(true);
  });

  test("returns true when first track title differs", () => {
    const a = [{ title: "Different" }];
    const b = [{ title: "Original" }];
    expect(appWindow.tracklistsDiffer(a, b)).toBe(true);
  });

  test("returns false for two empty lists", () => {
    expect(appWindow.tracklistsDiffer([], [])).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// debounce
// ---------------------------------------------------------------------------

describe("debounce", () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  test("does not call fn immediately", () => {
    const fn = jest.fn();
    const debounced = appWindow.debounce(fn, 200);
    debounced();
    expect(fn).not.toHaveBeenCalled();
  });

  test("calls fn after the delay", () => {
    const fn = jest.fn();
    const debounced = appWindow.debounce(fn, 200);
    debounced();
    jest.advanceTimersByTime(200);
    expect(fn).toHaveBeenCalledTimes(1);
  });

  test("calls fn only once for multiple rapid calls", () => {
    const fn = jest.fn();
    const debounced = appWindow.debounce(fn, 200);
    debounced(); debounced(); debounced();
    jest.advanceTimersByTime(200);
    expect(fn).toHaveBeenCalledTimes(1);
  });

  test("resets the timer on each call", () => {
    const fn = jest.fn();
    const debounced = appWindow.debounce(fn, 200);
    debounced();
    jest.advanceTimersByTime(100);
    debounced();
    jest.advanceTimersByTime(100);
    expect(fn).not.toHaveBeenCalled();
    jest.advanceTimersByTime(100);
    expect(fn).toHaveBeenCalledTimes(1);
  });

  test("passes arguments to the wrapped function", () => {
    const fn = jest.fn();
    const debounced = appWindow.debounce(fn, 100);
    debounced("hello", 42);
    jest.advanceTimersByTime(100);
    expect(fn).toHaveBeenCalledWith("hello", 42);
  });
});

// ---------------------------------------------------------------------------
// makeArtistLinks
// ---------------------------------------------------------------------------

describe("makeArtistLinks", () => {
  const makeArtistLinks = (...args) => appWindow.makeArtistLinks(...args);

  test("falls back to single artist text when artists_json is absent", () => {
    const album = { artist: "Test Artist", artist_id: "A1", artists_json: null };
    const el = makeArtistLinks(album, "album-artist");
    expect(el.className).toBe("album-artist");
    expect(el.textContent).toBe("Test Artist");
  });

  test("falls back to dash when artist is absent and no artists_json", () => {
    const album = { artist: null, artist_id: null, artists_json: null };
    const el = makeArtistLinks(album, "album-artist");
    expect(el.textContent).toBe("—");
  });

  test("renders single artist-link span for single-artist artists_json", () => {
    const album = {
      artist: "Jay Chou",
      artist_id: "300117743",
      artists_json: [{ id: "300117743", name: "Jay Chou", url: "https://music.apple.com/tw/artist/1" }],
    };
    const wrap = makeArtistLinks(album, "album-artist");
    const links = wrap.querySelectorAll(".artist-link");
    expect(links.length).toBe(1);
    expect(links[0].textContent).toBe("Jay Chou");
  });

  test("renders multiple artist-link spans for multi-artist albums", () => {
    const album = {
      artist: "Artist A & Artist B",
      artist_id: "A1",
      artists_json: [
        { id: "A1", name: "Artist A", url: null },
        { id: "A2", name: "Artist B", url: null },
      ],
    };
    const wrap = makeArtistLinks(album, "album-artist");
    const links = wrap.querySelectorAll(".artist-link");
    expect(links.length).toBe(2);
    expect(links[0].textContent).toBe("Artist A");
    expect(links[1].textContent).toBe("Artist B");
  });

  test("separates multiple artists with commas", () => {
    const album = {
      artist: "A & B",
      artist_id: "A1",
      artists_json: [
        { id: "A1", name: "A", url: null },
        { id: "A2", name: "B", url: null },
      ],
    };
    const wrap = makeArtistLinks(album, "album-artist");
    expect(wrap.textContent).toContain(", ");
  });

  test("sets title to combined artist string when using artists_json", () => {
    const album = {
      artist: "A & B",
      artist_id: "A1",
      artists_json: [
        { id: "A1", name: "A", url: null },
        { id: "A2", name: "B", url: null },
      ],
    };
    const wrap = makeArtistLinks(album, "album-artist");
    expect(wrap.title).toBe("A & B");
  });

  test("calls onNav callback when artist-link is clicked in multi-artist mode", () => {
    const album = {
      artist: "A & B",
      artist_id: "A1",
      artists_json: [
        { id: "A1", name: "A", url: null },
        { id: "A2", name: "B", url: null },
      ],
    };
    let called = false;
    const wrap = makeArtistLinks(album, "album-artist", () => { called = true; });
    wrap.querySelectorAll(".artist-link")[0].click();
    expect(called).toBe(true);
  });

  test("sets state.artistHint with full artist data when artist-link is clicked", () => {
    const album = {
      artist: "A & B",
      artist_id: "A1",
      artists_json: [
        { id: "A1", name: "Artist A", url: "https://music.apple.com/tw/artist/1", artwork_url: "https://example.com/a.jpg", genre: "Pop" },
        { id: "A2", name: "Artist B", url: "https://music.apple.com/tw/artist/2", artwork_url: "https://example.com/b.jpg", genre: "Rock" },
      ],
    };
    const wrap = makeArtistLinks(album, "album-artist");
    wrap.querySelectorAll(".artist-link")[1].click();
    const hint = appWindow.__test_state.artistHint;
    expect(hint.id).toBe("A2");
    expect(hint.name).toBe("Artist B");
    expect(hint.artwork_url).toBe("https://example.com/b.jpg");
    expect(hint.genre).toBe("Rock");
  });
});

// ---------------------------------------------------------------------------
// artistHint id type coercion (regression: Watch button from watchlist search)
// ---------------------------------------------------------------------------

describe("artistHint id type coercion", () => {
  // The artist id from the URL hash is always a string (e.g. "#/artist/300117743").
  // Search results return numeric ids. Storing the hint id as String() ensures
  // the strict equality check in renderArtist matches.

  test("String(numericId) matches string artistId from URL", () => {
    const numericId = 300117743;
    const hintId = String(numericId);
    const artistIdFromUrl = "300117743";
    expect(hintId === artistIdFromUrl).toBe(true);
  });

  test("numeric id does not match string artistId from URL (pre-fix behaviour)", () => {
    const numericId = 300117743;
    const artistIdFromUrl = "300117743";
    expect(numericId === artistIdFromUrl).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// innerHTML += vs insertAdjacentHTML (regression: buttons lose listeners)
// ---------------------------------------------------------------------------

describe("insertAdjacentHTML preserves existing event listeners", () => {
  // Regression: renderArtist used `wrap.innerHTML +=` to append the empty-state
  // for artists with no releases. `innerHTML +=` re-serialises the whole subtree
  // and replaces all nodes, destroying any click listeners that were already
  // attached to Watch / Fetch buttons in the same container.

  test("innerHTML += destroys existing event listeners", () => {
    const doc = appWindow.document;
    const div = doc.createElement("div");
    const btn = doc.createElement("button");
    let clicked = false;
    btn.addEventListener("click", () => { clicked = true; });
    div.appendChild(btn);

    // Simulate the buggy pattern
    div.innerHTML += "<span>appended</span>";

    // The button node was replaced — listener is gone
    div.querySelector("button").click();
    expect(clicked).toBe(false);
  });

  test("insertAdjacentHTML preserves existing event listeners", () => {
    const doc = appWindow.document;
    const div = doc.createElement("div");
    const btn = doc.createElement("button");
    let clicked = false;
    btn.addEventListener("click", () => { clicked = true; });
    div.appendChild(btn);

    // The fixed pattern
    div.insertAdjacentHTML("beforeend", "<span>appended</span>");

    // The button node is untouched — listener still works
    div.querySelector("button").click();
    expect(clicked).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// refreshStatus — room error warning
// ---------------------------------------------------------------------------

describe("refreshStatus room errors", () => {
  beforeEach(() => {
    appWindow.document.getElementById("status-room-errors")?.remove();
  });

  test("shows warning element when room_errors is non-empty", async () => {
    appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        is_running: false,
        last_run: null,
        room_errors: ["hk", "jp"],
      }),
    });
    await appWindow.__test_refreshStatus();
    const warn = appWindow.document.getElementById("status-room-errors");
    expect(warn).not.toBeNull();
    expect(warn.textContent).toContain("HK");
    expect(warn.textContent).toContain("JP");
    // warning element should be placed after status-card, not inside it
    const card = appWindow.document.getElementById("status-card");
    expect(warn.parentElement).toBe(card.parentElement);
    // status dot should have warn class
    const dot = appWindow.document.getElementById("status-dot");
    expect(dot.className).toContain("warn");
  });

  test("removes warning element when room_errors is empty", async () => {
    // First call creates the warning
    appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ is_running: false, last_run: null, room_errors: ["hk"] }),
    });
    await appWindow.__test_refreshStatus();
    expect(appWindow.document.getElementById("status-room-errors")).not.toBeNull();

    // Second call clears it
    appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ is_running: false, last_run: null, room_errors: [] }),
    });
    await appWindow.__test_refreshStatus();
    expect(appWindow.document.getElementById("status-room-errors")).toBeNull();
  });

  test("no warning element when room_errors absent", async () => {
    appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ is_running: false, last_run: null }),
    });
    await appWindow.__test_refreshStatus();
    expect(appWindow.document.getElementById("status-room-errors")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// renderSettings — all config fields are rendered and saved
// ---------------------------------------------------------------------------

describe("renderSettings", () => {
  const fullCfg = {
    check_storefronts: ["jp", "hk"],
    home_storefront: "hk",
    newrelease_poll_interval_days: 2,
    watchlist_poll_interval_minutes: 15,
    watchlist_poll_batch_size: 3,
    watchlist_refresh_interval_days: 14,
    cors_proxy: "https://proxy.example.com/",
  };

  let main;

  beforeEach(() => {
    main = appWindow.document.createElement("div");
    appWindow.document.body.appendChild(main);
    appWindow.fetch.mockClear();
  });

  afterEach(() => {
    main.remove();
  });

  function mockConfigFetch(cfg) {
    appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(cfg),
    });
  }

  test("renders input for check_storefronts", async () => {
    mockConfigFetch(fullCfg);
    await appWindow.__test_renderSettings(main);
    const inputs = main.querySelectorAll("input[type='text']");
    const values = Array.from(inputs).map(i => i.value);
    expect(values.some(v => v.includes("jp"))).toBe(true);
  });

  test("renders input for home_storefront", async () => {
    mockConfigFetch(fullCfg);
    await appWindow.__test_renderSettings(main);
    const inputs = main.querySelectorAll("input[type='text']");
    const values = Array.from(inputs).map(i => i.value);
    expect(values).toContain("hk");
  });

  test("renders input for newrelease_poll_interval_days", async () => {
    mockConfigFetch(fullCfg);
    await appWindow.__test_renderSettings(main);
    const inputs = main.querySelectorAll("input[type='number']");
    const values = Array.from(inputs).map(i => Number(i.value));
    expect(values).toContain(2);
  });

  test("renders input for watchlist_poll_interval_minutes", async () => {
    mockConfigFetch(fullCfg);
    await appWindow.__test_renderSettings(main);
    const inputs = main.querySelectorAll("input[type='number']");
    const values = Array.from(inputs).map(i => Number(i.value));
    expect(values).toContain(15);
  });

  test("renders input for watchlist_poll_batch_size", async () => {
    mockConfigFetch(fullCfg);
    await appWindow.__test_renderSettings(main);
    const inputs = main.querySelectorAll("input[type='number']");
    const values = Array.from(inputs).map(i => Number(i.value));
    expect(values).toContain(3);
  });

  test("renders input for watchlist_refresh_interval_days", async () => {
    mockConfigFetch(fullCfg);
    await appWindow.__test_renderSettings(main);
    const inputs = main.querySelectorAll("input[type='number']");
    const values = Array.from(inputs).map(i => Number(i.value));
    expect(values).toContain(14);
  });

  test("renders input for cors_proxy", async () => {
    mockConfigFetch(fullCfg);
    await appWindow.__test_renderSettings(main);
    const inputs = main.querySelectorAll("input[type='text']");
    const values = Array.from(inputs).map(i => i.value);
    expect(values).toContain("https://proxy.example.com/");
  });

  test("save sends all config fields including watchlist and cors_proxy", async () => {
    mockConfigFetch(fullCfg);
    await appWindow.__test_renderSettings(main);

    appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });

    const saveBtn = Array.from(main.querySelectorAll("button")).find(b =>
      b.textContent.includes("Save")
    );
    saveBtn.click();
    await new Promise(r => setTimeout(r, 50));

    const putCall = appWindow.fetch.mock.calls.find(
      ([url, opts]) => url === "/api/config" && opts && opts.method === "PUT"
    );
    expect(putCall).toBeDefined();
    const body = JSON.parse(putCall[1].body);
    expect(body).toHaveProperty("watchlist_poll_interval_minutes", 15);
    expect(body).toHaveProperty("watchlist_poll_batch_size", 3);
    expect(body).toHaveProperty("watchlist_refresh_interval_days", 14);
    expect(body).toHaveProperty("cors_proxy", "https://proxy.example.com/");
  });

  test("cors_proxy is empty string when blank", async () => {
    mockConfigFetch({ ...fullCfg, cors_proxy: "" });
    await appWindow.__test_renderSettings(main);

    appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });

    const saveBtn = Array.from(main.querySelectorAll("button")).find(b =>
      b.textContent.includes("Save")
    );
    saveBtn.click();
    await new Promise(r => setTimeout(r, 50));

    const putCall = appWindow.fetch.mock.calls.find(
      ([url, opts]) => url === "/api/config" && opts && opts.method === "PUT"
    );
    const body = JSON.parse(putCall[1].body);
    expect(body.cors_proxy).toBe("");
  });
});

// ---------------------------------------------------------------------------
// Collection Status constants
// ---------------------------------------------------------------------------

describe("COLLECTION_STATUS_LABELS", () => {
  test("has all four statuses", () => {
    const labels = appWindow.__test_COLLECTION_STATUS_LABELS;
    expect(labels).toBeDefined();
    expect(labels.new).toBe("New");
    expect(labels.complete).toBe("Complete");
    expect(labels.new_release).toBe("New Release");
    expect(labels.in_progress).toBe("In Progress");
  });

  test("has exactly four entries", () => {
    const labels = appWindow.__test_COLLECTION_STATUS_LABELS;
    expect(Object.keys(labels)).toHaveLength(4);
  });
});

describe("COLLECTION_TRANSITIONS", () => {
  test("new can transition to complete and in_progress", () => {
    const t = appWindow.__test_COLLECTION_TRANSITIONS;
    expect(t.new).toEqual(expect.arrayContaining(["complete", "in_progress"]));
    expect(t.new).toHaveLength(2);
  });

  test("complete can transition to in_progress", () => {
    const t = appWindow.__test_COLLECTION_TRANSITIONS;
    expect(t.complete).toEqual(["in_progress"]);
  });

  test("new_release can transition to complete and in_progress", () => {
    const t = appWindow.__test_COLLECTION_TRANSITIONS;
    expect(t.new_release).toEqual(expect.arrayContaining(["complete", "in_progress"]));
    expect(t.new_release).toHaveLength(2);
  });

  test("in_progress can only transition to complete", () => {
    const t = appWindow.__test_COLLECTION_TRANSITIONS;
    expect(t.in_progress).toEqual(["complete"]);
  });
});
