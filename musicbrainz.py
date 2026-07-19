"""MusicBrainz web-service client.

A thin, dependency-free (stdlib ``urllib`` only, matching :mod:`client`) wrapper
around the MusicBrainz ``/ws/2/`` JSON API. The public MusicBrainz web service
needs **no API key** — only a descriptive ``User-Agent`` and a hard ~1 req/sec
rate limit, both enforced here.

A single module-level lock serialises every outbound request so the background
seeding scanner and any on-demand admin lookups can never collectively exceed the
rate limit. Requests that hit a 503 (MusicBrainz's "slow down" signal) are retried
with exponential backoff; a persistent limit raises :class:`MusicBrainzRateLimitError`
so callers can fail gracefully and reschedule.
"""

import json
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

BASE_URL = "https://musicbrainz.org/ws/2"
_HEADERS = {
    "User-Agent": "AMDiscovery/1.0 (https://github.com/joshuatly/am-discovery)",
    "Accept": "application/json",
}

# MusicBrainz asks for no more than one request per second per IP. We keep a small
# safety margin. All requests funnel through _RATE_LOCK so concurrent callers
# (scanner threads + Flask request threads) still respect a single global cadence.
MIN_INTERVAL_SEC = 1.1
_RATE_LOCK = threading.Lock()
_last_request_at = 0.0

# Retry/backoff for transient failures (503 rate-limit, network hiccups).
MAX_RETRIES = 4
BACKOFF_BASE_SEC = 2.0

# Release-group primary types we care about when hunting for un-seeded releases.
# "Single" is deliberately excluded per product requirement; EPs are included.
SEED_PRIMARY_TYPES = ("album", "ep")


class MusicBrainzError(Exception):
    """Base class for MusicBrainz client errors."""


class MusicBrainzRateLimitError(MusicBrainzError):
    """Raised when MusicBrainz keeps returning 503 after exhausting retries."""


def _throttle():
    """Block until at least MIN_INTERVAL_SEC has elapsed since the last request."""
    global _last_request_at
    with _RATE_LOCK:
        wait = MIN_INTERVAL_SEC - (time.time() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.time()


def _request(path: str, params: dict) -> dict:
    """GET ``BASE_URL/path?params`` as JSON, honouring the rate limit and retrying.

    Raises :class:`MusicBrainzRateLimitError` on a persistent 503, or
    :class:`MusicBrainzError` on other unrecoverable failures.
    """
    query = urllib.parse.urlencode({**params, "fmt": "json"})
    url = f"{BASE_URL}/{path}?{query}"
    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES):
        _throttle()
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 503:
                delay = BACKOFF_BASE_SEC * (2**attempt)
                logger.warning("[MusicBrainz] 503 rate-limited, backing off %.1fs (attempt %d)", delay, attempt + 1)
                time.sleep(delay)
                continue
            raise MusicBrainzError(f"HTTP {e.code} for {path}") from e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last_err = e
            delay = BACKOFF_BASE_SEC * (2**attempt)
            logger.warning("[MusicBrainz] request error (%s), retrying in %.1fs", e, delay)
            time.sleep(delay)
    raise MusicBrainzRateLimitError(f"MusicBrainz unavailable after {MAX_RETRIES} attempts: {last_err}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def search_artist(name: str, limit: int = 5) -> list[dict]:
    """Search for an artist by name. Returns ranked candidates (best first)."""
    if not name or not name.strip():
        return []
    data = _request("artist", {"query": name.strip(), "limit": limit})
    out = []
    for a in data.get("artists", []):
        # Prefer the human-readable area name; fall back to the ISO country code.
        area = (a.get("area") or {}).get("name") or a.get("country") or ""
        out.append(
            {
                "id": a.get("id"),
                "name": a.get("name"),
                "score": a.get("score"),
                "disambiguation": a.get("disambiguation") or "",
                "type": a.get("type") or "",
                "country": a.get("country") or "",
                "area": area,
                "url": f"https://musicbrainz.org/artist/{a.get('id')}",
            }
        )
    return out


def browse_release_groups(artist_mbid: str, primary_types=SEED_PRIMARY_TYPES) -> list[dict]:
    """Return all release-groups for an artist filtered to the given primary types.

    Paginates through the browse endpoint (100 per page). Each entry carries a
    normalised title so callers can match against local albums cheaply.
    """
    if not artist_mbid:
        return []
    type_filter = "|".join(primary_types)
    groups: list[dict] = []
    offset = 0
    page = 100
    while True:
        data = _request(
            "release-group",
            {"artist": artist_mbid, "type": type_filter, "limit": page, "offset": offset},
        )
        batch = data.get("release-groups", [])
        for g in batch:
            groups.append(
                {
                    "id": g.get("id"),
                    "title": g.get("title") or "",
                    "norm_title": normalize_title(g.get("title") or ""),
                    "primary_type": (g.get("primary-type") or "").lower(),
                    "first_release_date": g.get("first-release-date") or "",
                }
            )
        total = data.get("release-group-count", len(batch))
        offset += page
        if offset >= total or not batch:
            break
    return groups


def get_release_group_barcodes(release_group_mbid: str) -> tuple[set[str], str | None]:
    """Return (set of barcodes, first release mbid) for a release-group's releases."""
    if not release_group_mbid:
        return set(), None
    data = _request("release", {"release-group": release_group_mbid, "limit": 100, "inc": ""})
    barcodes: set[str] = set()
    first_release_mbid: str | None = None
    for rel in data.get("releases", []):
        if first_release_mbid is None:
            first_release_mbid = rel.get("id")
        bc = rel.get("barcode")
        if bc:
            barcodes.add(bc.strip())
    return barcodes, first_release_mbid


def lookup_barcode(upc: str) -> list[dict]:
    """Find MusicBrainz releases carrying a given barcode (UPC)."""
    if not upc:
        return []
    data = _request("release", {"query": f"barcode:{upc}", "limit": 5})
    return data.get("releases", [])


# ---------------------------------------------------------------------------
# Title matching
# ---------------------------------------------------------------------------

_PAREN_RE = re.compile(r"[\(\[\{].*?[\)\]\}]")
_NONALNUM_RE = re.compile(r"[^a-z0-9一-鿿]+")
# Common edition/qualifier suffixes to strip before comparing titles.
_SUFFIX_RE = re.compile(
    r"\b(deluxe|edition|version|remaster(ed)?|expanded|bonus|explicit|clean|"
    r"single|ep|e\.p\.|feat\.?|special)\b.*$",
    re.IGNORECASE,
)


def normalize_title(title: str) -> str:
    """Loosely normalise an album/release-group title for fuzzy equality.

    Lowercases, strips bracketed qualifiers and common edition suffixes, drops
    punctuation, and collapses whitespace. Keeps CJK characters intact so that
    non-Latin titles still compare meaningfully.
    """
    if not title:
        return ""
    t = title.lower().strip()
    t = _PAREN_RE.sub(" ", t)
    t = _SUFFIX_RE.sub(" ", t)
    t = _NONALNUM_RE.sub(" ", t)
    return " ".join(t.split())
