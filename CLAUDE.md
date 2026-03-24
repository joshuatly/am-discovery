# CLAUDE.md — AM Discovery

## What this project is

AM Discovery is an Apple Music new-release discovery tool. It monitors regional Apple Music "Room" pages (curated new-release sections in storefronts like HK, JP, MY, TW), aggregates albums across them, fetches full metadata, and exposes everything via a Flask REST API with a lightweight frontend SPA.

**Early development notice:** The schema, data model, and even the storage backend are actively evolving. Changes to the database structure, new fields, and potentially swapping out SQLite for another backend are all expected. Keep that in mind when modifying the DB layer.

---

## Architecture

```
client.py   — AppleMusicClient: scrapes music.apple.com + amp-api.music.apple.com
db.py       — SQLite database layer (all SQL lives here, nowhere else)
server.py   — Flask REST API + background polling scheduler
migrate.py  — Standalone migration runner for schema upgrades
main.py     — Ad-hoc CLI script for manual testing/exploration
frontend/   — Static SPA (index.html, app.js, style.css)
```

The server starts a background thread that polls configured Room URLs on a timer, fetches metadata for new albums concurrently, and persists everything to SQLite.

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

**Start the server:**
```bash
uv run python server.py
# or with debug logging:
uv run python server.py --debug
```

Server runs on `http://localhost:5000` by default. Set `PORT` env var to change.

**Run Python tests:**
```bash
uv run pytest
```

**Run frontend (JS) tests:**
```bash
cd frontend && npm test
```

The frontend has Jest tests in `frontend/__tests__/app.test.js`. **All new frontend code must have corresponding Jest test cases.** All new Python code must have corresponding pytest cases in `tests/`.

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
| `check_storefronts` | array | Storefronts to poll for new releases and check availability |
| `home_storefront` | string | Default storefront for metadata lookups |
| `newrelease_poll_interval_days` | integer | How often to poll for new releases (default: 1) |
| `cors_proxy` | string | Optional URL prefix for proxying requests |

The config is live-reloaded on every poll, so changes take effect on the next cycle without restarting.

---

## API summary

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/releases` | Paginated list; supports `q`, `page`, `per_page`, `storefront`, `view=new` |
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

- **Upsert pattern:** `upsert_album()` does `INSERT OR IGNORE` followed by `UPDATE` so concurrent inserts from multiple storefront pollers don't conflict.
- **Storefront merging:** Each album tracks which storefronts it was seen in; storefronts are merged (not replaced) on each upsert.
- **Source tracking:** Albums are tagged with `source='discovered'` (from room polling) or `source='artist_fetch'` (manually fetched via artist page). The `view=new` filter shows only discovered ones.
- **Info fetch caching:** `info_fetched=1` is set once full metadata has been retrieved; subsequent polls skip the expensive API call for known albums.
- **Concurrent fetches:** `ThreadPoolExecutor(max_workers=10)` is used for batch metadata fetches. Keep individual fetch functions side-effect-free (write to DB only, no shared mutable state).

---

## Things that are still in flux

- Database backend (SQLite today, may move to PostgreSQL or another store)
- Schema — new fields are being added regularly; always write a migration
- Frontend — currently a single-file vanilla JS app; no build step
- Room URLs in config — these are tied to Apple Music's platform and may change
- Artist release scraping — parsing relies on Apple Music page structure, which can break

When in doubt, keep changes small and don't over-engineer — the codebase is moving fast.
