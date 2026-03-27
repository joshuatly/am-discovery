# AM Discovery

> **Early development.** Things will break, the schema will change, and features are incomplete. Use at your own risk.

AM Discovery monitors Apple Music regional "Room" pages to surface new releases across multiple storefronts. It polls configurable room URLs, fetches full album metadata, and presents everything through a web UI and REST API.

---

## Features

- Polls Apple Music Room pages across multiple storefronts (HK, JP, MY, TW, etc.)
- Aggregates releases and tracks which storefronts each album appears in
- Fetches full metadata: artwork, genre, tracklist, audio formats (Dolby Atmos, lossless), release type
- Artist watchlist — follow artists and fetch their full catalog on demand
- Storefront availability checker for any release
- Configurable poll interval with manual refresh option
- REST API with Swagger docs (`/apidocs`)
- Lightweight single-page frontend

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

On first start the server will:
1. Create a fresh SQLite database
2. Immediately run a poll against your configured rooms
3. Schedule subsequent polls at the configured interval

---

## Configuration

Copy `config.json.example` to `config.json` and edit it:

```json
{
  "cors_proxy": "",
  "check_storefronts": ["jp", "tw", "my", "hk", "sg", "us"],
  "home_storefront": "my",
  "poll_interval_minutes": 60,
  "rooms": {
    "hk": "https://music.apple.com/hk/room/...",
    "jp": "https://music.apple.com/jp/room/...",
    "my": "https://music.apple.com/my/room/...",
    "tw": "https://music.apple.com/tw/room/..."
  }
}
```

| Key | Description |
|-----|-------------|
| `rooms` | Map of storefront code → Apple Music Room URL. These are the pages polled for new releases. |
| `check_storefronts` | Storefronts used when checking a release's availability. |
| `home_storefront` | Default storefront for metadata lookups in the UI. |
| `poll_interval_minutes` | How often to poll rooms. Default: 60. |
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

Swagger UI is available at `/apidocs` when the server is running.

| Endpoint | Description |
|----------|-------------|
| `GET /api/releases` | Paginated release list. Supports `q` (search), `page`, `per_page`, `storefront`, `view=new` (discovered only). |
| `GET /api/releases/<id>` | Single release detail. |
| `GET /api/releases/<id>/check_storefronts` | Check availability across configured storefronts. |
| `GET /api/lookup/<id>` | Fetch fresh metadata from Apple Music (bypasses local cache). |
| `GET /api/artists/<id>/releases` | All stored releases for an artist. |
| `POST /api/artists/<id>/fetch` | Fetch and store the full catalog for an artist. |
| `GET /api/search/artists?term=...` | Search Apple Music catalog for artists. |
| `GET /api/watchlist` | Get all watched artists. |
| `POST /api/watchlist` | Add an artist to the watchlist (`artist_id`, `name`, `url`). |
| `DELETE /api/watchlist/<id>` | Remove an artist from the watchlist. |
| `GET /api/config` | Get current configuration. |
| `PUT /api/config` | Update configuration. |
| `POST /api/refresh` | Manually trigger a poll immediately. |
| `GET /api/status` | Server status, last poll info, next scheduled run. |

---

## Docker / Portainer deployment

### Overview

The container exposes port 5000 and expects a single persistent volume mounted at `/data` containing:

| File | Purpose |
|------|---------|
| `/data/config.json` | Application config (seeded from `config.json.example` on first boot) |
| `/data/am_discovery.db` | SQLite database |
| `/data/bearer_token.txt` | Cached Apple Music bearer token (auto-generated) |

### Deploying from Portainer via Gitea

1. In Portainer, go to **Stacks → Add stack → Git repository**.
2. Set the repository URL to your Gitea mirror (e.g. `https://gitea.example.com/youruser/am-discovery`).
3. If the repository is private, create a Gitea access token under *Settings → Applications → Access Tokens* and add it as a **Git credential** in Portainer (Settings → Git credentials).
4. Set the **Compose path** to `docker-compose.yml`.
5. Enable **Automatic updates** if you want Portainer to redeploy on new commits.
6. Deploy the stack.

Portainer will clone the repository and build the image from the `Dockerfile`.

### Nginx reverse proxy

Port 5000 is published on all interfaces (`0.0.0.0`), so the nginx proxy can reach the container by the Docker host's LAN IP (e.g. `192.168.5.x`).

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
        proxy_pass         http://192.168.5.x:5000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

Replace `192.168.5.x` with the actual LAN IP of the Portainer host. Place this in `/etc/nginx/sites-available/am-discovery` (or equivalent), symlink it to `sites-enabled`, then reload nginx.

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
| `PORT` | `5000` | Port Flask listens on inside the container |
| `AM_DB_PATH` | `/data/am_discovery.db` | Path to the SQLite database |

---

## Development

```bash
# Run tests
uv run pytest

# One-off manual test / exploration
uv run python main.py
```

The `bearer_token.txt` file is auto-generated and gitignored. The client extracts a JWT from the Apple Music web app and caches it locally; it will refresh automatically when it expires.

---

## Notes

- The app scrapes Apple Music web pages and uses their internal API. It does not use an official Apple Music API key. This means parsing can break if Apple changes their page structure.
- Room URLs are specific to each storefront and region. Finding the right room URLs for your region requires browsing the Apple Music app or website.
- The database schema is still evolving — expect migration steps when updating.
