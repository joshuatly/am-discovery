"use strict";

const ctx = require("./setup-jsdom");

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
    discovery_names: { jp: "ニューリリース", hk: "新發行" },
    discovery_fallback_titles: ["new release", "new releases"],
  };

  let main;

  beforeEach(() => {
    main = ctx.appWindow.document.createElement("div");
    ctx.appWindow.document.body.appendChild(main);
    ctx.appWindow.fetch.mockClear();
  });

  afterEach(() => {
    main.remove();
  });

  function mockConfigFetch(cfg) {
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(cfg),
    });
  }

  test("renders input for check_storefronts", async () => {
    mockConfigFetch(fullCfg);
    await ctx.appWindow.__test_renderSettings(main);
    const inputs = main.querySelectorAll("input[type='text']");
    const values = Array.from(inputs).map(i => i.value);
    expect(values.some(v => v.includes("jp"))).toBe(true);
  });

  test("renders input for home_storefront", async () => {
    mockConfigFetch(fullCfg);
    await ctx.appWindow.__test_renderSettings(main);
    const inputs = main.querySelectorAll("input[type='text']");
    const values = Array.from(inputs).map(i => i.value);
    expect(values).toContain("hk");
  });

  test("renders input for newrelease_poll_interval_days", async () => {
    mockConfigFetch(fullCfg);
    await ctx.appWindow.__test_renderSettings(main);
    const inputs = main.querySelectorAll("input[type='number']");
    const values = Array.from(inputs).map(i => Number(i.value));
    expect(values).toContain(2);
  });

  test("renders input for watchlist_poll_interval_minutes", async () => {
    mockConfigFetch(fullCfg);
    await ctx.appWindow.__test_renderSettings(main);
    const inputs = main.querySelectorAll("input[type='number']");
    const values = Array.from(inputs).map(i => Number(i.value));
    expect(values).toContain(15);
  });

  test("renders input for watchlist_poll_batch_size", async () => {
    mockConfigFetch(fullCfg);
    await ctx.appWindow.__test_renderSettings(main);
    const inputs = main.querySelectorAll("input[type='number']");
    const values = Array.from(inputs).map(i => Number(i.value));
    expect(values).toContain(3);
  });

  test("renders input for watchlist_refresh_interval_days", async () => {
    mockConfigFetch(fullCfg);
    await ctx.appWindow.__test_renderSettings(main);
    const inputs = main.querySelectorAll("input[type='number']");
    const values = Array.from(inputs).map(i => Number(i.value));
    expect(values).toContain(14);
  });

  test("renders input for cors_proxy", async () => {
    mockConfigFetch(fullCfg);
    await ctx.appWindow.__test_renderSettings(main);
    const inputs = main.querySelectorAll("input[type='text']");
    const values = Array.from(inputs).map(i => i.value);
    expect(values).toContain("https://proxy.example.com/");
  });

  test("save sends all config fields including watchlist and cors_proxy", async () => {
    mockConfigFetch(fullCfg);
    await ctx.appWindow.__test_renderSettings(main);

    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });

    const saveBtn = Array.from(main.querySelectorAll("button")).find(b =>
      b.textContent.includes("Save")
    );
    saveBtn.click();
    await new Promise(r => setTimeout(r, 50));

    const putCall = ctx.appWindow.fetch.mock.calls.find(
      ([url, opts]) => url === "/api/system/config" && opts && opts.method === "PUT"
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
    await ctx.appWindow.__test_renderSettings(main);

    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });

    const saveBtn = Array.from(main.querySelectorAll("button")).find(b =>
      b.textContent.includes("Save")
    );
    saveBtn.click();
    await new Promise(r => setTimeout(r, 50));

    const putCall = ctx.appWindow.fetch.mock.calls.find(
      ([url, opts]) => url === "/api/system/config" && opts && opts.method === "PUT"
    );
    const body = JSON.parse(putCall[1].body);
    expect(body.cors_proxy).toBe("");
  });

  test("renders a row with the configured keyword for each discovery storefront", async () => {
    mockConfigFetch(fullCfg);
    await ctx.appWindow.__test_renderSettings(main);
    const inputs = main.querySelectorAll("input[type='text']");
    const values = Array.from(inputs).map(i => i.value);
    expect(values).toContain("ニューリリース");
    expect(values).toContain("新發行");
  });

  test("storefront chip links directly to Apple Music's New Releases page", async () => {
    mockConfigFetch(fullCfg);
    await ctx.appWindow.__test_renderSettings(main);
    const jpLink = Array.from(main.querySelectorAll("a")).find(a =>
      a.href.includes("music.apple.com/jp/new")
    );
    expect(jpLink).toBeDefined();
    expect(jpLink.target).toBe("_blank");
    expect(jpLink.rel).toContain("noopener");
    expect(jpLink.querySelector(".sf-chip")).not.toBeNull();
  });

  test("renders fallback match titles joined by comma", async () => {
    mockConfigFetch(fullCfg);
    await ctx.appWindow.__test_renderSettings(main);
    const inputs = main.querySelectorAll("input[type='text']");
    const values = Array.from(inputs).map(i => i.value);
    expect(values).toContain("new release, new releases");
  });

  test("save sends edited discovery_names and discovery_fallback_titles", async () => {
    mockConfigFetch(fullCfg);
    await ctx.appWindow.__test_renderSettings(main);

    const jpInput = Array.from(main.querySelectorAll("input[type='text']")).find(
      i => i.value === "ニューリリース"
    );
    jpInput.value = "新曲";

    const fallbackInput = Array.from(main.querySelectorAll("input[type='text']")).find(
      i => i.value === "new release, new releases"
    );
    fallbackInput.value = "custom title";

    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });

    const saveBtn = Array.from(main.querySelectorAll("button")).find(b =>
      b.textContent.includes("Save")
    );
    saveBtn.click();
    await new Promise(r => setTimeout(r, 50));

    const putCall = ctx.appWindow.fetch.mock.calls.find(
      ([url, opts]) => url === "/api/system/config" && opts && opts.method === "PUT"
    );
    const body = JSON.parse(putCall[1].body);
    expect(body.discovery_names).toEqual({ jp: "新曲", hk: "新發行" });
    expect(body.discovery_fallback_titles).toEqual(["custom title"]);
  });

  test("clearing a storefront's keyword removes it from discovery_names (falls back)", async () => {
    mockConfigFetch(fullCfg);
    await ctx.appWindow.__test_renderSettings(main);

    const jpInput = Array.from(main.querySelectorAll("input[type='text']")).find(
      i => i.value === "ニューリリース"
    );
    jpInput.value = "";

    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });

    const saveBtn = Array.from(main.querySelectorAll("button")).find(b =>
      b.textContent.includes("Save")
    );
    saveBtn.click();
    await new Promise(r => setTimeout(r, 50));

    const putCall = ctx.appWindow.fetch.mock.calls.find(
      ([url, opts]) => url === "/api/system/config" && opts && opts.method === "PUT"
    );
    const body = JSON.parse(putCall[1].body);
    expect(body.discovery_names).toEqual({ hk: "新發行" });
  });
});
