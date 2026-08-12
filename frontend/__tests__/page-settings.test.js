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

  // ---------------------------------------------------------------------------
  // MusicBrainz Seeding Admin — enable checkbox
  // ---------------------------------------------------------------------------

  test("renders the MusicBrainz seeding checkbox checked when enabled", async () => {
    mockConfigFetch({ ...fullCfg, mb_scan_enabled: true });
    await ctx.appWindow.__test_renderSettings(main);
    const cb = main.querySelector("#cfg-mb-scan-enabled");
    expect(cb).toBeTruthy();
    expect(cb.checked).toBe(true);
  });

  test("renders the MusicBrainz seeding checkbox unchecked when disabled", async () => {
    mockConfigFetch({ ...fullCfg, mb_scan_enabled: false });
    await ctx.appWindow.__test_renderSettings(main);
    const cb = main.querySelector("#cfg-mb-scan-enabled");
    expect(cb.checked).toBe(false);
  });

  test("defaults the checkbox to checked when mb_scan_enabled is absent from config", async () => {
    const { mb_scan_enabled, ...cfgWithoutFlag } = fullCfg;
    mockConfigFetch(cfgWithoutFlag);
    await ctx.appWindow.__test_renderSettings(main);
    expect(main.querySelector("#cfg-mb-scan-enabled").checked).toBe(true);
  });

  test("unchecking the MusicBrainz seeding checkbox saves mb_scan_enabled:false and updates state", async () => {
    mockConfigFetch({ ...fullCfg, mb_scan_enabled: true });
    await ctx.appWindow.__test_renderSettings(main);

    main.querySelector("#cfg-mb-scan-enabled").click();

    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    const saveBtn = Array.from(main.querySelectorAll("button")).find(b => b.textContent.includes("Save"));
    saveBtn.click();
    await new Promise(r => setTimeout(r, 50));

    const putCall = ctx.appWindow.fetch.mock.calls.find(
      ([url, opts]) => url === "/api/system/config" && opts && opts.method === "PUT"
    );
    const body = JSON.parse(putCall[1].body);
    expect(body.mb_scan_enabled).toBe(false);
    expect(ctx.appWindow.__test_state.mbScanEnabled).toBe(false);
  });
});
