"""AM Discovery REST API — system, config, and status routes.

Flask Blueprint covering configuration, poll control, server status,
database statistics, discovery history, and the CLI Scheduler proxy.
"""

import json
import urllib.error
import urllib.request

from flask import Blueprint, jsonify, request

import db
import notifications
from config import CONFIG_LOCK, format_local_time, load_config, save_config

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
    incoming = request.get_json(force=True) or {}
    # `notifications` is owned by /api/notifications routes. The Settings page
    # echoes a stale copy from page-load, so accepting it here would wipe any
    # events created via the per-event modal.
    incoming.pop("notifications", None)
    with CONFIG_LOCK:
        cfg = load_config()
        cfg.update(incoming)
        save_config(cfg)
    # Re-arm the discovery timer based on last_run, so saving config does not
    # push the next poll out by a full interval.
    _server().reschedule_after_config_change()
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
    next_run_at = srv._next_run_at or None
    next_run_at_human = format_local_time(next_run_at) if next_run_at else None
    if last and last.get("ran_at"):
        last = {**last, "ran_at_human": format_local_time(last["ran_at"])}
    total = db.list_albums(1, 1)[1]
    last_notify_at = notifications.get_last_notify_at()
    return jsonify(
        {
            "last_run": last,
            "next_run_at": next_run_at,
            "next_run_at_human": next_run_at_human,
            "is_running": srv._is_running,
            "newrelease_poll_interval_days": cfg.get("newrelease_poll_interval_days"),
            "total_albums": total,
            "watchlist_poll_running": srv._watchlist_running,
            "watchlist_poll_interval_minutes": cfg.get("watchlist_poll_interval_minutes"),
            "room_errors": srv._last_room_errors,
            "last_notify_at": last_notify_at,
            "last_notify_at_human": format_local_time(last_notify_at) if last_notify_at else None,
            "notification_scan_interval_minutes": cfg.get("notification_scan_interval_minutes"),
            "notification_max_release_age_days": cfg.get("notification_max_release_age_days"),
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
    for r in runs:
        if r.get("ran_at") is not None:
            r["ran_at_human"] = format_local_time(r["ran_at"])
    return jsonify({"runs": runs, "count": len(runs)})


# ---------------------------------------------------------------------------
# GET /api/system/watchlist_log
# ---------------------------------------------------------------------------


@system_bp.route("/api/system/watchlist_log")
def api_watchlist_log():
    """Return recent watchlist batch run records, one row per batch.
    ---
    parameters:
      - name: limit
        in: query
        type: integer
        default: 200
        description: Maximum number of rows to return (most recent first)
    responses:
      200:
        description: List of watchlist batch run records
    """
    try:
        limit = int(request.args.get("limit", 200))
    except (TypeError, ValueError):
        limit = 200
    runs = db.get_watchlist_runs(limit=limit)
    for r in runs:
        if r.get("ran_at") is not None:
            r["ran_at_human"] = format_local_time(r["ran_at"])
        if r.get("next_run_at") is not None:
            r["next_run_at_human"] = format_local_time(r["next_run_at"])
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
