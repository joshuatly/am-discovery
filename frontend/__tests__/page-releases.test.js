"use strict";

const ctx = require("./setup-jsdom");

// ---------------------------------------------------------------------------
// renderNewReleases — cross-page navigation regression
// ---------------------------------------------------------------------------
// Regression: visiting any page that loads config (watchlist, settings, artist)
// sets state.configuredStorefronts without setting state.discoveryStorefronts.
// renderNewReleases then skips its config fetch (guard sees non-null
// configuredStorefronts) and crashes reading .length on null discoveryStorefronts.
// ---------------------------------------------------------------------------

describe("renderNewReleases — cross-page navigation regression", () => {
  test("renders without error after visiting watchlist (configuredStorefronts set, discoveryStorefronts null)", async () => {
    const state = ctx.appWindow.__test_state;
    const main = ctx.appWindow.document.getElementById("main-content");

    // Simulate state left behind by renderWatchlist: it sets configuredStorefronts
    // but never sets discoveryStorefronts.
    state.configuredStorefronts = ["jp", "tw"];
    state.discoveryStorefronts = null;

    ctx.appWindow.fetch.mockImplementation((url) => {
      if (url.includes("/api/system/config")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ check_storefronts: ["jp", "tw"] }) });
      }
      if (url.includes("/api/watchlist")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ items: [], total: 0 }) });
    });

    await expect(ctx.appWindow.__test_renderNewReleases(main)).resolves.toBeUndefined();

    // Page should show New Releases, not crash or fall through to another view
    expect(main.innerHTML).toContain("New Releases");

    // discoveryStorefronts must be populated after the render
    expect(Array.isArray(state.discoveryStorefronts)).toBe(true);
  });

  test("renders without error when both configuredStorefronts and discoveryStorefronts start null", async () => {
    const state = ctx.appWindow.__test_state;
    const main = ctx.appWindow.document.getElementById("main-content");

    state.configuredStorefronts = null;
    state.discoveryStorefronts = null;

    ctx.appWindow.fetch.mockImplementation((url) => {
      if (url.includes("/api/system/config")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ check_storefronts: ["hk"] }) });
      }
      if (url.includes("/api/watchlist")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ items: [], total: 0 }) });
    });

    await expect(ctx.appWindow.__test_renderNewReleases(main)).resolves.toBeUndefined();
    expect(main.innerHTML).toContain("New Releases");
    expect(Array.isArray(state.discoveryStorefronts)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// page-controls layout: search + filter bar unified structure
// ---------------------------------------------------------------------------

describe("page-controls layout — New Releases", () => {
  let main;

  beforeEach(() => {
    main = ctx.appWindow.document.getElementById("main-content");
    const state = ctx.appWindow.__test_state;
    state.configuredStorefronts = ["jp", "tw"];
    state.discoveryStorefronts = ["jp", "tw"];
    ctx.appWindow.fetch.mockImplementation((url) => {
      if (url.includes("/api/watchlist")) return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ items: [], total: 0 }) });
    });
  });

  test("renders a .page-controls container", async () => {
    await ctx.appWindow.__test_renderNewReleases(main);
    expect(main.querySelector(".page-controls")).not.toBeNull();
  });

  test("search input is inside .page-controls-search", async () => {
    await ctx.appWindow.__test_renderNewReleases(main);
    const searchDiv = main.querySelector(".page-controls-search");
    expect(searchDiv).not.toBeNull();
    expect(searchDiv.querySelector("input.search-input")).not.toBeNull();
  });

  test("filter bar is inside .page-controls-filters", async () => {
    await ctx.appWindow.__test_renderNewReleases(main);
    const filtersDiv = main.querySelector(".page-controls-filters");
    expect(filtersDiv).not.toBeNull();
    expect(filtersDiv.querySelector(".sf-filter-bar")).not.toBeNull();
  });

  test(".page-controls-filters comes before .page-controls-search in DOM order", async () => {
    await ctx.appWindow.__test_renderNewReleases(main);
    const controls = main.querySelector(".page-controls");
    const children = Array.from(controls.children);
    const filtersIdx = children.findIndex(c => c.classList.contains("page-controls-filters"));
    const searchIdx = children.findIndex(c => c.classList.contains("page-controls-search"));
    expect(filtersIdx).toBeLessThan(searchIdx);
  });
});

// ---------------------------------------------------------------------------
// renderAllReleases — Watched filter
// ---------------------------------------------------------------------------

describe("renderAllReleases — Watched filter", () => {
  let main;

  beforeEach(() => {
    main = ctx.appWindow.document.getElementById("main-content");
    const state = ctx.appWindow.__test_state;
    state.configuredStorefronts = ["jp", "tw"];
    ctx.appWindow.fetch.mockImplementation((url) => {
      if (url.includes("/api/watchlist")) return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ items: [], total: 0 }) });
    });
  });

  afterEach(() => {
    main.innerHTML = "";
    ctx.appWindow.fetch.mockClear();
  });

  test("renders a Watched toggle button in the filter bar", async () => {
    await ctx.appWindow.__test_renderAllReleases(main);
    const toggle = main.querySelector(".watched-toggle");
    expect(toggle).not.toBeNull();
    expect(toggle.textContent).toBe("Watched");
  });

  test("Watched toggle is not active by default", async () => {
    await ctx.appWindow.__test_renderAllReleases(main);
    const toggle = main.querySelector(".watched-toggle");
    expect(toggle.classList.contains("active")).toBe(false);
  });

  test("Watched toggle is active when watchedOnly=true", async () => {
    await ctx.appWindow.__test_renderAllReleases(main, 1, "", "", true);
    const toggle = main.querySelector(".watched-toggle");
    expect(toggle.classList.contains("active")).toBe(true);
  });

  test("passes watched=true to API when watchedOnly is true", async () => {
    await ctx.appWindow.__test_renderAllReleases(main, 1, "", "", true);
    const calls = ctx.appWindow.fetch.mock.calls.map(c => c[0]);
    const releaseCall = calls.find(u => u.startsWith("/api/releases"));
    expect(releaseCall).toContain("watched=true");
  });

  test("does not pass watched param to API when watchedOnly is false", async () => {
    await ctx.appWindow.__test_renderAllReleases(main, 1, "", "", false);
    const calls = ctx.appWindow.fetch.mock.calls.map(c => c[0]);
    const releaseCall = calls.find(u => u.startsWith("/api/releases"));
    expect(releaseCall).not.toContain("watched=true");
  });
});

// ---------------------------------------------------------------------------
// renderAllReleases — Type filter
// ---------------------------------------------------------------------------

describe("renderAllReleases — Type filter", () => {
  let main;

  beforeEach(() => {
    main = ctx.appWindow.document.getElementById("main-content");
    const state = ctx.appWindow.__test_state;
    state.configuredStorefronts = ["jp"];
    ctx.appWindow.fetch.mockImplementation((url) => {
      if (url.includes("/api/watchlist")) return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ items: [], total: 0 }) });
    });
  });

  afterEach(() => {
    main.innerHTML = "";
    ctx.appWindow.fetch.mockClear();
  });

  test("renders a type filter bar with All button", async () => {
    await ctx.appWindow.__test_renderAllReleases(main);
    const typeBar = main.querySelector(".type-filter-bar");
    expect(typeBar).not.toBeNull();
    const allBtn = Array.from(typeBar.querySelectorAll(".type-filter-btn")).find(b => b.textContent === "All");
    expect(allBtn).not.toBeNull();
  });

  test("All button is active by default", async () => {
    await ctx.appWindow.__test_renderAllReleases(main);
    const typeBar = main.querySelector(".type-filter-bar");
    const allBtn = Array.from(typeBar.querySelectorAll(".type-filter-btn")).find(b => b.textContent === "All");
    expect(allBtn.classList.contains("active")).toBe(true);
  });

  test("renders buttons for each release type", async () => {
    await ctx.appWindow.__test_renderAllReleases(main);
    const typeBar = main.querySelector(".type-filter-bar");
    const btns = typeBar.querySelectorAll(".type-filter-btn");
    // All + 4 types
    expect(btns.length).toBe(5);
  });

  test("selected type button is active", async () => {
    await ctx.appWindow.__test_renderAllReleases(main, 1, "", "", false, "main-albums");
    const typeBar = main.querySelector(".type-filter-bar");
    const activeBtn = typeBar.querySelector(".type-filter-btn.active");
    expect(activeBtn).not.toBeNull();
    expect(activeBtn.textContent).toBe("Albums");
  });

  test("passes release_type to API when typeFilter is set", async () => {
    await ctx.appWindow.__test_renderAllReleases(main, 1, "", "", false, "singles-eps");
    const calls = ctx.appWindow.fetch.mock.calls.map(c => c[0]);
    const releaseCall = calls.find(u => u.startsWith("/api/releases"));
    expect(releaseCall).toContain("release_type=singles-eps");
  });

  test("does not pass release_type to API when typeFilter is empty", async () => {
    await ctx.appWindow.__test_renderAllReleases(main, 1, "", "", false, "");
    const calls = ctx.appWindow.fetch.mock.calls.map(c => c[0]);
    const releaseCall = calls.find(u => u.startsWith("/api/releases"));
    expect(releaseCall).not.toContain("release_type");
  });

  test("allReleasesTypeFilter initial state is empty string", () => {
    expect(ctx.appWindow.__test_state.allReleasesTypeFilter).toBe("");
  });
});

// ---------------------------------------------------------------------------
// renderNewReleases — sort UI
// ---------------------------------------------------------------------------

describe("renderNewReleases — sort buttons", () => {
  let main;
  beforeEach(() => {
    ctx.appWindow.localStorage.clear();
    ctx.appWindow.__test_state.configuredStorefronts = [];
    ctx.appWindow.__test_state.discoveryStorefronts = [];
    ctx.appWindow.__test_state.currentSort = "release_date";
    main = ctx.appWindow.document.createElement("div");
    ctx.appWindow.fetch = jest.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({ items: [], total: 0, check_storefronts: [] }) })
    );
  });

  test("renders Release Date and First Seen sort buttons", async () => {
    await ctx.appWindow.__test_renderNewReleases(main);
    await new Promise(r => setTimeout(r, 100));
    const btns = Array.from(main.querySelectorAll(".type-filter-btn")).map(b => b.textContent);
    expect(btns).toContain("Release Date");
    expect(btns).toContain("First Seen");
  });

  test("Release Date button is active by default", async () => {
    await ctx.appWindow.__test_renderNewReleases(main, 1, "", "", false, "release_date");
    await new Promise(r => setTimeout(r, 100));
    const active = Array.from(main.querySelectorAll(".type-filter-btn.active")).map(b => b.textContent);
    expect(active).toContain("Release Date");
    expect(active).not.toContain("First Seen");
  });

  test("First Seen button is active when sort is first_seen", async () => {
    await ctx.appWindow.__test_renderNewReleases(main, 1, "", "", false, "first_seen");
    await new Promise(r => setTimeout(r, 100));
    const active = Array.from(main.querySelectorAll(".type-filter-btn.active")).map(b => b.textContent);
    expect(active).toContain("First Seen");
    expect(active).not.toContain("Release Date");
  });

  test("sort=first_seen passes sort param to API", async () => {
    await ctx.appWindow.__test_renderNewReleases(main, 1, "", "", false, "first_seen");
    await new Promise(r => setTimeout(r, 100));
    const calls = ctx.appWindow.fetch.mock.calls.map(c => c[0]);
    const releaseCall = calls.find(u => u.includes("/api/releases"));
    expect(releaseCall).toContain("sort=first_seen");
  });

  test("sort=release_date omits sort param from API", async () => {
    await ctx.appWindow.__test_renderNewReleases(main, 1, "", "", false, "release_date");
    await new Promise(r => setTimeout(r, 100));
    const calls = ctx.appWindow.fetch.mock.calls.map(c => c[0]);
    const releaseCall = calls.find(u => u.includes("/api/releases"));
    expect(releaseCall).not.toContain("sort=");
  });
});

// ---------------------------------------------------------------------------
// renderAllReleases — sort UI
// ---------------------------------------------------------------------------

describe("renderAllReleases — sort buttons", () => {
  let main;
  beforeEach(() => {
    ctx.appWindow.localStorage.clear();
    ctx.appWindow.__test_state.configuredStorefronts = [];
    ctx.appWindow.__test_state.currentSort = "release_date";
    main = ctx.appWindow.document.createElement("div");
    ctx.appWindow.fetch = jest.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({ items: [], total: 0, check_storefronts: [] }) })
    );
  });

  test("renders Release Date and First Seen sort buttons", async () => {
    await ctx.appWindow.__test_renderAllReleases(main);
    await new Promise(r => setTimeout(r, 100));
    const btns = Array.from(main.querySelectorAll(".type-filter-btn")).map(b => b.textContent);
    expect(btns).toContain("Release Date");
    expect(btns).toContain("First Seen");
  });

  test("First Seen button is active when sort is first_seen", async () => {
    await ctx.appWindow.__test_renderAllReleases(main, 1, "", "", false, "", "first_seen");
    await new Promise(r => setTimeout(r, 100));
    const active = Array.from(main.querySelectorAll(".type-filter-btn.active")).map(b => b.textContent);
    expect(active).toContain("First Seen");
  });

  test("sort=first_seen passes sort param to API", async () => {
    await ctx.appWindow.__test_renderAllReleases(main, 1, "", "", false, "", "first_seen");
    await new Promise(r => setTimeout(r, 100));
    const calls = ctx.appWindow.fetch.mock.calls.map(c => c[0]);
    const releaseCall = calls.find(u => u.includes("/api/releases"));
    expect(releaseCall).toContain("sort=first_seen");
  });
});
