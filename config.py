"""Application configuration helpers.

All code that reads or writes config.json lives here so that both the server
(scheduler) and the API blueprints can import it without circular dependencies.
"""

import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

_DEFAULTS = {
    "newrelease_poll_interval_days": 1,
    "check_storefronts": ["jp", "tw", "my", "hk", "sg"],
    "home_storefront": "my",
    "watchlist_poll_interval_minutes": 10,
    "watchlist_poll_batch_size": 5,
    "watchlist_refresh_interval_days": 7,
    "cli_scheduler_url": "",
    "cli_scheduler_preset": "",
}


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return {**_DEFAULTS, **json.load(f)}
    return dict(_DEFAULTS)


def save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
