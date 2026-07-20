# CLAUDE.md — AM Discovery

## What this project is

AM Discovery is an Apple Music new-release discovery tool. It monitors regional Apple Music "Room" pages (curated new-release sections in storefronts like HK, JP, MY, TW), aggregates albums across them, fetches full metadata, and exposes everything via a Flask REST API with a lightweight frontend SPA.

**Early development notice:** The schema, data model, and even the storage backend are actively evolving. Changes to the database structure, new fields, and potentially swapping out SQLite for another backend are all expected. Keep that in mind when modifying the DB layer.

---

## Architecture

```
client.py          — AppleMusicClient: scrapes music.apple.com + amp-api.music.apple.com
db.py              — SQLite database layer (all SQL lives here, nowhere else)
config.py          — load_config() / save_config() + CONFIG_PATH + timezone/date helpers
server.py          — Flask app creation, polling schedulers, init_scheduler(), main(); registers all blueprints
storefronts.py     — Per-storefront discovery constants (localized room titles)
storefront_locales.py — Storefront → locale map used when querying Apple Music

# API layer — one Flask Blueprint per domain
api_utility.py     — shared helpers (_serialize, _is_watched, _validate_storefront) + frontend catch-all routes
api_releases.py    — release routes (list, detail, check_storefronts, lookup, musicbrainz, you-might-also-like)
api_artists.py     — artist routes (releases, fetch, PATCH, similar, catalog + local search)
api_watchlist.py   — watchlist routes (GET/POST/PATCH/DELETE/ids/export/import)
api_system.py      — config/status/refresh, db + discovery + watchlist logs, CLI Scheduler proxy
api_admin.py       — MusicBrainz seeding admin (artist MBID linking + release seeding list)
api_notifications.py — Apprise notification event CRUD + test routes
api_debug.py       — raw Apple Music catalog debug endpoints

# Subsystems
notifications.py   — Apprise dispatch: event templates, send worker thread, watched-artist scanner
musicbrainz.py     — MusicBrainz /ws/2 client (stdlib urllib only; rate-limit + backoff; no API key needed)
seeding.py         — Background MusicBrainz seeding scanner (suggest artist MBIDs + flag un-seeded releases)

wsgi.py            — Gunicorn WSGI entry point (production); imports app and starts scheduler
gunicorn.conf.py   — Gunicorn config (1 worker required — scheduler runs as in-process thread)
migrate.py         — Standalone migration runner for schema upgrades
main.py            — Ad-hoc CLI script for manual testing/exploration
scripts/           — Dev helpers (dev_server.py launcher, backfill_alt_names.py)
frontend/          — Static SPA (index.html, style.css, plus JS modules below)
```

The server starts a background thread that polls each configured storefront's `/new` browse page on a timer, auto-discovers the new-release room URL from that page, fetches metadata for new albums concurrently, and persists everything to SQLite. Two more background threads run alongside it: the MusicBrainz seeding scanner (`seeding.py`) and the notification scanner + Apprise send worker (`notifications.py`).

### Backend module boundaries

- **`config.py`** — the only place that reads/writes `config.json`. Both `server.py` and the API blueprints import from here directly. Also owns `CONFIG_LOCK` and the timezone-aware `format_local_time` / `format_local_date` helpers. No circular dependencies.
- **`server.py`** — owns the Flask `app` object, the polling schedulers, `init_scheduler()`, and `main()`. Registers every API blueprint and starts the notification worker + scanner.
- **API blueprints** — one Blueprint per domain (see the tree above). Shared helpers (`_serialize`, `_is_watched`, `_validate_storefront`) live in `api_utility.py`; other blueprints import from it. Routes needing live scheduler state use a `_server()` lazy import.

**Where to add new backend code:**
- New config key or default → `config.py`
- New release/artist/search route → `api_releases.py` / `api_artists.py` / `api_system.py`
- New watchlist route → `api_watchlist.py`
- New MusicBrainz seeding admin route → `api_admin.py`
- New notification event route → `api_notifications.py`; dispatch/template/scanner logic → `notifications.py`
- New Apple Music debug endpoint → `api_debug.py`
- Storefront discovery constants / locales → `storefronts.py` / `storefront_locales.py`
- MusicBrainz web-service calls → `musicbrainz.py` (never call `/ws/2` directly elsewhere)
- Seeding scan / matching logic → `seeding.py`
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
page-admin.js     — renderAdmin (MusicBrainz seeding: Artists + Releases tabs)
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
- Changes to the Admin (MusicBrainz seeding) page → `page-admin.js`
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
- `tests/test_api.py` — core routes (releases, artists, search, config, status, frontend)
- `tests/test_api_watchlist.py` — routes in `api_watchlist.py`
- `tests/test_api_admin.py` — routes in `api_admin.py`
- `tests/test_api_notifications.py` — routes in `api_notifications.py`
- `tests/test_api_debug.py` — routes in `api_debug.py`
- `tests/test_notifications.py` — notification dispatch, templating, scanner (`notifications.py`)
- `tests/test_server.py` — config helpers (`config.py`) and polling logic (`server.py`)
- `tests/test_db.py` — database layer (`db.py`); real temp DB
- `tests/test_client.py` — `AppleMusicClient` parsing (`client.py`); network mocked
- `tests/test_musicbrainz.py` — MusicBrainz client (`musicbrainz.py`); network is always mocked
- `tests/test_seeding.py` — seeding scanner (`seeding.py`); MusicBrainz mocked, real temp DB
- `tests/test_storefronts.py` — storefront discovery constants / locale mapping
- `tests/test_migrate.py` — schema migrations (`migrate.py`)

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
- Schema version: tracked via `PRAGMA user_version` (currently v18)
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

## MusicBrainz seeding

The admin page (`/#/admin`, `page-admin.js`) and background scanner (`seeding.py`) help seed missing releases into MusicBrainz.

- **No API key required.** The MusicBrainz `/ws/2` web service is open for reads; it only needs a descriptive `User-Agent` (already set in `musicbrainz.py`) and a ~1 req/sec rate limit. Seeding itself happens in the browser via **Harmony** (`harmony.pulsewidth.org.uk`) using the user's own MusicBrainz login — the server never submits edits.
- **`musicbrainz.py`** is the only place that calls `/ws/2`. A module-level lock enforces the rate limit across the scanner thread and on-demand Flask requests; 503s back off exponentially and eventually raise `MusicBrainzRateLimitError`.
- **Scanner (`seeding.py`)** runs two phases per cycle, in small batches, at most once per `mb_artist_recheck_days` per artist: (1) suggest artist MBIDs for watchlist artists missing one (queued for approval — never auto-linked); (2) for artists with an MBID, flag albums that need seeding (excluding singles — Apple Music groups singles and EPs under one `singles-eps` type, so singles are detected by the `<Name> - Single` title suffix; EPs are kept). It reads only local DB data — never re-queries Apple Music — and skips albums already confirmed present. Matching first tries the linked artist's own MusicBrainz release-groups (title match, then barcode/edition check) as a cheap fast path; **before flagging**, it falls back to the same authoritative global lookup the album card uses (`musicbrainz.lookup_barcode` then `musicbrainz.search_release`), so releases credited to a different artist entity or typed outside album/EP aren't wrongly flagged. A manual scan (`POST /api/admin/scan`, the admin "Scan now" button) forces `force=True`, ignoring the weekly recheck window so stale flags can be re-verified immediately.
- **Seed state** lives on `albums` (`mb_seed_status`, `mb_release_mbid`, `mb_checked_at`, `hidden_from_seeding`); per-artist scan timestamps in `mb_scan_state`; the MBID approval queue in `artist_mbid_suggestions`.

---

## Notifications (Apprise)

`notifications.py` dispatches events to a self-hosted [Apprise](https://github.com/caronc/apprise) API (e.g. `http://host:8100/notify/apprise`). All routes live in `api_notifications.py`; the Settings page is the UI. **There is no DB table** — every event and the global queue settings persist in `config.json` under the `notifications` key.

- **Event types** (`notifications.EVENT_TYPES`): `onDiscoveryComplete`, `onDiscoveryFailed`, `onArtistNewRelease`, `onArtistNewSingle`, `onWatchlistBatchComplete`. Each type has default title/body templates and a documented set of `{variable}` names (`EVENT_VARIABLES`) surfaced to the UI via `GET /api/notifications/event-types`.
- **Dispatch:** `enqueue()` renders every enabled event of a type and puts it on a bounded queue; a single daemon worker thread (`init()`) sends at `rate_limit_per_sec`. Each event tracks `consecutive_failures` and auto-disables after `max_failures`. Templates use `str.format_map` with a `_SafeDict` so unknown/missing `{vars}` render empty instead of raising.
- **Scanner:** `init_scanner()` starts a separate timer thread that every `notification_scan_interval_minutes` finds watched-artist albums first-seen in the last window (and released within `notification_max_release_age_days`) and fires `onArtistNewRelease`/`onArtistNewSingle`. Discovery/watchlist-batch events fire directly from `server.py`.
- **Where to add code:** new event route → `api_notifications.py`; new event type, template, variable, or send/scan logic → `notifications.py`. Server wiring (`notifications.init()` / `init_scanner()`, and the discovery/batch `enqueue` calls) lives in `server.py`.

---

## Watchlist curation & CLI Scheduler

- **Collection status:** each watched artist carries a `collection_status` (`db.COLLECTION_STATUSES` = `new`, `in_progress`, `complete`, `new_release`), settable via `PATCH /api/watchlist/<id>` and used to filter/sort the watchlist. Frontend labels + allowed transitions live in `utils.js` (`COLLECTION_STATUS_LABELS`, `COLLECTION_TRANSITIONS`); the chip palette is in `DESIGN.md` §11.
- **CLI Scheduler:** `POST /api/system/cli-scheduler/submit` proxies an album URL to an optional external downloader configured by `cli_scheduler_url` / `cli_scheduler_preset`. The frontend helper is `submitCliSchedulerJob` in `state.js`; the "Send to scheduler" UI only appears when `cli_scheduler_url` is set.

---

## Configuration (`config.json`)

| Key | Type | Description |
|-----|------|-------------|
| `check_storefronts` | array | Storefronts to poll for new releases and check availability. The app auto-discovers the new-release room URL from each storefront's `/new` page. |
| `home_storefront` | string | Default storefront for metadata lookups |
| `timezone` | string | IANA zone (e.g. `Asia/Hong_Kong`) for all displayed timestamps; falls back to `UTC`. Used by `config.format_local_time`/`format_local_date` |
| `newrelease_poll_interval_days` | integer | How often to poll storefronts for new releases (default: 1) |
| `watchlist_poll_interval_minutes` | integer | How often to check watchlist artists for new releases (default: 10) |
| `watchlist_poll_batch_size` | integer | Artists refreshed per watchlist poll cycle (default: 5) |
| `watchlist_refresh_interval_days` | integer | Days before a watchlist artist's catalog is considered stale (default: 7) |
| `notification_scan_interval_minutes` | integer | How often the notification scanner looks for new watched-artist releases (default: 10) |
| `notification_max_release_age_days` | integer | Ignore releases older than this (by release date) when firing new-release notifications (default: 7) |
| `mb_scan_enabled` | boolean | Enable the background MusicBrainz seeding scanner (default: true) |
| `mb_scan_interval_minutes` | integer | How often the seeding scanner runs a cycle (default: 60) |
| `mb_scan_artist_batch` | integer | Artists processed per seeding-scan phase (default: 3) — keep small; MusicBrainz allows ~1 req/sec |
| `mb_artist_recheck_days` | integer | Minimum days before re-scanning an artist for MBID/releases (default: 7) |
| `cli_scheduler_url` | string | Base URL of an optional self-hosted CLI Scheduler; empty disables the integration |
| `cli_scheduler_preset` | string | Preset name sent with each CLI Scheduler job |
| `notifications` | object | Apprise notification block: `queue_max_size`, `max_failures`, `rate_limit_per_sec`, and the list of `events`. Managed via the notifications API / Settings page — see below |
| `cors_proxy` | string | Optional URL prefix for proxying requests |

The config is live-reloaded on every poll, so changes take effect on the next cycle without restarting. Every key has a default in `config._DEFAULTS`, so a partial `config.json` is valid.

---

## API summary

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/releases` | Paginated list; supports `q`, `page`, `per_page`, `storefront`, `view=new` (discovered only), `watched=true`, `release_type` |
| GET | `/api/releases/<id>` | Single release detail |
| GET | `/api/releases/<id>/check_storefronts` | Availability across configured storefronts |
| GET | `/api/releases/<id>/lookup` | Fresh metadata fetch (bypasses cache) |
| GET | `/api/releases/<id>/musicbrainz` | MusicBrainz lookup for the release (barcode → search) |
| GET | `/api/releases/<id>/you-might-also-like` | Apple Music recommendations for the release |
| GET | `/api/artists/<id>/releases` | All releases for an artist |
| POST | `/api/artists/<id>/fetch` | Fetch and store full artist catalog |
| PATCH | `/api/artists/<id>` | Update editable artist fields (alt names, MBID, …) |
| GET | `/api/artists/<id>/similar` | Similar artists from Apple Music |
| GET | `/api/artists/search` | Search Apple Music catalog for artists |
| GET | `/api/artists/search/local` | Search locally stored artists |
| GET | `/api/watchlist` | Get watched artists (`preferred_source`, `collection_status`, `sort`) |
| GET | `/api/watchlist/ids` | Set of watched artist IDs |
| POST | `/api/watchlist` | Add artist to watchlist |
| PATCH | `/api/watchlist/<id>` | Update watched artist (e.g. `collection_status`) |
| DELETE | `/api/watchlist/<id>` | Remove from watchlist |
| GET | `/api/watchlist/export` | Export watchlist as JSON |
| POST | `/api/watchlist/import` | Import watchlist JSON |
| GET | `/api/system/config` | Get current config |
| PUT | `/api/system/config` | Update config |
| POST | `/api/system/refresh` | Manually trigger a poll |
| GET | `/api/system/status` | Server/poll status |
| GET | `/api/system/db` | SQLite size + per-table stats |
| GET | `/api/system/discovery` | Recent discovery run records |
| GET | `/api/system/watchlist_log` | Recent watchlist batch records |
| POST | `/api/system/cli-scheduler/submit` | Proxy an album to the CLI Scheduler |
| GET/POST | `/api/notifications` | List / create notification events |
| PUT/DELETE | `/api/notifications/<id>` | Update / delete a notification event |
| POST | `/api/notifications/<id>/test`, `/api/notifications/test` | Send a test (saved / unsaved) |
| GET | `/api/notifications/event-types` | Event-type metadata (variables + defaults) |
| GET | `/api/debug/apple-music/artist`, `/album` | Raw Apple Music catalog responses |
| GET | `/api/admin/artists` | Watchlist artists with no MusicBrainz MBID, plus any suggestion |
| POST | `/api/admin/artists/search-all` | Bulk-search MusicBrainz for all un-suggested artists (background; poll `/search-all/status`) |
| POST | `/api/admin/artists/<id>/lookup` | Search MusicBrainz for an artist; store candidates as a suggestion |
| POST | `/api/admin/artists/<id>/approve` | Link an MBID (approve suggestion or manual entry) |
| POST | `/api/admin/artists/<id>/deny` | Dismiss a suggestion so the scanner won't re-suggest it |
| GET | `/api/admin/releases` | Releases flagged as missing from MusicBrainz (sortable; `include_hidden`) |
| POST | `/api/admin/releases/<id>/hide` | Hide / unhide a release from the seeding list (`/unhide`) |
| GET | `/api/admin/status` | Seeding scanner status + pending counts |
| POST | `/api/admin/scan` | Trigger a seeding scan cycle immediately |

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

## Frontend design system

Frontend visual rules live in `DESIGN.md` (repo root) and are auto-loaded via `frontend/CLAUDE.md` whenever you edit a file under `frontend/`.

**Rule of thumb:** design rules apply to everything under `frontend/`. Backend code has no visual concerns — don't import `DESIGN.md` for backend work.
