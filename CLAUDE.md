# CLAUDE.md — AM Discovery

## What this project is

AM Discovery is an Apple Music new-release discovery tool. It monitors regional Apple Music "Room" pages (curated new-release sections in storefronts like HK, JP, MY, TW), aggregates albums across them, fetches full metadata, and exposes everything via a Flask REST API with a lightweight frontend SPA.

**Early development notice:** The schema, data model, and even the storage backend are actively evolving. Changes to the database structure, new fields, and potentially swapping out SQLite for another backend are all expected. Keep that in mind when modifying the DB layer.

---

## Architecture

```
client.py        — AppleMusicClient: scrapes music.apple.com + amp-api.music.apple.com
db.py            — SQLite database layer (all SQL lives here, nowhere else)
config.py        — load_config() / save_config() + CONFIG_PATH (imported by server + API layers)
server.py        — Flask app creation, background polling scheduler, init_scheduler(), main()
api.py           — Flask Blueprint: releases, artists, search, config/status, frontend routes
api_watchlist.py — Flask Blueprint: all watchlist routes (GET/POST/PATCH/DELETE/export/import)
wsgi.py          — Gunicorn WSGI entry point (production); imports app and starts scheduler
gunicorn.conf.py — Gunicorn config (1 worker required — scheduler runs as in-process thread)
migrate.py       — Standalone migration runner for schema upgrades
main.py          — Ad-hoc CLI script for manual testing/exploration
frontend/        — Static SPA (index.html, style.css, plus JS modules below)
```

The server starts a background thread that polls each configured storefront's `/new` browse page on a timer, auto-discovers the new-release room URL from that page, fetches metadata for new albums concurrently, and persists everything to SQLite.

### Backend module boundaries

- **`config.py`** — the only place that reads/writes `config.json`. Both `server.py` and the API blueprints import from here directly. No circular dependencies.
- **`server.py`** — owns the Flask `app` object, both polling schedulers, `init_scheduler()`, and `main()`. Registers the two API blueprints.
- **`api.py`** — a Flask Blueprint (`api_bp`). Contains all non-watchlist routes plus the `_serialize`, `_is_watched`, and `_validate_storefront` helpers. Uses a `_server()` lazy import for the three routes that need live scheduler state (`/api/refresh`, `/api/status`, `/api/config` PUT).
- **`api_watchlist.py`** — a Flask Blueprint (`watchlist_bp`). Self-contained watchlist routes; imports `_validate_storefront` from `api.py`.

**Where to add new backend code:**
- New config key or default → `config.py`
- New release/artist/search route → `api.py`
- New watchlist route → `api_watchlist.py`
- Scheduler behaviour or polling logic → `server.py`
- All SQL → `db.py` (never scatter queries elsewhere)

Each Python source file must stay under 800 lines.

### Frontend JS modules

The frontend has no build step. JS is split into modules loaded via `<script>` tags in `index.html` in this order (each file depends on globals defined by files above it):

```
utils.js          — API helpers, DOM ($, el), sanitizeHtml, WatchlistPrefs, date/time
                    utils, RELEASE_TYPE_LABELS/ORDER, FORMAT_LABELS,
                    COLLECTION_STATUS_LABELS/TRANSITIONS, debounce, tracklistsDiffer
components.js     — formatBadges, artworkEl, placeholderEl, SF color palette + chip
                    helpers, skeletonGrid, buildHeader, buildPagination,
                    makeArtistLinks, albumCard
state.js          — global state object, loadWatchedIds, toggleWatch,
                    submitCliSchedulerJob
status.js         — refreshStatus, triggerRefresh, metadata source widget
                    (renderMetaSourceWidget, initMetaSourceWidget, updateSrcBadge, …)
modal.js          — openModal, closeModal, showImageLightbox
page-releases.js  — renderArtistReleaseGrid, renderNewReleases, renderAllReleases
page-artist.js    — renderArtist
page-watchlist.js — paginateList, WATCHLIST_PAGE_SIZE, renderWatchlist
page-settings.js  — renderSettings
app.js            — route(), DOMContentLoaded bootstrap
```

**Where to put new frontend code:**
- New shared utility or constant → `utils.js`
- New reusable UI component (card, badge, etc.) → `components.js`
- New state field or watchlist API helper → `state.js`
- Changes to the status bar or metadata source widget → `status.js`
- Changes to the album detail modal → `modal.js`
- Changes to New Releases or All Albums pages → `page-releases.js`
- Changes to Artist Detail page → `page-artist.js`
- Changes to Artist Watchlist page → `page-watchlist.js`
- Changes to Settings page → `page-settings.js`
- Changes to routing or app-level bootstrap → `app.js`

Each source file must stay under 800 lines. Tests live in `frontend/__tests__/app.test.js` (no line limit).

---

## Running the project

**Install dependencies:**
```bash
uv sync
```

**First-time setup:**
```bash
cp config.json.example config.json
# Edit config.json with your storefronts and settings
```

**Start the server (development):**

When running inside Claude Desktop or any environment with preview tool support, use `preview_start` with the "AM Discovery (Flask)" configuration from `.claude/launch.json` — do **not** run `uv` manually. The launch.json config uses `scripts/dev_server.py` which sets the correct DB path and enables debug mode.

```bash
# Only use this when running outside Claude Desktop (e.g. a plain terminal):
uv run python server.py --debug
```

Server runs on `http://localhost:5000` by default. Set `PORT` env var to change.

**Start the server (production):**
```bash
uv run gunicorn -c gunicorn.conf.py "wsgi:app"
```

`wsgi.py` is the WSGI entry point used by Gunicorn (and the Docker container). It imports the Flask app and calls `init_scheduler()`. `gunicorn.conf.py` must keep `workers = 1` because the scheduler runs as an in-process background thread.

**Run Python tests:**
```bash
uv run pytest
```

**Run frontend (JS) tests:**
```bash
cd frontend && npm test
```

The frontend has Jest tests in `frontend/__tests__/app.test.js`. **All new frontend code must have corresponding Jest test cases.** All new Python code must have corresponding pytest cases in `tests/`.

Python tests are split by module:
- `tests/test_api.py` — routes in `api.py` (releases, artists, search, config, status, frontend)
- `tests/test_api_watchlist.py` — routes in `api_watchlist.py`
- `tests/test_server.py` — config helpers (`config.py`) and polling logic (`server.py`)

**Lint and format (Python):**
```bash
uv run ruff check .
uv run ruff format --check .
# or auto-fix:
make lint
```

Ruff is configured in `pyproject.toml` (line length 120, Python 3.11). **All Python changes must pass `ruff check` and `ruff format --check` before committing.** Run `make lint` to auto-fix issues, or use `uv run ruff check --fix .` and `uv run ruff format .` individually.

**Custom DB path:**
```bash
AM_DB_PATH=/path/to/custom.db uv run python server.py
```

---

## Database

- Engine: SQLite with WAL mode and foreign keys enabled
- Schema version: tracked via `PRAGMA user_version` (currently v5)
- **All SQL lives in `db.py`** — do not scatter queries elsewhere
- `storefronts` and `audio_formats` columns are stored as JSON strings in SQLite; always serialize/deserialize them explicitly

### When changing the schema

1. Bump `SCHEMA_VERSION` in `db.py`
2. Update the `CREATE TABLE` statements in `init_db()` so fresh installs get the new schema
3. Add a new entry to the `MIGRATIONS` dict in `migrate.py` to upgrade existing databases
4. Run `uv run python migrate.py` to apply the migration on an existing DB

**Note:** The database backend may change in the future (PostgreSQL, etc.). Keep all persistence logic confined to `db.py` so it can be swapped without touching the rest of the codebase.

---

## HTTP client

`AppleMusicClient` in `client.py` uses only the Python standard library (`urllib`). Do not add `requests`, `httpx`, or any other HTTP dependency.

**Bearer token:** The client auto-extracts a bearer JWT from the Apple Music JS bundle and caches it in `bearer_token.txt`. This file is gitignored and will be refreshed automatically when expired.

**CORS proxy:** Set `cors_proxy` in `config.json` to prefix all outgoing URLs through a proxy (useful if the server is behind a firewall). The value should be a full URL prefix, e.g. `https://proxy.example.com/`.

---

## Configuration (`config.json`)

| Key | Type | Description |
|-----|------|-------------|
| `check_storefronts` | array | Storefronts to poll for new releases and check availability. The app auto-discovers the new-release room URL from each storefront's `/new` page. |
| `home_storefront` | string | Default storefront for metadata lookups |
| `newrelease_poll_interval_days` | integer | How often to poll storefronts for new releases (default: 1) |
| `watchlist_poll_interval_minutes` | integer | How often to check watchlist artists for new releases (default: 10) |
| `watchlist_poll_batch_size` | integer | Artists refreshed per watchlist poll cycle (default: 5) |
| `watchlist_refresh_interval_days` | integer | Days before a watchlist artist's catalog is considered stale (default: 7) |
| `cors_proxy` | string | Optional URL prefix for proxying requests |

The config is live-reloaded on every poll, so changes take effect on the next cycle without restarting.

---

## API summary

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/releases` | Paginated list; supports `q`, `page`, `per_page`, `storefront`, `view=new` (discovered only), `watched=true`, `release_type` |
| GET | `/api/releases/<id>` | Single release detail |
| GET | `/api/releases/<id>/check_storefronts` | Availability across configured storefronts |
| GET | `/api/lookup/<id>` | Fresh metadata fetch (bypasses cache) |
| GET | `/api/artists/<id>/releases` | All releases for an artist |
| POST | `/api/artists/<id>/fetch` | Fetch and store full artist catalog |
| GET | `/api/search/artists` | Search Apple Music catalog for artists |
| GET | `/api/watchlist` | Get watched artists |
| POST | `/api/watchlist` | Add artist to watchlist |
| DELETE | `/api/watchlist/<id>` | Remove from watchlist |
| GET | `/api/config` | Get current config |
| PUT | `/api/config` | Update config |
| POST | `/api/refresh` | Manually trigger a poll |
| GET | `/api/status` | Server/poll status |

Full Swagger docs at `/apidocs`.

---

## Key patterns

- **Room URL discovery:** `client.discover_room_url(storefront)` fetches the storefront's `/new` browse page and locates the new-release room URL automatically. No room URLs are stored in config.
- **Upsert pattern:** `upsert_album()` does `INSERT OR IGNORE` followed by `UPDATE` so concurrent inserts from multiple storefront pollers don't conflict.
- **Storefront merging:** Each album tracks which storefronts it was seen in; storefronts are merged (not replaced) on each upsert.
- **Source tracking:** Albums are tagged with `source='discovered'` (from room polling) or `source='artist_fetch'` (manually fetched via artist page). The `view=new` filter shows only discovered ones.
- **Info fetch caching:** `info_fetched=1` is set once full metadata has been retrieved; subsequent polls skip the expensive API call for known albums.
- **Concurrent fetches:** `ThreadPoolExecutor(max_workers=10)` is used for batch metadata fetches. Keep individual fetch functions side-effect-free (write to DB only, no shared mutable state).

---

## Frontend state gotchas

### Shared `state` fields with separate null-guards (recurring bug)

`state` in `state.js` has multiple fields that are lazily loaded from the API (e.g. `configuredStorefronts`, `discoveryStorefronts`). Different page renderers each guard their own config fetch with `if (state.X === null)`, but they don't all set the same fields. This causes crashes when navigating between pages: page A sets field X, page B's guard sees X is non-null and skips the fetch, but field Y (only set by page B's fetch) remains null.

**Rule:** When adding a new lazy-loaded state field, make sure every page that guards config loading also sets that field — or broaden the guard to `if (state.X === null || state.Y === null)`. Never assume all fields were populated just because one was.

---

## Things that are still in flux

- Schema — new fields are being added regularly; always write a migration
- Frontend — vanilla JS, no build step; split across 10 modules (see Frontend JS modules above)

When in doubt, keep changes small and don't over-engineer — the codebase is moving fast.
