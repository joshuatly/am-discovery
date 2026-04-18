"""Per-storefront constants used by discovery.

`STOREFRONTS` maps a two-letter storefront code to the locale sent as the
amp-api `l=` query param and the localized title of the "New Releases" room
in that storefront (matched against `attributes.name` in the editorial
groupings response). Extend this map when new markets are added.
"""

STOREFRONTS: dict[str, dict[str, str]] = {
    "hk": {"locale": "zh-Hant-HK", "discovery_name": "新發行"},
    "mo": {"locale": "zh-Hant-HK", "discovery_name": "新發行"},
    "tw": {"locale": "zh-Hant-TW", "discovery_name": "新發行"},
    "jp": {"locale": "ja-JP", "discovery_name": "ニューリリース"},
    "sg": {"locale": "en-SG", "discovery_name": "New Releases"},
    "my": {"locale": "en-MY", "discovery_name": "New Releases"},
    "us": {"locale": "en-US", "discovery_name": "New Releases"},
}

DEFAULT_LOCALE = "en-US"

# Fallback titles matched when a storefront is not in STOREFRONTS.
DEFAULT_DISCOVERY_NAMES: list[str] = [
    "new release",
    "new releases",
    "新發行",
    "ニューリリース",
    "Rilisan Baru",
    "keluaran baharu",
]


def locale_for(storefront: str) -> str:
    return STOREFRONTS.get(storefront, {}).get("locale", DEFAULT_LOCALE)


def discovery_names_for(storefront: str) -> list[str]:
    entry = STOREFRONTS.get(storefront)
    if entry and entry.get("discovery_name"):
        return [entry["discovery_name"]]
    return list(DEFAULT_DISCOVERY_NAMES)
