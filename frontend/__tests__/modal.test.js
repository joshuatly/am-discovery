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
  });
});
