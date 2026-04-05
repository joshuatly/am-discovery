"use strict";

const ctx = require("./setup-jsdom");

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

function makeArtistFetchMock(artistData) {
  return ctx.appWindow.fetch
    .mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(artistData),
    })
    .mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve([]), // watchlist
    });
}

// ---------------------------------------------------------------------------
// Collection status selector on artist detail page
// ---------------------------------------------------------------------------

describe("renderArtist collection status selector", () => {
  test("buildCsOptions creates correct options for new status", async () => {
    // We test the COLLECTION_TRANSITIONS constant to verify option logic
    const t = ctx.appWindow.__test_COLLECTION_TRANSITIONS;
    // "new" status should offer complete and in_progress
    expect(t.new).toContain("complete");
    expect(t.new).toContain("in_progress");
    // "complete" should offer in_progress
    expect(t.complete).toContain("in_progress");
    // "in_progress" should only offer complete
    expect(t.in_progress).toEqual(["complete"]);
  });

  test("COLLECTION_STATUS_LABELS maps all statuses to display names", () => {
    const labels = ctx.appWindow.__test_COLLECTION_STATUS_LABELS;
    const transitions = ctx.appWindow.__test_COLLECTION_TRANSITIONS;
    // Every key in transitions should have a label
    for (const status of Object.keys(transitions)) {
      expect(labels[status]).toBeDefined();
      expect(typeof labels[status]).toBe("string");
      expect(labels[status].length).toBeGreaterThan(0);
    }
  });
});

// ---------------------------------------------------------------------------
// renderArtist — extended artist info (born_or_formed, origin, artist_bio)
// ---------------------------------------------------------------------------

describe("renderArtist extended artist info", () => {
  let main;

  beforeEach(() => {
    main = ctx.appWindow.document.createElement("div");
    ctx.appWindow.document.getElementById("main-content").appendChild(main);
  });

  afterEach(() => {
    main.remove();
    ctx.appWindow.fetch.mockClear();
  });

  test("renders born_or_formed and origin as a combined detail line (group, already prefixed)", async () => {
    makeArtistFetchMock({
      artist_id: "1127116907",
      artist_name: "The Pale White",
      artist_artwork_url: null,
      artist_genre: "Alternative",
      artist_born_or_formed: "Formed 2016",
      artist_origin: "Newcastle, England",
      artist_bio: null,
      artist_is_group: true,
      watched: false,
      releases: [],
    });

    await ctx.appWindow.__test_renderArtist(main, "1127116907");
    const detail = main.querySelector(".artist-detail");
    expect(detail).not.toBeNull();
    // "Formed 2016" already starts with "Formed" so no extra prefix is added
    expect(detail.textContent).toBe("Formed 2016 · Newcastle, England");
  });

  test("prefixes localized born_or_formed with 'Born' for solo artist", async () => {
    makeArtistFetchMock({
      artist_id: "137938148",
      artist_name: "Eason Chan",
      artist_artwork_url: null,
      artist_genre: "Cantopop",
      artist_born_or_formed: "1974年7月27日",
      artist_origin: "Hong Kong",
      artist_bio: null,
      artist_is_group: false,
      watched: false,
      releases: [],
    });

    await ctx.appWindow.__test_renderArtist(main, "137938148");
    const detail = main.querySelector(".artist-detail");
    expect(detail).not.toBeNull();
    expect(detail.textContent).toContain("Born 1974年7月27日");
    expect(detail.textContent).toContain("Hong Kong");
  });

  test("prefixes localized born_or_formed with 'Formed' for group", async () => {
    makeArtistFetchMock({
      artist_id: "222",
      artist_name: "Some Band",
      artist_artwork_url: null,
      artist_genre: "Rock",
      artist_born_or_formed: "2010",
      artist_origin: null,
      artist_bio: null,
      artist_is_group: true,
      watched: false,
      releases: [],
    });

    await ctx.appWindow.__test_renderArtist(main, "222");
    const detail = main.querySelector(".artist-detail");
    expect(detail).not.toBeNull();
    expect(detail.textContent).toBe("Formed 2010");
  });

  test("renders only born_or_formed when origin is absent and is_group is unknown", async () => {
    makeArtistFetchMock({
      artist_id: "111",
      artist_name: "Solo Act",
      artist_artwork_url: null,
      artist_genre: null,
      artist_born_or_formed: "Born July 27, 1974",
      artist_origin: null,
      artist_bio: null,
      artist_is_group: null,
      watched: false,
      releases: [],
    });

    await ctx.appWindow.__test_renderArtist(main, "111");
    const detail = main.querySelector(".artist-detail");
    expect(detail).not.toBeNull();
    // No prefix added when is_group is unknown
    expect(detail.textContent).toBe("Born July 27, 1974");
  });

  test("renders artist_bio when present", async () => {
    makeArtistFetchMock({
      artist_id: "137938148",
      artist_name: "Eason Chan",
      artist_artwork_url: null,
      artist_genre: "Cantopop",
      artist_born_or_formed: "Born July 27, 1974",
      artist_origin: "Hong Kong",
      artist_bio: "Eason Chan is a legendary Cantopop artist.",
      artist_is_group: false,
      watched: false,
      releases: [],
    });

    await ctx.appWindow.__test_renderArtist(main, "137938148");
    const bio = main.querySelector(".artist-bio");
    expect(bio).not.toBeNull();
    expect(bio.textContent).toContain("Eason Chan");
  });

  test("renders artist_bio HTML tags as markup not literal text", async () => {
    makeArtistFetchMock({
      artist_id: "137938148",
      artist_name: "Eason Chan",
      artist_artwork_url: null,
      artist_genre: "Cantopop",
      artist_born_or_formed: "Born July 27, 1974",
      artist_origin: "Hong Kong",
      artist_bio: "<b>Bold section</b><br>Plain text<br><i>Italic</i>",
      artist_is_group: false,
      watched: false,
      releases: [],
    });

    await ctx.appWindow.__test_renderArtist(main, "137938148");
    const bio = main.querySelector(".artist-bio");
    expect(bio).not.toBeNull();
    expect(bio.querySelector("b")).not.toBeNull();
    expect(bio.querySelector("br")).not.toBeNull();
    expect(bio.querySelector("i")).not.toBeNull();
    expect(bio.textContent).not.toContain("<b>");
    expect(bio.textContent).not.toContain("<br>");
  });

  test("omits detail line and bio when all extended fields are absent", async () => {
    makeArtistFetchMock({
      artist_id: "999",
      artist_name: "Minimal Artist",
      artist_artwork_url: null,
      artist_genre: null,
      artist_born_or_formed: null,
      artist_origin: null,
      artist_bio: null,
      watched: false,
      releases: [],
    });

    await ctx.appWindow.__test_renderArtist(main, "999");
    expect(main.querySelector(".artist-detail")).toBeNull();
    expect(main.querySelector(".artist-bio")).toBeNull();
  });

  test("uses artistHint born_or_formed and origin when API returns nulls", async () => {
    ctx.appWindow.__test_state.artistHint = {
      id: "1001",
      name: "Hint Band",
      url: null,
      artwork_url: null,
      genre: null,
      born_or_formed: "Formed 2010",
      origin: "London, England",
      artist_bio: null,
      is_group: true,
    };

    makeArtistFetchMock({
      artist_id: "1001",
      artist_name: "Hint Band",
      artist_artwork_url: null,
      artist_genre: null,
      artist_born_or_formed: null,
      artist_origin: null,
      artist_bio: null,
      artist_is_group: null,
      watched: false,
      releases: [],
    });

    await ctx.appWindow.__test_renderArtist(main, "1001");
    const detail = main.querySelector(".artist-detail");
    expect(detail).not.toBeNull();
    expect(detail.textContent).toBe("Formed 2010 · London, England");
  });

  test("uses artistHint is_group to prefix born_or_formed when API returns nulls", async () => {
    ctx.appWindow.__test_state.artistHint = {
      id: "1002",
      name: "Solo Hint",
      url: null,
      artwork_url: null,
      genre: null,
      born_or_formed: "1990年1月1日",
      origin: null,
      artist_bio: null,
      is_group: false,
    };

    makeArtistFetchMock({
      artist_id: "1002",
      artist_name: "Solo Hint",
      artist_artwork_url: null,
      artist_genre: null,
      artist_born_or_formed: null,
      artist_origin: null,
      artist_bio: null,
      artist_is_group: null,
      watched: false,
      releases: [],
    });

    await ctx.appWindow.__test_renderArtist(main, "1002");
    const detail = main.querySelector(".artist-detail");
    expect(detail).not.toBeNull();
    expect(detail.textContent).toBe("Born 1990年1月1日");
  });
});

// ---------------------------------------------------------------------------
// renderArtist — alt name edit widget (Enter key saves)
// ---------------------------------------------------------------------------

describe("renderArtist alt name edit — Enter key saves", () => {
  let main;

  beforeEach(() => {
    main = ctx.appWindow.document.createElement("div");
    ctx.appWindow.document.getElementById("main-content").appendChild(main);
    ctx.appWindow.__test_state.watchedIds = new ctx.appWindow.Set(["ART99"]);
    ctx.appWindow.__test_state.watchedIdsLoaded = true;
  });

  afterEach(() => {
    main.remove();
    ctx.appWindow.fetch.mockClear();
    ctx.appWindow.__test_state.watchedIds = new ctx.appWindow.Set();
    ctx.appWindow.__test_state.watchedIdsLoaded = false;
  });

  test("pressing Enter in alt name input triggers save", async () => {
    // Artist fetch
    ctx.appWindow.fetch
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          artist_id: "ART99",
          artist_name: "Test Artist",
          artist_artwork_url: null,
          artist_genre: null,
          artist_born_or_formed: null,
          artist_origin: null,
          artist_bio: null,
          artist_is_group: null,
          watched: true,
          releases: [],
        }),
      })
      // Watchlist fetch (for pre-populating alt_name)
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve([
          { artist_id: "ART99", name: "Test Artist", alt_name: "Old Name", collection_status: "new", added_at: 1700000000 },
        ]),
      })
      // PATCH response
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ ok: true }),
      });

    await ctx.appWindow.__test_renderArtist(main, "ART99");
    await new Promise(r => setTimeout(r, 100));

    // Click Edit button to enter edit mode
    const editBtn = main.querySelector(".btn-alt-name-edit");
    expect(editBtn).not.toBeNull();
    editBtn.click();

    const input = main.querySelector(".alt-name-input");
    expect(input).not.toBeNull();
    input.value = "New Name";

    // Press Enter
    input.dispatchEvent(new ctx.appWindow.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await new Promise(r => setTimeout(r, 50));

    // PATCH should have been called
    const patchCall = ctx.appWindow.fetch.mock.calls.find(([url, opts]) =>
      typeof url === "string" && url.includes("/api/watchlist/ART99") && opts?.method === "PATCH"
    );
    expect(patchCall).toBeDefined();
    const body = JSON.parse(patchCall[1].body);
    expect(body.alt_name).toBe("New Name");
  });
});

// ---------------------------------------------------------------------------
// renderArtist — type filter bar visibility
// ---------------------------------------------------------------------------

describe("renderArtist type filter bar", () => {
  let main;

  beforeEach(() => {
    main = ctx.appWindow.document.createElement("div");
    ctx.appWindow.document.getElementById("main-content").appendChild(main);
    ctx.appWindow.__test_state.artistTypeFilter = "";
  });

  afterEach(() => {
    main.remove();
    ctx.appWindow.fetch.mockClear();
  });

  test("shows type filter bar when artist has only one release type", async () => {
    makeArtistFetchMock({
      artist_id: "42",
      artist_name: "Singles Only",
      artist_artwork_url: null,
      artist_genre: null,
      artist_born_or_formed: null,
      artist_origin: null,
      artist_bio: null,
      artist_is_group: false,
      watched: false,
      releases: [
        { id: "1", title: "Single A", release_type: "singles-eps", artist_name: "Singles Only" },
        { id: "2", title: "Single B", release_type: "singles-eps", artist_name: "Singles Only" },
      ],
    });

    await ctx.appWindow.__test_renderArtist(main, "42");
    const typeBar = main.querySelector(".type-filter-bar");
    expect(typeBar).not.toBeNull();
    const btns = typeBar.querySelectorAll(".type-filter-btn");
    // All + 1 type
    expect(btns.length).toBe(2);
  });

  test("shows type filter bar when artist has multiple release types", async () => {
    makeArtistFetchMock({
      artist_id: "43",
      artist_name: "Mixed Artist",
      artist_artwork_url: null,
      artist_genre: null,
      artist_born_or_formed: null,
      artist_origin: null,
      artist_bio: null,
      artist_is_group: false,
      watched: false,
      releases: [
        { id: "1", title: "Album A", release_type: "main-albums", artist_name: "Mixed Artist" },
        { id: "2", title: "Single B", release_type: "singles-eps", artist_name: "Mixed Artist" },
      ],
    });

    await ctx.appWindow.__test_renderArtist(main, "43");
    const typeBar = main.querySelector(".type-filter-bar");
    expect(typeBar).not.toBeNull();
    const btns = typeBar.querySelectorAll(".type-filter-btn");
    // All + 2 types
    expect(btns.length).toBe(3);
  });
});
