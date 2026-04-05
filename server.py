"""AM Discovery Web Server
Flask app creation, background polling scheduler, and CLI entry point.
Run: uv run python server.py
"""

import concurrent.futures
import logging
import os
import threading
import time

from flasgger import Swagger
from flask import Flask

import db
from api import api_bp
from api_watchlist import watchlist_bp
from client import AppleMusicClient
from config import CONFIG_PATH, load_config, save_config  # noqa: F401

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
swagger = Swagger(app)

app.register_blueprint(api_bp)
app.register_blueprint(watchlist_bp)

# ---------------------------------------------------------------------------
# Polling logic
# ---------------------------------------------------------------------------

_scheduler_lock = threading.Lock()
_next_run_at: float = 0.0
_poll_timer: threading.Timer | None = None
_is_running = False
_last_room_errors: list[str] = []


def _do_poll():
    global _next_run_at, _is_running, _last_room_errors
    _is_running = True
    try:
        cfg = load_config()
        storefronts = cfg.get("check_storefronts", [])
        client = AppleMusicClient()

        # 1. Discover new releases from each storefront's /new page
        all_releases: dict[str, dict] = {}
        room_errors = []
        for sf in storefronts:
            room_url = client.discover_room_url(sf)
            if not room_url:
                room_errors.append(sf)
                rels = []
            else:
                rels = client.get_room_new_releases(room_url, sf)
            logger.info("[Poll] [%s] %d releases", sf.upper(), len(rels))
            for r in rels:
                aid = r["storeAdamID"]
                if aid in all_releases:
                    if sf not in all_releases[aid]["storefronts"]:
                        all_releases[aid]["storefronts"].append(sf)
                else:
                    all_releases[aid] = r
        _last_room_errors = room_errors

        # 2. Separate new (need full info fetch) vs known (skip fetch)
        new_ids = []
        known_ids = []
        for aid in all_releases:
            row = db.get_album(aid)
            if row and row.get("info_fetched"):
                known_ids.append(aid)
            else:
                new_ids.append(aid)

        logger.info("[Poll] %d new, %d already cached", len(new_ids), len(known_ids))

        home_sf = cfg.get("home_storefront", "us")

        # 3. Fetch full info only for new albums (concurrent)
        def fetch_full(aid):
            r = all_releases[aid]
            info = client.get_album_full_info(r["url"])
            merged = {
                "store_adam_id": aid,
                "title": r.get("title"),
                "artist": r.get("artist"),
                "url": r.get("url"),
                "storefronts": r.get("storefronts", []),
                "release_date": info.get("release_date"),
                "artwork_url": info.get("artwork_url"),
                "track_count": info.get("track_count"),
                "genre": info.get("genre"),
                "description": info.get("description"),
                "artist_id": info.get("artist_id"),
                "artist_url": info.get("artist_url"),
                "artists_json": info.get("artists"),
                "audio_formats": info.get("audio_formats"),
                "info_fetched": 1,
                "source": "discovered",
            }
            db.upsert_album(merged)
            artist_id = info.get("artist_id")
            if artist_id and not db.get_artist_info(artist_id).get("born_or_formed"):
                artist_info = client.get_artist_info_only(artist_id, home_sf)
                if artist_info:
                    db.upsert_artist(
                        artist_id,
                        name=artist_info.get("name"),
                        artwork_url=artist_info.get("artwork_url"),
                        genre=artist_info.get("genre"),
                        born_or_formed=artist_info.get("born_or_formed"),
                        origin=artist_info.get("origin"),
                        artist_bio=artist_info.get("artist_bio"),
                        is_group=artist_info.get("is_group"),
                    )

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            list(ex.map(fetch_full, new_ids))

        # 4. For known albums, just update storefronts / last_seen
        for aid in known_ids:
            r = all_releases[aid]
            db.upsert_album(
                {
                    "store_adam_id": aid,
                    "title": r.get("title"),
                    "artist": r.get("artist"),
                    "url": r.get("url"),
                    "storefronts": r.get("storefronts", []),
                    "info_fetched": 1,
                    "source": "discovered",
                },
            )

        total = db.list_albums()[1]
        db.log_discovery_run(len(new_ids), total)
        logger.info("[Poll] Done. DB total: %d", total)

        # 5. Check if any discovered albums trigger a new_release status for watched artists
        watched_ids = db.get_watched_artist_ids()
        discovered_artist_ids = {all_releases[aid].get("artist_id") or "" for aid in all_releases}
        # Also include artist_id from full info fetches (stored in DB)
        for aid in new_ids:
            album = db.get_album(aid)
            if album and album.get("artist_id"):
                discovered_artist_ids.add(album["artist_id"])
        for artist_id in discovered_artist_ids & watched_ids:
            if db.check_and_update_new_releases(artist_id):
                logger.info("[Poll] Artist %s has new releases since collection was marked complete", artist_id)

    except Exception as e:
        logger.error("[Poll] Error: %s", e)
    finally:
        _is_running = False
        _schedule_next()


def _schedule_next(override_delay=None):
    global _next_run_at, _poll_timer
    cfg = load_config()
    interval_sec = cfg.get("newrelease_poll_interval_days", 1) * 86400
    delay = override_delay if override_delay is not None else interval_sec
    _next_run_at = time.time() + delay
    with _scheduler_lock:
        if _poll_timer:
            _poll_timer.cancel()
        _poll_timer = threading.Timer(delay, _do_poll)
        _poll_timer.daemon = True
        _poll_timer.start()
    logger.info("[Scheduler] Next poll in %.1f minutes", delay / 60)


def trigger_poll_now():
    """Cancel any pending timer and run immediately in a thread."""
    global _poll_timer
    with _scheduler_lock:
        if _poll_timer:
            _poll_timer.cancel()
            _poll_timer = None
    t = threading.Thread(target=_do_poll, daemon=True)
    t.start()


# ---------------------------------------------------------------------------
# Watchlist polling logic
# ---------------------------------------------------------------------------

_watchlist_lock = threading.Lock()
_watchlist_timer: threading.Timer | None = None
_watchlist_running = False


def _do_watchlist_poll():
    global _watchlist_running
    _watchlist_running = True
    try:
        cfg = load_config()
        batch_size = cfg.get("watchlist_poll_batch_size", 5)
        refresh_days = cfg.get("watchlist_refresh_interval_days", 7)
        home_sf = cfg.get("home_storefront", "my")

        artists = db.get_artists_needing_refresh(batch_size, refresh_days)
        if not artists:
            logger.info("[WatchlistPoll] No artists need refreshing")
            return

        logger.info("[WatchlistPoll] Refreshing %d artists", len(artists))
        client = AppleMusicClient()

        for artist in artists:
            artist_id = artist["artist_id"]
            storefront = artist.get("preferred_source") or home_sf
            artist_url = f"https://music.apple.com/{storefront}/artist/{artist_id}"

            try:
                releases, artist_info = client.get_artist_all_releases(artist_url, storefront)
                db.upsert_artist(
                    artist_id,
                    name=artist_info.get("name"),
                    artwork_url=artist_info.get("artwork_url"),
                    genre=artist_info.get("genre"),
                    born_or_formed=artist_info.get("born_or_formed"),
                    origin=artist_info.get("origin"),
                    artist_bio=artist_info.get("artist_bio"),
                    is_group=artist_info.get("is_group"),
                )

                def fetch_one(r, storefront=storefront, artist_id=artist_id):
                    aid = r["storeAdamID"]
                    existing = db.get_album(aid)
                    album_url = f"https://music.apple.com/{storefront}/album/{aid}"
                    info = client.get_album_full_info(album_url)
                    album_data = {
                        "store_adam_id": aid,
                        "url": r.get("url") or album_url,
                        "storefronts": r.get("storefronts", [storefront]),
                        "release_date": info.get("release_date"),
                        "artwork_url": info.get("artwork_url"),
                        "track_count": info.get("track_count"),
                        "genre": info.get("genre"),
                        "description": info.get("description"),
                        "artist_id": info.get("artist_id") or artist_id,
                        "artist_url": info.get("artist_url"),
                        "artists_json": info.get("artists"),
                        "audio_formats": info.get("audio_formats"),
                        "release_type": r.get("release_type"),
                        "info_fetched": 1,
                        "source": "artist_fetch",
                    }
                    if not existing:
                        album_data["title"] = r.get("title") or info.get("title") or "Unknown"
                        album_data["artist"] = r.get("artist") or info.get("artist")
                    db.upsert_album(album_data)

                with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
                    list(ex.map(fetch_one, releases))

                db.mark_artist_refreshed(artist_id)
                if db.check_and_update_new_releases(artist_id):
                    logger.info(
                        "[WatchlistPoll] %s has new releases since collection was marked complete",
                        artist.get("name"),
                    )
                logger.info("[WatchlistPoll] Refreshed %s (%d releases)", artist.get("name"), len(releases))

            except Exception as e:
                logger.error("[WatchlistPoll] Error refreshing %s: %s", artist.get("name"), e)

    except Exception as e:
        logger.error("[WatchlistPoll] Error: %s", e)
    finally:
        _watchlist_running = False
        _schedule_watchlist_next()


def _schedule_watchlist_next(override_delay=None):
    global _watchlist_timer
    cfg = load_config()
    interval_sec = cfg.get("watchlist_poll_interval_minutes", 10) * 60
    delay = override_delay if override_delay is not None else interval_sec
    with _watchlist_lock:
        if _watchlist_timer:
            _watchlist_timer.cancel()
        _watchlist_timer = threading.Timer(delay, _do_watchlist_poll)
        _watchlist_timer.daemon = True
        _watchlist_timer.start()
    logger.info("[WatchlistScheduler] Next watchlist poll in %.1f minutes", delay / 60)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def init_scheduler():
    """Initialise the database and start background polling timers.

    Called by both main() and the gunicorn WSGI entry point (wsgi.py).
    """
    db.init_db()

    cfg = load_config()
    interval_sec = cfg.get("newrelease_poll_interval_days", 1) * 86400

    last_run = db.get_last_run()
    should_poll_now = True
    delay = interval_sec

    if last_run and last_run.get("ran_at"):
        elapsed = time.time() - last_run["ran_at"]
        if elapsed < interval_sec:
            should_poll_now = False
            delay = interval_sec - elapsed

    if should_poll_now:
        logger.info("Starting initial poll...")
        trigger_poll_now()
    else:
        logger.info("Last poll was recent, scheduling next poll in %.1f minutes...", delay / 60)
        _schedule_next(override_delay=delay)

    watchlist_interval = cfg.get("watchlist_poll_interval_minutes", 10) * 60
    logger.info("Starting watchlist polling (every %.1f minutes)...", watchlist_interval / 60)
    _schedule_watchlist_next()


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="Enable debug logging and Flask debug mode")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logger.info("Initialising database...")
    init_scheduler()

    port = int(os.environ.get("PORT", 5000))
    logger.info("Serving on http://localhost:%d", port)
    app.run(host="0.0.0.0", port=port, debug=args.debug, use_reloader=args.debug)


if __name__ == "__main__":
    main()
