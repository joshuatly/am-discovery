"""AM Discovery REST API — releases routes.

Flask Blueprint covering all release-centric endpoints including
storefront availability checks, MusicBrainz lookups, and live metadata fetch.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

from flask import Blueprint, jsonify, request

import db
from api import _is_watched, _serialize, _validate_storefront
from client import AppleMusicClient
from config import load_config

releases_bp = Blueprint("releases", __name__)

_MB_HEADERS = {
    "User-Agent": "AMDiscovery/1.0 (https://github.com/joshuatly/am-discovery)",
    "Accept": "application/json",
}


def _mb_query(query: str) -> list:
    """Run a MusicBrainz release search and return the releases list."""
    url = f"https://musicbrainz.org/ws/2/release/?query={urllib.parse.quote(query)}&fmt=json&limit=5"
    req = urllib.request.Request(url, headers=_MB_HEADERS)
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("releases") or []


def _mb_format_releases(releases: list) -> tuple[list, str | None]:
    """Return (serialised releases list, artist_mbid from top result)."""
    result = []
    for r in releases[:5]:
        mb_id = r.get("id")
        result.append({"id": mb_id, "title": r.get("title"), "url": f"https://musicbrainz.org/release/{mb_id}"})
    artist_mbid = None
    credits = releases[0].get("artist-credit") or []
    if credits:
        artist_mbid = credits[0].get("artist", {}).get("id")
    return result, artist_mbid


# ---------------------------------------------------------------------------
# GET /api/releases
# ---------------------------------------------------------------------------


@releases_bp.route("/api/releases")
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


# ---------------------------------------------------------------------------
# GET /api/releases/<store_adam_id>
# ---------------------------------------------------------------------------


@releases_bp.route("/api/releases/<store_adam_id>")
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


# ---------------------------------------------------------------------------
# GET /api/releases/<store_adam_id>/check_storefronts
# ---------------------------------------------------------------------------


@releases_bp.route("/api/releases/<store_adam_id>/check_storefronts")
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


# ---------------------------------------------------------------------------
# GET /api/releases/<store_adam_id>/musicbrainz
# ---------------------------------------------------------------------------


@releases_bp.route("/api/releases/<store_adam_id>/musicbrainz")
def api_musicbrainz_lookup(store_adam_id):
    """Look up a release on MusicBrainz (barcode first, then title+artist fallback).
    ---

    parameters:
      - name: store_adam_id
        in: path
        type: string
        required: true
    responses:
      200:
        description: MusicBrainz lookup result
      404:
        description: Album not found in local database

    """
    row = db.get_album(store_adam_id)
    if not row:
        return jsonify({"error": "Not found"}), 404

    upc = row.get("upc")
    title = row.get("title") or ""
    artist = row.get("artist") or ""

    try:
        # 1. Barcode lookup (most precise)
        if upc:
            releases = _mb_query(f"barcode:{upc}")
            if releases:
                result_releases, artist_mbid = _mb_format_releases(releases)
                return jsonify(
                    {
                        "found": True,
                        "method": "barcode",
                        "upc": upc,
                        "releases": result_releases,
                        "artist_mbid": artist_mbid,
                    }
                )

        # 2. Title + artist search (fuzzy fallback)
        if title and artist:
            # Lucene: escape special chars and quote phrases
            def _q(s):
                return '"' + s.replace('"', '\\"') + '"'

            releases = _mb_query(f"release:{_q(title)} AND artist:{_q(artist)}")
            if releases:
                result_releases, artist_mbid = _mb_format_releases(releases)
                return jsonify(
                    {
                        "found": True,
                        "method": "title_artist",
                        "upc": upc,
                        "releases": result_releases,
                        "artist_mbid": artist_mbid,
                    }
                )

        return jsonify({"found": False, "upc": upc})
    except Exception as e:
        return jsonify({"found": False, "upc": upc, "error": str(e)}), 502


# ---------------------------------------------------------------------------
# GET /api/releases/<store_adam_id>/lookup
# ---------------------------------------------------------------------------


@releases_bp.route("/api/releases/<store_adam_id>/lookup")
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
