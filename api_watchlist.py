"""AM Discovery REST API — watchlist routes.

Flask Blueprint covering all watchlist CRUD, export/import, and
preferred-source / collection-status management.
"""

import json
from datetime import datetime

from flask import Blueprint, Response, jsonify, request

import db
from api_utility import _validate_storefront

watchlist_bp = Blueprint("watchlist", __name__)


@watchlist_bp.route("/api/watchlist", methods=["GET"])
def api_watchlist_get():
    """Get the current watchlist.
    ---

    parameters:
      - name: preferred_source
        in: query
        type: string
        description: Filter by preferred metadata source country
      - name: collection_status
        in: query
        type: string
        description: Filter by collection status (new, complete, new_release, in_progress)
      - name: sort
        in: query
        type: string
        enum: ["name", "added", "recent_release", "recent_album"]
        default: name
        description: Sort order for results
    responses:
      200:
        description: List of watched artists

    """
    raw_ps = request.args.get("preferred_source", "").strip().lower()
    preferred_source = _validate_storefront(raw_ps) if raw_ps else ""
    if raw_ps and not preferred_source:
        return jsonify({"error": "invalid preferred_source"}), 400
    collection_status = request.args.get("collection_status", "").strip().lower()
    if collection_status and collection_status not in db.COLLECTION_STATUSES:
        return jsonify({"error": "invalid collection_status"}), 400
    sort = request.args.get("sort", "name").strip().lower()
    if sort not in {"name", "added", "recent_release", "recent_album"}:
        return jsonify({"error": "invalid sort"}), 400
    return jsonify(db.get_watchlist(preferred_source=preferred_source, collection_status=collection_status, sort=sort))


@watchlist_bp.route("/api/watchlist", methods=["POST"])
def api_watchlist_add():
    """Add an artist to the watchlist.
    ---

    parameters:
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
            preferred_source:
              type: string
              description: Two/three-letter storefront code for preferred metadata source (optional)
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


@watchlist_bp.route("/api/watchlist/<artist_id>", methods=["PATCH"])
def api_watchlist_patch(artist_id):
    """Update a watched artist's preferred source, collection status, or alt name.
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
            preferred_source:
              type: string
              description: Two/three-letter storefront code, or null to clear
            collection_status:
              type: string
              description: Collection status (complete, in_progress)
            alt_name:
              type: string
              description: User-defined alternate name (e.g. English transliteration), or null to clear
    responses:
      200:
        description: Success
      400:
        description: Invalid input
      409:
        description: Invalid status transition

    """
    body = request.get_json(force=True)
    if "preferred_source" in body:
        raw_ps = body["preferred_source"]
        if raw_ps is not None:
            raw_ps = str(raw_ps).strip().lower()
            if not _validate_storefront(raw_ps):
                return jsonify({"error": "invalid preferred_source"}), 400
        db.update_preferred_source(artist_id, raw_ps)
    raw_cs = body.get("collection_status")
    if raw_cs is not None:
        raw_cs = str(raw_cs).strip().lower()
        if raw_cs not in db.COLLECTION_STATUSES:
            return jsonify({"error": "invalid collection_status"}), 400
        if not db.update_collection_status(artist_id, raw_cs):
            return jsonify({"error": "invalid status transition"}), 409
    if "alt_name" in body:
        raw_an = body["alt_name"]
        if raw_an is not None:
            raw_an = str(raw_an).strip()
            if len(raw_an) > 200:
                return jsonify({"error": "alt_name too long (max 200 characters)"}), 400
            raw_an = raw_an or None  # treat empty string as null
        db.update_watchlist_alt_name(artist_id, raw_an)
    return jsonify({"ok": True})


@watchlist_bp.route("/api/watchlist/<artist_id>", methods=["DELETE"])
def api_watchlist_remove(artist_id):
    """Remove an artist from the watchlist.
    ---

    parameters:
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


@watchlist_bp.route("/api/watchlist/ids", methods=["GET"])
def api_watchlist_ids():
    """Get only the artist IDs from the watchlist.
    ---
    responses:
      200:
        description: List of watched artist IDs

    """
    return jsonify(db.get_watchlist_ids())


@watchlist_bp.route("/api/watchlist/export", methods=["GET"])
def api_watchlist_export():
    """Export the watchlist as a downloadable JSON file.
    ---
    responses:
      200:
        description: JSON file download
    """
    data = db.export_watchlist()
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"am_discovery_{today}.json"
    content = json.dumps(data, indent=2, ensure_ascii=False)
    return Response(
        content,
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@watchlist_bp.route("/api/watchlist/import", methods=["POST"])
def api_watchlist_import():
    """Import artists into the watchlist from a JSON file or body.
    ---

    parameters:
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
