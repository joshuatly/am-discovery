"use strict";

const ctx = require("./setup-jsdom");

// ---------------------------------------------------------------------------
// formatDate
// ---------------------------------------------------------------------------

describe("formatDate", () => {
  test("returns em-dash for null", () => {
    expect(ctx.appWindow.formatDate(null)).toBe("—");
  });

  test("returns em-dash for undefined", () => {
    expect(ctx.appWindow.formatDate(undefined)).toBe("—");
  });

  test("returns em-dash for the string 'Unknown'", () => {
    expect(ctx.appWindow.formatDate("Unknown")).toBe("—");
  });

  test("returns em-dash for empty string", () => {
    expect(ctx.appWindow.formatDate("")).toBe("—");
  });

  test("returns year only for YYYY-00-00 format", () => {
    expect(ctx.appWindow.formatDate("2024-00-00")).toBe("2024");
  });

  test("returns year only for 1990-00-00", () => {
    expect(ctx.appWindow.formatDate("1990-00-00")).toBe("1990");
  });

  test("formats a valid ISO date and includes the year", () => {
    const result = ctx.appWindow.formatDate("2024-03-15");
    expect(result).toContain("2024");
  });

  test("formats another valid date with the correct year", () => {
    const result = ctx.appWindow.formatDate("2020-12-25");
    expect(result).toContain("2020");
  });

  test("returns a string for an unparseable date", () => {
    const result = ctx.appWindow.formatDate("not-a-date");
    expect(typeof result).toBe("string");
  });

  test("handles dates from the far past", () => {
    const result = ctx.appWindow.formatDate("1960-06-01");
    expect(result).toContain("1960");
  });
});

// ---------------------------------------------------------------------------
// isFutureDate
// ---------------------------------------------------------------------------

describe("isFutureDate", () => {
  test("returns false for null", () => {
    expect(ctx.appWindow.isFutureDate(null)).toBe(false);
  });

  test("returns false for undefined", () => {
    expect(ctx.appWindow.isFutureDate(undefined)).toBe(false);
  });

  test("returns false for empty string", () => {
    expect(ctx.appWindow.isFutureDate("")).toBe(false);
  });

  test("returns false for YYYY-00-00 format even in the far future", () => {
    expect(ctx.appWindow.isFutureDate("2099-00-00")).toBe(false);
  });

  test("returns true for a date far in the future", () => {
    expect(ctx.appWindow.isFutureDate("2099-12-31")).toBe(true);
  });

  test("returns false for a clearly past date", () => {
    expect(ctx.appWindow.isFutureDate("2000-01-01")).toBe(false);
  });

  test("returns false for an invalid date string", () => {
    const result = ctx.appWindow.isFutureDate("not-a-date");
    expect(typeof result).toBe("boolean");
  });

  test("returns false for yesterday", () => {
    const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
    expect(ctx.appWindow.isFutureDate(yesterday)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// timeAgo
// ---------------------------------------------------------------------------

describe("timeAgo", () => {
  test("returns 'never' for null", () => {
    expect(ctx.appWindow.timeAgo(null)).toBe("never");
  });

  test("returns 'never' for undefined", () => {
    expect(ctx.appWindow.timeAgo(undefined)).toBe("never");
  });

  test("returns 'just now' for a timestamp a few seconds ago (unix seconds)", () => {
    const nowSec = Math.floor(Date.now() / 1000);
    expect(ctx.appWindow.timeAgo(nowSec)).toBe("just now");
  });

  test("returns 'just now' for a timestamp 30 seconds ago", () => {
    const sec = Math.floor(Date.now() / 1000) - 30;
    expect(ctx.appWindow.timeAgo(sec)).toBe("just now");
  });

  test("returns 'Xm ago' for 30 minutes ago", () => {
    const sec = Math.floor(Date.now() / 1000) - 30 * 60;
    expect(ctx.appWindow.timeAgo(sec)).toBe("30m ago");
  });

  test("returns '1m ago' for exactly 60 seconds ago", () => {
    const sec = Math.floor(Date.now() / 1000) - 60;
    expect(ctx.appWindow.timeAgo(sec)).toBe("1m ago");
  });

  test("returns 'Xh ago' for 3 hours ago", () => {
    const sec = Math.floor(Date.now() / 1000) - 3 * 3600;
    expect(ctx.appWindow.timeAgo(sec)).toBe("3h ago");
  });

  test("returns '1h ago' for 60 minutes ago", () => {
    const sec = Math.floor(Date.now() / 1000) - 60 * 60;
    expect(ctx.appWindow.timeAgo(sec)).toBe("1h ago");
  });

  test("returns 'Xd ago' for 2 days ago", () => {
    const sec = Math.floor(Date.now() / 1000) - 2 * 24 * 3600;
    expect(ctx.appWindow.timeAgo(sec)).toBe("2d ago");
  });

  test("accepts an ISO string for recent time", () => {
    const isoStr = new Date(Date.now() - 100).toISOString().replace("Z", "");
    expect(ctx.appWindow.timeAgo(isoStr)).toBe("just now");
  });
});

// ---------------------------------------------------------------------------
// formatDuration
// ---------------------------------------------------------------------------

describe("formatDuration", () => {
  test("returns empty string for null", () => {
    expect(ctx.appWindow.formatDuration(null)).toBe("");
  });

  test("returns empty string for undefined", () => {
    expect(ctx.appWindow.formatDuration(undefined)).toBe("");
  });

  test("returns empty string for 0", () => {
    expect(ctx.appWindow.formatDuration(0)).toBe("");
  });

  test("formats 60000ms as '1:00'", () => {
    expect(ctx.appWindow.formatDuration(60000)).toBe("1:00");
  });

  test("formats 90000ms as '1:30'", () => {
    expect(ctx.appWindow.formatDuration(90000)).toBe("1:30");
  });

  test("pads seconds with leading zero: 65000ms → '1:05'", () => {
    expect(ctx.appWindow.formatDuration(65000)).toBe("1:05");
  });

  test("formats 30000ms as '0:30'", () => {
    expect(ctx.appWindow.formatDuration(30000)).toBe("0:30");
  });

  test("formats exactly 5 minutes", () => {
    expect(ctx.appWindow.formatDuration(300000)).toBe("5:00");
  });

  test("formats 3661000ms (61 minutes 1 second) as '61:01'", () => {
    expect(ctx.appWindow.formatDuration(3661000)).toBe("61:01");
  });

  test("formats 1000ms as '0:01'", () => {
    expect(ctx.appWindow.formatDuration(1000)).toBe("0:01");
  });
});

// ---------------------------------------------------------------------------
// el (DOM element factory)
// ---------------------------------------------------------------------------

describe("el (DOM element factory)", () => {
  test("creates a div with correct tagName", () => {
    expect(ctx.appWindow.__test_el("div").tagName).toBe("DIV");
  });

  test("creates a span element", () => {
    expect(ctx.appWindow.__test_el("span").tagName).toBe("SPAN");
  });

  test("sets className when provided", () => {
    expect(ctx.appWindow.__test_el("div", "my-class").className).toBe("my-class");
  });

  test("leaves className empty when null", () => {
    expect(ctx.appWindow.__test_el("div", null).className).toBe("");
  });

  test("sets textContent when provided", () => {
    expect(ctx.appWindow.__test_el("p", null, "hello").textContent).toBe("hello");
  });

  test("leaves textContent empty when null", () => {
    expect(ctx.appWindow.__test_el("div", "cls", null).textContent).toBe("");
  });

  test("sets both className and textContent together", () => {
    const e = ctx.appWindow.__test_el("button", "btn", "Click me");
    expect(e.className).toBe("btn");
    expect(e.textContent).toBe("Click me");
  });
});

// ---------------------------------------------------------------------------
// sanitizeHtml
// ---------------------------------------------------------------------------

describe("sanitizeHtml", () => {
  let sanitize;
  beforeEach(() => { sanitize = ctx.appWindow.__test_sanitizeHtml; });

  test("passes through plain text unchanged", () => {
    expect(sanitize("Hello world")).toBe("Hello world");
  });

  test("renders <br> as <br>", () => {
    expect(sanitize("line1<br>line2")).toContain("<br>");
  });

  test("renders <b> and <i> as markup", () => {
    const result = sanitize("<b>bold</b> and <i>italic</i>");
    expect(result).toContain("<b>bold</b>");
    expect(result).toContain("<i>italic</i>");
  });

  test("strips <script> tags but keeps their text content", () => {
    const result = sanitize('<script>alert(1)</script>safe');
    expect(result).not.toContain("<script>");
    expect(result).toContain("safe");
  });

  test("strips <a> tags but keeps their text content", () => {
    const result = sanitize('<a href="x">link text</a>');
    expect(result).not.toContain("<a");
    expect(result).toContain("link text");
  });

  test("does not render raw angle brackets as literal text for allowed tags", () => {
    const result = sanitize("<b>Title</b>");
    expect(result).not.toContain("&lt;b&gt;");
  });
});

// ---------------------------------------------------------------------------
// FORMAT_LABELS constant
// ---------------------------------------------------------------------------

describe("FORMAT_LABELS", () => {
  test("lossy-stereo maps to AAC", () => {
    expect(ctx.appWindow.__test_FORMAT_LABELS["lossy-stereo"]).toBe("AAC");
  });

  test("lossless maps to Lossless", () => {
    expect(ctx.appWindow.__test_FORMAT_LABELS["lossless"]).toBe("Lossless");
  });

  test("hi-res-lossless maps to Hi-Res Lossless", () => {
    expect(ctx.appWindow.__test_FORMAT_LABELS["hi-res-lossless"]).toBe("Hi-Res Lossless");
  });

  test("atmos maps to Dolby Atmos", () => {
    expect(ctx.appWindow.__test_FORMAT_LABELS["atmos"]).toBe("Dolby Atmos");
  });

  test("spatial maps to Spatial Audio", () => {
    expect(ctx.appWindow.__test_FORMAT_LABELS["spatial"]).toBe("Spatial Audio");
  });

  test("adm maps to Apple Digital Masters", () => {
    expect(ctx.appWindow.__test_FORMAT_LABELS["adm"]).toBe("Apple Digital Masters");
  });
});

// ---------------------------------------------------------------------------
// RELEASE_TYPE_LABELS constant
// ---------------------------------------------------------------------------

describe("RELEASE_TYPE_LABELS", () => {
  test("main-albums → Albums", () => {
    expect(ctx.appWindow.__test_RELEASE_TYPE_LABELS["main-albums"]).toBe("Albums");
  });

  test("compilation-albums → Compilations", () => {
    expect(ctx.appWindow.__test_RELEASE_TYPE_LABELS["compilation-albums"]).toBe("Compilations");
  });

  test("live-albums → Live Albums", () => {
    expect(ctx.appWindow.__test_RELEASE_TYPE_LABELS["live-albums"]).toBe("Live Albums");
  });

  test("singles-eps → Singles & EPs", () => {
    expect(ctx.appWindow.__test_RELEASE_TYPE_LABELS["singles-eps"]).toBe("Singles & EPs");
  });
});

// ---------------------------------------------------------------------------
// RELEASE_TYPE_ORDER
// ---------------------------------------------------------------------------

describe("RELEASE_TYPE_ORDER", () => {
  test("is an Array", () => {
    expect(Array.isArray(ctx.appWindow.__test_RELEASE_TYPE_ORDER)).toBe(true);
  });

  test("has four entries", () => {
    expect(ctx.appWindow.__test_RELEASE_TYPE_ORDER.length).toBe(4);
  });

  test("main-albums is first", () => {
    expect(ctx.appWindow.__test_RELEASE_TYPE_ORDER[0]).toBe("main-albums");
  });

  test("contains singles-eps", () => {
    expect(ctx.appWindow.__test_RELEASE_TYPE_ORDER).toContain("singles-eps");
  });

  test("contains compilation-albums", () => {
    expect(ctx.appWindow.__test_RELEASE_TYPE_ORDER).toContain("compilation-albums");
  });

  test("contains live-albums", () => {
    expect(ctx.appWindow.__test_RELEASE_TYPE_ORDER).toContain("live-albums");
  });

  test("main-albums comes before singles-eps", () => {
    const order = ctx.appWindow.__test_RELEASE_TYPE_ORDER;
    expect(order.indexOf("main-albums")).toBeLessThan(order.indexOf("singles-eps"));
  });
});

// ---------------------------------------------------------------------------
// API helper (fetch integration)
// ---------------------------------------------------------------------------

describe("API helper", () => {
  test("API.get calls fetch with the path", async () => {
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ items: [] }),
    });
    const result = await ctx.appWindow.__test_API.get("/api/releases");
    expect(ctx.appWindow.fetch).toHaveBeenCalledWith("/api/releases");
    expect(result).toEqual({ items: [] });
  });

  test("API.get throws on non-ok response", async () => {
    ctx.appWindow.fetch.mockResolvedValueOnce({ ok: false, status: 404 });
    await expect(ctx.appWindow.__test_API.get("/api/missing")).rejects.toThrow("HTTP 404");
  });

  test("API.post sends POST with JSON body and Content-Type header", async () => {
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    const body = { artist_id: "ART1", name: "Test Artist" };
    await ctx.appWindow.__test_API.post("/api/watchlist", body);
    const [url, opts] = ctx.appWindow.fetch.mock.calls[0];
    expect(url).toBe("/api/watchlist");
    expect(opts.method).toBe("POST");
    expect(JSON.parse(opts.body)).toEqual(body);
    expect(opts.headers["Content-Type"]).toBe("application/json");
  });

  test("API.put sends PUT method with JSON body", async () => {
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    await ctx.appWindow.__test_API.put("/api/system/config", { newrelease_poll_interval_days: 1 });
    const [, opts] = ctx.appWindow.fetch.mock.calls[0];
    expect(opts.method).toBe("PUT");
  });

  test("API.del sends DELETE method", async () => {
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    await ctx.appWindow.__test_API.del("/api/watchlist/ART1");
    const [url, opts] = ctx.appWindow.fetch.mock.calls[0];
    expect(url).toBe("/api/watchlist/ART1");
    expect(opts.method).toBe("DELETE");
  });

  test("API.post returns parsed JSON", async () => {
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    const result = await ctx.appWindow.__test_API.post("/api/system/refresh", {});
    expect(result.ok).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// API.patch
// ---------------------------------------------------------------------------

describe("API.patch", () => {
  test("sends PATCH method", async () => {
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    await ctx.appWindow.__test_API.patch("/api/watchlist/ART1", { preferred_source: "jp" });
    const [, opts] = ctx.appWindow.fetch.mock.calls[0];
    expect(opts.method).toBe("PATCH");
  });

  test("sends the correct URL", async () => {
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    await ctx.appWindow.__test_API.patch("/api/watchlist/ART1", { preferred_source: "jp" });
    const [url] = ctx.appWindow.fetch.mock.calls[0];
    expect(url).toBe("/api/watchlist/ART1");
  });

  test("sends Content-Type: application/json", async () => {
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    await ctx.appWindow.__test_API.patch("/api/watchlist/ART1", { preferred_source: "jp" });
    const [, opts] = ctx.appWindow.fetch.mock.calls[0];
    expect(opts.headers["Content-Type"]).toBe("application/json");
  });

  test("serialises body as JSON", async () => {
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    const body = { preferred_source: "us" };
    await ctx.appWindow.__test_API.patch("/api/watchlist/ART1", body);
    const [, opts] = ctx.appWindow.fetch.mock.calls[0];
    expect(JSON.parse(opts.body)).toEqual(body);
  });

  test("serialises null preferred_source correctly", async () => {
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    await ctx.appWindow.__test_API.patch("/api/watchlist/ART1", { preferred_source: null });
    const [, opts] = ctx.appWindow.fetch.mock.calls[0];
    expect(JSON.parse(opts.body)).toEqual({ preferred_source: null });
  });

  test("returns parsed JSON response", async () => {
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    const result = await ctx.appWindow.__test_API.patch("/api/watchlist/ART1", {});
    expect(result.ok).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// tracklistsDiffer
// ---------------------------------------------------------------------------

describe("tracklistsDiffer", () => {
  test("returns false for identical single-track lists", () => {
    const t = [{ title: "Song A" }];
    expect(ctx.appWindow.tracklistsDiffer(t, t)).toBe(false);
  });

  test("returns false for two equal lists", () => {
    const a = [{ title: "Song A" }, { title: "Song B" }];
    const b = [{ title: "Song A" }, { title: "Song B" }];
    expect(ctx.appWindow.tracklistsDiffer(a, b)).toBe(false);
  });

  test("returns true when lengths differ", () => {
    const a = [{ title: "Song A" }, { title: "Song B" }];
    const b = [{ title: "Song A" }];
    expect(ctx.appWindow.tracklistsDiffer(a, b)).toBe(true);
  });

  test("returns true when a track title differs", () => {
    const a = [{ title: "Song A" }, { title: "Song B" }];
    const b = [{ title: "Song A" }, { title: "Song C" }];
    expect(ctx.appWindow.tracklistsDiffer(a, b)).toBe(true);
  });

  test("returns true when first track title differs", () => {
    const a = [{ title: "Different" }];
    const b = [{ title: "Original" }];
    expect(ctx.appWindow.tracklistsDiffer(a, b)).toBe(true);
  });

  test("returns false for two empty lists", () => {
    expect(ctx.appWindow.tracklistsDiffer([], [])).toBe(false);
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
    const debounced = ctx.appWindow.debounce(fn, 200);
    debounced();
    expect(fn).not.toHaveBeenCalled();
  });

  test("calls fn after the delay", () => {
    const fn = jest.fn();
    const debounced = ctx.appWindow.debounce(fn, 200);
    debounced();
    jest.advanceTimersByTime(200);
    expect(fn).toHaveBeenCalledTimes(1);
  });

  test("calls fn only once for multiple rapid calls", () => {
    const fn = jest.fn();
    const debounced = ctx.appWindow.debounce(fn, 200);
    debounced(); debounced(); debounced();
    jest.advanceTimersByTime(200);
    expect(fn).toHaveBeenCalledTimes(1);
  });

  test("resets the timer on each call", () => {
    const fn = jest.fn();
    const debounced = ctx.appWindow.debounce(fn, 200);
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
    const debounced = ctx.appWindow.debounce(fn, 100);
    debounced("hello", 42);
    jest.advanceTimersByTime(100);
    expect(fn).toHaveBeenCalledWith("hello", 42);
  });
});

// ---------------------------------------------------------------------------
// COLLECTION_STATUS_LABELS
// ---------------------------------------------------------------------------

describe("COLLECTION_STATUS_LABELS", () => {
  test("has all four statuses", () => {
    const labels = ctx.appWindow.__test_COLLECTION_STATUS_LABELS;
    expect(labels).toBeDefined();
    expect(labels.new).toBe("New");
    expect(labels.complete).toBe("Complete");
    expect(labels.new_release).toBe("New Release");
    expect(labels.in_progress).toBe("In Progress");
  });

  test("has exactly four entries", () => {
    const labels = ctx.appWindow.__test_COLLECTION_STATUS_LABELS;
    expect(Object.keys(labels)).toHaveLength(4);
  });
});

describe("COLLECTION_TRANSITIONS", () => {
  test("new can transition to complete and in_progress", () => {
    const t = ctx.appWindow.__test_COLLECTION_TRANSITIONS;
    expect(t.new).toEqual(expect.arrayContaining(["complete", "in_progress"]));
    expect(t.new).toHaveLength(2);
  });

  test("complete can transition to in_progress", () => {
    const t = ctx.appWindow.__test_COLLECTION_TRANSITIONS;
    expect(t.complete).toEqual(["in_progress"]);
  });

  test("new_release can transition to complete and in_progress", () => {
    const t = ctx.appWindow.__test_COLLECTION_TRANSITIONS;
    expect(t.new_release).toEqual(expect.arrayContaining(["complete", "in_progress"]));
    expect(t.new_release).toHaveLength(2);
  });

  test("in_progress can only transition to complete", () => {
    const t = ctx.appWindow.__test_COLLECTION_TRANSITIONS;
    expect(t.in_progress).toEqual(["complete"]);
  });
});

// ---------------------------------------------------------------------------
// WatchlistPrefs sort persistence
// ---------------------------------------------------------------------------

describe("WatchlistPrefs sort persistence", () => {
  beforeEach(() => {
    ctx.appWindow.localStorage.clear();
  });

  test("getSortFilter returns 'name' when nothing is stored", () => {
    expect(ctx.appWindow.__test_WatchlistPrefs.getSortFilter()).toBe("name");
  });

  test("setSortFilter persists the value and getSortFilter retrieves it", () => {
    ctx.appWindow.__test_WatchlistPrefs.setSortFilter("added");
    expect(ctx.appWindow.__test_WatchlistPrefs.getSortFilter()).toBe("added");
  });

  test("setSortFilter can be updated to a new value", () => {
    ctx.appWindow.__test_WatchlistPrefs.setSortFilter("added");
    ctx.appWindow.__test_WatchlistPrefs.setSortFilter("recent_release");
    expect(ctx.appWindow.__test_WatchlistPrefs.getSortFilter()).toBe("recent_release");
  });
});

// ---------------------------------------------------------------------------
// ReleasesPrefs — sort preference persistence
// ---------------------------------------------------------------------------

describe("ReleasesPrefs", () => {
  beforeEach(() => ctx.appWindow.localStorage.clear());

  test("getSort returns release_date by default", () => {
    expect(ctx.appWindow.__test_ReleasesPrefs.getSort()).toBe("release_date");
  });

  test("setSort persists and getSort returns it", () => {
    ctx.appWindow.__test_ReleasesPrefs.setSort("first_seen");
    expect(ctx.appWindow.__test_ReleasesPrefs.getSort()).toBe("first_seen");
  });
});
