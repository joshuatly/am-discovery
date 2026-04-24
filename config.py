"""Application configuration helpers.

All code that reads or writes config.json lives here so that both the server
(scheduler) and the API blueprints can import it without circular dependencies.
"""

import copy
import json
import os
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

# Shared across any module that does read-modify-write on config.json.
# RLock so callers can nest load_config/save_config inside a held lock.
CONFIG_LOCK = threading.RLock()

_DEFAULTS = {
    "newrelease_poll_interval_days": 1,
    "check_storefronts": ["jp", "tw", "my", "hk", "sg"],
    "home_storefront": "my",
    "watchlist_poll_interval_minutes": 10,
    "watchlist_poll_batch_size": 5,
    "watchlist_refresh_interval_days": 7,
    "cli_scheduler_url": "",
    "cli_scheduler_preset": "",
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
