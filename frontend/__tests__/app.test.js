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
  <div id="status-dot"></div>
  <div id="status-last-run"></div>
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

  test("any other class gives album-artwork-placeholder", () => {
    expect(appWindow.placeholderEl("something-else").className).toBe("album-artwork-placeholder");
  });

  test("text content is musical note", () => {
    expect(appWindow.placeholderEl("album-artwork").textContent).toBe("♫");
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
    await appWindow.__test_API.put("/api/config", { poll_interval_minutes: 30 });
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
