"""Per-storefront discovery constants and lookup helpers.

`discovery_names_for()` returns the localized title(s) of a storefront's
"New Releases" room, matched against `attributes.name` in the amp-api
editorial groupings response (and, via `fallback_titles()`, against room
titles scraped from the `/new` page in client.py).

Defaults live in `config._DEFAULTS` (`discovery_names` /
`discovery_fallback_titles`) and are editable at runtime via the Settings
page (`PUT /api/system/config`) — every lookup here calls `load_config()`
fresh, so an edit takes effect on the next discovery poll with no restart.
Locales live in `storefront_locales.py`.
"""

from config import load_config
from storefront_locales import STOREFRONT_LOCALES

DEFAULT_LOCALE = "en-US"


def locale_for(storefront: str) -> str:
    return STOREFRONT_LOCALES.get(storefront, DEFAULT_LOCALE)


def discovery_names_for(storefront: str) -> list[str]:
    """Candidate room-title string(s) to match for `storefront`.

    A configured `discovery_names[storefront]` entry is matched exactly
    (case-insensitively by the caller); otherwise falls back to
    `discovery_fallback_titles`, substring-matched by the caller.
    """
    cfg = load_config()
    name = (cfg.get("discovery_names") or {}).get(storefront)
    if name:
        return [name]
    return fallback_titles(cfg)


def fallback_titles(cfg: dict | None = None) -> list[str]:
    """The shared substring-match fallback list (storefront-agnostic)."""
    cfg = cfg if cfg is not None else load_config()
    return list(cfg.get("discovery_fallback_titles") or [])
