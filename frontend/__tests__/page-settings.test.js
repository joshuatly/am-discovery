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

  // ---------------------------------------------------------------------------
  // Discovery Room Matching
  // ---------------------------------------------------------------------------

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

  // ---------------------------------------------------------------------------
  // MusicBrainz — scan interval / batch size / recheck interval
  // ---------------------------------------------------------------------------

  // Fields can share default values (e.g. mb_scan_artist_batch and
  // watchlist_poll_batch_size both default to 3), so look inputs up by their
  // label text rather than by value.
  function inputForLabel(container, labelText) {
    const label = Array.from(container.querySelectorAll("label")).find(l => l.textContent === labelText);
    return label?.parentElement.querySelector("input");
  }

  test("renders MusicBrainz interval, batch size, and recheck interval with configured values", async () => {
    mockConfigFetch({
      ...fullCfg,
      mb_scan_enabled: true,
      mb_scan_interval_minutes: 90,
      mb_scan_artist_batch: 5,
      mb_artist_recheck_days: 10,
    });
    await ctx.appWindow.__test_renderSettings(main);
    expect(inputForLabel(main, "MusicBrainz Scan Interval (minutes)").value).toBe("90");
    expect(inputForLabel(main, "MusicBrainz Artist Batch Size").value).toBe("5");
    expect(inputForLabel(main, "MusicBrainz Artist Recheck Interval (days)").value).toBe("10");
  });

  test("defaults MusicBrainz interval fields when absent from config", async () => {
    mockConfigFetch({ ...fullCfg, mb_scan_enabled: true });
    await ctx.appWindow.__test_renderSettings(main);
    expect(inputForLabel(main, "MusicBrainz Scan Interval (minutes)").value).toBe("60");
    expect(inputForLabel(main, "MusicBrainz Artist Batch Size").value).toBe("3");
    expect(inputForLabel(main, "MusicBrainz Artist Recheck Interval (days)").value).toBe("7");
  });

  test("MusicBrainz interval fields are hidden when the feature is disabled, shown when enabled", async () => {
    mockConfigFetch({ ...fullCfg, mb_scan_enabled: false });
    await ctx.appWindow.__test_renderSettings(main);
    const intervalInput = inputForLabel(main, "MusicBrainz Scan Interval (minutes)");
    expect(intervalInput.closest("div").parentElement.style.display).toBe("none");

    main.querySelector("#cfg-mb-scan-enabled").click();
    // Must be an explicit "flex", not "" — clearing to "" falls back to
    // block layout, which silently drops the container's `gap` and
    // collapses the spacing between the revealed fields.
    expect(intervalInput.closest("div").parentElement.style.display).toBe("flex");
  });

  test("save sends the MusicBrainz interval, batch size, and recheck interval fields", async () => {
    mockConfigFetch({ ...fullCfg, mb_scan_enabled: true });
    await ctx.appWindow.__test_renderSettings(main);

    inputForLabel(main, "MusicBrainz Scan Interval (minutes)").value = "120";
    inputForLabel(main, "MusicBrainz Artist Batch Size").value = "8";
    inputForLabel(main, "MusicBrainz Artist Recheck Interval (days)").value = "14";

    ctx.appWindow.fetch.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ ok: true }) });
    Array.from(main.querySelectorAll("button")).find(b => b.textContent.includes("Save")).click();
    await new Promise(r => setTimeout(r, 50));

    const putCall = ctx.appWindow.fetch.mock.calls.find(
      ([url, opts]) => url === "/api/system/config" && opts && opts.method === "PUT"
    );
    const body = JSON.parse(putCall[1].body);
    expect(body.mb_scan_interval_minutes).toBe(120);
    expect(body.mb_scan_artist_batch).toBe(8);
    expect(body.mb_artist_recheck_days).toBe(14);
  });

  // ---------------------------------------------------------------------------
  // CLI Scheduler — enable checkbox gates the URL/preset fields
  // ---------------------------------------------------------------------------

  test("CLI Scheduler checkbox is checked and fields shown when a URL is already configured", async () => {
    mockConfigFetch({ ...fullCfg, cli_scheduler_url: "http://cli.example.com", cli_scheduler_preset: "amdl" });
    await ctx.appWindow.__test_renderSettings(main);
    const cb = main.querySelector("#cfg-cli-scheduler-enabled");
    expect(cb.checked).toBe(true);
    const urlInput = Array.from(main.querySelectorAll("input[type='text']")).find(i => i.value === "http://cli.example.com");
    expect(urlInput).toBeTruthy();
    expect(urlInput.closest("div").parentElement.style.display).toBe("flex");
  });

  test("CLI Scheduler checkbox is unchecked and fields hidden when no URL is configured", async () => {
    mockConfigFetch({ ...fullCfg, cli_scheduler_url: "" });
    await ctx.appWindow.__test_renderSettings(main);
    const cb = main.querySelector("#cfg-cli-scheduler-enabled");
    expect(cb.checked).toBe(false);
    // The URL field's wrapping group should be hidden.
    const urlLabel = Array.from(main.querySelectorAll("label")).find(l => l.textContent === "CLI Scheduler URL");
    expect(urlLabel.closest("div").parentElement.style.display).toBe("none");
  });

  test("unchecking the CLI Scheduler checkbox clears cli_scheduler_url on save", async () => {
    mockConfigFetch({ ...fullCfg, cli_scheduler_url: "http://cli.example.com", cli_scheduler_preset: "amdl" });
    await ctx.appWindow.__test_renderSettings(main);

    main.querySelector("#cfg-cli-scheduler-enabled").click();

    ctx.appWindow.fetch.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ ok: true }) });
    Array.from(main.querySelectorAll("button")).find(b => b.textContent.includes("Save")).click();
    await new Promise(r => setTimeout(r, 50));

    const putCall = ctx.appWindow.fetch.mock.calls.find(
      ([url, opts]) => url === "/api/system/config" && opts && opts.method === "PUT"
    );
    const body = JSON.parse(putCall[1].body);
    expect(body.cli_scheduler_url).toBe("");
  });

  test("checking the CLI Scheduler checkbox and entering a URL saves it", async () => {
    mockConfigFetch({ ...fullCfg, cli_scheduler_url: "" });
    await ctx.appWindow.__test_renderSettings(main);

    main.querySelector("#cfg-cli-scheduler-enabled").click();
    const urlLabel = Array.from(main.querySelectorAll("label")).find(l => l.textContent === "CLI Scheduler URL");
    const urlInput = urlLabel.closest("div").querySelector("input");
    urlInput.value = "http://new-cli.example.com";

    ctx.appWindow.fetch.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ ok: true }) });
    Array.from(main.querySelectorAll("button")).find(b => b.textContent.includes("Save")).click();
    await new Promise(r => setTimeout(r, 50));

    const putCall = ctx.appWindow.fetch.mock.calls.find(
      ([url, opts]) => url === "/api/system/config" && opts && opts.method === "PUT"
    );
    const body = JSON.parse(putCall[1].body);
    expect(body.cli_scheduler_url).toBe("http://new-cli.example.com");
  });

  // ---------------------------------------------------------------------------
  // Section headings
  // ---------------------------------------------------------------------------

  test("renders the section headings in order", async () => {
    mockConfigFetch(fullCfg);
    await ctx.appWindow.__test_renderSettings(main);
    const headings = ["Storefronts & Discovery", "Polling Intervals & Batch Sizes", "MusicBrainz Seeding", "CLI Scheduler", "Notifications", "Backup / Restore"];
    for (const h of headings) {
      expect(main.textContent).toContain(h);
    }
  });
});
