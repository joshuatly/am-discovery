"use strict";

const ctx = require("./setup-jsdom");

// ---------------------------------------------------------------------------
// refreshStatus — room error warning
// ---------------------------------------------------------------------------

describe("refreshStatus room errors", () => {
  beforeEach(() => {
    ctx.appWindow.document.getElementById("status-room-errors")?.remove();
  });

  test("shows warning element when room_errors is non-empty", async () => {
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        is_running: false,
        last_run: null,
        room_errors: ["hk", "jp"],
      }),
    });
    await ctx.appWindow.__test_refreshStatus();
    const warn = ctx.appWindow.document.getElementById("status-room-errors");
    expect(warn).not.toBeNull();
    expect(warn.textContent).toContain("HK");
    expect(warn.textContent).toContain("JP");
    // warning element should be placed after status-card, not inside it
    const card = ctx.appWindow.document.getElementById("status-card");
    expect(warn.parentElement).toBe(card.parentElement);
    // status dot should have warn class
    const dot = ctx.appWindow.document.getElementById("status-dot");
    expect(dot.className).toContain("warn");
  });

  test("removes warning element when room_errors is empty", async () => {
    // First call creates the warning
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ is_running: false, last_run: null, room_errors: ["hk"] }),
    });
    await ctx.appWindow.__test_refreshStatus();
    expect(ctx.appWindow.document.getElementById("status-room-errors")).not.toBeNull();

    // Second call clears it
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ is_running: false, last_run: null, room_errors: [] }),
    });
    await ctx.appWindow.__test_refreshStatus();
    expect(ctx.appWindow.document.getElementById("status-room-errors")).toBeNull();
  });

  test("no warning element when room_errors absent", async () => {
    ctx.appWindow.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ is_running: false, last_run: null }),
    });
    await ctx.appWindow.__test_refreshStatus();
    expect(ctx.appWindow.document.getElementById("status-room-errors")).toBeNull();
  });
});
