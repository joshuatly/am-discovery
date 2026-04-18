"""Per-storefront discovery constants.

`DISCOVERY_NAMES` maps a storefront code to the localized title of its
"New Releases" room (matched against `attributes.name` in the editorial
groupings response). Locales live in `storefront_locales.py`.
"""

from storefront_locales import STOREFRONT_LOCALES

DEFAULT_LOCALE = "en-US"

DISCOVERY_NAMES: dict[str, str] = {
    "hk": "新發行",
    "mo": "新發行",
    "tw": "新發行",
    "jp": "ニューリリース",
    "sg": "New Releases",
    "my": "New Releases",
    "us": "New Releases",
}

# Fallback titles matched when a storefront has no entry in DISCOVERY_NAMES.
DEFAULT_DISCOVERY_NAMES: list[str] = [
    "new release",
    "new releases",
    "新發行",
    "ニューリリース",
    "Rilisan Baru",
    "keluaran baharu",
]


def locale_for(storefront: str) -> str:
    return STOREFRONT_LOCALES.get(storefront, DEFAULT_LOCALE)


def discovery_names_for(storefront: str) -> list[str]:
    name = DISCOVERY_NAMES.get(storefront)
    if name:
        return [name]
    return list(DEFAULT_DISCOVERY_NAMES)
