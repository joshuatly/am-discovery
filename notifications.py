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

import ipaddress
import json
import logging
import queue
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta

import db
from config import CONFIG_LOCK, format_local_date, format_local_time, load_config, save_config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

EVENT_TYPES = [
    "onDiscoveryComplete",
    "onDiscoveryFailed",
    "onArtistNewRelease",
    "onArtistNewSingle",
    "onWatchlistBatchComplete",
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
    "onWatchlistBatchComplete": {
        "title": "AM Discovery: watchlist batch refreshed ({refreshed_count}/{batch_size})",
        "body": (
            "Run at {run_at}\n"
            "Refreshed: {refreshed_artists}\n"
            "Pending: {pending_count} artists\n"
            "Next batch: {next_run_at}"
        ),
        "notification_type": "info",
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
    "onWatchlistBatchComplete": [
        "run_at",
        "batch_size",
        "refreshed_count",
        "error_count",
        "refreshed_artists",
        "failed_artists",
        "pending_count",
        "next_run_at",
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
    "onWatchlistBatchComplete": {
        "run_at": "2026-04-23 14:30 UTC",
        "batch_size": 5,
        "refreshed_count": 4,
        "error_count": 1,
        "refreshed_artists": "Taylor Swift, IU, YOASOBI, LiSA",
        "failed_artists": "aespa",
        "pending_count": 12,
        "next_run_at": "2026-04-23 14:40 UTC",
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

# Scanner-thread state (separate from the Apprise sender above).
_last_notify_at: int | None = None
_scan_timer: threading.Timer | None = None
_scan_lock = threading.Lock()
_scanner_started = False


def _safe_format(template: str, variables: dict) -> str:
    try:
        return template.format_map(_SafeDict(variables))
    except (ValueError, IndexError):
        # Malformed template (e.g. unmatched braces); return raw template so
        # the user sees what they typed and can fix it.
        return template


_APPRISE_ALLOWED_SCHEMES = {"http", "https"}

# Apprise targets are expected to live on the operator's own LAN or Docker
# network, so private/loopback addresses are allowed. Only link-local
# addresses are blocked outright — that range is where every major cloud's
# instance-metadata service lives (169.254.169.254 on AWS/GCP/Azure/
# DigitalOcean/Oracle/Kubernetes) and is never a legitimate Apprise target.
# A couple of metadata IPs that fall outside the link-local range are
# blocked explicitly.
_APPRISE_EXTRA_BLOCKED_HOSTS = {
    "100.100.100.200",  # Alibaba Cloud instance metadata
}


def _unsafe_apprise_target_reason(url: str) -> str | None:
    """Return a reason string if url is unsafe to fetch (SSRF guard), else None."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in _APPRISE_ALLOWED_SCHEMES:
        return f"scheme '{parts.scheme}' is not allowed (only http/https)"
    hostname = parts.hostname
    if not hostname:
        return "URL has no host"
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        return f"could not resolve host: {e}"
    for info in infos:
        ip_str = info[4][0]
        ip = ipaddress.ip_address(ip_str)
        unsafe = ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip_str in _APPRISE_EXTRA_BLOCKED_HOSTS
        if unsafe:
            return f"host resolves to a blocked metadata/link-local address ({ip})"
    return None


class _SSRFGuardError(Exception):
    pass


class _SSRFSafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-validates the redirect target so a 30x response can't retarget the request."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        reason = _unsafe_apprise_target_reason(newurl)
        if reason:
            raise _SSRFGuardError(f"blocked redirect: {reason}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _post_apprise(url: str, payload: dict, timeout: int = 10) -> tuple[bool, str]:
    if not url:
        return False, "apprise_url is empty"
    reason = _unsafe_apprise_target_reason(url)
    if reason:
        return False, f"blocked: {reason}"
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        opener = urllib.request.build_opener(_SSRFSafeRedirectHandler)
        with opener.open(req, timeout=timeout) as resp:
            if 200 <= resp.status < 300:
                return True, f"HTTP {resp.status}"
            return False, f"HTTP {resp.status}"
    except _SSRFGuardError as e:
        return False, str(e)
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


def _build_sample_variables(event_type: str) -> dict:
    """Build sample variables for an event type, injecting live timezone-formatted
    timestamps so test notifications reflect the configured ``timezone``."""
    variables = dict(SAMPLE_VARIABLES.get(event_type, {}))
    if event_type in ("onDiscoveryComplete", "onDiscoveryFailed", "onWatchlistBatchComplete"):
        now = time.time()
        variables["run_at"] = format_local_time(now)
        if event_type == "onWatchlistBatchComplete":
            variables["next_run_at"] = format_local_time(now + 600)
    return variables


def send_test(event: dict, variables: dict | None = None) -> tuple[bool, str]:
    """Synchronously send a test notification; bypasses the queue."""
    event_type = event.get("event_type")
    if variables is None:
        variables = _build_sample_variables(event_type)
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


# ---------------------------------------------------------------------------
# Watched-artist scanner (fires onArtistNewRelease / onArtistNewSingle)
# ---------------------------------------------------------------------------


def _ids_from_artists_json(blob) -> set[str]:
    """Extract the set of ``id`` fields from an ``artists_json`` text blob.

    The blob is JSON-encoded by :func:`db.upsert_album` as a list of
    ``{id, name, url}`` objects. Returns an empty set on missing/malformed input.
    """
    if not blob:
        return set()
    try:
        parsed = json.loads(blob) if isinstance(blob, str) else blob
    except (TypeError, ValueError):
        return set()
    if not isinstance(parsed, list):
        return set()
    out: set[str] = set()
    for entry in parsed:
        if isinstance(entry, dict):
            aid = entry.get("id")
            if aid:
                out.add(str(aid))
    return out


def enqueue_album_notification(album: dict, artist_name: str) -> None:
    """Pick the right event type for ``album`` and enqueue a notification."""
    rt = album.get("release_type") or ""
    event = "onArtistNewSingle" if rt == "singles-eps" else "onArtistNewRelease"
    sf_raw = album.get("storefronts") or "[]"
    try:
        sf_list = json.loads(sf_raw) if isinstance(sf_raw, str) else list(sf_raw)
    except (TypeError, ValueError):
        sf_list = []
    enqueue(
        event,
        {
            "artist": artist_name,
            "artist_id": album.get("artist_id") or "",
            "title": album.get("title", ""),
            "track_count": album.get("track_count") or 0,
            "upc": album.get("upc") or "",
            "url": album.get("url") or "",
            "storefronts": ", ".join(sf_list),
            "store_adam_id": album.get("store_adam_id") or "",
            "release_date": album.get("release_date") or "",
            "release_type": rt,
            "description": (album.get("description") or "").strip(),
        },
    )


def get_last_notify_at() -> int | None:
    """Return the unix timestamp of the most recent completed scan, or None
    if the scanner has not yet been started or has not yet completed a scan."""
    return _last_notify_at


def _run_scan() -> None:
    """One scanner tick: find new watched-artist albums in the lookback window
    and enqueue notifications. Reschedules itself in ``finally``."""
    global _last_notify_at
    try:
        cfg = load_config()
        interval_sec = max(60, int(cfg.get("notification_scan_interval_minutes", 10)) * 60)
        max_age_days = max(0, int(cfg.get("notification_max_release_age_days", 7)))
        now = int(time.time())

        today_local = format_local_date(now)
        min_release_date = (datetime.strptime(today_local, "%Y-%m-%d") - timedelta(days=max_age_days)).strftime(
            "%Y-%m-%d"
        )

        rows = db.get_albums_first_seen_after(
            since_ts=now - interval_sec,
            min_release_date=min_release_date,
        )
        fired = 0
        if rows:
            watched = db.get_watched_artist_ids()
            for r in rows:
                ids: set[str] = set()
                primary = r.get("artist_id")
                if primary:
                    ids.add(str(primary))
                ids |= _ids_from_artists_json(r.get("artists_json"))
                hit = ids & watched
                if not hit:
                    continue
                matched_id = next(iter(hit))
                artist_name = (db.get_artist_info(matched_id) or {}).get("name", "")
                enqueue_album_notification(r, artist_name)
                fired += 1

        _last_notify_at = now
        logger.info(
            "[notifications] scan complete (window=%ds rows=%d fired=%d)",
            interval_sec,
            len(rows),
            fired,
        )
    except Exception as e:  # noqa: BLE001
        logger.error("[notifications] scan failed: %s", e)
    finally:
        _schedule_next_scan()


def _schedule_next_scan() -> None:
    global _scan_timer
    cfg = load_config()
    interval_sec = max(60, int(cfg.get("notification_scan_interval_minutes", 10)) * 60)
    with _scan_lock:
        if _scan_timer:
            _scan_timer.cancel()
        _scan_timer = threading.Timer(interval_sec, _run_scan)
        _scan_timer.daemon = True
        _scan_timer.start()
    logger.debug("[notifications] next scan in %ds", interval_sec)


def init_scanner() -> None:
    """Start the watched-artist scanner thread. Idempotent.

    Initialises ``_last_notify_at`` to ``now()`` so the first scan window
    is ``(startup_ts, startup_ts + interval_sec]`` — no inserts before
    startup get notified.
    """
    global _scanner_started, _last_notify_at
    if _scanner_started:
        return
    _last_notify_at = int(time.time())
    _scanner_started = True
    _schedule_next_scan()
    cfg = load_config()
    logger.info(
        "[notifications] scanner started (interval=%dm, max_release_age_days=%d)",
        cfg.get("notification_scan_interval_minutes", 10),
        cfg.get("notification_max_release_age_days", 7),
    )
