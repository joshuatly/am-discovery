"""AM Discovery REST API — Apple Music debug endpoints.

Flask Blueprint exposing raw Apple Music catalog query endpoints for
debugging. Returns the unmodified JSON payload from the Apple Music
amp-api, including any error responses. Uses the configured CORS proxy
when present.
"""

from flask import Blueprint, jsonify, request

from api_utility import _validate_storefront
from client import AppleMusicClient
from config import load_config

debug_bp = Blueprint("debug", __name__)


def _storefront_or_default(sf_param: str | None) -> str | None:
    if sf_param:
        return _validate_storefront(sf_param)
    cfg = load_config()
    return cfg.get("home_storefront") or "us"


# ---------------------------------------------------------------------------
# GET /api/debug/apple-music/artist
# ---------------------------------------------------------------------------


@debug_bp.route("/api/debug/apple-music/artist")
def debug_apple_music_artist():
    """Query the Apple Music catalog for an artist and return the raw response.
    ---
    tags:
      - Debug
    parameters:
      - name: id
        in: query
        type: string
        required: true
        description: Artist Adam ID (e.g. "909253")
      - name: storefront
        in: query
        type: string
        required: false
        description: >
          Two-letter storefront code (e.g. "us", "jp"). Defaults to
          home_storefront from config.
      - name: include
        in: query
        type: string
        required: false
        description: >
          Comma-separated relationships to include (e.g. "albums,playlists").
          Forwarded verbatim to the Apple Music API.
      - name: extend
        in: query
        type: string
        required: false
        description: >
          Comma-separated extended attributes (e.g. "bornOrFormed,artistBio").
          Forwarded verbatim to the Apple Music API.
    responses:
      200:
        description: Raw Apple Music catalog response (success or API error body)
        schema:
          type: object
      400:
        description: Missing or invalid parameters
    """
    artist_id = request.args.get("id", "").strip()
    if not artist_id:
        return jsonify({"error": "Missing required parameter: id"}), 400

    storefront = _storefront_or_default(request.args.get("storefront", "").strip() or None)
    if not storefront:
        return jsonify({"error": "Invalid storefront"}), 400

    params = {}
    if request.args.get("include"):
        params["include"] = request.args["include"]
    if request.args.get("extend"):
        params["extend"] = request.args["extend"]

    client = AppleMusicClient()
    status, body = client.catalog_get_raw(f"/v1/catalog/{storefront}/artists/{artist_id}", params or None)
    return jsonify(body), status or 502


# ---------------------------------------------------------------------------
# GET /api/debug/apple-music/album
# ---------------------------------------------------------------------------


@debug_bp.route("/api/debug/apple-music/album")
def debug_apple_music_album():
    """Query the Apple Music catalog for an album and return the raw response.
    ---
    tags:
      - Debug
    parameters:
      - name: id
        in: query
        type: string
        required: true
        description: Album Adam ID (e.g. "1234567890")
      - name: storefront
        in: query
        type: string
        required: false
        description: >
          Two-letter storefront code (e.g. "us", "jp"). Defaults to
          home_storefront from config.
      - name: include
        in: query
        type: string
        required: false
        description: >
          Comma-separated relationships to include (e.g. "tracks,artists").
          Forwarded verbatim to the Apple Music API.
      - name: extend
        in: query
        type: string
        required: false
        description: >
          Comma-separated extended attributes (e.g. "extendedAssetUrls").
          Forwarded verbatim to the Apple Music API.
    responses:
      200:
        description: Raw Apple Music catalog response (success or API error body)
        schema:
          type: object
      400:
        description: Missing or invalid parameters
    """
    album_id = request.args.get("id", "").strip()
    if not album_id:
        return jsonify({"error": "Missing required parameter: id"}), 400

    storefront = _storefront_or_default(request.args.get("storefront", "").strip() or None)
    if not storefront:
        return jsonify({"error": "Invalid storefront"}), 400

    params = {}
    if request.args.get("include"):
        params["include"] = request.args["include"]
    if request.args.get("extend"):
        params["extend"] = request.args["extend"]

    client = AppleMusicClient()
    status, body = client.catalog_get_raw(f"/v1/catalog/{storefront}/albums/{album_id}", params or None)
    return jsonify(body), status or 502
