"""Apprise notification dispatch.

Stateless integration with a self-hosted Apprise API: events from the discovery
and watchlist pollers are routed to user-configured Apprise URLs (e.g.
``http://host:8100/notify/apprise``) using rendered title/body templates.

All configuration (the list of notification events and global queue settings)
is persisted in ``config.json`` under the ``notifications`` key — see
:func:`config.load_config`. There is no separate database table.

Sends are processed by a single daemon worker thread at a configurable rate
(default 1/sec). Each event tracks ``consecutive_failures`` and is auto-disabled
after ``max_failures`` consecutive failures.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import urllib.error
import urllib.request
import uuid

from config import CONFIG_LOCK, load_config, save_config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

EVENT_TYPES = [
    "onDiscoveryComplete",
    "onDiscoveryFailed",
    "onArtistNewRelease",
    "onArtistNewSingle",
]

NOTIFICATION_TYPES = ["info", "success", "warning", "failure"]

DEFAULT_TEMPLATES: dict[str, dict] = {
    "onDiscoveryComplete": {
        "title": "AM Discovery: {new_count} new releases",
        "body": "Run at {run_at}\n{summary}",
        "notification_type": "info",
    },
    "onDiscoveryFailed": {
        "title": "AM Discovery: discovery failed",
        "body": "Failed storefronts: {storefronts}\nRun at {run_at}",
        "notification_type": "failure",
    },
    "onArtistNewRelease": {
        "title": "New {release_type} from {artist}",
        "body": '{artist} just released "{title}" ({track_count} tracks, {release_date})\n{url}',
        "notification_type": "success",
    },
    "onArtistNewSingle": {
        "title": "New single from {artist}",
        "body": '{artist} just released "{title}" ({release_date})\n{url}',
        "notification_type": "success",
    },
}

EVENT_VARIABLES: dict[str, list[str]] = {
    "onDiscoveryComplete": ["run_at", "new_count", "storefronts", "summary", "room_ids"],
    "onDiscoveryFailed": ["run_at", "storefronts"],
    "onArtistNewRelease": [
        "artist",
        "artist_id",
        "title",
        "track_count",
        "upc",
        "url",
        "storefronts",
        "store_adam_id",
        "release_date",
        "release_type",
        "description",
    ],
    "onArtistNewSingle": [
        "artist",
        "artist_id",
        "title",
        "track_count",
        "upc",
        "url",
        "storefronts",
        "store_adam_id",
        "release_date",
        "release_type",
        "description",
    ],
}

SAMPLE_VARIABLES: dict[str, dict] = {
    "onDiscoveryComplete": {
        "run_at": "2026-04-23 14:30 UTC",
        "new_count": 16,
        "storefronts": "jp, tw, my, hk, sg",
        "summary": "JP: 12 new\nTW: 4 new\nMY: 0 new\nHK: 0 new\nSG: 0 new",
        "room_ids": "1234, 5678, 9012, 3456, 7890",
    },
    "onDiscoveryFailed": {
        "run_at": "2026-04-23 14:30 UTC",
        "storefronts": "jp, tw",
    },
    "onArtistNewRelease": {
        "artist": "Sample Artist",
        "artist_id": "123456",
        "title": "Sample Album",
        "track_count": 12,
        "upc": "0000000000000",
        "url": "https://music.apple.com/us/album/123456",
        "storefronts": "us, jp",
        "store_adam_id": "123456",
        "release_date": "2026-04-23",
        "release_type": "main-albums",
        "description": "Sample album description.",
    },
    "onArtistNewSingle": {
        "artist": "Sample Artist",
        "artist_id": "123456",
        "title": "Sample Single",
        "track_count": 1,
        "upc": "0000000000000",
        "url": "https://music.apple.com/us/album/123456",
        "storefronts": "us, jp",
        "store_adam_id": "123456",
        "release_date": "2026-04-23",
        "release_type": "singles-eps",
        "description": "Sample single description.",
    },
}


# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------


class _SafeDict(dict):
    def __missing__(self, key):
        return ""


_queue: queue.Queue | None = None
_thread: threading.Thread | None = None
_started = False
_state_lock = threading.Lock()


def _safe_format(template: str, variables: dict) -> str:
    try:
        return template.format_map(_SafeDict(variables))
    except (ValueError, IndexError):
        # Malformed template (e.g. unmatched braces); return raw template so
        # the user sees what they typed and can fix it.
        return template


def _post_apprise(url: str, payload: dict, timeout: int = 10) -> tuple[bool, str]:
    if not url:
        return False, "apprise_url is empty"
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if 200 <= resp.status < 300:
                return True, f"HTTP {resp.status}"
            return False, f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code} {e.reason}"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# Config persistence (read-modify-write under CONFIG_LOCK)
# ---------------------------------------------------------------------------


def _get_notifications_block(cfg: dict) -> dict:
    block = cfg.get("notifications") or {}
    block.setdefault("queue_max_size", 100)
    block.setdefault("max_failures", 5)
    block.setdefault("rate_limit_per_sec", 1)
    block.setdefault("events", [])
    return block


def _persist_event_change(event_id: str, **fields) -> None:
    with CONFIG_LOCK:
        cfg = load_config()
        block = _get_notifications_block(cfg)
        for ev in block["events"]:
            if ev.get("id") == event_id:
                ev.update(fields)
                break
        cfg["notifications"] = block
        save_config(cfg)


# ---------------------------------------------------------------------------
# CRUD API (used by the Flask blueprint)
# ---------------------------------------------------------------------------


def _normalise_event(event: dict) -> dict:
    out = dict(event)
    out.setdefault("id", uuid.uuid4().hex[:12])
    out.setdefault("enabled", True)
    out.setdefault("consecutive_failures", 0)
    out.setdefault("disabled_reason", None)
    event_type = out.get("event_type")
    defaults = DEFAULT_TEMPLATES.get(event_type, {})
    if not out.get("title_template"):
        out["title_template"] = defaults.get("title", "")
    if not out.get("body_template"):
        out["body_template"] = defaults.get("body", "")
    if not out.get("notification_type"):
        out["notification_type"] = defaults.get("notification_type", "info")
    out.setdefault("apprise_url", "")
    return out


def list_events() -> list[dict]:
    return _get_notifications_block(load_config())["events"]


def get_event(event_id: str) -> dict | None:
    for ev in list_events():
        if ev.get("id") == event_id:
            return ev
    return None


def create_event(event: dict) -> dict:
    new_event = _normalise_event(event)
    with CONFIG_LOCK:
        cfg = load_config()
        block = _get_notifications_block(cfg)
        block["events"].append(new_event)
        cfg["notifications"] = block
        save_config(cfg)
    return new_event


def update_event(event_id: str, patch: dict) -> dict | None:
    with CONFIG_LOCK:
        cfg = load_config()
        block = _get_notifications_block(cfg)
        for i, ev in enumerate(block["events"]):
            if ev.get("id") == event_id:
                merged = {**ev, **patch, "id": event_id}
                block["events"][i] = merged
                cfg["notifications"] = block
                save_config(cfg)
                return merged
    return None


def delete_event(event_id: str) -> bool:
    with CONFIG_LOCK:
        cfg = load_config()
        block = _get_notifications_block(cfg)
        before = len(block["events"])
        block["events"] = [ev for ev in block["events"] if ev.get("id") != event_id]
        if len(block["events"]) == before:
            return False
        cfg["notifications"] = block
        save_config(cfg)
        return True


def get_event_types_meta() -> dict:
    return {
        "types": [
            {
                "event_type": et,
                "variables": EVENT_VARIABLES[et],
                "default_title": DEFAULT_TEMPLATES[et]["title"],
                "default_body": DEFAULT_TEMPLATES[et]["body"],
                "default_notification_type": DEFAULT_TEMPLATES[et]["notification_type"],
            }
            for et in EVENT_TYPES
        ],
        "notification_types": NOTIFICATION_TYPES,
    }


# ---------------------------------------------------------------------------
# Enqueue / send
# ---------------------------------------------------------------------------


def _render(event: dict, variables: dict) -> dict:
    return {
        "event_id": event.get("id"),
        "apprise_url": event.get("apprise_url", ""),
        "title": _safe_format(event.get("title_template", ""), variables),
        "body": _safe_format(event.get("body_template", ""), variables),
        "notification_type": event.get("notification_type", "info"),
    }


def enqueue(event_type: str, variables: dict) -> None:
    """Enqueue rendered notifications for every enabled event of ``event_type``."""
    if event_type not in EVENT_TYPES:
        logger.warning("[notifications] unknown event_type: %s", event_type)
        return
    if _queue is None:
        logger.debug("[notifications] queue not initialised; dropping %s", event_type)
        return
    events = list_events()
    for ev in events:
        if ev.get("event_type") != event_type or not ev.get("enabled"):
            continue
        item = _render(ev, variables)
        try:
            _queue.put_nowait(item)
        except queue.Full:
            try:
                dropped = _queue.get_nowait()
                logger.warning(
                    "[notifications] queue full; dropped oldest event_id=%s to make room for %s",
                    dropped.get("event_id"),
                    item.get("event_id"),
                )
            except queue.Empty:
                pass
            try:
                _queue.put_nowait(item)
            except queue.Full:
                logger.warning("[notifications] queue still full; dropping new item")


def send_test(event: dict, variables: dict | None = None) -> tuple[bool, str]:
    """Synchronously send a test notification; bypasses the queue."""
    event_type = event.get("event_type")
    if variables is None:
        variables = SAMPLE_VARIABLES.get(event_type, {})
    item = _render(event, variables)
    item["title"] = f"[TEST] {item['title']}"
    payload = {"body": item["body"], "title": item["title"], "type": item["notification_type"]}
    return _post_apprise(item["apprise_url"], payload)


# ---------------------------------------------------------------------------
# Worker thread
# ---------------------------------------------------------------------------


def _on_send_success(event_id: str | None) -> None:
    if not event_id:
        return
    with _state_lock:
        ev = get_event(event_id)
        if ev and ev.get("consecutive_failures"):
            _persist_event_change(event_id, consecutive_failures=0, disabled_reason=None)


def _on_send_failure(event_id: str | None, message: str) -> None:
    if not event_id:
        return
    with _state_lock:
        ev = get_event(event_id)
        if not ev:
            return
        new_count = (ev.get("consecutive_failures") or 0) + 1
        max_failures = _get_notifications_block(load_config()).get("max_failures", 5)
        fields = {"consecutive_failures": new_count}
        if new_count >= max_failures:
            fields["enabled"] = False
            fields["disabled_reason"] = "max_failures"
            logger.warning(
                "[notifications] event %s auto-disabled after %d consecutive failures (last: %s)",
                event_id,
                new_count,
                message,
            )
        _persist_event_change(event_id, **fields)


def _worker_loop() -> None:
    rate_limit = max(1, _get_notifications_block(load_config()).get("rate_limit_per_sec", 1))
    interval = 1.0 / rate_limit
    while True:
        try:
            item = _queue.get()
        except Exception as e:  # noqa: BLE001
            logger.error("[notifications] queue.get failed: %s", e)
            time.sleep(1)
            continue
        try:
            payload = {
                "body": item["body"],
                "title": item["title"],
                "type": item["notification_type"],
            }
            ok, message = _post_apprise(item["apprise_url"], payload)
            if ok:
                logger.info("[notifications] sent event_id=%s (%s)", item.get("event_id"), message)
                _on_send_success(item.get("event_id"))
            else:
                logger.warning("[notifications] send failed event_id=%s: %s", item.get("event_id"), message)
                _on_send_failure(item.get("event_id"), message)
        except Exception as e:  # noqa: BLE001
            logger.error("[notifications] worker loop error: %s", e)
        time.sleep(interval)


def init() -> None:
    """Initialise the queue and start the worker thread. Idempotent."""
    global _queue, _thread, _started
    if _started:
        return
    block = _get_notifications_block(load_config())
    _queue = queue.Queue(maxsize=block.get("queue_max_size", 100))
    _thread = threading.Thread(target=_worker_loop, name="apprise-sender", daemon=True)
    _thread.start()
    _started = True
    logger.info(
        "[notifications] started (queue_max_size=%d, rate_limit_per_sec=%d, max_failures=%d)",
        block.get("queue_max_size", 100),
        block.get("rate_limit_per_sec", 1),
        block.get("max_failures", 5),
    )
