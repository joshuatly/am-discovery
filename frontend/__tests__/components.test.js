"use strict";

const ctx = require("./setup-jsdom");

// ---------------------------------------------------------------------------
// sfChips
// ---------------------------------------------------------------------------

describe("sfChips", () => {
  test("returns a div element", () => {
    expect(ctx.appWindow.sfChips([]).tagName).toBe("DIV");
  });

  test("has class sf-chips", () => {
    expect(ctx.appWindow.sfChips([]).className).toBe("sf-chips");
  });

  test("creates one chip per storefront", () => {
    expect(ctx.appWindow.sfChips(["us", "jp", "hk"]).children.length).toBe(3);
  });

  test("chip text is uppercased storefront code", () => {
    const chips = ctx.appWindow.sfChips(["us"]);
    expect(chips.children[0].textContent).toBe("US");
  });

  test("chip className includes sf-chip and storefront code", () => {
    const chips = ctx.appWindow.sfChips(["jp"]);
    expect(chips.children[0].className).toContain("sf-chip");
    expect(chips.children[0].className).toContain("jp");
  });

  test("handles empty array — no chips", () => {
    expect(ctx.appWindow.sfChips([]).children.length).toBe(0);
  });

  test("handles null — no chips", () => {
    expect(ctx.appWindow.sfChips(null).children.length).toBe(0);
  });

  test("handles undefined — no chips", () => {
    expect(ctx.appWindow.sfChips(undefined).children.length).toBe(0);
  });

  test("preserves order of storefronts", () => {
    const chips = ctx.appWindow.sfChips(["us", "jp", "hk"]);
    expect(chips.children[0].textContent).toBe("US");
    expect(chips.children[1].textContent).toBe("JP");
    expect(chips.children[2].textContent).toBe("HK");
  });
});

// ---------------------------------------------------------------------------
// sfPaletteColor / sfChipInlineStyle / sfChipHtml / applysfChipColor
// ---------------------------------------------------------------------------

describe("sfPaletteColor", () => {
  test("returns an object with bg and fg", () => {
    const color = ctx.appWindow.sfPaletteColor("us");
    expect(color).toHaveProperty("bg");
    expect(color).toHaveProperty("fg");
  });

  test("same storefront always returns same color (deterministic)", () => {
    expect(ctx.appWindow.sfPaletteColor("kr")).toEqual(ctx.appWindow.sfPaletteColor("kr"));
  });

  test("different storefronts may return different colors", () => {
    const codes = ["us", "kr", "gb", "au", "fr", "de", "cn", "in"];
    const colors = codes.map(c => ctx.appWindow.sfPaletteColor(c).fg);
    const unique = new Set(colors);
    expect(unique.size).toBeGreaterThan(1);
  });
});

describe("sfChipInlineStyle", () => {
  test("returns empty string for known storefronts", () => {
    expect(ctx.appWindow.sfChipInlineStyle("hk")).toBe("");
    expect(ctx.appWindow.sfChipInlineStyle("jp")).toBe("");
    expect(ctx.appWindow.sfChipInlineStyle("my")).toBe("");
    expect(ctx.appWindow.sfChipInlineStyle("tw")).toBe("");
    expect(ctx.appWindow.sfChipInlineStyle("sg")).toBe("");
  });

  test("returns non-empty style string for unknown storefront", () => {
    const style = ctx.appWindow.sfChipInlineStyle("us");
    expect(style.length).toBeGreaterThan(0);
    expect(style).toContain("background:");
    expect(style).toContain("color:");
  });

  test("is case-insensitive — HK treated as known", () => {
    expect(ctx.appWindow.sfChipInlineStyle("HK")).toBe("");
  });
});

describe("sfChipHtml", () => {
  test("known storefront has no inline style attribute", () => {
    const html = ctx.appWindow.sfChipHtml("jp");
    expect(html).not.toContain("style=");
    expect(html).toContain("sf-chip jp");
    expect(html).toContain("JP");
  });

  test("unknown storefront includes inline style", () => {
    const html = ctx.appWindow.sfChipHtml("us");
    expect(html).toContain("style=");
    expect(html).toContain("sf-chip us");
    expect(html).toContain("US");
  });

  test("extra style is merged in", () => {
    const html = ctx.appWindow.sfChipHtml("us", "font-size:10px;");
    expect(html).toContain("font-size:10px;");
  });

  test("extra style applies to known storefronts too", () => {
    const html = ctx.appWindow.sfChipHtml("jp", "vertical-align:middle;");
    expect(html).toContain("style=");
    expect(html).toContain("vertical-align:middle;");
  });
});

describe("applysfChipColor", () => {
  test("does not set style on known storefronts", () => {
    const span = ctx.appWindow.document.createElement("span");
    ctx.appWindow.applysfChipColor(span, "hk");
    expect(span.style.background).toBe("");
  });

  test("sets background and color style on unknown storefronts", () => {
    const span = ctx.appWindow.document.createElement("span");
    ctx.appWindow.applysfChipColor(span, "us");
    expect(span.style.background).not.toBe("");
    expect(span.style.color).not.toBe("");
  });
});

describe("applyMetaSrcBtnColor", () => {
  test("does nothing for known storefront", () => {
    const btn = ctx.appWindow.document.createElement("button");
    ctx.appWindow.applyMetaSrcBtnColor(btn, "jp", true);
    expect(btn.style.color).toBe("");
  });

  test("does nothing when not active", () => {
    const btn = ctx.appWindow.document.createElement("button");
    ctx.appWindow.applyMetaSrcBtnColor(btn, "us", false);
    expect(btn.style.color).toBe("");
  });

  test("sets color, background, and borderColor when active and unknown", () => {
    const btn = ctx.appWindow.document.createElement("button");
    ctx.appWindow.applyMetaSrcBtnColor(btn, "us", true);
    expect(btn.style.color).not.toBe("");
    expect(btn.style.background).not.toBe("");
    expect(btn.style.borderColor).not.toBe("");
  });
});

// ---------------------------------------------------------------------------
// sfChips — unknown storefront gets palette color
// ---------------------------------------------------------------------------

describe("sfChips dynamic color", () => {
  test("unknown storefront chip has inline style applied", () => {
    const chips = ctx.appWindow.sfChips(["us"]);
    const chip = chips.children[0];
    expect(chip.style.background).not.toBe("");
  });

  test("known storefront chip has no inline background style", () => {
    const chips = ctx.appWindow.sfChips(["jp"]);
    const chip = chips.children[0];
    expect(chip.style.background).toBe("");
  });
});

// ---------------------------------------------------------------------------
// skeletonGrid
// ---------------------------------------------------------------------------

describe("skeletonGrid", () => {
  test("returns div with class loading-grid", () => {
    expect(ctx.appWindow.skeletonGrid().className).toBe("loading-grid");
  });

  test("creates 12 skeleton cards by default", () => {
    expect(ctx.appWindow.skeletonGrid().children.length).toBe(12);
  });

  test("creates the specified number of cards", () => {
    expect(ctx.appWindow.skeletonGrid(6).children.length).toBe(6);
  });

  test("creates zero cards when n=0", () => {
    expect(ctx.appWindow.skeletonGrid(0).children.length).toBe(0);
  });

  test("each card has class skeleton-card", () => {
    const grid = ctx.appWindow.skeletonGrid(3);
    for (const card of grid.children) {
      expect(card.className).toBe("skeleton-card");
    }
  });

  test("each card contains skeleton-art child element", () => {
    const grid = ctx.appWindow.skeletonGrid(1);
    expect(grid.children[0].innerHTML).toContain("skeleton-art");
  });

  test("creates 1 card when n=1", () => {
    expect(ctx.appWindow.skeletonGrid(1).children.length).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// formatBadges
// ---------------------------------------------------------------------------

describe("formatBadges", () => {
  test("returns null for null", () => {
    expect(ctx.appWindow.formatBadges(null)).toBeNull();
  });

  test("returns null for undefined", () => {
    expect(ctx.appWindow.formatBadges(undefined)).toBeNull();
  });

  test("returns null for empty array", () => {
    expect(ctx.appWindow.formatBadges([])).toBeNull();
  });

  test("returns null when all formats are unknown", () => {
    expect(ctx.appWindow.formatBadges(["totally-unknown"])).toBeNull();
  });

  test("returns a div element for known format", () => {
    const result = ctx.appWindow.formatBadges(["lossless"]);
    expect(result).not.toBeNull();
    expect(result.tagName).toBe("DIV");
  });

  test("creates one badge per known format", () => {
    const result = ctx.appWindow.formatBadges(["lossless", "atmos"]);
    expect(result.children.length).toBe(2);
  });

  test("lossless badge text is 'Lossless'", () => {
    expect(ctx.appWindow.formatBadges(["lossless"]).children[0].textContent).toBe("Lossless");
  });

  test("lossy-stereo badge text is 'AAC'", () => {
    expect(ctx.appWindow.formatBadges(["lossy-stereo"]).children[0].textContent).toBe("AAC");
  });

  test("hi-res-lossless badge text is 'Hi-Res Lossless'", () => {
    expect(ctx.appWindow.formatBadges(["hi-res-lossless"]).children[0].textContent).toBe("Hi-Res Lossless");
  });

  test("atmos badge text is 'Dolby Atmos'", () => {
    expect(ctx.appWindow.formatBadges(["atmos"]).children[0].textContent).toBe("Dolby Atmos");
  });

  test("spatial badge text is 'Spatial Audio'", () => {
    expect(ctx.appWindow.formatBadges(["spatial"]).children[0].textContent).toBe("Spatial Audio");
  });

  test("adm badge text is 'Apple Digital Masters'", () => {
    expect(ctx.appWindow.formatBadges(["adm"]).children[0].textContent).toBe("Apple Digital Masters");
  });

  test("badge has class containing the format key", () => {
    const result = ctx.appWindow.formatBadges(["atmos"]);
    expect(result.children[0].className).toContain("atmos");
  });

  test("badge has class format-badge", () => {
    const result = ctx.appWindow.formatBadges(["lossless"]);
    expect(result.children[0].className).toContain("format-badge");
  });

  test("skips unknown formats but renders known ones in the same array", () => {
    const result = ctx.appWindow.formatBadges(["unknown", "lossless"]);
    expect(result).not.toBeNull();
    expect(result.children.length).toBe(1);
    expect(result.children[0].textContent).toBe("Lossless");
  });

  test("wrap div has class format-badges", () => {
    const result = ctx.appWindow.formatBadges(["lossless"]);
    expect(result.className).toBe("format-badges");
  });
});

// ---------------------------------------------------------------------------
// placeholderEl
// ---------------------------------------------------------------------------

describe("placeholderEl", () => {
  test("returns a div", () => {
    expect(ctx.appWindow.placeholderEl("album-artwork").tagName).toBe("DIV");
  });

  test("album-artwork class gives album-artwork-placeholder", () => {
    expect(ctx.appWindow.placeholderEl("album-artwork").className).toBe("album-artwork-placeholder");
  });

  test("modal-artwork class gives modal-artwork-placeholder", () => {
    expect(ctx.appWindow.placeholderEl("modal-artwork").className).toBe("modal-artwork-placeholder");
  });

  test("modal-artwork-thumb class gives modal-artwork-thumb-placeholder", () => {
    expect(ctx.appWindow.placeholderEl("modal-artwork-thumb").className).toBe("modal-artwork-thumb-placeholder");
  });

  test("any other class gives album-artwork-placeholder", () => {
    expect(ctx.appWindow.placeholderEl("something-else").className).toBe("album-artwork-placeholder");
  });

  test("text content is musical note", () => {
    expect(ctx.appWindow.placeholderEl("album-artwork").textContent).toBe("♫");
  });
});

// ---------------------------------------------------------------------------
// makeArtistLinks
// ---------------------------------------------------------------------------

describe("makeArtistLinks", () => {
  const makeArtistLinks = (...args) => ctx.appWindow.makeArtistLinks(...args);

  test("falls back to single artist text when artists_json is absent", () => {
    const album = { artist: "Test Artist", artist_id: "A1", artists_json: null };
    const el = makeArtistLinks(album, "album-artist");
    expect(el.className).toBe("album-artist");
    expect(el.textContent).toBe("Test Artist");
  });

  test("falls back to dash when artist is absent and no artists_json", () => {
    const album = { artist: null, artist_id: null, artists_json: null };
    const el = makeArtistLinks(album, "album-artist");
    expect(el.textContent).toBe("—");
  });

  test("renders single artist-link span for single-artist artists_json", () => {
    const album = {
      artist: "Jay Chou",
      artist_id: "300117743",
      artists_json: [{ id: "300117743", name: "Jay Chou", url: "https://music.apple.com/tw/artist/1" }],
    };
    const wrap = makeArtistLinks(album, "album-artist");
    const links = wrap.querySelectorAll(".artist-link");
    expect(links.length).toBe(1);
    expect(links[0].textContent).toBe("Jay Chou");
  });

  test("renders multiple artist-link spans for multi-artist albums", () => {
    const album = {
      artist: "Artist A & Artist B",
      artist_id: "A1",
      artists_json: [
        { id: "A1", name: "Artist A", url: null },
        { id: "A2", name: "Artist B", url: null },
      ],
    };
    const wrap = makeArtistLinks(album, "album-artist");
    const links = wrap.querySelectorAll(".artist-link");
    expect(links.length).toBe(2);
    expect(links[0].textContent).toBe("Artist A");
    expect(links[1].textContent).toBe("Artist B");
  });

  test("separates multiple artists with commas", () => {
    const album = {
      artist: "A & B",
      artist_id: "A1",
      artists_json: [
        { id: "A1", name: "A", url: null },
        { id: "A2", name: "B", url: null },
      ],
    };
    const wrap = makeArtistLinks(album, "album-artist");
    expect(wrap.textContent).toContain(", ");
  });

  test("sets title to combined artist string when using artists_json", () => {
    const album = {
      artist: "A & B",
      artist_id: "A1",
      artists_json: [
        { id: "A1", name: "A", url: null },
        { id: "A2", name: "B", url: null },
      ],
    };
    const wrap = makeArtistLinks(album, "album-artist");
    expect(wrap.title).toBe("A & B");
  });

  test("calls onNav callback when artist-link is clicked in multi-artist mode", () => {
    const album = {
      artist: "A & B",
      artist_id: "A1",
      artists_json: [
        { id: "A1", name: "A", url: null },
        { id: "A2", name: "B", url: null },
      ],
    };
    let called = false;
    const wrap = makeArtistLinks(album, "album-artist", () => { called = true; });
    wrap.querySelectorAll(".artist-link")[0].click();
    expect(called).toBe(true);
  });

  test("sets state.artistHint with full artist data when artist-link is clicked", () => {
    const album = {
      artist: "A & B",
      artist_id: "A1",
      artists_json: [
        { id: "A1", name: "Artist A", url: "https://music.apple.com/tw/artist/1", artwork_url: "https://example.com/a.jpg", genre: "Pop" },
        { id: "A2", name: "Artist B", url: "https://music.apple.com/tw/artist/2", artwork_url: "https://example.com/b.jpg", genre: "Rock" },
      ],
    };
    const wrap = makeArtistLinks(album, "album-artist");
    wrap.querySelectorAll(".artist-link")[1].click();
    const hint = ctx.appWindow.__test_state.artistHint;
    expect(hint.id).toBe("A2");
    expect(hint.name).toBe("Artist B");
    expect(hint.artwork_url).toBe("https://example.com/b.jpg");
    expect(hint.genre).toBe("Rock");
  });
});

// ---------------------------------------------------------------------------
// artistHint id type coercion (regression: Watch button from watchlist search)
// ---------------------------------------------------------------------------

describe("artistHint id type coercion", () => {
  test("String(numericId) matches string artistId from URL", () => {
    const numericId = 300117743;
    const hintId = String(numericId);
    const artistIdFromUrl = "300117743";
    expect(hintId === artistIdFromUrl).toBe(true);
  });

  test("numeric id does not match string artistId from URL (pre-fix behaviour)", () => {
    const numericId = 300117743;
    const artistIdFromUrl = "300117743";
    expect(numericId === artistIdFromUrl).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// innerHTML += vs insertAdjacentHTML (regression: buttons lose listeners)
// ---------------------------------------------------------------------------

describe("insertAdjacentHTML preserves existing event listeners", () => {
  test("innerHTML += destroys existing event listeners", () => {
    const doc = ctx.appWindow.document;
    const div = doc.createElement("div");
    const btn = doc.createElement("button");
    let clicked = false;
    btn.addEventListener("click", () => { clicked = true; });
    div.appendChild(btn);

    // Simulate the buggy pattern
    div.innerHTML += "<span>appended</span>";

    // The button node was replaced — listener is gone
    div.querySelector("button").click();
    expect(clicked).toBe(false);
  });

  test("insertAdjacentHTML preserves existing event listeners", () => {
    const doc = ctx.appWindow.document;
    const div = doc.createElement("div");
    const btn = doc.createElement("button");
    let clicked = false;
    btn.addEventListener("click", () => { clicked = true; });
    div.appendChild(btn);

    // The fixed pattern
    div.insertAdjacentHTML("beforeend", "<span>appended</span>");

    // The button node is untouched — listener still works
    div.querySelector("button").click();
    expect(clicked).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// albumCard — track-count chip
// ---------------------------------------------------------------------------

describe("albumCard track-count chip", () => {
  const baseAlbum = {
    store_adam_id: "123",
    title: "Test Album",
    artwork_url: null,
    artists: [{ id: "A1", name: "Artist", url: null }],
    release_date: "2024-01-01",
    storefronts: [],
    watched: false,
  };

  test("shows track-count chip when track_count is present", () => {
    const card = ctx.appWindow.albumCard({ ...baseAlbum, track_count: 10 });
    const chip = card.querySelector(".track-count-chip");
    expect(chip).not.toBeNull();
    expect(chip.textContent).toBe("10");
  });

  test("does not show track-count chip when track_count is absent", () => {
    const card = ctx.appWindow.albumCard({ ...baseAlbum });
    expect(card.querySelector(".track-count-chip")).toBeNull();
  });

  test("does not show track-count chip when track_count is 0", () => {
    const card = ctx.appWindow.albumCard({ ...baseAlbum, track_count: 0 });
    expect(card.querySelector(".track-count-chip")).toBeNull();
  });

  test("chip is inside album-art-wrap", () => {
    const card = ctx.appWindow.albumCard({ ...baseAlbum, track_count: 5 });
    const wrap = card.querySelector(".album-art-wrap");
    expect(wrap).not.toBeNull();
    expect(wrap.querySelector(".track-count-chip")).not.toBeNull();
  });

  test("artwork is inside album-art-wrap", () => {
    const card = ctx.appWindow.albumCard({ ...baseAlbum, track_count: 3 });
    const wrap = card.querySelector(".album-art-wrap");
    // placeholder used when artwork_url is null
    expect(wrap.querySelector(".album-artwork-placeholder")).not.toBeNull();
  });
});

// ---------------------------------------------------------------------------
// buildPagination scroll-to-top
// ---------------------------------------------------------------------------

describe("buildPagination scroll-to-top", () => {
  let windowScrollCalls;

  beforeEach(() => {
    windowScrollCalls = [];
    ctx.appWindow.scrollTo = (...args) => windowScrollCalls.push(args);
  });

  test("scrolls window to top when a page button is clicked", () => {
    const onPage = jest.fn();
    const pagination = ctx.appWindow.__test_buildPagination(2, 5, onPage);

    // Click the first numbered page button (start = max(1, 2-2) = 1)
    const pageBtn = pagination.querySelector(".page-btn:not([disabled])");
    pageBtn.click();

    expect(windowScrollCalls.length).toBeGreaterThan(0);
    expect(windowScrollCalls[0]).toEqual([0, 0]);
    expect(onPage).toHaveBeenCalled();
  });

  test("scrolls window to top when Prev button is clicked", () => {
    const onPage = jest.fn();
    const pagination = ctx.appWindow.__test_buildPagination(3, 5, onPage);

    const prevBtn = pagination.querySelector(".page-btn");
    prevBtn.click();

    expect(windowScrollCalls.length).toBeGreaterThan(0);
    expect(windowScrollCalls[0]).toEqual([0, 0]);
    expect(onPage).toHaveBeenCalledWith(2);
  });

  test("scrolls window to top when Next button is clicked", () => {
    const onPage = jest.fn();
    const pagination = ctx.appWindow.__test_buildPagination(2, 5, onPage);

    const buttons = pagination.querySelectorAll(".page-btn");
    const nextBtn = buttons[buttons.length - 1];
    nextBtn.click();

    expect(windowScrollCalls.length).toBeGreaterThan(0);
    expect(windowScrollCalls[0]).toEqual([0, 0]);
    expect(onPage).toHaveBeenCalledWith(3);
  });
});
