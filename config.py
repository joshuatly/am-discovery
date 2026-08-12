"""Application configuration helpers.

All code that reads or writes config.json lives here so that both the server
(scheduler) and the API blueprints can import it without circular dependencies.
"""

import copy
import json
import logging
import os
import threading
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

# Shared across any module that does read-modify-write on config.json.
# RLock so callers can nest load_config/save_config inside a held lock.
CONFIG_LOCK = threading.RLock()

_DEFAULTS = {
    "newrelease_poll_interval_days": 1,
    "check_storefronts": ["us", "jp"],
    "home_storefront": "us",
    # Per-storefront localized title of the "New Releases" editorial room
    # (resourceTypes == ["albums"]), matched against `attributes.name` in
    # the amp-api groupings response. This is the new-*albums* room —
    # storefronts also expose a separate new-*songs* room (singles/EPs)
    # that this app does not track. Edit via the Settings page —
    # storefronts.py/client.py re-read config on every discovery call, so
    # changes take effect on the next poll without a restart.
    "discovery_names": {
        "cn": "本周新发行",
        "hk": "新發行",
        "mo": "新發行",
        "tw": "新發行",
        "jp": "ニューリリース",
        "sg": "Recent Releases",
        "my": "Recent Releases",
        "us": "New Releases",
    },
    # Substring fallback used when a storefront has no `discovery_names`
    # entry (amp-api path) and by the /new page scraping path in client.py.
    "discovery_fallback_titles": [
        "new release",
        "new releases",
        "新發行",
        "ニューリリース",
        "Rilisan Baru",
        "keluaran baharu",
    ],
    "watchlist_poll_interval_minutes": 10,
    "watchlist_poll_batch_size": 5,
    "watchlist_refresh_interval_days": 7,
    "notification_scan_interval_minutes": 10,
    "notification_max_release_age_days": 7,
    "mb_scan_enabled": True,
    "mb_scan_interval_minutes": 60,
    "mb_scan_artist_batch": 3,
    "mb_artist_recheck_days": 7,
    "cli_scheduler_url": "",
    "cli_scheduler_preset": "",
    "timezone": "UTC",
    "notifications": {
        "queue_max_size": 100,
        "max_failures": 5,
        "rate_limit_per_sec": 1,
        "events": [],
    },
}


def load_config() -> dict:
    defaults = copy.deepcopy(_DEFAULTS)
    with CONFIG_LOCK:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, encoding="utf-8") as f:
                return {**defaults, **json.load(f)}
        return defaults


def save_config(cfg: dict) -> None:
    with CONFIG_LOCK, open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def _local_tz() -> ZoneInfo:
    tz_name = (load_config().get("timezone") or "UTC").strip() or "UTC"
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("invalid timezone %r, falling back to UTC", tz_name)
        return UTC


def format_local_time(ts) -> str:
    """Format a UNIX timestamp into a human-readable string using ``timezone`` from config.

    Falls back to UTC when the configured value is empty or not a recognised IANA zone.
    The ``%Z`` suffix renders the zone abbreviation (e.g. ``HKT``, ``EDT``, ``UTC``).
    """
    return datetime.fromtimestamp(ts, tz=_local_tz()).strftime("%Y-%m-%d %H:%M %Z")


def format_local_date(ts) -> str:
    """Return ``YYYY-MM-DD`` for ``ts`` (UNIX seconds) in the configured ``timezone``."""
    return datetime.fromtimestamp(ts, tz=_local_tz()).strftime("%Y-%m-%d")
