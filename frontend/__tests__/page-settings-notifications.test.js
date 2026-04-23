"use strict";

const ctx = require("./setup-jsdom");

// ---------------------------------------------------------------------------
// renderNotificationEvents — list row rendering
// ---------------------------------------------------------------------------

describe("renderNotificationEvents", () => {
  let container;
  const eventTypesMeta = [
    {
      event_type: "onArtistNewSingle",
      variables: ["artist", "title"],
      default_title: "New single from {artist}",
      default_body: "{title}",
      default_notification_type: "success",
    },
    {
      event_type: "onArtistNewRelease",
      variables: ["artist", "title", "track_count"],
      default_title: "New release from {artist}",
      default_body: "{title}",
      default_notification_type: "success",
    },
  ];

  beforeEach(() => {
    container = ctx.appWindow.document.createElement("div");
    ctx.appWindow.document.body.appendChild(container);
    ctx.appWindow.fetch.mockClear();
  });

  afterEach(() => {
    container.remove();
  });

  test("renders empty placeholder when no events", () => {
    ctx.appWindow.__test_renderNotificationEvents(container, [], eventTypesMeta, () => {});
    expect(container.textContent).toContain("No notification events configured");
  });

  test("renders one row per event with type label and URL", () => {
    const events = [
      { id: "e1", event_type: "onArtistNewSingle", apprise_url: "http://a/notify/x", enabled: true },
      { id: "e2", event_type: "onArtistNewRelease", apprise_url: "http://b/notify/y", enabled: false },
    ];
    ctx.appWindow.__test_renderNotificationEvents(container, events, eventTypesMeta, () => {});
    const rows = container.querySelectorAll("div > div");
    expect(container.textContent).toContain("new single");
    expect(container.textContent).toContain("http://a/notify/x");
    expect(container.textContent).toContain("http://b/notify/y");
    // Both enabled checkboxes present
    const checkboxes = container.querySelectorAll("input[type='checkbox']");
    expect(checkboxes.length).toBe(2);
    expect(checkboxes[0].checked).toBe(true);
    expect(checkboxes[1].checked).toBe(false);
  });

  test("auto-disabled badge renders when disabled_reason is max_failures", () => {
    const events = [
      {
        id: "e1",
        event_type: "onArtistNewSingle",
        apprise_url: "http://a",
        enabled: false,
        disabled_reason: "max_failures",
        consecutive_failures: 5,
      },
    ];
    ctx.appWindow.__test_renderNotificationEvents(container, events, eventTypesMeta, () => {});
    expect(container.textContent).toContain("auto-disabled");
  });

  test("test button calls the test endpoint and shows feedback", async () => {
    const events = [
      { id: "e1", event_type: "onArtistNewSingle", apprise_url: "http://a", enabled: true },
    ];
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true, message: "OK" }),
    });
    ctx.appWindow.__test_renderNotificationEvents(container, events, eventTypesMeta, () => {});
    const buttons = Array.from(container.querySelectorAll("button"));
    const testBtn = buttons.find(b => b.textContent === "Test");
    testBtn.click();
    // Wait for async click handler to complete
    await new Promise(r => setTimeout(r, 10));
    expect(ctx.appWindow.fetch).toHaveBeenCalledWith(
      "/api/notifications/e1/test",
      expect.objectContaining({ method: "POST" }),
    );
    expect(testBtn.textContent).toBe("✓ Sent");
  });

  test("delete button calls DELETE endpoint when confirmed", async () => {
    const events = [
      { id: "e1", event_type: "onArtistNewSingle", apprise_url: "http://a", enabled: true },
    ];
    ctx.appWindow.confirm = jest.fn(() => true);
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    let changeCalled = false;
    ctx.appWindow.__test_renderNotificationEvents(
      container,
      events,
      eventTypesMeta,
      () => {
        changeCalled = true;
      },
    );
    const delBtn = Array.from(container.querySelectorAll("button")).find(b => b.textContent === "Delete");
    delBtn.click();
    await new Promise(r => setTimeout(r, 10));
    expect(ctx.appWindow.fetch).toHaveBeenCalledWith(
      "/api/notifications/e1",
      expect.objectContaining({ method: "DELETE" }),
    );
    expect(changeCalled).toBe(true);
  });
});


// ---------------------------------------------------------------------------
// openNotificationEventModal — add flow
// ---------------------------------------------------------------------------

describe("openNotificationEventModal", () => {
  const eventTypesMeta = [
    {
      event_type: "onArtistNewSingle",
      variables: ["artist", "title"],
      default_title: "New single from {artist}",
      default_body: "{title}",
      default_notification_type: "success",
    },
  ];

  beforeEach(() => {
    ctx.appWindow.fetch.mockClear();
    // Reset modal state
    const overlay = ctx.appWindow.document.getElementById("modal-overlay");
    overlay.style.display = "none";
    ctx.appWindow.document.getElementById("modal-body").innerHTML = "";
  });

  test("opens modal with default templates populated for the selected type", () => {
    ctx.appWindow.__test_openNotificationEventModal(null, eventTypesMeta, () => {});
    const overlay = ctx.appWindow.document.getElementById("modal-overlay");
    expect(overlay.style.display).toBe("flex");
    const body = ctx.appWindow.document.getElementById("modal-body");
    const titleInput = body.querySelector("input[type='text']:not([placeholder^='http'])");
    const bodyTextarea = body.querySelector("textarea");
    expect(titleInput.value).toBe("New single from {artist}");
    expect(bodyTextarea.value).toBe("{title}");
  });

  test("renders variable chips for the selected event type", () => {
    ctx.appWindow.__test_openNotificationEventModal(null, eventTypesMeta, () => {});
    const body = ctx.appWindow.document.getElementById("modal-body");
    const chips = Array.from(body.querySelectorAll("code"));
    const labels = chips.map(c => c.textContent);
    expect(labels).toEqual(expect.arrayContaining(["{artist}", "{title}"]));
  });

  test("save button POSTs to /api/notifications when creating new", async () => {
    let saved = false;
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ id: "new", event_type: "onArtistNewSingle" }),
    });
    ctx.appWindow.__test_openNotificationEventModal(
      null,
      eventTypesMeta,
      () => {
        saved = true;
      },
    );
    const body = ctx.appWindow.document.getElementById("modal-body");
    const urlInput = body.querySelector("input[placeholder^='http']");
    urlInput.value = "http://x/notify/y";
    const buttons = Array.from(body.querySelectorAll("button"));
    const saveBtn = buttons.find(b => b.textContent === "Create");
    saveBtn.click();
    await new Promise(r => setTimeout(r, 10));
    expect(ctx.appWindow.fetch).toHaveBeenCalledWith(
      "/api/notifications",
      expect.objectContaining({ method: "POST" }),
    );
    expect(saved).toBe(true);
  });

  test("save button PUTs when editing existing event", async () => {
    const existing = {
      id: "e1",
      event_type: "onArtistNewSingle",
      apprise_url: "http://x",
      title_template: "t",
      body_template: "b",
      notification_type: "info",
      enabled: true,
    };
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(existing),
    });
    ctx.appWindow.__test_openNotificationEventModal(existing, eventTypesMeta, () => {});
    const body = ctx.appWindow.document.getElementById("modal-body");
    const buttons = Array.from(body.querySelectorAll("button"));
    const saveBtn = buttons.find(b => b.textContent === "Save");
    saveBtn.click();
    await new Promise(r => setTimeout(r, 10));
    expect(ctx.appWindow.fetch).toHaveBeenCalledWith(
      "/api/notifications/e1",
      expect.objectContaining({ method: "PUT" }),
    );
  });

  test("test button POSTs to /api/notifications/test with current form state", async () => {
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true, message: "OK" }),
    });
    ctx.appWindow.__test_openNotificationEventModal(null, eventTypesMeta, () => {});
    const body = ctx.appWindow.document.getElementById("modal-body");
    const buttons = Array.from(body.querySelectorAll("button"));
    const testBtn = buttons.find(b => b.textContent === "Test");
    testBtn.click();
    await new Promise(r => setTimeout(r, 10));
    expect(ctx.appWindow.fetch).toHaveBeenCalledWith(
      "/api/notifications/test",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
