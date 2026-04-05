"""AM Discovery REST API — core routes.

Flask Blueprint covering releases, artists, search, config, status,
CLI scheduler proxy, and the frontend SPA catch-all.

Watchlist routes live in api_watchlist.py.
"""

import concurrent.futures
import json
import re
import urllib.error
import urllib.request
from datetime import UTC, datetime

from flask import Blueprint, jsonify, request, send_from_directory

import db
from client import AppleMusicClient, RateLimitError
from config import load_config, save_config

api_bp = Blueprint("api", __name__)

_STOREFRONT_RE = re.compile(r"^[a-z]{2,3}$")


def _validate_storefront(sf: str):
    """Return sf if it looks like a valid ISO storefront code, else None."""
    return sf if _STOREFRONT_RE.match(sf) else None


def _serialize(row: dict) -> dict:
    """Ensure storefronts, audio_formats, and artists_json are lists (stored as JSON strings in SQLite)."""
    if isinstance(row.get("storefronts"), str):
        row["storefronts"] = json.loads(row["storefronts"])
    if isinstance(row.get("audio_formats"), str):
        row["audio_formats"] = json.loads(row["audio_formats"])
    if isinstance(row.get("artists_json"), str):
        row["artists_json"] = json.loads(row["artists_json"])
    return row


def _is_watched(row: dict, watched_ids: set) -> bool:
    """Return True if any artist credited on the album is in watched_ids."""
    if row.get("artist_id") in watched_ids:
        return True
    return any(artist.get("id") in watched_ids for artist in row.get("artists_json") or [])


def _server():
    """Lazy import of the server module to avoid circular imports at load time.

    Used only by the three routes that need to read or trigger scheduler state
    (_is_running, _next_run_at, _watchlist_running, _last_room_errors,
    trigger_poll_now, _schedule_next, FRONTEND_DIR).
    """
    import server

    return server


# ---------------------------------------------------------------------------
# Releases
# ---------------------------------------------------------------------------


@api_bp.route("/api/releases")
def api_releases():
    """Get a paginated list of releases.
    ---

    parameters:
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
      - name: storefront
        in: query
        type: string
        description: Filter by storefront (e.g. "us", "jp")
      - name: view
        in: query
        type: string
        enum: ["new"]
        description: Pass "new" to return only discovered releases (from room polling); omit for all releases
      - name: watched
        in: query
        type: string
        enum: ["true"]
        description: Pass "true" to return only releases by watched artists
      - name: release_type
        in: query
        type: string
        description: Filter by release type (e.g. "Album", "EP", "Single")
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
    release_type = request.args.get("release_type", "").strip()
    sort = request.args.get("sort", "release_date").strip().lower()
    if sort not in {"release_date", "first_seen"}:
        return jsonify({"error": "invalid sort"}), 400

    if q:
        rows, total = db.search_albums(
            q,
            page,
            per_page,
            storefront=storefront,
            discovered_only=discovered_only,
            watched_only=watched_only,
            release_type=release_type,
            sort=sort,
        )
    else:
        rows, total = db.list_albums(
            page,
            per_page,
            storefront=storefront,
            discovered_only=discovered_only,
            watched_only=watched_only,
            release_type=release_type,
            sort=sort,
        )

    watched_ids = db.get_watched_artist_ids()
    result = []
    for r in rows:
        r = _serialize(r)
        r["watched"] = _is_watched(r, watched_ids)
        result.append(r)

    return jsonify({"items": result, "total": total, "page": page, "per_page": per_page})


@api_bp.route("/api/releases/<store_adam_id>")
def api_release_detail(store_adam_id):
    """Get details for a specific release.
    ---

    parameters:
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
    row["watched"] = _is_watched(row, watched_ids)
    return jsonify(row)


@api_bp.route("/api/releases/<store_adam_id>/check_storefronts")
def api_check_storefronts(store_adam_id):
    """Check availability of a release across different storefronts.
    ---

    parameters:
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


@api_bp.route("/api/lookup/<store_adam_id>")
def api_lookup(store_adam_id):
    """Fetch fresh metadata for a release from a specific storefront.
    ---

    parameters:
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


# ---------------------------------------------------------------------------
# Artists
# ---------------------------------------------------------------------------


@api_bp.route("/api/artists/<artist_id>/fetch", methods=["POST"])
def api_artist_fetch(artist_id):
    """Fetch all releases for an artist from a specific storefront and store them.
    ---

    parameters:
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

    # Cache artist metadata regardless of whether any releases were found
    if artist_info:
        db.upsert_artist(
            artist_id,
            name=artist_info.get("name"),
            artwork_url=artist_info.get("artwork_url"),
            genre=artist_info.get("genre"),
            born_or_formed=artist_info.get("born_or_formed"),
            origin=artist_info.get("origin"),
            artist_bio=artist_info.get("artist_bio"),
            is_group=artist_info.get("is_group"),
        )

    if not releases:
        return jsonify({"ok": True, "fetched": 0, "message": "No releases found on artist page"})

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

    db.check_and_update_new_releases(artist_id)

    return jsonify({"ok": True, "fetched": len(releases)})


@api_bp.route("/api/artists/<artist_id>/releases")
def api_artist_releases(artist_id):
    """Get all releases for a specific artist.
    ---

    parameters:
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
            "artist_born_or_formed": artist_info.get("born_or_formed"),
            "artist_origin": artist_info.get("origin"),
            "artist_bio": artist_info.get("artist_bio"),
            "artist_is_group": artist_info.get("is_group"),
            "watched": watched,
            "releases": result,
        },
    )


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@api_bp.route("/api/search/artists")
def api_search_artists():
    """Search Apple Music catalog for artists.
    ---

    parameters:
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
    try:
        results = client.search_artists(term, storefront=storefront, limit=limit)
    except RateLimitError:
        return jsonify({"error": "rate_limited"}), 429
    return jsonify({"results": results})


@api_bp.route("/api/search/artists/local")
def api_search_artists_local():
    """Search local database for artists without querying Apple Music.

    Results come exclusively from the local SQLite database — no external
    network requests are made.  Only artists that have previously been
    discovered through album polling, artist fetches, or watchlist additions
    will appear.

    Results are ranked by match quality (best match first):

    - **name_exact** — artist name exactly matches the term (case-insensitive)
    - **name_prefix** — artist name starts with the term
    - **name_contains** — artist name contains the term anywhere
    - **info_contains** — term found in bio, genre, or origin (name doesn't match)
    ---

    parameters:
      - name: term
        in: query
        type: string
        required: true
        description: >
          Search term matched against artist name (primary), and against
          artist bio, genre, and origin (secondary, ranked lower).
      - name: limit
        in: query
        type: integer
        default: 25
        description: Maximum number of results to return (capped at 50).
    responses:
      200:
        description: Ranked list of matching artists from the local database.
        schema:
          type: object
          properties:
            results:
              type: array
              items:
                type: object
                properties:
                  artist_id:
                    type: string
                    description: Apple Music artist ID.
                  name:
                    type: string
                  artwork_url:
                    type: string
                  genre:
                    type: string
                  born_or_formed:
                    type: string
                  origin:
                    type: string
                  artist_bio:
                    type: string
                  is_group:
                    type: boolean
                  watched:
                    type: boolean
                    description: Whether the artist is on the watchlist.
                  collection_status:
                    type: string
                    description: Watchlist collection status; null if not watched.
                  match_reason:
                    type: string
                    enum: [name_exact, name_prefix, name_contains, info_contains]
                    description: >
                      Why this result was included and its relevance tier.
                      name_exact > name_prefix > name_contains > info_contains.
      400:
        description: Missing or invalid parameters.

    """
    term = request.args.get("term", "").strip()
    if not term:
        return jsonify({"error": "term is required"}), 400
    try:
        limit = min(int(request.args.get("limit", 25)), 50)
    except (ValueError, TypeError):
        return jsonify({"error": "limit must be an integer"}), 400

    results = db.search_artists_local(term, limit=limit)
    return jsonify({"results": results})


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@api_bp.route("/api/config", methods=["GET"])
def api_config_get():
    """Get the current application configuration.
    ---
    responses:
      200:
        description: Current configuration
    """
    return jsonify(load_config())


@api_bp.route("/api/config", methods=["PUT"])
def api_config_put():
    """Update the application configuration.
    ---

    parameters:
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
    _server()._schedule_next()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# CLI Scheduler proxy
# ---------------------------------------------------------------------------


@api_bp.route("/api/cli_scheduler/submit", methods=["POST"])
def api_cli_scheduler_submit():
    """Proxy a job submission to the configured CLI Scheduler.
    ---
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            storefront:
              type: string
            album_id:
              type: string
    responses:
      201:
        description: Job accepted by CLI Scheduler
      400:
        description: Job rejected by CLI Scheduler
      502:
        description: Could not reach CLI Scheduler
      503:
        description: CLI Scheduler not configured
    """
    cfg = load_config()
    scheduler_url = cfg.get("cli_scheduler_url", "").rstrip("/")
    preset = cfg.get("cli_scheduler_preset", "")
    if not scheduler_url:
        return jsonify({"error": "CLI Scheduler not configured"}), 503

    data = request.get_json(force=True)
    storefront = data.get("storefront", "")
    album_id = data.get("album_id", "")
    if not storefront or not album_id:
        return jsonify({"error": "Missing storefront or album_id"}), 400

    apple_url = f"https://music.apple.com/{storefront}/album/{album_id}"
    payload = json.dumps({"preset": preset, "urls": [apple_url]}).encode()
    req = urllib.request.Request(
        f"{scheduler_url}/api/jobs",
        data=payload,
        headers={"Content-Type": "application/json", "accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return jsonify({"ok": True}), resp.status
    except urllib.error.HTTPError as e:
        return jsonify({"error": e.reason}), e.code
    except Exception as e:
        return jsonify({"error": str(e)}), 502


# ---------------------------------------------------------------------------
# Poll control and status
# ---------------------------------------------------------------------------


@api_bp.route("/api/refresh", methods=["POST"])
def api_refresh():
    """Manually trigger a background poll.
    ---
    responses:
      200:
        description: Poll triggered
      409:
        description: Poll already in progress
    """
    srv = _server()
    if srv._is_running:
        return jsonify({"ok": False, "message": "Poll already in progress"}), 409
    srv.trigger_poll_now()
    return jsonify({"ok": True, "message": "Poll triggered"})


@api_bp.route("/api/status")
def api_status():
    """Get the current server status and last poll info.
    ---
    responses:
      200:
        description: Server status
    """
    srv = _server()
    last = db.get_last_run()
    cfg = load_config()
    next_dt = datetime.fromtimestamp(srv._next_run_at, tz=UTC).isoformat() if srv._next_run_at else None
    total = db.list_albums(1, 1)[1]
    return jsonify(
        {
            "last_run": last,
            "next_run_at": next_dt,
            "is_running": srv._is_running,
            "newrelease_poll_interval_days": cfg.get("newrelease_poll_interval_days"),
            "total_albums": total,
            "watchlist_poll_running": srv._watchlist_running,
            "watchlist_poll_interval_minutes": cfg.get("watchlist_poll_interval_minutes"),
            "room_errors": srv._last_room_errors,
        },
    )


# ---------------------------------------------------------------------------
# Frontend SPA catch-all
# ---------------------------------------------------------------------------


@api_bp.route("/")
@api_bp.route("/<path:path>")
def serve_frontend(path="index.html"):
    # API and Swagger routes should skip the frontend handler
    if path.startswith("api/") or path.startswith("apidocs") or "apispec" in path or path.startswith("flasgger_static"):
        return jsonify({"error": "Not found"}), 404

    frontend_dir = _server().FRONTEND_DIR
    # Use send_from_directory's built-in safe_join for path validation.
    # Do NOT use os.path.join + os.path.exists here — that resolves traversal
    # sequences and leaks whether files outside FRONTEND_DIR exist.
    try:
        return send_from_directory(frontend_dir, path)
    except Exception:
        return send_from_directory(frontend_dir, "index.html")
