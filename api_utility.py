"""AM Discovery REST API — shared helpers and frontend SPA catch-all.

This module defines the shared helper functions used across all API blueprints
and the frontend SPA catch-all route.

Route blueprints live in:
  api_releases.py  — /api/releases/*
  api_artists.py   — /api/artists/*
  api_system.py    — /api/system/*
  api_watchlist.py — /api/watchlist/*
"""

import json
import re

from flask import Blueprint, jsonify, send_from_directory

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
    """Lazy import of the server module to avoid circular imports at load time."""
    import server

    return server


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
