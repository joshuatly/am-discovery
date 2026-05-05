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

  test("renders MusicBrainz artist link in modal header", async () => {
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
    expect(url.searchParams.has("musicbrainz")).toBe(true);
    expect(url.searchParams.has("deezer")).toBe(true);
    expect(url.searchParams.has("itunes")).toBe(true);
    expect(url.searchParams.has("spotify")).toBe(true);
    expect(url.searchParams.has("tidal")).toBe(true);
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
