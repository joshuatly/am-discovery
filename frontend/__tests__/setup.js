/**
 * Jest setup file — runs before every test suite.
 * Provides minimal browser globals that app.js expects.
 */

// localStorage is provided by jest-environment-jsdom, but ensure it exists
if (typeof localStorage === "undefined") {
  global.localStorage = {
    _store: {},
    getItem(k) { return this._store[k] ?? null; },
    setItem(k, v) { this._store[k] = String(v); },
    removeItem(k) { delete this._store[k]; },
    clear() { this._store = {}; },
  };
}

// fetch mock — tests override this per-test as needed
global.fetch = jest.fn(() =>
  Promise.resolve({
    ok: true,
    json: () => Promise.resolve({}),
  })
);
