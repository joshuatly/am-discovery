"""AM Discovery REST API — artist and search routes.

Flask Blueprint covering artist metadata, full-catalog fetches,
and both remote (Apple Music) and local artist search.
"""

import concurrent.futures
import logging
import threading

from flask import Blueprint, jsonify, request

import db
from api_utility import _serialize, _validate_storefront
from client import AppleMusicClient, RateLimitError
from config import load_config

artists_bp = Blueprint("artists", __name__)

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GET /api/artists/<artist_id>/releases
# ---------------------------------------------------------------------------


@artists_bp.route("/api/artists/<artist_id>/releases")
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
            "artist_musicbrainz_id": artist_info.get("musicbrainz_id"),
            "watched": watched,
            "releases": result,
        },
    )


# ---------------------------------------------------------------------------
# POST /api/artists/<artist_id>/fetch
# ---------------------------------------------------------------------------


@artists_bp.route("/api/artists/<artist_id>/fetch", methods=["POST"])
def api_artist_fetch(artist_id):
    """Fetch all releases for an artist from a specific storefront and store them.

    The fetch runs in a background thread so it never blocks the Gunicorn worker.
    Returns 202 immediately; the caller should re-query the artist's releases
    after a short delay to pick up the results.
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
      202:
        description: Fetch queued; runs in background
      400:
        description: Invalid storefront

    """
    raw_sf = request.args.get("storefront", "").strip().lower()
    if raw_sf:
        storefront = _validate_storefront(raw_sf)
        if not storefront:
            return jsonify({"error": "invalid storefront"}), 400
    else:
        cfg = load_config()
        storefront = (cfg.get("check_storefronts") or ["us"])[0]

    def _run():
        try:
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
                return

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
                    "upc": info.get("upc"),
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
            _logger.info("[ArtistFetch] Done: artist %s, %d releases", artist_id, len(releases))
        except Exception:
            _logger.exception("[ArtistFetch] Error fetching artist %s", artist_id)

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "async": True}), 202


# ---------------------------------------------------------------------------
# PATCH /api/artists/<artist_id>
# ---------------------------------------------------------------------------


@artists_bp.route("/api/artists/<artist_id>", methods=["PATCH"])
def api_artist_patch(artist_id):
    """Update an artist's MusicBrainz ID.
    ---

    parameters:
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
            musicbrainz_id:
              type: string
              description: MusicBrainz artist MBID, or null to clear
    responses:
      200:
        description: Success

    """
    body = request.get_json(force=True)
    if "musicbrainz_id" in body:
        raw = body["musicbrainz_id"]
        if raw is not None:
            raw = str(raw).strip()
            if not raw:
                raw = None
        db.update_artist_musicbrainz_id(artist_id, raw)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# GET /api/artists/search
# ---------------------------------------------------------------------------


@artists_bp.route("/api/artists/search")
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


# ---------------------------------------------------------------------------
# GET /api/artists/search/local
# ---------------------------------------------------------------------------


@artists_bp.route("/api/artists/search/local")
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
# GET /api/artists/<artist_id>/similar
# ---------------------------------------------------------------------------


@artists_bp.route("/api/artists/<artist_id>/similar")
def api_similar_artists(artist_id):
    """Fetch Apple Music's similar-artists view for an artist.
    ---

    parameters:
      - name: artist_id
        in: path
        type: string
        required: true
      - name: storefront
        in: query
        type: string
        default: us
      - name: limit
        in: query
        type: integer
        default: 10
    responses:
      200:
        description: List of similar artists from Apple Music
      400:
        description: Invalid storefront or limit
      429:
        description: Rate limited by Apple Music

    """
    storefront = _validate_storefront(request.args.get("storefront", "us").strip().lower())
    if not storefront:
        return jsonify({"error": "invalid storefront"}), 400
    try:
        limit = min(int(request.args.get("limit", 10)), 25)
    except (ValueError, TypeError):
        return jsonify({"error": "limit must be an integer"}), 400

    client = AppleMusicClient()
    try:
        results = client.get_similar_artists(artist_id, storefront=storefront, limit=limit)
    except RateLimitError:
        return jsonify({"error": "rate_limited"}), 429
    return jsonify({"results": results})
