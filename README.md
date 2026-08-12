# AM Discovery

> **Early development.** Things will break, the schema will change, and features are incomplete. Use at your own risk.

AM Discovery monitors Apple Music regional new-release pages to surface new releases across multiple storefronts. It automatically discovers new releases from each configured storefront's `/new` browse page, fetches full album metadata, and presents everything through a web UI and REST API.

---

## Features

- Polls Apple Music new-release pages across multiple storefronts (HK, JP, MY, TW, etc.)
- Automatically discovers the new-release section from each storefront's `/new` browse page — no manual room URL configuration required
- Aggregates releases and tracks which storefronts each album appears in
- Fetches full metadata: artwork, genre, tracklist, audio formats (Dolby Atmos, lossless, Hi-Res, Apple Digital Masters), release type; separates music videos from song tracks
- Artist watchlist — follow artists and fetch their full catalog on demand; background polling keeps watchlist artists up to date
- Watchlist curation — tag each followed artist with a collection status (New, In Progress, Complete, New Release) and filter/sort by it; export and import your watchlist as JSON
- Apprise notifications — send push/webhook alerts on discovery runs, watchlist batches, and new releases/singles from watched artists, with per-event customizable templates
- MusicBrainz seeding admin — flag releases missing from MusicBrainz and link artist MBIDs, with a background scanner and browser-side [Harmony](https://harmony.pulsewidth.org.uk/) seeding
- Similar-artist and "you might also like" discovery pulled from Apple Music
- Storefront availability checker for any release
- Configurable timezone for all displayed timestamps
- Optional CLI Scheduler integration — POST an album's Apple Music URL as a webhook job to an external service such as [cli-scheduler](https://github.com/joshuatly/cli-scheduler) for further processing (see [CLI Scheduler integration](#cli-scheduler-integration))
- Configurable poll intervals with manual refresh option
- REST API with Swagger docs (`/apidocs`)
- Lightweight single-page frontend (vanilla JS, no build step)

---

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv)

---

## Setup

```bash
# 1. Clone and install dependencies
git clone <repo>
cd am-discovery
uv sync

# 2. Create config
cp config.json.example config.json
```

Edit `config.json` with your settings (see [Configuration](#configuration) below).

---

## Running

### Development

```bash
uv run python server.py
```

Open `http://localhost:5000` in your browser.

```bash
# With debug logging
uv run python server.py --debug

# Custom port
PORT=8080 uv run python server.py

# Custom database path
AM_DB_PATH=/data/am.db uv run python server.py
```

### Production (Gunicorn)

```bash
uv run gunicorn -c gunicorn.conf.py "wsgi:app"
```

`wsgi.py` is the WSGI entry point — it imports the Flask app and starts the background polling scheduler. `gunicorn.conf.py` pins the worker count to 1 (required because the scheduler runs as an in-process background thread).

On first start the server will:
1. Create a fresh SQLite database
2. Immediately run a poll against your configured storefronts
3. Schedule subsequent polls at the configured interval

---

## Configuration

Copy `config.json.example` to `config.json` and edit it:

```json
{
  "cors_proxy": "",
  "check_storefronts": ["jp", "tw", "my", "hk", "sg", "us"],
  "home_storefront": "my",
  "timezone": "UTC",
  "newrelease_poll_interval_days": 1,
  "watchlist_poll_interval_minutes": 10,
  "watchlist_poll_batch_size": 5,
  "watchlist_refresh_interval_days": 7,
  "notification_scan_interval_minutes": 10,
  "notification_max_release_age_days": 7,
  "mb_scan_enabled": true,
  "mb_scan_interval_minutes": 60,
  "mb_scan_artist_batch": 3,
  "mb_artist_recheck_days": 7,
  "cli_scheduler_url": "",
  "cli_scheduler_preset": "",
  "notifications": {
    "queue_max_size": 100,
    "max_failures": 5,
    "rate_limit_per_sec": 1,
    "events": []
  }
}
```

Every key has a built-in default, so a minimal `config.json` only needs the settings you want to override.

| Key | Description |
|-----|-------------|
| `check_storefronts` | Storefronts to poll for new releases and check availability. The app auto-discovers the new-release section from each storefront's `/new` page. |
| `home_storefront` | Default storefront for metadata lookups in the UI. |
| `timezone` | IANA timezone (e.g. `Asia/Hong_Kong`) used to render every displayed timestamp. Falls back to `UTC` if unset or unrecognized. |
| `newrelease_poll_interval_days` | How often to poll for new releases. Default: 1. |
| `watchlist_poll_interval_minutes` | How often to check watchlist artists for new releases. Default: 10. |
| `watchlist_poll_batch_size` | Number of watchlist artists to refresh per poll cycle. Default: 5. |
| `watchlist_refresh_interval_days` | How many days before a watchlist artist's catalog is considered stale and re-fetched. Default: 7. |
| `notification_scan_interval_minutes` | How often the notification scanner looks for new watched-artist releases to alert on. Default: 10. |
| `notification_max_release_age_days` | Ignore releases older than this (by release date) when firing new-release notifications. Default: 7. |
| `mb_scan_enabled` | Enable the background MusicBrainz seeding scanner. Default: true. |
| `mb_scan_interval_minutes` | How often the seeding scanner runs a cycle. Default: 60. |
| `mb_scan_artist_batch` | Artists processed per seeding-scan phase. Keep small — MusicBrainz allows ~1 req/sec. Default: 3. |
| `mb_artist_recheck_days` | Minimum days before re-scanning an artist for its MBID / releases. Default: 7. |
| `cli_scheduler_url` | Base URL of an optional external webhook service that receives album job submissions (see [CLI Scheduler integration](#cli-scheduler-integration)). Empty disables the integration. |
| `cli_scheduler_preset` | Preset name passed with each job submission. |
| `notifications` | Apprise notification settings — see [Notifications](#notifications). Global queue tuning (`queue_max_size`, `max_failures`, `rate_limit_per_sec`) plus the list of configured `events`. Edit events from the Settings page, not by hand. |
| `cors_proxy` | Optional URL prefix to proxy outbound requests through (e.g. `https://proxy.example.com/`). Leave empty if not needed. |

Config changes are picked up automatically on the next poll — no restart required.

---

## Database migrations

If you have an existing database and pull new code that bumps the schema version, run:

```bash
uv run python migrate.py
```

This applies any pending migrations and updates the schema version. It is safe to run repeatedly — already-applied migrations are skipped.

**Fresh installs do not need this** — the server creates the database at the latest schema version automatically.

---

## API

Swagger UI is available at `/apidocs` when the server is running. `/apidocs` is the authoritative reference — the table below is a summary.

**Releases**

| Endpoint | Description |
|----------|-------------|
| `GET /api/releases` | Paginated release list. Supports `q` (search), `page`, `per_page`, `storefront`, `view=new` (discovered only), `watched=true`, `release_type`. |
| `GET /api/releases/<id>` | Single release detail. |
| `GET /api/releases/<id>/check_storefronts` | Check availability across configured storefronts. |
| `GET /api/releases/<id>/lookup` | Fetch fresh metadata from Apple Music (bypasses local cache). |
| `GET /api/releases/<id>/musicbrainz` | Look up the release on MusicBrainz (barcode, then search). |
| `GET /api/releases/<id>/you-might-also-like` | Apple Music "you might also like" recommendations for the release. |

**Artists**

| Endpoint | Description |
|----------|-------------|
| `GET /api/artists/<id>/releases` | All stored releases for an artist. |
| `POST /api/artists/<id>/fetch` | Fetch and store the full catalog for an artist. |
| `PATCH /api/artists/<id>` | Update editable artist fields (e.g. alternate names, MBID). |
| `GET /api/artists/<id>/similar` | Similar artists from Apple Music. |
| `GET /api/artists/search?term=...` | Search the Apple Music catalog for artists. |
| `GET /api/artists/search/local?q=...` | Search artists already stored locally. |

**Watchlist**

| Endpoint | Description |
|----------|-------------|
| `GET /api/watchlist` | Get watched artists. Supports `preferred_source`, `collection_status`, `sort`. |
| `GET /api/watchlist/ids` | Get just the set of watched artist IDs. |
| `POST /api/watchlist` | Add an artist to the watchlist. |
| `PATCH /api/watchlist/<id>` | Update a watched artist (e.g. `collection_status`, `preferred_source`). |
| `DELETE /api/watchlist/<id>` | Remove an artist from the watchlist. |
| `GET /api/watchlist/export` | Export the watchlist as JSON. |
| `POST /api/watchlist/import` | Import a watchlist JSON payload. |

**System / config**

| Endpoint | Description |
|----------|-------------|
| `GET /api/system/config` | Get current configuration. |
| `PUT /api/system/config` | Update configuration. |
| `POST /api/system/refresh` | Manually trigger a poll immediately. |
| `GET /api/system/status` | Server status, last poll info, next scheduled run. |
| `GET /api/system/db` | SQLite database size and per-table statistics. |
| `GET /api/system/discovery` | Recent discovery run records (one row per storefront per run). |
| `GET /api/system/watchlist_log` | Recent watchlist batch run records. |
| `POST /api/system/cli-scheduler/submit` | POST an album's Apple Music URL as a webhook job to the configured external service (see [CLI Scheduler integration](#cli-scheduler-integration)). |

**Notifications** (see [Notifications](#notifications))

| Endpoint | Description |
|----------|-------------|
| `GET /api/notifications` | List configured events + global settings. |
| `POST /api/notifications` | Create an event. |
| `PUT /api/notifications/<id>` | Update an event. |
| `DELETE /api/notifications/<id>` | Delete an event. |
| `POST /api/notifications/<id>/test` | Send a test notification for a saved event. |
| `POST /api/notifications/test` | Send a test notification for an unsaved event payload. |
| `GET /api/notifications/event-types` | Event-type metadata (variables + default templates). |

**MusicBrainz seeding admin** (see [MusicBrainz seeding](#musicbrainz-seeding))

| Endpoint | Description |
|----------|-------------|
| `GET /api/admin/artists` | Watchlist artists missing an MBID, plus any suggestion. |
| `POST /api/admin/artists/search-all` | Bulk-search MusicBrainz for all un-suggested artists (background). |
| `GET /api/admin/artists/search-all/status` | Progress of the bulk search. |
| `POST /api/admin/artists/<id>/lookup` | Search MusicBrainz for one artist; store candidates. |
| `POST /api/admin/artists/<id>/approve` | Link an MBID (approve or manual entry). |
| `POST /api/admin/artists/<id>/deny` | Dismiss a suggestion. |
| `GET /api/admin/releases` | Releases flagged as missing from MusicBrainz. |
| `POST /api/admin/releases/<id>/hide` | Hide (or `/unhide`) a release from the seeding list. |
| `GET /api/admin/status` | Seeding scanner status + pending counts. |
| `POST /api/admin/scan` | Trigger a seeding scan cycle immediately. |

**Debug**

| Endpoint | Description |
|----------|-------------|
| `GET /api/debug/apple-music/artist` | Raw Apple Music catalog response for an artist. |
| `GET /api/debug/apple-music/album` | Raw Apple Music catalog response for an album. |

---

## Notifications

AM Discovery can push alerts to an [Apprise](https://github.com/caronc/apprise) API server (e.g. a self-hosted `http://host:8100/notify/apprise` endpoint). Configure notifications from the **Settings** page — no manual config editing needed.

Supported events:

| Event | Fires when |
|-------|-----------|
| `onDiscoveryComplete` | A storefront discovery poll finishes. |
| `onDiscoveryFailed` | One or more storefronts fail during a discovery poll. |
| `onArtistNewRelease` | A watched artist releases a new album/EP. |
| `onArtistNewSingle` | A watched artist releases a new single. |
| `onWatchlistBatchComplete` | A watchlist refresh batch finishes. |

Each event has its own Apprise URL, notification type (info/success/warning/failure), and customizable `{variable}` title/body templates. A "Send test" button verifies delivery. Sends run through a single rate-limited worker thread; an event that fails `max_failures` times in a row is auto-disabled. Watched-artist alerts are driven by a separate scanner thread (`notification_scan_interval_minutes`) that looks back over recently first-seen releases. All notification config lives in `config.json` under the `notifications` key — there is no separate database table.

---

## MusicBrainz seeding

The **Admin** page (`/#/admin`) helps get your watched artists' releases into [MusicBrainz](https://musicbrainz.org/):

- **Artists tab** — links watchlist artists to a MusicBrainz artist MBID. The app suggests candidates (individually or via a bulk background search); you approve or deny each. Nothing is auto-linked.
- **Releases tab** — lists releases flagged as missing from MusicBrainz. A background scanner cross-checks each watched artist's catalog against MusicBrainz and flags gaps. Actual seeding happens in your browser via [Harmony](https://harmony.pulsewidth.org.uk/) using your own MusicBrainz login — the server never submits edits.

No MusicBrainz API key is required; the read-only `/ws/2` web service only needs a descriptive User-Agent and ~1 req/sec rate limiting, both handled automatically. Tune the scanner with the `mb_scan_*` and `mb_artist_recheck_days` config keys.

---

## CLI Scheduler integration

AM Discovery doesn't download anything itself. When `cli_scheduler_url` is set, a "Send to scheduler" button appears on each release, and pressing it does the following:

```
POST {cli_scheduler_url}/api/jobs
{ "preset": "<cli_scheduler_preset>", "urls": ["https://music.apple.com/<storefront>/album/<id>"] }
```

That's it — it's a thin webhook proxy (`POST /api/system/cli-scheduler/submit`, see [`api_system.py`](api_system.py)) that hands the album's Apple Music URL and your configured preset name to whatever HTTP service you point it at. What happens next is entirely up to that service.

It was built against [joshuatly/cli-scheduler](https://github.com/joshuatly/cli-scheduler), a self-hosted job queue that turns an Apple Music URL into an automated download using a preset (e.g. a specific format/quality profile), but any service that accepts the same `{preset, urls}` payload on `/api/jobs` works.

---

## Docker / Portainer deployment

### Overview

The container exposes port 5000 and expects a single persistent volume mounted at `/data` containing:

| File | Purpose |
|------|---------|
| `/data/config.json` | Application config (seeded from `config.json.example` on first boot) |
| `/data/am_discovery.db` | SQLite database |
| `/data/bearer_token.txt` | Cached Apple Music bearer token (auto-generated) |

The container runs Gunicorn via `wsgi.py` as its entry point.

### Deploying from Portainer via Gitea

1. In Portainer, go to **Stacks → Add stack → Git repository**.
2. Set the repository URL to your Gitea mirror (e.g. `https://gitea.example.com/youruser/am-discovery`).
3. If the repository is private, create a Gitea access token under *Settings → Applications → Access Tokens* and add it as a **Git credential** in Portainer (Settings → Git credentials).
4. Set the **Compose path** to `docker-compose.yml`.
5. Enable **Automatic updates** if you want Portainer to redeploy on new commits.
6. Deploy the stack.

Portainer will clone the repository and build the image from the `Dockerfile`.

### Nginx reverse proxy

Port 5000 is published on all interfaces (`0.0.0.0`), so the nginx proxy can reach the container by the Docker host's LAN IP (e.g. `192.168.1.x`).

```nginx
server {
    listen 80;
    server_name am.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name am.example.com;

    ssl_certificate     /etc/ssl/certs/am.example.com.crt;
    ssl_certificate_key /etc/ssl/private/am.example.com.key;

    location / {
        proxy_pass         http://192.168.1.x:5000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

Replace `192.168.1.x` with the actual LAN IP of the Portainer host. Place this in `/etc/nginx/sites-available/am-discovery` (or equivalent), symlink it to `sites-enabled`, then reload nginx.

### First-run configuration

On first boot the entrypoint copies `config.json.example` to `/data/config.json`. The container will start polling immediately with the default settings. **Edit `/data/config.json` inside the volume to configure your storefronts and other options** — changes are picked up on the next poll without restarting.

To edit the config through Portainer: go to **Volumes**, browse the `am_data` volume, and edit `config.json` in place. Alternatively, exec into the container:

```bash
docker exec -it am-discovery sh
vi /data/config.json
```

### Running database migrations

If you update the stack from a commit that bumps the database schema version, run the migration before (or immediately after) the new container starts:

```bash
docker exec -it am-discovery uv run python migrate.py
```

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `5000` | Port Gunicorn listens on inside the container |
| `AM_DB_PATH` | `/data/am_discovery.db` | Path to the SQLite database |

---

## Development

```bash
# Run Python tests
uv run pytest

# Run frontend JS tests
cd frontend && npm test

# One-off manual test / exploration
uv run python main.py
```

Python tests are split by module — e.g. `tests/test_api.py` (core routes), `tests/test_api_watchlist.py` (watchlist), `tests/test_api_admin.py` (seeding admin), `tests/test_api_notifications.py` and `tests/test_notifications.py` (notifications), `tests/test_api_debug.py` (debug endpoints), `tests/test_server.py` (config helpers + polling scheduler), `tests/test_db.py`, `tests/test_client.py`, `tests/test_musicbrainz.py`, `tests/test_seeding.py`, `tests/test_storefronts.py`, and `tests/test_migrate.py`. Network is always mocked. All new Python code must ship with matching tests.

### Frontend structure

The frontend is vanilla JS with no build step. JS is split into focused modules loaded via `<script>` tags in `frontend/index.html`:

| File | Responsibility |
|------|---------------|
| `utils.js` | API helpers, DOM utilities, date/time, constants |
| `components.js` | Reusable UI components (cards, chips, pagination) |
| `state.js` | Global app state and watchlist helpers |
| `status.js` | Status bar and metadata source widget |
| `modal.js` | Album detail modal |
| `page-releases.js` | New Releases and All Albums pages |
| `page-artist.js` | Artist Detail page |
| `page-watchlist.js` | Artist Watchlist page (collection-status curation) |
| `page-settings.js` | Settings page (config, timezone, notifications, CLI Scheduler) |
| `page-admin.js` | Admin page (MusicBrainz seeding: Artists + Releases tabs) |
| `app.js` | Router and bootstrap |

See `CLAUDE.md` for the full breakdown of where to put new frontend code.

The `bearer_token.txt` file is auto-generated and gitignored. The client extracts a JWT from the Apple Music web app and caches it locally; it will refresh automatically when it expires.

---

## Notes

- The app scrapes Apple Music web pages and uses their internal API. It does not use an official Apple Music API key. This means parsing can break if Apple changes their page structure.
- New releases are discovered automatically by scanning each storefront's `/new` browse page. No manual room URL configuration is needed.
- The database schema is still evolving — expect migration steps when updating.
