"""AM Discovery REST API — admin (MusicBrainz seeding) routes.

Flask Blueprint powering the admin page: linking watchlist artists to
MusicBrainz MBIDs (with human approval) and surfacing releases that appear to
be missing from MusicBrainz so the user can seed them via Harmony.
"""

import logging

from flask import Blueprint, jsonify, request

import db
import musicbrainz as mb
import seeding
from api_utility import _serialize

admin_bp = Blueprint("admin", __name__)

_logger = logging.getLogger(__name__)

_RELEASE_SORTS = {"release_date", "release_type", "artist"}


def _am_artist_url(artist_id: str, url: str | None) -> str:
    return url or f"https://music.apple.com/artist/{artist_id}"


# ---------------------------------------------------------------------------
# GET /api/admin/artists  — watchlist artists missing an MBID
# ---------------------------------------------------------------------------


@admin_bp.route("/api/admin/artists")
def api_admin_artists():
    """List watchlist artists that have no MusicBrainz id, with any suggestion.
    ---
    responses:
      200:
        description: Unlinked artists plus their pending/denied MBID suggestions

    """
    rows = db.get_unlinked_watchlist_artists()
    out = []
    for r in rows:
        mbid = r.get("suggested_mbid")
        candidates = r.get("candidates") or []
        # The top candidate (matching the suggested MBID) carries the richer
        # descriptors — type (Person/Group), area, and disambiguation.
        top = next((c for c in candidates if c.get("id") == mbid), candidates[0] if candidates else {})
        out.append(
            {
                "artist_id": r["artist_id"],
                "name": r.get("name"),
                "alt_name": r.get("alt_name"),
                "artwork_url": r.get("artwork_url"),
                "preferred_source": r.get("preferred_source"),
                "am_url": _am_artist_url(r["artist_id"], r.get("url")),
                "am_discovery_url": f"#/artist/{r['artist_id']}",
                "suggestion_status": r.get("suggestion_status"),
                "suggested_mbid": mbid,
                "suggested_name": r.get("suggested_name"),
                "score": r.get("score"),
                "suggested_type": top.get("type") or None,
                "suggested_area": top.get("area") or top.get("country") or None,
                "suggested_disambiguation": top.get("disambiguation") or None,
                "mb_url": f"https://musicbrainz.org/artist/{mbid}" if mbid else None,
                "candidates": candidates,
                "mbid_checked_at": r.get("mbid_checked_at"),
            }
        )
    return jsonify({"items": out, "total": len(out)})


# ---------------------------------------------------------------------------
# POST /api/admin/artists/<artist_id>/lookup  — on-demand MBID search
# ---------------------------------------------------------------------------


@admin_bp.route("/api/admin/artists/<artist_id>/lookup", methods=["POST"])
def api_admin_artist_lookup(artist_id):
    """Search MusicBrainz for an artist and store the candidates as a suggestion.
    ---
    parameters:
      - name: artist_id
        in: path
        type: string
        required: true
      - name: body
        in: body
        required: false
        schema:
          type: object
          properties:
            name:
              type: string
              description: Override search term (defaults to the stored artist name)
    responses:
      200:
        description: Ranked MusicBrainz candidates
      429:
        description: MusicBrainz rate limited

    """
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        info = db.get_artist_info(artist_id)
        name = info.get("name") or ""
    if not name:
        # Fall back to the watchlist name.
        for w in db.get_unlinked_watchlist_artists():
            if w["artist_id"] == artist_id:
                name = w.get("name") or ""
                break
    if not name:
        return jsonify({"error": "no name to search"}), 400

    try:
        candidates = mb.search_artist(name, limit=5)
    except mb.MusicBrainzRateLimitError:
        return jsonify({"error": "rate_limited"}), 429
    except mb.MusicBrainzError as e:
        return jsonify({"error": str(e)}), 502

    top = candidates[0] if candidates else None
    db.upsert_mbid_suggestion(
        artist_id,
        suggested_mbid=top.get("id") if top else None,
        suggested_name=top.get("name") if top else None,
        score=top.get("score") if top else None,
        candidates=candidates,
        status="pending",
    )
    db.mark_mbid_checked(artist_id)
    return jsonify({"candidates": candidates})


# ---------------------------------------------------------------------------
# POST /api/admin/artists/search-all  — bulk MBID search  ·  GET status
# ---------------------------------------------------------------------------


@admin_bp.route("/api/admin/artists/search-all", methods=["POST"])
def api_admin_artists_search_all():
    """Search MusicBrainz for every watchlist artist without a suggestion yet.

    Runs in the background (rate-limited to ~1 req/sec), storing a suggestion per
    artist for later approval. Returns immediately with a progress snapshot; poll
    the status endpoint to follow along.
    ---
    responses:
      202:
        description: Bulk search started (or already running)

    """
    return jsonify(seeding.trigger_bulk_mbid_search()), 202


@admin_bp.route("/api/admin/artists/search-all/status")
def api_admin_artists_search_all_status():
    """Return progress of the bulk MBID search.
    ---
    responses:
      200:
        description: Progress snapshot (running, total, done, found)

    """
    return jsonify(seeding.bulk_mbid_search_status())


# ---------------------------------------------------------------------------
# POST /api/admin/artists/<artist_id>/approve  — link an MBID
# ---------------------------------------------------------------------------


@admin_bp.route("/api/admin/artists/<artist_id>/approve", methods=["POST"])
def api_admin_artist_approve(artist_id):
    """Link a MusicBrainz MBID to an artist (approve a suggestion or manual entry).
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
              description: MBID to link. Omit to accept the stored suggestion.
    responses:
      200:
        description: Linked
      400:
        description: No MBID available to link

    """
    body = request.get_json(silent=True) or {}
    mbid = (body.get("musicbrainz_id") or "").strip()
    if not mbid:
        suggestion = db.get_mbid_suggestion(artist_id)
        mbid = (suggestion.get("suggested_mbid") if suggestion else "") or ""
    if not mbid:
        return jsonify({"error": "no musicbrainz_id provided or suggested"}), 400

    # upsert_artist guarantees an artists row exists even if the artist was only
    # ever on the watchlist (update alone would silently no-op).
    db.upsert_artist(artist_id, musicbrainz_id=mbid)
    db.set_suggestion_status(artist_id, "approved")
    return jsonify({"ok": True, "musicbrainz_id": mbid})


# ---------------------------------------------------------------------------
# POST /api/admin/artists/<artist_id>/deny  — dismiss the suggestion
# ---------------------------------------------------------------------------


@admin_bp.route("/api/admin/artists/<artist_id>/deny", methods=["POST"])
def api_admin_artist_deny(artist_id):
    """Dismiss an artist's MBID suggestion so the scanner won't re-suggest it.
    ---
    parameters:
      - name: artist_id
        in: path
        type: string
        required: true
    responses:
      200:
        description: Denied

    """
    if db.get_mbid_suggestion(artist_id):
        db.set_suggestion_status(artist_id, "denied")
    else:
        db.upsert_mbid_suggestion(artist_id, None, None, None, None, status="denied")
    db.mark_mbid_checked(artist_id)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# GET /api/admin/releases  — releases needing seeding
# ---------------------------------------------------------------------------


@admin_bp.route("/api/admin/releases")
def api_admin_releases():
    """List releases flagged as missing from MusicBrainz, ready for seeding.
    ---
    parameters:
      - name: sort
        in: query
        type: string
        enum: [release_date, release_type, artist]
        default: release_date
      - name: include_hidden
        in: query
        type: string
        enum: ["true"]
        description: Pass "true" to also include releases hidden from the list
    responses:
      200:
        description: Releases needing seeding

    """
    sort = request.args.get("sort", "release_date").strip().lower()
    if sort not in _RELEASE_SORTS:
        return jsonify({"error": "invalid sort"}), 400
    include_hidden = request.args.get("include_hidden") == "true"

    rows = db.get_seeding_releases(sort=sort, include_hidden=include_hidden)
    items = [_serialize(r) for r in rows]
    return jsonify({"items": items, "total": len(items)})


# ---------------------------------------------------------------------------
# POST /api/admin/releases/<store_adam_id>/hide  (and /unhide)
# ---------------------------------------------------------------------------


@admin_bp.route("/api/admin/releases/<store_adam_id>/hide", methods=["POST"])
def api_admin_release_hide(store_adam_id):
    """Hide a release from the admin seeding list.
    ---
    parameters:
      - name: store_adam_id
        in: path
        type: string
        required: true
    responses:
      200:
        description: Hidden

    """
    db.set_album_hidden_from_seeding(store_adam_id, True)
    return jsonify({"ok": True})


@admin_bp.route("/api/admin/releases/<store_adam_id>/unhide", methods=["POST"])
def api_admin_release_unhide(store_adam_id):
    """Restore a previously hidden release to the admin seeding list.
    ---
    parameters:
      - name: store_adam_id
        in: path
        type: string
        required: true
    responses:
      200:
        description: Unhidden

    """
    db.set_album_hidden_from_seeding(store_adam_id, False)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# GET /api/admin/status  — scanner status  ·  POST /api/admin/scan  — run now
# ---------------------------------------------------------------------------


@admin_bp.route("/api/admin/status")
def api_admin_status():
    """Return MusicBrainz seeding scanner status and pending counts.
    ---
    responses:
      200:
        description: Scanner status

    """
    return jsonify(seeding.status())


@admin_bp.route("/api/admin/scan", methods=["POST"])
def api_admin_scan():
    """Trigger a MusicBrainz seeding scan cycle immediately.

    A manual scan forces a re-check, ignoring the per-artist weekly recheck
    window, so recently-scanned artists are re-verified (e.g. to clear flags
    after a matching-logic change). Already-confirmed albums are still skipped.
    ---
    responses:
      202:
        description: Scan started

    """
    seeding.trigger_scan_now(force=True)
    return jsonify({"ok": True, "async": True}), 202
