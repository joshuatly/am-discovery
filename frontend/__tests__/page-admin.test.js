"use strict";

const ctx = require("./setup-jsdom");

// ---------------------------------------------------------------------------
// Admin page — Artists and Releases tabs
// ---------------------------------------------------------------------------

describe("Admin page", () => {
  let main;

  beforeEach(() => {
    main = ctx.appWindow.document.createElement("div");
    ctx.appWindow.document.body.appendChild(main);
    ctx.appWindow.fetch.mockClear();
    // Pre-seed config state so ensureAdminConfig skips the config fetch,
    // keeping the fetch sequence deterministic for each test.
    ctx.appWindow.__test_state.configuredStorefronts = ["tw", "hk"];
    ctx.appWindow.__test_state.discoveryStorefronts = ["tw", "hk"];
    ctx.appWindow.__test_state.homeStorefront = "my";
    ctx.appWindow.__test_state.adminGroupByArtist = false;
    ctx.appWindow.__test_state.adminReleaseSort = "release_date";
    ctx.appWindow.__test_state.adminReleaseCountry = "";
  });

  afterEach(() => {
    main.remove();
  });

  function mockOnce(payload, ok = true) {
    ctx.appWindow.fetch.mockResolvedValueOnce({ ok, json: () => Promise.resolve(payload) });
  }

  // --- buildHarmonyUrl -----------------------------------------------------
  test("buildHarmonyUrl produces a Harmony release URL with all params", () => {
    const url = ctx.appWindow.__test_buildHarmonyUrl("A1", "tw", "12345", ["tw", "hk"]);
    expect(url).toContain("https://harmony.pulsewidth.org.uk/release?");
    expect(url).toContain(encodeURIComponent("https://music.apple.com/tw/album/A1"));
    expect(url).toContain("gtin=12345");
    expect(url).toContain("region=TW%2CHK");
    expect(url).toContain("musicbrainz=");
  });

  test("buildHarmonyUrl tolerates a missing UPC", () => {
    const url = ctx.appWindow.__test_buildHarmonyUrl("A1", "tw", null, []);
    expect(url).toContain("gtin=");
  });

  // --- Artists tab ---------------------------------------------------------
  test("renders unlinked artist with a suggestion and action buttons", async () => {
    mockOnce({
      total: 1,
      items: [
        {
          artist_id: "ART1",
          name: "Jay Chou",
          alt_name: null,
          preferred_source: "tw",
          am_url: "https://music.apple.com/tw/artist/ART1",
          am_discovery_url: "#/artist/ART1",
          suggestion_status: "pending",
          suggested_mbid: "mbid-1",
          suggested_name: "Jay Chou",
          score: 99,
          suggested_type: "Person",
          suggested_area: "Taiwan",
          suggested_disambiguation: "Taiwanese singer",
          mb_url: "https://musicbrainz.org/artist/mbid-1",
          candidates: [{ id: "mbid-1" }],
        },
      ],
    });
    await ctx.appWindow.__test_renderAdminArtists(main);

    expect(main.textContent).toContain("Jay Chou");
    const approve = Array.from(main.querySelectorAll("button")).find(b => b.textContent === "Approve");
    expect(approve).toBeTruthy();
    const mbLink = Array.from(main.querySelectorAll("a")).find(a => a.href.includes("musicbrainz.org/artist/mbid-1"));
    expect(mbLink).toBeTruthy();
    // Type / area / disambiguation are shown to help identify the match.
    expect(main.querySelector(".admin-suggestion-tag").textContent).toBe("Person · Taiwan");
    expect(main.querySelector(".admin-suggestion-disambig").textContent).toBe("Taiwanese singer");
    // Manual entry input present
    expect(main.querySelector(".admin-mbid-input")).toBeTruthy();
  });

  test("renders the artist avatar image when artwork_url is present", async () => {
    mockOnce({
      total: 1,
      items: [
        {
          artist_id: "ART1", name: "Jay", alt_name: null, preferred_source: "tw",
          artwork_url: "http://img.example/a.jpg", am_url: "x", am_discovery_url: "#/artist/ART1",
          suggestion_status: null, suggested_mbid: null, suggested_name: null, score: null,
          mb_url: null, candidates: [],
        },
      ],
    });
    await ctx.appWindow.__test_renderAdminArtists(main);
    const img = main.querySelector(".admin-artist-avatar-img");
    expect(img).toBeTruthy();
    expect(img.src).toContain("http://img.example/a.jpg");
  });

  test("falls back to the artist initial when no artwork_url", async () => {
    mockOnce({
      total: 1,
      items: [
        {
          artist_id: "ART1", name: "Jay", alt_name: null, preferred_source: "tw",
          artwork_url: null, am_url: "x", am_discovery_url: "#/artist/ART1",
          suggestion_status: null, suggested_mbid: null, suggested_name: null, score: null,
          mb_url: null, candidates: [],
        },
      ],
    });
    await ctx.appWindow.__test_renderAdminArtists(main);
    expect(main.querySelector(".admin-artist-avatar").textContent).toBe("J");
  });

  test("empty artists list shows the all-linked message", async () => {
    mockOnce({ total: 0, items: [] });
    await ctx.appWindow.__test_renderAdminArtists(main);
    expect(main.textContent).toContain("Every watched artist is linked");
  });

  test("Approve posts to the approve endpoint with the suggested MBID", async () => {
    mockOnce({
      total: 1,
      items: [
        {
          artist_id: "ART1", name: "Jay", alt_name: null, preferred_source: "tw",
          am_url: "x", am_discovery_url: "#/artist/ART1", suggestion_status: "pending",
          suggested_mbid: "mbid-1", suggested_name: "Jay", score: 99,
          mb_url: "https://musicbrainz.org/artist/mbid-1", candidates: [],
        },
      ],
    });
    await ctx.appWindow.__test_renderAdminArtists(main);

    mockOnce({ ok: true });      // approve POST
    mockOnce({ total: 0, items: [] }); // re-render GET
    const approve = Array.from(main.querySelectorAll("button")).find(b => b.textContent === "Approve");
    approve.click();
    await new Promise(r => setTimeout(r, 0));

    const approveCall = ctx.appWindow.fetch.mock.calls.find(c => String(c[0]).includes("/approve"));
    expect(approveCall).toBeTruthy();
    expect(JSON.parse(approveCall[1].body)).toEqual({ musicbrainz_id: "mbid-1" });
  });

  test("Search all button triggers the bulk search endpoint", async () => {
    mockOnce({
      total: 1,
      items: [
        {
          artist_id: "ART1", name: "Jay", alt_name: null, preferred_source: null,
          am_url: "x", am_discovery_url: "#/artist/ART1", suggestion_status: null,
          suggested_mbid: null, suggested_name: null, score: null, mb_url: null, candidates: [],
        },
      ],
    });
    await ctx.appWindow.__test_renderAdminArtists(main);

    // Queue: POST search-all, then first status poll (not running -> re-render), then re-render GET.
    mockOnce({ running: true, total: 1, done: 0 });
    mockOnce({ running: false, total: 1, done: 1, found: 1 });
    mockOnce({ total: 0, items: [] });
    const btn = Array.from(main.querySelectorAll("button")).find(b => b.textContent.includes("Search all"));
    expect(btn).toBeTruthy();
    btn.click();
    await new Promise(r => setTimeout(r, 0));

    const postCall = ctx.appWindow.fetch.mock.calls.find(
      c => String(c[0]).includes("/search-all") && c[1] && c[1].method === "POST"
    );
    expect(postCall).toBeTruthy();
  });

  test("Search all is disabled when every artist already has a suggestion", async () => {
    mockOnce({
      total: 1,
      items: [
        {
          artist_id: "ART1", name: "Jay", alt_name: null, preferred_source: "tw",
          am_url: "x", am_discovery_url: "#/artist/ART1", suggestion_status: "pending",
          suggested_mbid: "mbid-1", suggested_name: "Jay", score: 99,
          mb_url: "https://musicbrainz.org/artist/mbid-1", candidates: [],
        },
      ],
    });
    await ctx.appWindow.__test_renderAdminArtists(main);
    const btn = Array.from(main.querySelectorAll("button")).find(b => b.textContent.includes("Search all"));
    expect(btn.disabled).toBe(true);
  });

  test("approving reloads in place and restores scroll instead of jumping to top", async () => {
    mockOnce({
      total: 1,
      items: [
        {
          artist_id: "ART1", name: "Jay", alt_name: null, preferred_source: "tw",
          am_url: "x", am_discovery_url: "#/artist/ART1", suggestion_status: "pending",
          suggested_mbid: "mbid-1", suggested_name: "Jay", score: 99,
          mb_url: "https://musicbrainz.org/artist/mbid-1", candidates: [],
        },
      ],
    });
    await ctx.appWindow.__test_renderAdminArtists(main);
    ctx.appWindow.scrollTo.mockClear();

    mockOnce({ ok: true });            // approve POST
    mockOnce({ total: 0, items: [] }); // in-place reload GET
    Array.from(main.querySelectorAll("button")).find(b => b.textContent === "Approve").click();
    await new Promise(r => setTimeout(r, 20));

    // restoreScroll() runs on the preserveScroll reload path.
    expect(ctx.appWindow.scrollTo).toHaveBeenCalled();
  });

  test("artist without suggestion shows a Look up button", async () => {
    mockOnce({
      total: 1,
      items: [
        {
          artist_id: "ART1", name: "Jay", alt_name: null, preferred_source: null,
          am_url: "x", am_discovery_url: "#/artist/ART1", suggestion_status: null,
          suggested_mbid: null, suggested_name: null, score: null, mb_url: null, candidates: [],
        },
      ],
    });
    await ctx.appWindow.__test_renderAdminArtists(main);
    const lookup = Array.from(main.querySelectorAll("button")).find(b => b.textContent.includes("Look up"));
    expect(lookup).toBeTruthy();
  });

  // --- Releases tab --------------------------------------------------------
  test("renders a release card with cover, Harmony link, and Hide button", async () => {
    mockOnce({
      total: 1,
      items: [
        {
          store_adam_id: "A1", title: "Greatest Works", artist_name: "Jay Chou",
          release_date: "2020-01-01", release_type: "Album", preferred_source: "tw",
          artist_musicbrainz_id: "artist-mbid", upc: "111", artwork_url: "http://img/x.jpg",
          storefronts: ["tw"],
        },
      ],
    });
    await ctx.appWindow.__test_renderAdminReleases(main);

    expect(main.textContent).toContain("Greatest Works");
    const harmony = Array.from(main.querySelectorAll("a")).find(a => a.href.includes("harmony.pulsewidth.org.uk"));
    expect(harmony).toBeTruthy();
    expect(harmony.href).toContain(encodeURIComponent("https://music.apple.com/tw/album/A1"));
    const hide = Array.from(main.querySelectorAll("button")).find(b => b.textContent === "Hide");
    expect(hide).toBeTruthy();
  });

  test("Hide posts to the hide endpoint", async () => {
    mockOnce({
      total: 1,
      items: [
        {
          store_adam_id: "A1", title: "Album", artist_name: "Jay", release_date: "2020-01-01",
          release_type: "Album", preferred_source: "tw", artist_musicbrainz_id: null, upc: "111",
          artwork_url: null, storefronts: ["tw"],
        },
      ],
    });
    await ctx.appWindow.__test_renderAdminReleases(main);

    mockOnce({ ok: true });            // hide POST
    mockOnce({ total: 0, items: [] }); // re-render GET
    const hide = Array.from(main.querySelectorAll("button")).find(b => b.textContent === "Hide");
    hide.click();
    await new Promise(r => setTimeout(r, 0));

    const hideCall = ctx.appWindow.fetch.mock.calls.find(c => String(c[0]).includes("/A1/hide"));
    expect(hideCall).toBeTruthy();
    expect(hideCall[1].method).toBe("POST");
  });

  test("release card shows a track-count chip", async () => {
    mockOnce({
      total: 1,
      items: [
        {
          store_adam_id: "A1", title: "Album", artist_name: "Jay", release_date: "2020-01-01",
          release_type: "Album", preferred_source: "tw", artist_musicbrainz_id: null, upc: "1",
          artwork_url: null, storefronts: ["tw"], track_count: 12,
        },
      ],
    });
    await ctx.appWindow.__test_renderAdminReleases(main);
    const chip = main.querySelector(".track-count-chip");
    expect(chip).toBeTruthy();
    expect(chip.textContent).toBe("12");
  });

  test("track-count chip splits songs and music videos", async () => {
    mockOnce({
      total: 1,
      items: [
        {
          store_adam_id: "A1", title: "Album", artist_name: "Jay", release_date: "2020-01-01",
          release_type: "Album", preferred_source: "tw", artist_musicbrainz_id: null, upc: "1",
          artwork_url: null, storefronts: ["tw"], track_count: 12, music_video_count: 2,
        },
      ],
    });
    await ctx.appWindow.__test_renderAdminReleases(main);
    expect(main.querySelector(".track-count-chip").textContent).toBe("10+2");
  });

  test("release grid reuses .album-grid for size parity with other pages", async () => {
    mockOnce({
      total: 1,
      items: [
        {
          store_adam_id: "A1", title: "Album", artist_name: "Jay", release_date: "2020-01-01",
          release_type: "Album", preferred_source: "tw", artist_musicbrainz_id: null, upc: "1",
          artwork_url: null, storefronts: ["tw"], track_count: 5,
        },
      ],
    });
    await ctx.appWindow.__test_renderAdminReleases(main);
    expect(main.querySelector(".album-grid.admin-release-grid")).toBeTruthy();
  });

  test("empty releases list shows the nothing-pending message", async () => {
    mockOnce({ total: 0, items: [] });
    await ctx.appWindow.__test_renderAdminReleases(main);
    expect(main.textContent).toContain("No releases pending");
  });

  test("release count is shown above the grid", async () => {
    mockOnce({
      total: 2,
      items: [
        { store_adam_id: "A1", title: "One", artist_name: "Jay", release_date: "2020-01-01", release_type: "Album", preferred_source: "tw", artist_musicbrainz_id: null, upc: "1", artwork_url: null, storefronts: ["tw"] },
        { store_adam_id: "A2", title: "Two", artist_name: "Jay", release_date: "2021-01-01", release_type: "EP", preferred_source: "tw", artist_musicbrainz_id: null, upc: "2", artwork_url: null, storefronts: ["tw"] },
      ],
    });
    await ctx.appWindow.__test_renderAdminReleases(main);
    expect(main.textContent).toContain("2 releases missing from MusicBrainz");
  });

  test("group-by-artist renders a group header with the artist name", async () => {
    ctx.appWindow.__test_state.adminGroupByArtist = true;
    mockOnce({
      total: 1,
      items: [
        { store_adam_id: "A1", title: "One", artist_name: "Jay Chou", release_date: "2020-01-01", release_type: "Album", preferred_source: "tw", artist_musicbrainz_id: "m", upc: "1", artwork_url: null, storefronts: ["tw"] },
      ],
    });
    await ctx.appWindow.__test_renderAdminReleases(main);
    expect(main.querySelector(".admin-group-header")).toBeTruthy();
    expect(main.querySelector(".admin-group-name").textContent).toBe("Jay Chou");
    ctx.appWindow.__test_state.adminGroupByArtist = false;
  });

  test("group-by-artist header links to the AM Discovery artist page", async () => {
    ctx.appWindow.__test_state.adminGroupByArtist = true;
    mockOnce({
      total: 1,
      items: [
        { store_adam_id: "A1", artist_id: "artist-1", title: "One", artist_name: "Jay Chou", release_date: "2020-01-01", release_type: "Album", preferred_source: "tw", artist_musicbrainz_id: "m", upc: "1", artwork_url: null, storefronts: ["tw"] },
      ],
    });
    await ctx.appWindow.__test_renderAdminReleases(main);
    const header = main.querySelector(".admin-group-header");
    const discLink = Array.from(header.querySelectorAll("a.admin-link")).find(a => a.getAttribute("href") === "#/artist/artist-1");
    expect(discLink).toBeTruthy();
    expect(discLink.textContent).toContain("AM Discovery");
    ctx.appWindow.__test_state.adminGroupByArtist = false;
  });

  // --- Default tab ---------------------------------------------------------
  test("Admin page opens on the Releases tab by default", async () => {
    ctx.appWindow.__test_state.adminTab = "releases";
    mockOnce({ total: 0, items: [] }); // releases fetch for the default tab
    await ctx.appWindow.__test_renderAdmin(main, null);
    const tabs = Array.from(main.querySelectorAll(".admin-tab"));
    expect(tabs[0].textContent).toBe("Releases");
    const active = main.querySelector(".admin-tab.active");
    expect(active.textContent).toBe("Releases");
  });

  // --- Country filter ------------------------------------------------------
  test("country filter bar renders a pill per configured storefront", async () => {
    mockOnce({ total: 0, items: [] });
    await ctx.appWindow.__test_renderAdminReleases(main);
    const labels = Array.from(main.querySelectorAll(".sf-filter-btn")).map(b => b.textContent);
    expect(labels).toEqual(["All", "TW", "HK"]);
  });

  test("selecting a country filters releases by preferred source", async () => {
    ctx.appWindow.__test_state.adminReleaseCountry = "hk";
    mockOnce({
      total: 2,
      items: [
        { store_adam_id: "A1", title: "TW One", artist_name: "Jay", release_date: "2020-01-01", release_type: "Album", preferred_source: "tw", artist_musicbrainz_id: null, upc: "1", artwork_url: null, storefronts: ["tw"] },
        { store_adam_id: "A2", title: "HK Two", artist_name: "Eason", release_date: "2021-01-01", release_type: "Album", preferred_source: "hk", artist_musicbrainz_id: null, upc: "2", artwork_url: null, storefronts: ["hk"] },
      ],
    });
    await ctx.appWindow.__test_renderAdminReleases(main);
    expect(main.textContent).toContain("HK Two");
    expect(main.textContent).not.toContain("TW One");
    expect(main.textContent).toContain("1 release missing from MusicBrainz");
    ctx.appWindow.__test_state.adminReleaseCountry = "";
  });

  // --- Alpha index (group by artist) ---------------------------------------
  test("group-by-artist shows an A–Z index for multiple artists", async () => {
    ctx.appWindow.__test_state.adminGroupByArtist = true;
    mockOnce({
      total: 2,
      items: [
        { store_adam_id: "A1", title: "One", artist_name: "Jay Chou", release_date: "2020-01-01", release_type: "Album", preferred_source: "tw", artist_musicbrainz_id: null, upc: "1", artwork_url: null, storefronts: ["tw"] },
        { store_adam_id: "A2", title: "Two", artist_name: "Eason Chan", release_date: "2021-01-01", release_type: "Album", preferred_source: "tw", artist_musicbrainz_id: null, upc: "2", artwork_url: null, storefronts: ["tw"] },
      ],
    });
    await ctx.appWindow.__test_renderAdminReleases(main);
    const idx = main.querySelector(".alpha-index");
    expect(idx).toBeTruthy();
    // Letters E and J have groups; they should be clickable.
    const active = Array.from(idx.querySelectorAll(".alpha-index-btn.has-artists")).map(b => b.textContent).sort();
    expect(active).toEqual(["E", "J"]);
    ctx.appWindow.__test_state.adminGroupByArtist = false;
  });
});
