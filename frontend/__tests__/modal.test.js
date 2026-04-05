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
