"""AM Discovery REST API — system, config, and status routes.

Flask Blueprint covering configuration, poll control, server status,
database statistics, discovery history, and the CLI Scheduler proxy.
"""

import json
import urllib.error
import urllib.request
from datetime import UTC, datetime

from flask import Blueprint, jsonify, request

import db
from config import load_config, save_config

system_bp = Blueprint("system", __name__)


def _server():
    """Lazy import of the server module to avoid circular imports at load time."""
    import server

    return server


# ---------------------------------------------------------------------------
# GET /api/system/config
# ---------------------------------------------------------------------------


@system_bp.route("/api/system/config", methods=["GET"])
def api_config_get():
    """Get the current application configuration.
    ---
    responses:
      200:
        description: Current configuration
    """
    return jsonify(load_config())


# ---------------------------------------------------------------------------
# PUT /api/system/config
# ---------------------------------------------------------------------------


@system_bp.route("/api/system/config", methods=["PUT"])
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
# POST /api/system/refresh
# ---------------------------------------------------------------------------


@system_bp.route("/api/system/refresh", methods=["POST"])
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


# ---------------------------------------------------------------------------
# GET /api/system/status
# ---------------------------------------------------------------------------


@system_bp.route("/api/system/status")
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
# GET /api/system/db
# ---------------------------------------------------------------------------


@system_bp.route("/api/system/db")
def api_dbstatus():
    """Return SQLite database size and per-table statistics.
    ---
    responses:
      200:
        description: Database statistics
    """
    return jsonify(db.get_db_stats())


# ---------------------------------------------------------------------------
# GET /api/system/discovery
# ---------------------------------------------------------------------------


@system_bp.route("/api/system/discovery")
def api_discovery_status():
    """Return recent discovery run records, one row per storefront per run.
    ---
    parameters:
      - name: limit
        in: query
        type: integer
        default: 200
        description: Maximum number of rows to return (most recent first)
    responses:
      200:
        description: List of discovery run records
    """
    try:
        limit = int(request.args.get("limit", 200))
    except (TypeError, ValueError):
        limit = 200
    runs = db.get_discovery_runs(limit=limit)
    return jsonify({"runs": runs, "count": len(runs)})


# ---------------------------------------------------------------------------
# POST /api/system/cli-scheduler/submit
# ---------------------------------------------------------------------------


@system_bp.route("/api/system/cli-scheduler/submit", methods=["POST"])
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
