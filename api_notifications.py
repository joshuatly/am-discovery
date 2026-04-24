"""AM Discovery REST API — notification event routes.

Flask Blueprint exposing CRUD + test endpoints for Apprise notification events.
All persistence and dispatch logic lives in :mod:`notifications`.
"""

from flask import Blueprint, jsonify, request

import notifications
from config import load_config

notifications_bp = Blueprint("notifications", __name__)


# ---------------------------------------------------------------------------
# GET /api/notifications
# ---------------------------------------------------------------------------


@notifications_bp.route("/api/notifications", methods=["GET"])
def api_notifications_list():
    """List configured notification events and global settings.
    ---
    responses:
      200:
        description: Notification configuration
    """
    block = notifications._get_notifications_block(load_config())
    return jsonify(
        {
            "events": block.get("events", []),
            "queue_max_size": block.get("queue_max_size"),
            "max_failures": block.get("max_failures"),
            "rate_limit_per_sec": block.get("rate_limit_per_sec"),
        },
    )


# ---------------------------------------------------------------------------
# POST /api/notifications
# ---------------------------------------------------------------------------


@notifications_bp.route("/api/notifications", methods=["POST"])
def api_notifications_create():
    """Create a new notification event.
    ---
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
    responses:
      201:
        description: Event created
      400:
        description: Invalid event_type
    """
    event = request.get_json(force=True) or {}
    if event.get("event_type") not in notifications.EVENT_TYPES:
        return jsonify({"error": "invalid event_type"}), 400
    return jsonify(notifications.create_event(event)), 201


# ---------------------------------------------------------------------------
# PUT /api/notifications/<id>
# ---------------------------------------------------------------------------


@notifications_bp.route("/api/notifications/<event_id>", methods=["PUT"])
def api_notifications_update(event_id):
    """Update fields on an existing notification event (partial patch).
    ---
    parameters:
      - name: event_id
        in: path
        required: true
        type: string
      - name: body
        in: body
        required: true
        schema:
          type: object
    responses:
      200:
        description: Updated event
      400:
        description: Invalid event_type
      404:
        description: Event not found
    """
    patch = request.get_json(force=True) or {}
    if "event_type" in patch and patch["event_type"] not in notifications.EVENT_TYPES:
        return jsonify({"error": "invalid event_type"}), 400
    updated = notifications.update_event(event_id, patch)
    if updated is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(updated)


# ---------------------------------------------------------------------------
# DELETE /api/notifications/<id>
# ---------------------------------------------------------------------------


@notifications_bp.route("/api/notifications/<event_id>", methods=["DELETE"])
def api_notifications_delete(event_id):
    """Delete a notification event.
    ---
    parameters:
      - name: event_id
        in: path
        required: true
        type: string
    responses:
      200:
        description: Deleted
      404:
        description: Event not found
    """
    if not notifications.delete_event(event_id):
        return jsonify({"error": "not found"}), 404
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# POST /api/notifications/<id>/test
# ---------------------------------------------------------------------------


@notifications_bp.route("/api/notifications/<event_id>/test", methods=["POST"])
def api_notifications_test_saved(event_id):
    """Send a test notification using a saved event's configuration.
    ---
    parameters:
      - name: event_id
        in: path
        required: true
        type: string
    responses:
      200:
        description: Test result
      404:
        description: Event not found
    """
    event = notifications.get_event(event_id)
    if event is None:
        return jsonify({"error": "not found"}), 404
    ok, message = notifications.send_test(event)
    return jsonify({"ok": ok, "message": message})


# ---------------------------------------------------------------------------
# POST /api/notifications/test
# ---------------------------------------------------------------------------


@notifications_bp.route("/api/notifications/test", methods=["POST"])
def api_notifications_test_unsaved():
    """Send a test notification using an in-flight (unsaved) event payload.
    ---
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
    responses:
      200:
        description: Test result
      400:
        description: Invalid event_type
    """
    event = request.get_json(force=True) or {}
    if event.get("event_type") not in notifications.EVENT_TYPES:
        return jsonify({"error": "invalid event_type"}), 400
    # Apply default templates so a blank form still sends something useful.
    event = notifications._normalise_event(event)
    ok, message = notifications.send_test(event)
    return jsonify({"ok": ok, "message": message})


# ---------------------------------------------------------------------------
# GET /api/notifications/event-types
# ---------------------------------------------------------------------------


@notifications_bp.route("/api/notifications/event-types", methods=["GET"])
def api_notifications_event_types():
    """Return metadata for the supported event types (used by the UI).
    ---
    responses:
      200:
        description: Event-type metadata
    """
    return jsonify(notifications.get_event_types_meta())
