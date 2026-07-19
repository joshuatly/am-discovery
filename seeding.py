"""Background MusicBrainz seeding scanner.

Two responsibilities, run on a timer:

1. **Suggest artist MBIDs** — for watchlist artists that have no MusicBrainz id,
   search MusicBrainz by name and queue the best candidates for the user to
   approve in the admin UI. Nothing is auto-linked.
2. **Find un-seeded releases** — for artists that already have an MBID, compare
   the artist's local (Apple Music) catalogue against their MusicBrainz
   release-groups. An album whose release-group is absent — or whose specific
   edition (barcode) is missing from an existing group — is flagged as needing
   seeding.

The scanner works in small batches, leans entirely on data already in the DB
(never re-querying Apple Music), and skips albums already confirmed present in
MusicBrainz. Each artist is scanned at most once per ``mb_artist_recheck_days``.
All MusicBrainz traffic goes through :mod:`musicbrainz`, which enforces the
~1 req/sec rate limit and backs off on 503; a persistent rate-limit aborts the
cycle cleanly and reschedules sooner.
"""

import logging
import threading
import time

import db
import musicbrainz as mb
from config import load_config

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_timer: threading.Timer | None = None
_running = False
# When MusicBrainz rate-limits us mid-cycle, retry sooner than a full interval.
RATE_LIMIT_RETRY_SEC = 900


# ---------------------------------------------------------------------------
# Per-artist scan units (pure-ish; write to DB only)
# ---------------------------------------------------------------------------


def suggest_mbid_for_artist(artist: dict) -> int:
    """Look up an artist on MusicBrainz and queue a suggestion for approval.

    Returns the number of candidates found. The artist is always marked checked
    (even when nothing matched) so it isn't retried within the recheck window.
    """
    artist_id = artist["artist_id"]
    name = artist.get("name") or artist.get("alt_name") or ""
    candidates = mb.search_artist(name, limit=5)
    if candidates:
        top = candidates[0]
        db.upsert_mbid_suggestion(
            artist_id,
            suggested_mbid=top.get("id"),
            suggested_name=top.get("name"),
            score=top.get("score"),
            candidates=candidates,
            status="pending",
        )
        logger.info("[Seeding] Suggested MBID for %s -> %s (score %s)", name, top.get("id"), top.get("score"))
    else:
        logger.info("[Seeding] No MusicBrainz artist match for %s", name)
    db.mark_mbid_checked(artist_id)
    return len(candidates)


def _global_confirm_release(title: str, artist_name: str, upc: str) -> str | None:
    """Authoritative "is this release on MusicBrainz?" check across all of MB.

    Mirrors the on-demand album-card lookup — barcode first (most precise), then
    a fuzzy title+artist search — and is independent of which artist the release
    is credited to. Returns a matching MB release MBID, or None if nothing found.
    """
    if upc:
        rels = mb.lookup_barcode(upc)
        if rels:
            return rels[0].get("id")
    rels = mb.search_release(title, artist_name)
    if rels:
        return rels[0].get("id")
    return None


def scan_releases_for_artist(artist: dict) -> int:
    """Compare an artist's local catalogue against MusicBrainz; flag un-seeded albums.

    A cheap artist-scoped release-group match handles the common "clearly
    present" case without extra queries. Anything it can't confirm falls through
    to a global barcode/title check (the same one the album card uses) before an
    album is flagged — so releases credited to a different artist entity, typed
    outside album/EP, or titled slightly differently aren't wrongly flagged.

    Returns the number of albums newly flagged as needing seeding.
    """
    artist_id = artist["artist_id"]
    mbid = artist.get("musicbrainz_id")
    groups = mb.browse_release_groups(mbid)

    # Index release-groups by normalised title (several groups may share a title).
    by_title: dict[str, list[dict]] = {}
    for g in groups:
        by_title.setdefault(g["norm_title"], []).append(g)

    albums = db.get_artist_albums(artist_id)
    barcode_cache: dict[str, tuple[set[str], str | None]] = {}
    flagged = 0

    for album in albums:
        title = album.get("title") or ""
        # Singles are out of scope — by release_type, and by Apple Music's
        # "<Track> - Single" title convention (the type field is sometimes absent).
        if (album.get("release_type") or "").lower() == "single":
            continue
        if " - single" in title.lower():
            continue
        # Skip albums already confirmed present in MusicBrainz.
        if album.get("mb_seed_status") == "known":
            continue

        upc = (album.get("upc") or "").strip()
        matches = by_title.get(mb.normalize_title(title), [])

        # Fast path: the linked artist's own release-groups confirm presence.
        known_mbid: str | None = None
        present = False
        if matches:
            if not upc:
                present, known_mbid = True, matches[0].get("id")
            else:
                all_barcodes: set[str] = set()
                for g in matches:
                    rg_id = g["id"]
                    if rg_id not in barcode_cache:
                        barcode_cache[rg_id] = mb.get_release_group_barcodes(rg_id)
                    bcs, rel_mbid = barcode_cache[rg_id]
                    all_barcodes |= bcs
                    known_mbid = known_mbid or rel_mbid
                present = upc in all_barcodes

        # Authoritative fallback before flagging — matches the album-card check.
        if not present:
            confirmed = _global_confirm_release(title, album.get("artist") or "", upc)
            if confirmed:
                present, known_mbid = True, confirmed

        if present:
            db.set_album_seed_status(album["store_adam_id"], "known", known_mbid)
        else:
            db.set_album_seed_status(album["store_adam_id"], "needs_seeding")
            flagged += 1

    db.mark_release_checked(artist_id)
    logger.info("[Seeding] Scanned releases for %s: %d flagged", artist.get("name") or artist_id, flagged)
    return flagged


# ---------------------------------------------------------------------------
# Cycle
# ---------------------------------------------------------------------------


def run_seeding_cycle(force: bool = False) -> dict:
    """Run one scan cycle: a batch of MBID suggestions, then a batch of release scans.

    When ``force`` is set the per-artist recheck window is ignored, so a manual
    scan re-verifies artists that were checked recently (used to clear stale
    flags after a matching-logic change). Returns a summary dict. Raises
    :class:`musicbrainz.MusicBrainzRateLimitError` if MusicBrainz stays
    unavailable — the caller reschedules sooner in that case.
    """
    cfg = load_config()
    artist_batch = cfg.get("mb_scan_artist_batch", 3)
    recheck_days = 0 if force else cfg.get("mb_artist_recheck_days", 7)

    summary = {"mbid_suggested": 0, "releases_scanned": 0, "flagged": 0}

    for artist in db.get_artists_for_mbid_scan(artist_batch, recheck_days):
        suggest_mbid_for_artist(artist)
        summary["mbid_suggested"] += 1

    for artist in db.get_artists_for_release_scan(artist_batch, recheck_days):
        summary["flagged"] += scan_releases_for_artist(artist)
        summary["releases_scanned"] += 1

    return summary


def _do_scan(force: bool = False):
    global _running
    _running = True
    override_delay = None
    try:
        summary = run_seeding_cycle(force=force)
        logger.info(
            "[Seeding] Cycle done: %d MBID suggestions, %d artists scanned, %d releases flagged",
            summary["mbid_suggested"],
            summary["releases_scanned"],
            summary["flagged"],
        )
    except mb.MusicBrainzRateLimitError:
        logger.warning("[Seeding] MusicBrainz rate-limited; rescheduling sooner")
        override_delay = RATE_LIMIT_RETRY_SEC
    except Exception as e:  # noqa: BLE001
        logger.error("[Seeding] Cycle error: %s", e)
    finally:
        _running = False
        _schedule_next(override_delay=override_delay)


def _schedule_next(override_delay=None):
    global _timer
    cfg = load_config()
    if not cfg.get("mb_scan_enabled", True):
        logger.info("[Seeding] Scanner disabled; not scheduling")
        return
    interval_sec = cfg.get("mb_scan_interval_minutes", 60) * 60
    delay = override_delay if override_delay is not None else interval_sec
    with _lock:
        if _timer:
            _timer.cancel()
        _timer = threading.Timer(delay, _do_scan)
        _timer.daemon = True
        _timer.start()
    logger.info("[Seeding] Next scan in %.1f minutes", delay / 60)


def trigger_scan_now(force: bool = False):
    """Cancel any pending timer and run one cycle immediately in a thread.

    ``force`` ignores the per-artist weekly recheck window so a manual scan
    re-verifies recently-checked artists.
    """
    global _timer
    with _lock:
        if _timer:
            _timer.cancel()
            _timer = None
    threading.Thread(target=_do_scan, kwargs={"force": force}, daemon=True).start()


# ---------------------------------------------------------------------------
# On-demand bulk MBID search
# ---------------------------------------------------------------------------

_bulk_lock = threading.Lock()
_bulk_state = {
    "running": False,
    "total": 0,
    "done": 0,
    "found": 0,
    "rate_limited": False,
    "started_at": None,
    "finished_at": None,
}


def _bulk_worker():
    global _bulk_state
    try:
        artists = db.get_unlinked_artists_without_suggestion()
        with _bulk_lock:
            _bulk_state.update(total=len(artists), done=0, found=0)
        for artist in artists:
            try:
                found = suggest_mbid_for_artist(artist)
            except mb.MusicBrainzRateLimitError:
                logger.warning("[Seeding] Bulk search hit MusicBrainz rate limit; stopping early")
                with _bulk_lock:
                    _bulk_state["rate_limited"] = True
                break
            with _bulk_lock:
                _bulk_state["done"] += 1
                if found:
                    _bulk_state["found"] += 1
        logger.info("[Seeding] Bulk MBID search done: %d/%d processed", _bulk_state["done"], _bulk_state["total"])
    except Exception as e:  # noqa: BLE001
        logger.error("[Seeding] Bulk search error: %s", e)
    finally:
        with _bulk_lock:
            _bulk_state["running"] = False
            _bulk_state["finished_at"] = time.time()


def trigger_bulk_mbid_search() -> dict:
    """Start a background bulk MBID search over all un-suggested artists.

    Idempotent while running — a second call just returns the live progress
    snapshot instead of starting a competing search.
    """
    with _bulk_lock:
        if _bulk_state["running"]:
            return dict(_bulk_state)
        _bulk_state.update(
            running=True,
            total=0,
            done=0,
            found=0,
            rate_limited=False,
            started_at=time.time(),
            finished_at=None,
        )
        snapshot = dict(_bulk_state)
    threading.Thread(target=_bulk_worker, daemon=True).start()
    return snapshot


def bulk_mbid_search_status() -> dict:
    with _bulk_lock:
        return dict(_bulk_state)


def init_scheduler():
    """Start the seeding scanner timer (idempotent-ish; called from server startup)."""
    cfg = load_config()
    if not cfg.get("mb_scan_enabled", True):
        logger.info("[Seeding] Scanner disabled in config")
        return
    interval_min = cfg.get("mb_scan_interval_minutes", 60)
    logger.info("[Seeding] Starting MusicBrainz seeding scanner (every %d minutes)", interval_min)
    # First cycle after a short delay so startup polling isn't competing for the
    # MusicBrainz rate budget the instant the server boots.
    _schedule_next(override_delay=min(interval_min * 60, 120))


def is_running() -> bool:
    return _running


def status() -> dict:
    """Lightweight status for the admin page."""
    cfg = load_config()
    recheck_days = cfg.get("mb_artist_recheck_days", 7)
    return {
        "enabled": cfg.get("mb_scan_enabled", True),
        "running": _running,
        "interval_minutes": cfg.get("mb_scan_interval_minutes", 60),
        "artist_batch": cfg.get("mb_scan_artist_batch", 3),
        "recheck_days": recheck_days,
        "pending_mbid_scan": db.count_artists_pending_mbid_scan(recheck_days),
        "seeding_release_count": db.count_seeding_releases(),
    }
