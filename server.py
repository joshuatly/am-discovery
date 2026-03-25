"""AM Discovery Web Server
Flask-based REST API + background polling scheduler.
Run: uv run python server.py
"""

import concurrent.futures
import json
import logging
import os
import re
import threading
import time
from datetime import UTC, datetime

from flasgger import Swagger
from flask import Flask, jsonify, request, send_from_directory

import db
from client import AppleMusicClient

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

logger = logging.getLogger(__name__)

_STOREFRONT_RE = re.compile(r"^[a-z]{2,3}$")


def _validate_storefront(sf: str):
    """Return sf if it looks like a valid ISO storefront code, else None."""
    return sf if _STOREFRONT_RE.match(sf) else None


app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
swagger = Swagger(app)

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def load_config() -> dict:
    defaults = {
        "newrelease_poll_interval_days": 1,
        "check_storefronts": ["jp", "tw", "my", "hk", "sg"],
        "home_storefront": "my",
        "watchlist_poll_interval_minutes": 10,
        "watchlist_poll_batch_size": 5,
        "watchlist_refresh_interval_days": 7,
    }
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return {**defaults, **json.load(f)}
    return defaults


def save_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Polling logic
# ---------------------------------------------------------------------------

_scheduler_lock = threading.Lock()
_next_run_at: float = 0.0
_poll_timer: threading.Timer | None = None
_is_running = False
_last_room_errors: list[str] = []


def _do_poll():
    global _next_run_at, _is_running, _last_room_errors
    _is_running = True
    try:
        cfg = load_config()
        storefronts = cfg.get("check_storefronts", [])
        client = AppleMusicClient()

        # 1. Discover new releases from each storefront's /new page
        all_releases: dict[str, dict] = {}
        room_errors = []
        for sf in storefronts:
            room_url = client.discover_room_url(sf)
            if not room_url:
                room_errors.append(sf)
                rels = []
            else:
                rels = client.get_room_new_releases(room_url, sf)
            logger.info("[Poll] [%s] %d releases", sf.upper(), len(rels))
            for r in rels:
                aid = r["storeAdamID"]
                if aid in all_releases:
                    if sf not in all_releases[aid]["storefronts"]:
                        all_releases[aid]["storefronts"].append(sf)
                else:
                    all_releases[aid] = r
        _last_room_errors = room_errors

        # 2. Separate new (need full info fetch) vs known (skip fetch)
        new_ids = []
        known_ids = []
        for aid in all_releases:
            row = db.get_album(aid)
            if row and row.get("info_fetched"):
                known_ids.append(aid)
            else:
                new_ids.append(aid)

        logger.info("[Poll] %d new, %d already cached", len(new_ids), len(known_ids))

        # 3. Fetch full info only for new albums (concurrent)
        def fetch_full(aid):
            r = all_releases[aid]
            info = client.get_album_full_info(r["url"])
            merged = {
                "store_adam_id": aid,
                "title": r.get("title"),
                "artist": r.get("artist"),
                "url": r.get("url"),
                "storefronts": r.get("storefronts", []),
                "release_date": info.get("release_date"),
                "artwork_url": info.get("artwork_url"),
                "track_count": info.get("track_count"),
                "genre": info.get("genre"),
                "description": info.get("description"),
                "artist_id": info.get("artist_id"),
                "artist_url": info.get("artist_url"),
                "artists_json": info.get("artists"),
                "audio_formats": info.get("audio_formats"),
                "info_fetched": 1,
                "source": "discovered",
            }
            db.upsert_album(merged)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            list(ex.map(fetch_full, new_ids))

        # 4. For known albums, just update storefronts / last_seen
        for aid in known_ids:
            r = all_releases[aid]
            db.upsert_album(
                {
                    "store_adam_id": aid,
                    "title": r.get("title"),
                    "artist": r.get("artist"),
                    "url": r.get("url"),
                    "storefronts": r.get("storefronts", []),
                    "info_fetched": 1,
                    "source": "discovered",
                },
            )

        total = db.list_albums()[1]
        db.log_discovery_run(len(new_ids), total)
        logger.info("[Poll] Done. DB total: %d", total)

    except Exception as e:
        logger.error("[Poll] Error: %s", e)
    finally:
        _is_running = False
        _schedule_next()


def _schedule_next(override_delay=None):
    global _next_run_at, _poll_timer
    cfg = load_config()
    interval_sec = cfg.get("newrelease_poll_interval_days", 1) * 86400
    delay = override_delay if override_delay is not None else interval_sec
    _next_run_at = time.time() + delay
    with _scheduler_lock:
        if _poll_timer:
            _poll_timer.cancel()
        _poll_timer = threading.Timer(delay, _do_poll)
        _poll_timer.daemon = True
        _poll_timer.start()
    logger.info("[Scheduler] Next poll in %.1f minutes", delay / 60)


def trigger_poll_now():
    """Cancel any pending timer and run immediately in a thread."""
    global _poll_timer
    with _scheduler_lock:
        if _poll_timer:
            _poll_timer.cancel()
            _poll_timer = None
    t = threading.Thread(target=_do_poll, daemon=True)
    t.start()


# ---------------------------------------------------------------------------
# Watchlist polling logic
# ---------------------------------------------------------------------------

_watchlist_lock = threading.Lock()
_watchlist_timer: threading.Timer | None = None
_watchlist_running = False


def _do_watchlist_poll():
    global _watchlist_running
    _watchlist_running = True
    try:
        cfg = load_config()
        batch_size = cfg.get("watchlist_poll_batch_size", 5)
        refresh_days = cfg.get("watchlist_refresh_interval_days", 7)
        home_sf = cfg.get("home_storefront", "my")

        artists = db.get_artists_needing_refresh(batch_size, refresh_days)
        if not artists:
            logger.info("[WatchlistPoll] No artists need refreshing")
            return

        logger.info("[WatchlistPoll] Refreshing %d artists", len(artists))
        client = AppleMusicClient()

        for artist in artists:
            artist_id = artist["artist_id"]
            storefront = artist.get("preferred_source") or home_sf
            artist_url = f"https://music.apple.com/{storefront}/artist/{artist_id}"

            try:
                releases, artist_info = client.get_artist_all_releases(artist_url, storefront)
                db.upsert_artist(
                    artist_id,
                    name=artist_info.get("name"),
                    artwork_url=artist_info.get("artwork_url"),
                    genre=artist_info.get("genre"),
                )

                def fetch_one(r, storefront=storefront, artist_id=artist_id):
                    aid = r["storeAdamID"]
                    existing = db.get_album(aid)
                    album_url = f"https://music.apple.com/{storefront}/album/{aid}"
                    info = client.get_album_full_info(album_url)
                    album_data = {
                        "store_adam_id": aid,
                        "url": r.get("url") or album_url,
                        "storefronts": r.get("storefronts", [storefront]),
                        "release_date": info.get("release_date"),
                        "artwork_url": info.get("artwork_url"),
                        "track_count": info.get("track_count"),
                        "genre": info.get("genre"),
                        "description": info.get("description"),
                        "artist_id": info.get("artist_id") or artist_id,
                        "artist_url": info.get("artist_url"),
                        "artists_json": info.get("artists"),
                        "audio_formats": info.get("audio_formats"),
                        "release_type": r.get("release_type"),
                        "info_fetched": 1,
                        "source": "artist_fetch",
                    }
                    if not existing:
                        album_data["title"] = r.get("title") or info.get("title") or "Unknown"
                        album_data["artist"] = r.get("artist") or info.get("artist")
                    db.upsert_album(album_data)

                with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
                    list(ex.map(fetch_one, releases))

                db.mark_artist_refreshed(artist_id)
                logger.info("[WatchlistPoll] Refreshed %s (%d releases)", artist.get("name"), len(releases))

            except Exception as e:
                logger.error("[WatchlistPoll] Error refreshing %s: %s", artist.get("name"), e)

    except Exception as e:
        logger.error("[WatchlistPoll] Error: %s", e)
    finally:
        _watchlist_running = False
        _schedule_watchlist_next()


def _schedule_watchlist_next(override_delay=None):
    global _watchlist_timer
    cfg = load_config()
    interval_sec = cfg.get("watchlist_poll_interval_minutes", 10) * 60
    delay = override_delay if override_delay is not None else interval_sec
    with _watchlist_lock:
        if _watchlist_timer:
            _watchlist_timer.cancel()
        _watchlist_timer = threading.Timer(delay, _do_watchlist_poll)
        _watchlist_timer.daemon = True
        _watchlist_timer.start()
    logger.info("[WatchlistScheduler] Next watchlist poll in %.1f minutes", delay / 60)


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------


def _serialize(row: dict) -> dict:
    """Ensure storefronts, audio_formats, and artists_json are lists (stored as JSON strings in SQLite)."""
    if isinstance(row.get("storefronts"), str):
        row["storefronts"] = json.loads(row["storefronts"])
    if isinstance(row.get("audio_formats"), str):
        row["audio_formats"] = json.loads(row["audio_formats"])
    if isinstance(row.get("artists_json"), str):
        row["artists_json"] = json.loads(row["artists_json"])
    return row


@app.route("/api/releases")
def api_releases():
    """Get a paginated list of releases.
    ---

    Parameters
    ----------
      - name: page
        in: query
        type: integer
        default: 1
      - name: per_page
        in: query
        type: integer
        default: 50
      - name: q
        in: query
        type: string
        description: Search query for title or artist
    responses:
      200:
        description: A list of releases

    """
    try:
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 50))
    except (ValueError, TypeError):
        return jsonify({"error": "page and per_page must be integers"}), 400
    q = request.args.get("q", "").strip()
    raw_sf = request.args.get("storefront", "").strip().lower()
    storefront = _validate_storefront(raw_sf) if raw_sf else ""
    if raw_sf and not storefront:
        return jsonify({"error": "invalid storefront"}), 400
    discovered_only = request.args.get("view") == "new"
    watched_only = request.args.get("watched") == "true"

    if q:
        rows, total = db.search_albums(
            q,
            page,
            per_page,
            storefront=storefront,
            discovered_only=discovered_only,
            watched_only=watched_only,
        )
    else:
        rows, total = db.list_albums(
            page,
            per_page,
            storefront=storefront,
            discovered_only=discovered_only,
            watched_only=watched_only,
        )

    watched_ids = db.get_watched_artist_ids()
    result = []
    for r in rows:
        r = _serialize(r)
        r["watched"] = r.get("artist_id") in watched_ids
        result.append(r)

    return jsonify({"items": result, "total": total, "page": page, "per_page": per_page})


@app.route("/api/releases/<store_adam_id>")
def api_release_detail(store_adam_id):
    """Get details for a specific release.
    ---

    Parameters
    ----------
      - name: store_adam_id
        in: path
        type: string
        required: true
    responses:
      200:
        description: Release details
      404:
        description: Release not found

    """
    row = db.get_album(store_adam_id)
    if not row:
        return jsonify({"error": "Not found"}), 404
    row = _serialize(row)
    watched_ids = db.get_watched_artist_ids()
    row["watched"] = row.get("artist_id") in watched_ids
    return jsonify(row)


@app.route("/api/releases/<store_adam_id>/check_storefronts")
def api_check_storefronts(store_adam_id):
    """Check availability of a release across different storefronts.
    ---

    Parameters
    ----------
      - name: store_adam_id
        in: path
        type: string
        required: true
    responses:
      200:
        description: Availability results

    """
    cfg = load_config()
    storefronts = cfg.get("check_storefronts", ["jp", "my", "us", "hk", "tw", "sg"])
    client = AppleMusicClient()
    result = client.check_storefront_availability(store_adam_id, storefronts)
    return jsonify(result)


@app.route("/api/lookup/<store_adam_id>")
def api_lookup(store_adam_id):
    """Fetch fresh metadata for a release from a specific storefront.
    ---

    Parameters
    ----------
      - name: store_adam_id
        in: path
        type: string
        required: true
      - name: storefront
        in: query
        type: string
        default: us
    responses:
      200:
        description: Fresh metadata from the specified storefront

    """
    storefront = _validate_storefront(request.args.get("storefront", "us").strip().lower())
    if not storefront:
        return jsonify({"error": "invalid storefront"}), 400
    url = f"https://music.apple.com/{storefront}/album/{store_adam_id}"
    client = AppleMusicClient()
    info = client.get_album_full_info(url)
    return jsonify(info)


@app.route("/api/artists/<artist_id>/fetch", methods=["POST"])
def api_artist_fetch(artist_id):
    """Fetch all releases for an artist from a specific storefront and store them.
    ---

    Parameters
    ----------
      - name: artist_id
        in: path
        type: string
        required: true
      - name: storefront
        in: query
        type: string
        description: Storefront to fetch from (defaults to first configured storefront)
    responses:
      200:
        description: Fetch result with count

    """
    raw_sf = request.args.get("storefront", "").strip().lower()
    if raw_sf:
        storefront = _validate_storefront(raw_sf)
        if not storefront:
            return jsonify({"error": "invalid storefront"}), 400
    else:
        cfg = load_config()
        storefront = (cfg.get("check_storefronts") or ["us"])[0]

    client = AppleMusicClient()
    artist_url = f"https://music.apple.com/{storefront}/artist/{artist_id}"
    releases, artist_info = client.get_artist_all_releases(artist_url, storefront)

    if not releases:
        return jsonify({"ok": True, "fetched": 0, "message": "No releases found on artist page"})

    # Cache artist metadata (name, artwork, genre) for any artist that gets fetched
    db.upsert_artist(
        artist_id,
        name=artist_info.get("name"),
        artwork_url=artist_info.get("artwork_url"),
        genre=artist_info.get("genre"),
    )

    def fetch_one(r):
        aid = r["storeAdamID"]
        existing = db.get_album(aid)
        album_url = f"https://music.apple.com/{storefront}/album/{aid}"
        info = client.get_album_full_info(album_url)

        album_data = {
            "store_adam_id": aid,
            "url": r.get("url") or album_url,
            "storefronts": r.get("storefronts", [storefront]),
            "release_date": info.get("release_date"),
            "artwork_url": info.get("artwork_url"),
            "track_count": info.get("track_count"),
            "genre": info.get("genre"),
            "description": info.get("description"),
            "artist_id": info.get("artist_id") or artist_id,
            "artist_url": info.get("artist_url"),
            "artists_json": info.get("artists"),
            "audio_formats": info.get("audio_formats"),
            "release_type": r.get("release_type"),
            "info_fetched": 1,
            "source": "artist_fetch",
        }
        if not existing:
            # New to DB — store localised title/artist from this storefront
            album_data["title"] = r.get("title") or info.get("title") or "Unknown"
            album_data["artist"] = r.get("artist") or info.get("artist")

        db.upsert_album(album_data)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(fetch_one, releases))

    return jsonify({"ok": True, "fetched": len(releases)})


@app.route("/api/artists/<artist_id>/releases")
def api_artist_releases(artist_id):
    """Get all releases for a specific artist.
    ---

    Parameters
    ----------
      - name: artist_id
        in: path
        type: string
        required: true
    responses:
      200:
        description: Artist releases

    """
    rows = db.get_artist_albums(artist_id)
    watched_ids = db.get_watched_artist_ids()
    result = [_serialize(r) for r in rows]
    watched = artist_id in watched_ids
    artist_url = next((r.get("artist_url") for r in result if r.get("artist_url")), None)
    artist_info = db.get_artist_info(artist_id)
    return jsonify(
        {
            "artist_id": artist_id,
            "artist_name": artist_info.get("name"),
            "artist_url": artist_url,
            "artist_artwork_url": artist_info.get("artwork_url"),
            "artist_genre": artist_info.get("genre"),
            "watched": watched,
            "releases": result,
        },
    )


@app.route("/api/search/artists")
def api_search_artists():
    """Search Apple Music catalog for artists.
    ---

    Parameters
    ----------
      - name: term
        in: query
        type: string
        required: true
      - name: storefront
        in: query
        type: string
        default: us
      - name: limit
        in: query
        type: integer
        default: 25
    responses:
      200:
        description: List of matching artists
      400:
        description: Missing term parameter

    """
    term = request.args.get("term", "").strip()
    if not term:
        return jsonify({"error": "term is required"}), 400

    storefront = _validate_storefront(request.args.get("storefront", "us").strip().lower())
    if not storefront:
        return jsonify({"error": "invalid storefront"}), 400
    try:
        limit = min(int(request.args.get("limit", 25)), 50)
    except (ValueError, TypeError):
        return jsonify({"error": "limit must be an integer"}), 400

    client = AppleMusicClient()
    results = client.search_artists(term, storefront=storefront, limit=limit)
    return jsonify({"results": results})


@app.route("/api/watchlist", methods=["GET"])
def api_watchlist_get():
    """Get the current watchlist.
    ---

    Parameters
    ----------
      - name: preferred_source
        in: query
        type: string
        description: Filter by preferred metadata source country
    responses:
      200:
        description: List of watched artists

    """
    raw_ps = request.args.get("preferred_source", "").strip().lower()
    preferred_source = _validate_storefront(raw_ps) if raw_ps else ""
    if raw_ps and not preferred_source:
        return jsonify({"error": "invalid preferred_source"}), 400
    return jsonify(db.get_watchlist(preferred_source=preferred_source))


@app.route("/api/watchlist", methods=["POST"])
def api_watchlist_add():
    """Add an artist to the watchlist.
    ---

    Parameters
    ----------
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            artist_id:
              type: string
            name:
              type: string
            url:
              type: string
    responses:
      200:
        description: Success
      400:
        description: Missing required fields

    """
    body = request.get_json(force=True)
    artist_id = body.get("artist_id", "").strip()
    name = body.get("name", "").strip()
    url = body.get("url", "").strip()
    preferred_source = body.get("preferred_source", "").strip().lower() or None
    if preferred_source and not _validate_storefront(preferred_source):
        return jsonify({"error": "invalid preferred_source"}), 400
    if not artist_id or not name:
        return jsonify({"error": "artist_id and name required"}), 400
    db.add_to_watchlist(artist_id, name, url, preferred_source=preferred_source)
    return jsonify({"ok": True})


@app.route("/api/watchlist/<artist_id>", methods=["PATCH"])
def api_watchlist_patch(artist_id):
    """Update a watched artist's preferred metadata source.
    ---

    Parameters
    ----------
      - name: artist_id
        in: path
        type: string
        required: true
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            preferred_source:
              type: string
              description: Two/three-letter storefront code, or null to clear
    responses:
      200:
        description: Success
      400:
        description: Invalid preferred_source

    """
    body = request.get_json(force=True)
    raw_ps = body.get("preferred_source")
    if raw_ps is not None:
        raw_ps = str(raw_ps).strip().lower()
        if not _validate_storefront(raw_ps):
            return jsonify({"error": "invalid preferred_source"}), 400
    db.update_preferred_source(artist_id, raw_ps)
    return jsonify({"ok": True})


@app.route("/api/watchlist/<artist_id>", methods=["DELETE"])
def api_watchlist_remove(artist_id):
    """Remove an artist from the watchlist.
    ---

    Parameters
    ----------
      - name: artist_id
        in: path
        type: string
        required: true
    responses:
      200:
        description: Success

    """
    db.remove_from_watchlist(artist_id)
    return jsonify({"ok": True})


@app.route("/api/watchlist/export", methods=["GET"])
def api_watchlist_export():
    """Export the watchlist as a downloadable JSON file.
    ---
    responses:
      200:
        description: JSON file download
    """
    from flask import Response

    data = db.export_watchlist()
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"am_discovery_{today}.json"
    content = json.dumps(data, indent=2, ensure_ascii=False)
    return Response(
        content,
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/api/watchlist/import", methods=["POST"])
def api_watchlist_import():
    """Import artists into the watchlist from a JSON file or body.
    ---

    Parameters
    ----------
      - name: file
        in: formData
        type: file
        description: JSON file with artist list
      - name: body
        in: body
        schema:
          type: array
    responses:
      200:
        description: Import result
      400:
        description: Invalid data

    """
    if request.content_type and "multipart/form-data" in request.content_type:
        f = request.files.get("file")
        if not f:
            return jsonify({"error": "No file provided"}), 400
        try:
            data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return jsonify({"error": "Invalid JSON file"}), 400
    else:
        data = request.get_json(force=True)

    if not isinstance(data, list):
        return jsonify({"error": "Expected a JSON array of artists"}), 400

    for item in data:
        if not isinstance(item, dict) or not item.get("artist_id") or not item.get("name"):
            return jsonify({"error": "Each artist must have artist_id and name"}), 400

    db.import_watchlist(data)
    return jsonify({"ok": True, "imported": len(data)})


@app.route("/api/config", methods=["GET"])
def api_config_get():
    """Get the current application configuration.
    ---
    responses:
      200:
        description: Current configuration
    """
    return jsonify(load_config())


@app.route("/api/config", methods=["PUT"])
def api_config_put():
    """Update the application configuration.
    ---

    Parameters
    ----------
      - name: body
        in: body
        required: true
        schema:
          type: object
    responses:
      200:
        description: Success

    """
    cfg = request.get_json(force=True)
    save_config(cfg)
    # Reschedule with new interval
    _schedule_next()
    return jsonify({"ok": True})


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    """Manually trigger a background poll.
    ---
    responses:
      200:
        description: Poll triggered
      409:
        description: Poll already in progress
    """
    if _is_running:
        return jsonify({"ok": False, "message": "Poll already in progress"}), 409
    trigger_poll_now()
    return jsonify({"ok": True, "message": "Poll triggered"})


@app.route("/api/status")
def api_status():
    """Get the current server status and last poll info.
    ---
    responses:
      200:
        description: Server status
    """
    last = db.get_last_run()
    cfg = load_config()
    next_dt = datetime.fromtimestamp(_next_run_at, tz=UTC).isoformat() if _next_run_at else None
    total = db.list_albums(1, 1)[1]
    return jsonify(
        {
            "last_run": last,
            "next_run_at": next_dt,
            "is_running": _is_running,
            "newrelease_poll_interval_days": cfg.get("newrelease_poll_interval_days"),
            "total_albums": total,
            "watchlist_poll_running": _watchlist_running,
            "watchlist_poll_interval_minutes": cfg.get("watchlist_poll_interval_minutes"),
            "room_errors": _last_room_errors,
        },
    )


# ---------------------------------------------------------------------------
# Serve frontend SPA
# ---------------------------------------------------------------------------


@app.route("/")
@app.route("/<path:path>")
def serve_frontend(path="index.html"):
    # API and Swagger routes should skip the frontend handler
    if path.startswith("api/") or path.startswith("apidocs") or "apispec" in path or path.startswith("flasgger_static"):
        return jsonify({"error": "Not found"}), 404

    # Use send_from_directory's built-in safe_join for path validation.
    # Do NOT use os.path.join + os.path.exists here — that resolves traversal
    # sequences and leaks whether files outside FRONTEND_DIR exist.
    try:
        return send_from_directory(FRONTEND_DIR, path)
    except Exception:
        return send_from_directory(FRONTEND_DIR, "index.html")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="Enable debug logging and Flask debug mode")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logger.info("Initialising database...")
    db.init_db()

    cfg = load_config()
    interval_sec = cfg.get("newrelease_poll_interval_days", 1) * 86400

    last_run = db.get_last_run()
    should_poll_now = True
    delay = interval_sec

    if last_run and last_run.get("ran_at"):
        elapsed = time.time() - last_run["ran_at"]
        if elapsed < interval_sec:
            should_poll_now = False
            delay = interval_sec - elapsed

    if should_poll_now:
        logger.info("Starting initial poll...")
        trigger_poll_now()
    else:
        logger.info("Last poll was recent, scheduling next poll in %.1f minutes...", delay / 60)
        _schedule_next(override_delay=delay)

    # Start watchlist background polling
    watchlist_interval = cfg.get("watchlist_poll_interval_minutes", 10) * 60
    logger.info("Starting watchlist polling (every %.1f minutes)...", watchlist_interval / 60)
    _schedule_watchlist_next()

    port = int(os.environ.get("PORT", 5000))
    logger.info("Serving on http://localhost:%d", port)
    app.run(host="0.0.0.0", port=port, debug=args.debug, use_reloader=args.debug)


if __name__ == "__main__":
    main()
