"use strict";

const ctx = require("./setup-jsdom");

// ---------------------------------------------------------------------------
// showImageLightbox
// ---------------------------------------------------------------------------

describe("showImageLightbox", () => {
  afterEach(() => {
    // Clean up any lightbox appended to body
    const boxes = ctx.appWindow.document.querySelectorAll(".image-lightbox");
    boxes.forEach(b => b.remove());
  });

  test("appends an .image-lightbox div to body", () => {
    ctx.appWindow.showImageLightbox("https://example.com/art.jpg");
    expect(ctx.appWindow.document.querySelector(".image-lightbox")).not.toBeNull();
  });

  test("lightbox contains an img with the given src", () => {
    ctx.appWindow.showImageLightbox("https://example.com/art.jpg");
    const img = ctx.appWindow.document.querySelector(".image-lightbox img");
    expect(img).not.toBeNull();
    expect(img.src).toContain("art.jpg");
  });

  test("clicking the lightbox removes it from the DOM", () => {
    ctx.appWindow.showImageLightbox("https://example.com/art.jpg");
    const box = ctx.appWindow.document.querySelector(".image-lightbox");
    box.click();
    expect(ctx.appWindow.document.querySelector(".image-lightbox")).toBeNull();
  });

  test("creates a new lightbox each call", () => {
    ctx.appWindow.showImageLightbox("https://example.com/a.jpg");
    ctx.appWindow.showImageLightbox("https://example.com/b.jpg");
    expect(ctx.appWindow.document.querySelectorAll(".image-lightbox").length).toBe(2);
  });
});

// ---------------------------------------------------------------------------
// MusicBrainz and Harmony sections in modal
// ---------------------------------------------------------------------------

describe("openModal MusicBrainz and Harmony sections", () => {
  afterEach(() => {
    ctx.appWindow.fetch.mockClear();
    // Close modal
    const overlay = ctx.appWindow.document.getElementById("modal-overlay");
    if (overlay) overlay.style.display = "none";
    const body = ctx.appWindow.document.getElementById("modal-body");
    if (body) body.innerHTML = "";
  });

  const albumData = {
    store_adam_id: "12345",
    title: "Test Album",
    artist: "Test Artist",
    artist_id: "ART1",
    artist_url: "https://music.apple.com/us/artist/1",
    url: "https://music.apple.com/us/album/12345",
    storefronts: ["us", "jp"],
    release_date: "2024-01-15",
    artwork_url: null,
    track_count: 10,
    genre: "Pop",
    description: null,
    upc: "123456789",
    audio_formats: [],
    artists_json: [],
  };

  test("renders MusicBrainz check button in modal", async () => {
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(albumData),
    });
    ctx.appWindow.__test_state.metadataStorefront = "us";
    ctx.appWindow.__test_state.configuredStorefronts = ["us", "jp"];

    await ctx.appWindow.openModal("12345");

    const body = ctx.appWindow.document.getElementById("modal-body");
    const sections = body.querySelectorAll(".cli-scheduler-section");
    const labels = Array.from(sections).map(s => {
      const lbl = s.querySelector(".cli-scheduler-label");
      return lbl ? lbl.textContent : "";
    });
    expect(labels).toContain("MusicBrainz");
    expect(labels).toContain("Harmony");
  });

  test("MusicBrainz header link falls back to search when artist has no MBID", async () => {
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(albumData),
    });
    ctx.appWindow.__test_state.metadataStorefront = "us";

    await ctx.appWindow.openModal("12345");

    const body = ctx.appWindow.document.getElementById("modal-body");
    const mbLink = Array.from(body.querySelectorAll(".btn-header-action"))
      .find(el => el.textContent.includes("MusicBrainz"));
    expect(mbLink).not.toBeUndefined();
    expect(mbLink.href).toContain("musicbrainz.org/search");
    expect(mbLink.href).toContain("Test%20Artist");
  });

  test("MusicBrainz header link points directly at the artist when MBID is set", async () => {
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ...albumData, artist_musicbrainz_id: "mbid-abc-123" }),
    });
    ctx.appWindow.__test_state.metadataStorefront = "us";

    await ctx.appWindow.openModal("12345");

    const body = ctx.appWindow.document.getElementById("modal-body");
    const mbLink = Array.from(body.querySelectorAll(".btn-header-action"))
      .find(el => el.textContent.includes("MusicBrainz"));
    expect(mbLink).not.toBeUndefined();
    expect(mbLink.href).toBe("https://musicbrainz.org/artist/mbid-abc-123");
    expect(mbLink.href).not.toContain("/search");
  });

  test("Harmony buttons use correct URL structure", async () => {
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(albumData),
    });
    ctx.appWindow.__test_state.metadataStorefront = "us";
    ctx.appWindow.__test_state.homeStorefront = "jp";
    ctx.appWindow.__test_state.configuredStorefronts = ["us", "jp", "hk"];

    await ctx.appWindow.openModal("12345");

    const body = ctx.appWindow.document.getElementById("modal-body");
    const sections = body.querySelectorAll(".cli-scheduler-section");
    const harmonySection = Array.from(sections).find(s => {
      const lbl = s.querySelector(".cli-scheduler-label");
      return lbl && lbl.textContent === "Harmony";
    });
    expect(harmonySection).not.toBeUndefined();

    const btns = harmonySection.querySelectorAll(".btn-cli-sf");
    expect(btns.length).toBeGreaterThan(0);
    // First button should be for metadataStorefront (US)
    expect(btns[0].textContent).toBe("US");
    expect(btns[0].href).toContain("harmony.pulsewidth.org.uk");
    expect(btns[0].href).toContain("music.apple.com");
    expect(btns[0].target).toBe("_blank");

    // Must include all required Harmony params
    const url = new URL(btns[0].href);
    expect(url.searchParams.has("gtin")).toBe(true);
    expect(url.searchParams.has("region")).toBe(true);
    expect(url.searchParams.get("category")).toBe("preferred");
    // Provider overrides are left to Harmony's "preferred" category
    for (const p of ["musicbrainz", "deezer", "itunes", "spotify", "tidal"]) {
      expect(url.searchParams.has(p)).toBe(false);
    }
    // region should be uppercased configured storefronts
    expect(url.searchParams.get("region")).toBe("US,JP,HK");
  });
});

// ---------------------------------------------------------------------------
// You Might Also Like — discover-similar button inside the album modal
// ---------------------------------------------------------------------------

describe("openModal You Might Also Like", () => {
  const albumData = {
    store_adam_id: "12345",
    title: "Test Album",
    artist: "Test Artist",
    artist_id: "ART1",
    artist_url: "https://music.apple.com/us/artist/1",
    url: "https://music.apple.com/us/album/12345",
    storefronts: ["us"],
    release_date: "2024-01-15",
    artwork_url: null,
    track_count: 0,
    genre: "Pop",
    description: null,
    upc: "123456789",
    audio_formats: [],
    artists_json: [],
  };

  afterEach(() => {
    ctx.appWindow.fetch.mockClear();
    const overlay = ctx.appWindow.document.getElementById("modal-overlay");
    if (overlay) overlay.style.display = "none";
    const body = ctx.appWindow.document.getElementById("modal-body");
    if (body) body.innerHTML = "";
  });

  test("renders button and shows album grid after click", async () => {
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(albumData),
    });
    ctx.appWindow.__test_state.metadataStorefront = "us";

    await ctx.appWindow.openModal("12345");

    const body = ctx.appWindow.document.getElementById("modal-body");
    const btn = body.querySelector(".btn-discover-similar");
    expect(btn).not.toBeNull();
    expect(btn.textContent).toContain("Discover Similar");
    const heading = body.querySelector(".discover-results-section h3");
    expect(heading).not.toBeNull();
    expect(heading.textContent).toBe("You Might Also Like");

    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        results: [
          { store_adam_id: "A2", title: "Suggested", artist: "Other", artists: [{ name: "Other", url: null }],
            artwork_url: null, release_date: "2024-02-01", url: null, storefronts: ["us"], watched: false },
        ],
      }),
    });

    btn.click();
    await new Promise(r => setTimeout(r, 0));
    await new Promise(r => setTimeout(r, 0));

    const section = body.querySelector(".discover-results-section");
    expect(section).not.toBeNull();
    const cards = section.querySelectorAll(".discover-grid .album-card");
    expect(cards.length).toBe(1);
    expect(cards[0].dataset.id).toBe("A2");
  });

  test("shows empty-state text when no suggestions are returned", async () => {
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(albumData),
    });
    ctx.appWindow.__test_state.metadataStorefront = "us";

    await ctx.appWindow.openModal("12345");

    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ results: [] }),
    });

    const body = ctx.appWindow.document.getElementById("modal-body");
    body.querySelector(".btn-discover-similar").click();
    await new Promise(r => setTimeout(r, 0));
    await new Promise(r => setTimeout(r, 0));

    const empty = body.querySelector(".discover-results-section .discover-empty");
    expect(empty).not.toBeNull();
    expect(empty.textContent).toMatch(/No suggestions/i);
  });
});

// ---------------------------------------------------------------------------
// Music video track handling in modal
// ---------------------------------------------------------------------------

describe("openModal music video tracks", () => {
  const makeAlbumData = (extra = {}) => ({
    store_adam_id: "12345",
    title: "Test Single",
    artist: "Test Artist",
    artist_id: "ART1",
    artist_url: "https://music.apple.com/us/artist/1",
    url: "https://music.apple.com/us/album/12345",
    storefronts: ["us"],
    release_date: "2024-01-15",
    artwork_url: null,
    track_count: 2,
    music_video_count: 1,
    genre: "Pop",
    description: null,
    upc: null,
    audio_formats: [],
    artists_json: [],
    tracks: [
      { title: "Song A", track_number: 1, duration_ms: 200000, is_music_video: false },
      { title: "Song A", track_number: 2, duration_ms: 198000, is_music_video: true },
    ],
    ...extra,
  });

  afterEach(() => {
    ctx.appWindow.fetch.mockClear();
    const overlay = ctx.appWindow.document.getElementById("modal-overlay");
    if (overlay) overlay.style.display = "none";
    const body = ctx.appWindow.document.getElementById("modal-body");
    if (body) body.innerHTML = "";
  });

  test("track count tag shows X+Y when music_video_count > 0", async () => {
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(makeAlbumData()),
    });
    ctx.appWindow.__test_state.metadataStorefront = null;

    await ctx.appWindow.openModal("12345");

    const body = ctx.appWindow.document.getElementById("modal-body");
    const tags = Array.from(body.querySelectorAll(".modal-tag"));
    const trackTag = tags.find(t => t.textContent.includes("🎵"));
    expect(trackTag).not.toBeUndefined();
    expect(trackTag.textContent).toContain("1+1");
  });

  test("track count tag shows plain count when no music videos", async () => {
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(makeAlbumData({ track_count: 10, music_video_count: 0, tracks: [] })),
    });
    ctx.appWindow.__test_state.metadataStorefront = null;

    await ctx.appWindow.openModal("12345");

    const body = ctx.appWindow.document.getElementById("modal-body");
    const tags = Array.from(body.querySelectorAll(".modal-tag"));
    const trackTag = tags.find(t => t.textContent.includes("🎵"));
    expect(trackTag).not.toBeUndefined();
    expect(trackTag.textContent).toContain("10");
    expect(trackTag.textContent).not.toContain("+");
  });

  test("tracklist header shows songs + videos count", async () => {
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(makeAlbumData()),
    });
    ctx.appWindow.__test_state.metadataStorefront = null;

    await ctx.appWindow.openModal("12345");

    const body = ctx.appWindow.document.getElementById("modal-body");
    const header = body.querySelector(".tracklist-header");
    expect(header).not.toBeNull();
    expect(header.textContent).toMatch(/1 track/);
    expect(header.textContent).toMatch(/1 video/);
  });

  test("music video track row has MV badge", async () => {
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(makeAlbumData()),
    });
    ctx.appWindow.__test_state.metadataStorefront = null;

    await ctx.appWindow.openModal("12345");

    const body = ctx.appWindow.document.getElementById("modal-body");
    const rows = body.querySelectorAll(".track-row");
    expect(rows.length).toBe(2);
    // Row 1: song — no badge
    expect(rows[0].querySelector(".track-mv-badge")).toBeNull();
    // Row 2: music video — has badge
    expect(rows[1].querySelector(".track-mv-badge")).not.toBeNull();
    expect(rows[1].querySelector(".track-mv-badge").textContent).toBe("MV");
  });
});

// ---------------------------------------------------------------------------
// "Show info" — extended track/album metadata from the existing lookup
// ---------------------------------------------------------------------------

describe("openModal Show info", () => {
  const dbAlbum = {
    store_adam_id: "777",
    title: "Piecemeal Album",
    artist: "Test Artist",
    artist_id: "ART1",
    url: "https://music.apple.com/jp/album/777",
    storefronts: ["jp"],
    release_date: "2025-03-01",
    track_count: 3,
    music_video_count: 0,
    upc: "0000111",
    audio_formats: [],
    artists_json: [],
  };
  const lookup = {
    title: "Piecemeal Album",
    artist: "Test Artist",
    release_date: "2025-03-01",
    source: "apple_music",
    storefront: "jp",
    record_label: "Test Records",
    copyright: "℗ 2025 Test Records",
    is_complete: true,
    is_compilation: false,
    tracks: [
      { title: "Single 1", track_number: 1, duration_ms: 1000, release_date: "2024-10-01",
        isrc: "JPAAA2400001", has_lyrics: true, has_synced_lyrics: true, artist: "Test Artist" },
      { title: "Single 2", track_number: 2, duration_ms: 1000, release_date: "2025-01-10",
        isrc: "JPAAA2500001", has_lyrics: true, has_synced_lyrics: false, artist: "Test Artist feat. Guest",
        composer: "Writer" },
      { title: "New Song", track_number: 3, duration_ms: 1000, release_date: "2025-03-01",
        isrc: "JPAAA2500002", has_lyrics: false, has_synced_lyrics: false, artist: "Test Artist" },
    ],
  };

  // Route fetch by URL; record every path requested.
  let calls;
  function routeFetch(routes) {
    calls = [];
    ctx.appWindow.fetch.mockImplementation((path) => {
      calls.push(path);
      for (const [frag, body] of routes) {
        if (path.includes(frag)) {
          if (body === 404) return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) });
          // Clone: openModal mutates the album object it receives.
          return Promise.resolve({ ok: true, json: () => Promise.resolve(JSON.parse(JSON.stringify(body))) });
        }
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });
  }
  const body = () => ctx.appWindow.document.getElementById("modal-body");
  const lookupCalls = () => calls.filter(p => p.includes("/lookup"));

  beforeEach(() => {
    const s = ctx.appWindow.__test_state;
    s.metadataStorefront = "jp";
    s.homeStorefront = "jp";
    s.alwaysIncludeMY = false;
    ctx.appWindow.localStorage.removeItem("release_info_collapsed");
  });

  afterEach(() => {
    ctx.appWindow.fetch.mockReset();
    ctx.appWindow.fetch.mockImplementation(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({ items: [], total: 0 }) }));
    body().innerHTML = "";
  });

  test("info is hidden by default and the toggle reveals it without another request", async () => {
    routeFetch([["/lookup", lookup], ["/api/releases/777", dbAlbum]]);
    await ctx.appWindow.openModal("777");

    const section = body().querySelector(".track-section");
    const btn = body().querySelector(".tracklist-header .btn-track-info");
    expect(btn).not.toBeNull();
    expect(btn.textContent).toContain("Show info");
    expect(section.classList.contains("show-track-info")).toBe(false);
    expect(lookupCalls()).toHaveLength(1);

    const before = calls.length;
    btn.click();
    expect(section.classList.contains("show-track-info")).toBe(true);
    expect(btn.classList.contains("active")).toBe(true);
    expect(btn.textContent).toContain("Hide info");
    expect(calls.length).toBe(before);

    btn.click();
    expect(section.classList.contains("show-track-info")).toBe(false);
  });

  test("toggle is per album: the next modal opens with track info collapsed", async () => {
    routeFetch([["/lookup", lookup], ["/api/releases/777", dbAlbum]]);
    await ctx.appWindow.openModal("777");
    body().querySelector(".btn-track-info").click();
    expect(body().querySelector(".track-section").classList.contains("show-track-info")).toBe(true);

    await ctx.appWindow.openModal("777");
    const btn = body().querySelector(".btn-track-info");
    expect(body().querySelector(".track-section").classList.contains("show-track-info")).toBe(false);
    expect(btn.textContent).toContain("Show info");
  });

  test("release info is shown without toggling, above the tracklist", async () => {
    routeFetch([["/lookup", lookup], ["/api/releases/777", dbAlbum]]);
    await ctx.appWindow.openModal("777");
    expect(body().querySelector(".track-section").classList.contains("show-track-info")).toBe(false);
    const panel = body().querySelector(".album-info-panel");
    expect(panel.classList.contains("collapsed")).toBe(false);
    expect(body().querySelector(".album-info-panel + .track-section .tracklist")).not.toBeNull();
    expect(panel.querySelectorAll(".aip-note.modal-tag").length).toBeGreaterThan(0);
  });

  test("track info lines show dates, lyrics, ISRC, featured artist and composer", async () => {
    routeFetch([["/lookup", lookup], ["/api/releases/777", dbAlbum]]);
    await ctx.appWindow.openModal("777");

    const lines = body().querySelectorAll(".track-row .track-info-line");
    expect(lines).toHaveLength(3);
    expect(lines[0].querySelector(".ti-date").classList.contains("ti-early")).toBe(true);
    expect(lines[0].querySelector(".ti-lyrics").textContent).toBe("Synced lyrics");
    expect(lines[0].querySelector(".ti-isrc").textContent).toBe("JPAAA2400001");
    expect(lines[1].querySelector(".ti-lyrics").textContent).toBe("Lyrics");
    expect(lines[1].textContent).toContain("Test Artist feat. Guest");
    expect(lines[1].querySelector(".ti-composer").textContent).toContain("Writer");
    // Same-day track is not flagged; album artist is not repeated
    expect(lines[2].querySelector(".ti-date").classList.contains("ti-early")).toBe(false);
    expect(lines[2].querySelector(".ti-lyrics").classList.contains("ti-none")).toBe(true);
    expect(lines[2].textContent).not.toContain("Test Artist");
  });

  test("release info panel summarizes pre-released tracks, lyrics and label", async () => {
    routeFetch([["/lookup", lookup], ["/api/releases/777", dbAlbum]]);
    await ctx.appWindow.openModal("777");

    const panel = body().querySelector(".album-info-panel");
    expect(panel).not.toBeNull();
    const text = panel.textContent;
    expect(text).toContain("2 of 3 tracks released before the album");
    expect(text).toContain("Lyrics on 2 of 3 tracks · 1 synced");
    expect(text).toContain("Test Records");
    expect(text).toContain("℗ 2025 Test Records");
    expect(text).toContain("0000111");  // UPC from the DB row survives a lookup without one
    expect(panel.querySelector(".sf-chip")).not.toBeNull();
    expect(text).not.toContain("Incomplete");
  });

  test("flags an album whose tracks were all released earlier", async () => {
    const compilation = {
      ...lookup,
      is_compilation: true,
      tracks: lookup.tracks.map(t => ({ ...t, release_date: "2020-01-01" })),
    };
    routeFetch([["/lookup", compilation], ["/api/releases/777", dbAlbum]]);
    await ctx.appWindow.openModal("777");
    const text = body().querySelector(".album-info-panel").textContent;
    expect(text).toContain("All 3 tracks were released before this album");
    expect(text).toContain("Compilation");
  });

  test("notes an incomplete album", async () => {
    routeFetch([["/lookup", { ...lookup, is_complete: false, track_count: 5 }], ["/api/releases/777", dbAlbum]]);
    await ctx.appWindow.openModal("777");
    expect(body().querySelector(".album-info-panel").textContent).toContain("Incomplete — 3 of 5 tracks");
  });

  test("comparison tracklist gets its own info lines from the home-storefront lookup", async () => {
    const s = ctx.appWindow.__test_state;
    s.homeStorefront = "my";
    s.alwaysIncludeMY = true;
    const myLookup = {
      ...lookup,
      tracks: lookup.tracks.map((t, i) => ({ ...t, title: `${t.title} (EN)`, isrc: `MYISRC${i}` })),
    };
    routeFetch([["storefront=my", myLookup], ["storefront=jp", lookup], ["/api/releases/777", dbAlbum]]);
    await ctx.appWindow.openModal("777");

    expect(lookupCalls()).toHaveLength(2);
    const lists = body().querySelectorAll(".tracklist");
    expect(lists).toHaveLength(2);
    expect(lists[1].querySelector(".ti-isrc").textContent).toBe("MYISRC0");
  });

  test("metadata source off: one on-demand lookup, then info is shown", async () => {
    const s = ctx.appWindow.__test_state;
    s.metadataStorefront = "";
    routeFetch([["/lookup", lookup], ["/api/releases/777", dbAlbum]]);
    await ctx.appWindow.openModal("777");

    expect(lookupCalls()).toHaveLength(0);
    expect(body().querySelectorAll(".track-row")).toHaveLength(0);
    // Release Info still renders from the DB row (date, UPC); no chip selected yet
    const dbPanel = body().querySelector(".album-info-panel");
    expect(dbPanel.querySelector(".aip-body").textContent).toContain("0000111");
    expect(dbPanel.querySelector(".aip-sf-chip.selected")).toBeNull();
    const btn = body().querySelector(".btn-track-info");
    expect(btn).not.toBeNull();

    btn.click();
    await new Promise(r => setTimeout(r, 0));
    await new Promise(r => setTimeout(r, 0));

    expect(lookupCalls()).toEqual(["/api/releases/777/lookup?storefront=jp"]);
    expect(body().querySelectorAll(".track-row")).toHaveLength(3);
    expect(body().querySelector(".track-section").classList.contains("show-track-info")).toBe(true);
    // Release Info switches to the storefront that was just loaded
    expect(body().querySelector(".aip-sf-chip.selected").textContent).toBe("JP");
    expect(body().querySelector(".album-info-panel").textContent).toContain("Test Records");
  });

  test("lookup that returned no tracks shows the note, not a re-fetch button", async () => {
    routeFetch([["/lookup", { ...lookup, tracks: [] }], ["/api/releases/777", dbAlbum]]);
    await ctx.appWindow.openModal("777");
    expect(body().querySelector(".btn-track-info")).toBeNull();
    expect(body().querySelector(".tracklist-empty")).not.toBeNull();
    // Album-level info from the lookup is still shown
    expect(body().querySelector(".album-info-panel").textContent).toContain("Test Records");
  });

  test("album not in local DB reuses the in-flight lookup instead of fetching twice", async () => {
    routeFetch([["/lookup", lookup], ["/api/releases/777", 404]]);
    await ctx.appWindow.openModal("777");

    expect(lookupCalls()).toHaveLength(1);
    expect(body().querySelector(".modal-title").textContent).toBe("Piecemeal Album");
    expect(body().querySelectorAll(".track-row")).toHaveLength(3);
    expect(body().querySelector(".album-info-panel").textContent).toContain("Test Records");
  });
});

// ---------------------------------------------------------------------------
// Release Info section: persistent collapse + per-storefront chips
// ---------------------------------------------------------------------------

describe("openModal Release Info", () => {
  const dbAlbum = {
    store_adam_id: "888", title: "Multi SF", artist: "A", artist_id: "ART1",
    url: "https://music.apple.com/jp/album/888", storefronts: ["jp", "hk", "tw"],
    release_date: "2025-03-01", track_count: 2, upc: "999", audio_formats: [], artists_json: [],
  };
  const mkLookup = (sf, label, date) => ({
    title: "Multi SF", artist: "A", release_date: date, storefront: sf, record_label: label,
    tracks: [
      { title: "One", track_number: 1, release_date: "2024-01-01", has_lyrics: true, has_synced_lyrics: true },
      { title: "Two", track_number: 2, release_date: date, has_lyrics: false, has_synced_lyrics: false },
    ],
  });
  const bySf = { jp: mkLookup("jp", "JP Label", "2025-03-01"), my: mkLookup("my", "MY Label", "2025-03-01"),
                 hk: mkLookup("hk", "HK Label", "2025-03-08"), tw: { title: null, tracks: [] } };

  let calls;
  const route = () => {
    calls = [];
    ctx.appWindow.fetch.mockImplementation((path) => {
      calls.push(path);
      const m = path.match(/lookup\?storefront=(\w+)/);
      const bodyData = m ? bySf[m[1]] : dbAlbum;
      return Promise.resolve({ ok: true, json: () => Promise.resolve(JSON.parse(JSON.stringify(bodyData))) });
    });
  };
  const body = () => ctx.appWindow.document.getElementById("modal-body");
  const panel = () => body().querySelector(".album-info-panel");
  const chip = (code) => [...panel().querySelectorAll(".aip-sf-chip")].find(c => c.textContent === code);
  const lookupsFor = (sf) => calls.filter(p => p.endsWith(`lookup?storefront=${sf}`)).length;
  const flush = async () => { for (let i = 0; i < 3; i++) await new Promise(r => setTimeout(r, 0)); };

  beforeEach(() => {
    const s = ctx.appWindow.__test_state;
    s.metadataStorefront = "jp";
    s.homeStorefront = "my";
    s.alwaysIncludeMY = true;
    ctx.appWindow.localStorage.removeItem("release_info_collapsed");
    route();
  });

  afterEach(() => {
    ctx.appWindow.fetch.mockReset();
    ctx.appWindow.fetch.mockImplementation(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({ items: [], total: 0 }) }));
    body().innerHTML = "";
    ctx.appWindow.__test_state.alwaysIncludeMY = false;
    ctx.appWindow.localStorage.removeItem("release_info_collapsed");
  });

  test("shows a chip per storefront, metadata storefront selected by default", async () => {
    await ctx.appWindow.openModal("888");
    const codes = [...panel().querySelectorAll(".aip-sf-chip")].map(c => c.textContent);
    expect(codes).toEqual(["JP", "MY", "HK", "TW"]);
    expect(chip("JP").classList.contains("selected")).toBe(true);
    expect(panel().querySelector(".aip-body").textContent).toContain("JP Label");
  });

  test("switching to an already-fetched storefront is instant and sends no request", async () => {
    await ctx.appWindow.openModal("888");
    const before = calls.length;
    chip("MY").click();
    expect(chip("MY").classList.contains("selected")).toBe(true);
    expect(chip("JP").classList.contains("selected")).toBe(false);
    expect(panel().querySelector(".aip-body").textContent).toContain("MY Label");
    expect(calls.length).toBe(before);
  });

  test("other storefronts are fetched once on click, then reused", async () => {
    await ctx.appWindow.openModal("888");
    expect(lookupsFor("hk")).toBe(0);
    chip("HK").click();
    expect(panel().querySelector(".aip-status").textContent).toContain("Loading HK");
    await flush();
    const text = panel().querySelector(".aip-body").textContent;
    expect(text).toContain("HK Label");
    expect(text).toContain("8 Mar 2025");  // HK's own release date
    chip("JP").click();
    chip("HK").click();
    await flush();
    expect(lookupsFor("hk")).toBe(1);
    expect(lookupsFor("jp")).toBe(1);
  });

  test("storefront with no data shows a neutral note", async () => {
    await ctx.appWindow.openModal("888");
    chip("TW").click();
    await flush();
    expect(panel().querySelector(".aip-status").textContent).toContain("No release info from the TW storefront");
  });

  test("collapse persists across albums and is saved as a preference", async () => {
    await ctx.appWindow.openModal("888");
    const toggle = panel().querySelector(".aip-toggle");
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(panel().querySelector(".aip-chevron").textContent).toBe("▾");
    toggle.click();
    expect(panel().classList.contains("collapsed")).toBe(true);
    expect(panel().querySelector(".aip-chevron").textContent).toBe("▸");
    expect(ctx.appWindow.__test_ReleaseInfoPrefs.isCollapsed()).toBe(true);

    await ctx.appWindow.openModal("888");
    expect(panel().classList.contains("collapsed")).toBe(true);
    expect(panel().querySelector(".aip-toggle").getAttribute("aria-expanded")).toBe("false");

    panel().querySelector(".aip-toggle").click();
    expect(ctx.appWindow.__test_ReleaseInfoPrefs.isCollapsed()).toBe(false);
    await ctx.appWindow.openModal("888");
    expect(panel().classList.contains("collapsed")).toBe(false);
  });

  test("track Show info stays per album even with release info collapsed", async () => {
    ctx.appWindow.__test_ReleaseInfoPrefs.setCollapsed(true);
    await ctx.appWindow.openModal("888");
    expect(body().querySelector(".track-section").classList.contains("show-track-info")).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Tracklist comparison helpers (track-info.js)
// ---------------------------------------------------------------------------

describe("groupTracklistComparisons", () => {
  const T = (...titles) => titles.map((title, i) => ({ title, track_number: i + 1 }));
  const group = (...a) => ctx.appWindow.groupTracklistComparisons(...a);

  test("drops comparisons that match the primary tracklist or have no tracks", () => {
    const primary = T("A", "B");
    expect(group(primary, [
      { sf: "my", data: { tracks: T("A", "B") } },
      { sf: "jp", data: { tracks: [] } },
      { sf: "hk", data: null },
    ])).toEqual([]);
  });

  test("merges storefronts that returned the same differing tracklist", () => {
    const groups = group(T("A", "B"), [
      { sf: "jp", data: { tracks: T("あ", "B") } },
      { sf: "my", data: { tracks: T("X", "Y") } },
      { sf: "hk", data: { tracks: T("あ", "B") } },
    ]);
    expect(groups.map(g => g.sfs)).toEqual([["jp", "hk"], ["my"]]);
  });

  test("nothing to compare when the primary tracklist is empty", () => {
    expect(group([], [{ sf: "jp", data: { tracks: T("A") } }])).toEqual([]);
  });
});

describe("buildTracklist multi-comparison", () => {
  const T = (...titles) => titles.map((title, i) => ({ title, track_number: i + 1 }));

  test("a row is marked when it differs from any comparison list", () => {
    const tl = ctx.appWindow.buildTracklist(T("A", "B", "C"), {
      compareLists: [T("A", "b", "C"), T("A", "B", "c")], diffClass: "track-differs", diffColor: "#6496ff",
    });
    const marked = [...tl.querySelectorAll(".track-row")].map(r => r.classList.contains("track-differs"));
    expect(marked).toEqual([false, true, true]);
    expect(tl.style.getPropertyValue("--diff-color")).toBe("#6496ff");
  });

  test("header shows a chip per storefront and rings the preferred one", () => {
    const tl = ctx.appWindow.buildTracklist(T("A"), { headerSf: ["jp", "my"], preferredSf: "jp" });
    const chips = [...tl.querySelectorAll(".tracklist-header .sf-chip")];
    expect(chips.map(c => c.textContent)).toEqual(["JP", "MY"]);
    expect(chips.map(c => c.classList.contains("sf-preferred"))).toEqual([true, false]);
  });
});

// ---------------------------------------------------------------------------
// Watched artist's preferred storefront as an extra comparison
// ---------------------------------------------------------------------------

describe("openModal preferred storefront comparison", () => {
  const T = (...titles) => titles.map((title, i) => ({ title, track_number: i + 1, duration_ms: 1000 }));
  const mk = (sf, tracks, extra = {}) => ({
    title: `Album ${sf.toUpperCase()}`, artist: "Artist", artist_id: "ART1", release_date: "2025-01-01",
    storefront: sf, record_label: `${sf.toUpperCase()} Label`, tracks, ...extra,
  });
  const dbAlbum = (extra = {}) => ({
    store_adam_id: "555", title: "DB Title", artist: "Artist", artist_id: "ART1",
    url: "https://music.apple.com/tw/album/555", storefronts: ["tw", "jp", "hk"],
    release_date: "2025-01-01", track_count: 2, upc: "111", audio_formats: [], artists_json: [],
    preferred_source: null, ...extra,
  });

  let calls;
  let bySf;
  let db;
  const route = () => {
    calls = [];
    ctx.appWindow.fetch.mockImplementation((path) => {
      calls.push(path);
      const m = path.match(/lookup\?storefront=(\w+)/);
      const data = m ? bySf[m[1]] : (path.startsWith("/api/releases/555") ? db : {});
      if (data === 404 || data === undefined) {
        return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve(JSON.parse(JSON.stringify(data))) });
    });
  };
  const body = () => ctx.appWindow.document.getElementById("modal-body");
  const lookups = () => calls.filter(p => p.includes("/lookup")).map(p => p.split("=")[1]);
  const headerChips = (tl) => [...tl.querySelectorAll(".tracklist-header .sf-chip")].map(c => c.textContent);
  const ringed = (sel) => [...body().querySelectorAll(`${sel} .sf-preferred, ${sel}.sf-preferred`)].map(c => c.textContent);

  beforeEach(() => {
    const s = ctx.appWindow.__test_state;
    s.metadataStorefront = "tw";
    s.homeStorefront = "my";
    s.alwaysIncludeMY = false;
    s.cliSchedulerEnabled = false;
    ctx.appWindow.localStorage.removeItem("release_info_collapsed");
    bySf = { tw: mk("tw", T("中文一", "中文二")), jp: mk("jp", T("日本語一", "日本語二")), my: mk("my", T("English 1", "English 2")) };
    db = dbAlbum();
    route();
  });

  afterEach(() => {
    ctx.appWindow.fetch.mockReset();
    ctx.appWindow.fetch.mockImplementation(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({ items: [], total: 0 }) }));
    body().innerHTML = "";
    ctx.appWindow.__test_state.alwaysIncludeMY = false;
  });

  test("unwatched artist: unchanged — only the metadata storefront is looked up", async () => {
    await ctx.appWindow.openModal("555");
    expect(lookups()).toEqual(["tw"]);
    expect(body().querySelector(".tracklist-diff-banner")).toBeNull();
    expect(body().querySelectorAll(".tracklist")).toHaveLength(1);
    expect(body().querySelector(".sf-preferred")).toBeNull();
    expect(body().querySelector(".modal-meta-sf-badge").textContent).not.toContain("preferred");
  });

  test("watched artist: preferred storefront is fetched and compared even with +HOME off", async () => {
    db = dbAlbum({ preferred_source: "jp" });
    await ctx.appWindow.openModal("555");
    expect(lookups().sort()).toEqual(["jp", "tw"]);
    // Metadata storefront stays primary
    expect(body().querySelector(".modal-title").textContent).toBe("Album TW");
    const banner = body().querySelector(".tracklist-diff-banner");
    expect(banner.textContent).toContain("TW");
    expect(banner.textContent).toContain("JP");
    const lists = body().querySelectorAll(".tracklist");
    expect(lists).toHaveLength(2);
    expect(headerChips(lists[1])).toEqual(["JP"]);
    expect(lists[1].style.getPropertyValue("--diff-color")).toBe(ctx.appWindow.sfColor("jp"));
    expect(lists[1].querySelectorAll(".track-differs")).toHaveLength(2);
    const badge = body().querySelector(".modal-meta-sf-badge");
    expect(badge.textContent).toContain("preferred source");
    expect(badge.querySelector(".sf-preferred").textContent).toBe("JP");
  });

  test("three-way: metadata vs preferred vs home, in that order", async () => {
    ctx.appWindow.__test_state.alwaysIncludeMY = true;
    db = dbAlbum({ preferred_source: "jp" });
    await ctx.appWindow.openModal("555");
    expect(lookups().sort()).toEqual(["jp", "my", "tw"]);
    const lists = body().querySelectorAll(".tracklist");
    expect(lists).toHaveLength(3);
    expect(headerChips(lists[0])).toEqual(["TW"]);
    expect(headerChips(lists[1])).toEqual(["JP"]);
    expect(headerChips(lists[2])).toEqual(["MY"]);
    // Release Info: metadata, preferred, home, then the other storefronts seen
    const infoChips = [...body().querySelectorAll(".aip-sf-chip")];
    expect(infoChips.map(c => c.textContent)).toEqual(["TW", "JP", "MY", "HK"]);
    expect(infoChips.filter(c => c.classList.contains("sf-preferred")).map(c => c.textContent)).toEqual(["JP"]);
    // The preferred storefront's release info is already loaded — no extra request
    const before = calls.length;
    infoChips[1].click();
    expect(body().querySelector(".aip-body").textContent).toContain("JP Label");
    expect(calls.length).toBe(before);
  });

  test("storefronts with the same differing tracklist are shown once", async () => {
    ctx.appWindow.__test_state.alwaysIncludeMY = true;
    bySf.my = mk("my", T("日本語一", "日本語二"));
    db = dbAlbum({ preferred_source: "jp" });
    await ctx.appWindow.openModal("555");
    const lists = body().querySelectorAll(".tracklist");
    expect(lists).toHaveLength(2);
    expect(headerChips(lists[1])).toEqual(["JP", "MY"]);
  });

  test("preferred = metadata storefront: no extra request, metadata chip is ringed", async () => {
    db = dbAlbum({ preferred_source: "tw" });
    await ctx.appWindow.openModal("555");
    expect(lookups()).toEqual(["tw"]);
    const badge = body().querySelector(".modal-meta-sf-badge");
    expect(badge.textContent).toContain("metadata · preferred source");
    expect(badge.querySelector(".sf-preferred").textContent).toBe("TW");
  });

  test("preferred = home with +HOME on: home is fetched once and compared once", async () => {
    ctx.appWindow.__test_state.alwaysIncludeMY = true;
    db = dbAlbum({ preferred_source: "my" });
    await ctx.appWindow.openModal("555");
    expect(lookups().sort()).toEqual(["my", "tw"]);
    const lists = body().querySelectorAll(".tracklist");
    expect(lists).toHaveLength(2);
    expect(headerChips(lists[1])).toEqual(["MY"]);
    expect(lists[1].querySelector(".tracklist-header .sf-preferred").textContent).toBe("MY");
  });

  test("metadata source Off: no Apple Music calls, but the preferred storefront is still highlighted", async () => {
    ctx.appWindow.__test_state.metadataStorefront = "";
    db = dbAlbum({ preferred_source: "jp" });
    await ctx.appWindow.openModal("555");
    expect(lookups()).toEqual([]);
    expect(ringed(".modal-tags")).toEqual(["JP"]);
    const harmony = [...body().querySelectorAll(".cli-scheduler-section")]
      .find(s => s.querySelector(".cli-scheduler-label").textContent === "Harmony");
    expect([...harmony.querySelectorAll(".btn-cli-sf")].map(b => b.textContent)).toEqual(["JP", "MY"]);
  });

  test("Harmony and CLI Scheduler start with metadata, preferred, then home", async () => {
    ctx.appWindow.__test_state.cliSchedulerEnabled = true;
    db = dbAlbum({ preferred_source: "jp" });
    await ctx.appWindow.openModal("555");
    const sections = [...body().querySelectorAll(".cli-scheduler-section")];
    const btns = (label) => [...sections.find(s => s.querySelector(".cli-scheduler-label").textContent === label)
      .querySelectorAll(".btn-cli-sf")];
    for (const label of ["Harmony", "CLI Scheduler"]) {
      expect(btns(label).map(b => b.textContent)).toEqual(["TW", "JP", "MY"]);
      expect(btns(label).filter(b => b.classList.contains("sf-preferred")).map(b => b.textContent)).toEqual(["JP"]);
    }
    expect(ringed(".modal-tags")).toEqual(["JP"]);
  });

  test("album not in the DB: the lookup's preferred_source triggers the comparison", async () => {
    db = 404;
    bySf.tw = mk("tw", T("中文一", "中文二"), { preferred_source: "jp" });
    await ctx.appWindow.openModal("555");
    expect(lookups()).toEqual(["tw", "jp"]);
    expect(body().querySelectorAll(".tracklist")).toHaveLength(2);
    expect(body().querySelector(".modal-meta-sf-badge .sf-preferred").textContent).toBe("JP");
  });

  test("preferred storefront without the album: modal still renders and says so", async () => {
    bySf.jp = 404;
    db = dbAlbum({ preferred_source: "jp" });
    await ctx.appWindow.openModal("555");
    expect(body().querySelector(".modal-title").textContent).toBe("Album TW");
    expect(body().querySelectorAll(".tracklist")).toHaveLength(1);
    expect(body().querySelector(".modal-meta-sf-badge").textContent).toContain("preferred source (not available)");
  });

  test("matching tracklists: no banner, preferred data still available in Release Info", async () => {
    bySf.jp = mk("jp", T("中文一", "中文二"));
    db = dbAlbum({ preferred_source: "jp" });
    await ctx.appWindow.openModal("555");
    expect(body().querySelector(".tracklist-diff-banner")).toBeNull();
    expect(body().querySelectorAll(".tracklist")).toHaveLength(1);
    const jpChip = [...body().querySelectorAll(".aip-sf-chip")].find(c => c.textContent === "JP");
    const before = calls.length;
    jpChip.click();
    expect(body().querySelector(".aip-body").textContent).toContain("JP Label");
    expect(calls.length).toBe(before);
  });
});
