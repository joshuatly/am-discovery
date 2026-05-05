"""SQLite database layer for AM Discovery."""

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import UTC, datetime

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("AM_DB_PATH", os.path.join(_BASE_DIR, "am_discovery.db"))


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA_VERSION = 17

# Valid collection_status values and allowed transitions
COLLECTION_STATUSES = {"new", "complete", "new_release", "in_progress"}
COLLECTION_TRANSITIONS = {
    "new": {"complete", "in_progress"},
    "complete": {"new_release", "in_progress"},
    "new_release": {"complete", "in_progress"},
    "in_progress": {"complete"},
}


def init_db():
    with get_conn() as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]

        if version == 0:
            # Check whether this is a fresh DB or a pre-versioning DB
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if tables:
                raise RuntimeError(
                    "Database exists but has no version stamp (pre-versioning schema). Run:  uv run migrate.py",
                )
            # Fresh install — create at current version
            conn.executescript(f"""
                CREATE TABLE IF NOT EXISTS albums (
                    store_adam_id  TEXT PRIMARY KEY,
                    title          TEXT NOT NULL,
                    artist         TEXT,
                    artist_id      TEXT,
                    artist_url     TEXT,
                    artists_json   TEXT,
                    url            TEXT,
                    storefronts    TEXT DEFAULT '[]',
                    release_date   TEXT,
                    artwork_url    TEXT,
                    track_count    INTEGER,
                    music_video_count INTEGER DEFAULT 0,
                    genre          TEXT,
                    description    TEXT,
                    info_fetched   INTEGER DEFAULT 0,
                    audio_formats  TEXT,
                    release_type   TEXT,
                    first_seen     INTEGER,
                    last_seen      INTEGER,
                    source         TEXT,
                    upc            TEXT
                );

                CREATE TABLE IF NOT EXISTS watched_artists (
                    artist_id                    TEXT PRIMARY KEY,
                    name                         TEXT NOT NULL,
                    url                          TEXT,
                    added_at                     INTEGER,
                    preferred_source             TEXT,
                    last_refreshed               INTEGER,
                    collection_status            TEXT DEFAULT 'new',
                    collection_status_updated_at INTEGER,
                    alt_name                     TEXT
                );

                CREATE TABLE IF NOT EXISTS artists (
                    artist_id      TEXT PRIMARY KEY,
                    name           TEXT,
                    artwork_url    TEXT,
                    genre          TEXT,
                    born_or_formed TEXT,
                    origin         TEXT,
                    artist_bio     TEXT,
                    is_group       INTEGER,
                    updated_at     INTEGER,
                    musicbrainz_id TEXT
                );

                CREATE TABLE IF NOT EXISTS discovery_runs (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    ran_at              INTEGER,
                    storefront          TEXT,
                    room_id             TEXT,
                    room_last_modified  TEXT,
                    new_count           INTEGER DEFAULT 0,
                    total_count         INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS watchlist_runs (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    ran_at            INTEGER,
                    batch_size        INTEGER DEFAULT 0,
                    refreshed_count   INTEGER DEFAULT 0,
                    error_count       INTEGER DEFAULT 0,
                    refreshed_artists TEXT,
                    failed_artists    TEXT,
                    pending_count     INTEGER DEFAULT 0,
                    next_run_at       INTEGER
                );

                PRAGMA user_version = {SCHEMA_VERSION};
            """)

        elif version != SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema version {version} does not match expected {SCHEMA_VERSION}. Run:  uv run migrate.py",
            )


def get_album(store_adam_id: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM albums WHERE store_adam_id = ?", (store_adam_id,)).fetchone()
        return dict(row) if row else None


def upsert_album(data: dict):
    """Insert or update an album row."""
    now = int(time.time())
    new_sf = data.get("storefronts", [])
    audio_formats = json.dumps(data["audio_formats"]) if data.get("audio_formats") is not None else None
    artists_json = json.dumps(data["artists_json"]) if data.get("artists_json") is not None else None
    with get_conn() as conn:
        # INSERT OR IGNORE ensures concurrent inserts for the same store_adam_id
        # (from polling multiple storefronts) don't raise a UNIQUE constraint error.
        conn.execute(
            """INSERT OR IGNORE INTO albums
                (store_adam_id, title, storefronts, first_seen, last_seen, source)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                data["store_adam_id"],
                data.get("title", ""),
                json.dumps(new_sf),
                now,
                now,
                data.get("source"),
            ),
        )
        # Fetch current storefronts to merge
        existing = conn.execute(
            "SELECT storefronts FROM albums WHERE store_adam_id = ?",
            (data["store_adam_id"],),
        ).fetchone()
        old_sf = json.loads(existing["storefronts"])
        merged = list(dict.fromkeys(old_sf + new_sf))
        conn.execute(
            """UPDATE albums SET
                title=coalesce(?, title),
                artist=coalesce(?, artist),
                artist_id=coalesce(?, artist_id),
                artist_url=coalesce(?, artist_url),
                artists_json=coalesce(?, artists_json),
                url=coalesce(?, url),
                storefronts=?,
                release_date=coalesce(?, release_date),
                artwork_url=coalesce(?, artwork_url),
                track_count=coalesce(?, track_count),
                music_video_count=coalesce(?, music_video_count),
                genre=coalesce(?, genre),
                description=coalesce(?, description),
                info_fetched=max(info_fetched, ?),
                audio_formats=coalesce(?, audio_formats),
                release_type=coalesce(?, release_type),
                source=CASE WHEN ? = 'discovered' THEN 'discovered' ELSE source END,
                upc=coalesce(?, upc),
                last_seen=?
            WHERE store_adam_id=?""",
            (
                data.get("title"),
                data.get("artist"),
                data.get("artist_id"),
                data.get("artist_url"),
                artists_json,
                data.get("url"),
                json.dumps(merged),
                data.get("release_date"),
                data.get("artwork_url"),
                data.get("track_count"),
                data.get("music_video_count"),
                data.get("genre"),
                data.get("description"),
                1 if data.get("info_fetched") else 0,
                audio_formats,
                data.get("release_type"),
                data.get("source"),
                data.get("upc"),
                now,
                data["store_adam_id"],
            ),
        )


ALBUM_SORT_OPTIONS = {"release_date", "first_seen"}


def list_albums(
    page: int = 1,
    per_page: int = 50,
    storefront: str = "",
    discovered_only: bool = False,
    watched_only: bool = False,
    release_type: str = "",
    sort: str = "release_date",
):
    if sort not in ALBUM_SORT_OPTIONS:
        sort = "release_date"
    order_by = "release_date DESC, first_seen DESC" if sort == "release_date" else "first_seen DESC, release_date DESC"
    offset = (page - 1) * per_page
    with get_conn() as conn:
        conditions = []
        params: list = []
        if storefront:
            conditions.append("storefronts LIKE ?")
            params.append(f'%"{storefront.lower()}"%')
        if discovered_only:
            conditions.append("source = 'discovered'")
        if watched_only:
            conditions.append(
                "(artist_id IN (SELECT artist_id FROM watched_artists)"
                " OR EXISTS (SELECT 1 FROM json_each(albums.artists_json)"
                "  WHERE json_extract(value, '$.id') IN (SELECT artist_id FROM watched_artists)))"
            )
        if release_type:
            conditions.append("release_type = ?")
            params.append(release_type)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        total = conn.execute(f"SELECT COUNT(*) FROM albums {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM albums {where} ORDER BY {order_by} LIMIT ? OFFSET ?",
            params + [per_page, offset],
        ).fetchall()
        return [dict(r) for r in rows], total


def get_artist_albums(artist_id: str):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT albums.* FROM albums
            WHERE artist_id = ?
               OR EXISTS (
                   SELECT 1 FROM json_each(albums.artists_json)
                   WHERE json_extract(value, '$.id') = ?
               )
            ORDER BY release_date DESC
            """,
            (artist_id, artist_id),
        ).fetchall()
        return [dict(r) for r in rows]


WATCHLIST_SORT_OPTIONS = {"name", "added", "recent_release", "recent_album"}


def get_watchlist_ids() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT artist_id FROM watched_artists").fetchall()
        return [r["artist_id"] for r in rows]


def get_watchlist(preferred_source: str = "", collection_status: str = "", sort: str = "name"):
    if sort not in WATCHLIST_SORT_OPTIONS:
        sort = "name"
    order_by = {
        "name": "LOWER(COALESCE(NULLIF(TRIM(w.alt_name), ''), w.name))",
        "added": "w.added_at DESC",
        "recent_release": "latest_release_date DESC NULLS LAST, LOWER(COALESCE(NULLIF(TRIM(w.alt_name), ''), w.name))",
        "recent_album": "latest_album_date DESC NULLS LAST, LOWER(COALESCE(NULLIF(TRIM(w.alt_name), ''), w.name))",
    }[sort]
    with get_conn() as conn:
        conditions = []
        params: list = []
        if preferred_source:
            conditions.append("w.preferred_source = ?")
            params.append(preferred_source.lower())
        if collection_status:
            conditions.append("w.collection_status = ?")
            params.append(collection_status)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        rows = conn.execute(
            f"""SELECT w.*, ar.artwork_url, ar.genre, ar.artist_bio,
                      MAX(alb.release_date) AS latest_release_date,
                      MAX(CASE WHEN alb.title NOT LIKE '% - Single' THEN alb.release_date END) AS latest_album_date
               FROM watched_artists w
               LEFT JOIN artists ar ON w.artist_id = ar.artist_id
               LEFT JOIN albums alb ON w.artist_id = alb.artist_id
               {where}
               GROUP BY w.artist_id
               ORDER BY {order_by}""",
            params,
        ).fetchall()
        return [dict(r) for r in rows]


def add_to_watchlist(artist_id: str, name: str, url: str = None, preferred_source: str = None):
    now = int(time.time())
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO watched_artists
                   (artist_id, name, url, added_at, preferred_source,
                    collection_status, collection_status_updated_at)
               VALUES (?,?,?,?,?, 'new', ?)
               ON CONFLICT(artist_id) DO UPDATE SET
                   name=excluded.name,
                   url=excluded.url,
                   preferred_source=coalesce(excluded.preferred_source, preferred_source)""",
            (artist_id, name, url, now, preferred_source, now),
        )


def remove_from_watchlist(artist_id: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM watched_artists WHERE artist_id = ?", (artist_id,))


def upsert_artist(
    artist_id: str,
    name: str = None,
    artwork_url: str = None,
    genre: str = None,
    born_or_formed: str = None,
    origin: str = None,
    artist_bio: str = None,
    is_group: bool = None,
    musicbrainz_id: str = None,
):
    now = int(time.time())
    is_group_int = int(is_group) if is_group is not None else None
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO artists
               (artist_id, name, artwork_url, genre, born_or_formed, origin,
                artist_bio, is_group, updated_at, musicbrainz_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(artist_id) DO UPDATE SET
                   name           = coalesce(excluded.name, name),
                   artwork_url    = coalesce(excluded.artwork_url, artwork_url),
                   genre          = coalesce(excluded.genre, genre),
                   born_or_formed = coalesce(excluded.born_or_formed, born_or_formed),
                   origin         = coalesce(excluded.origin, origin),
                   artist_bio     = coalesce(excluded.artist_bio, artist_bio),
                   is_group       = coalesce(excluded.is_group, is_group),
                   musicbrainz_id = coalesce(excluded.musicbrainz_id, musicbrainz_id),
                   updated_at     = excluded.updated_at""",
            (
                artist_id,
                name,
                artwork_url,
                genre,
                born_or_formed,
                origin,
                artist_bio,
                is_group_int,
                now,
                musicbrainz_id,
            ),
        )


def get_artist_artwork(artist_id: str):
    with get_conn() as conn:
        row = conn.execute("SELECT artwork_url FROM artists WHERE artist_id = ?", (artist_id,)).fetchone()
        return row["artwork_url"] if row else None


def get_artist_info(artist_id: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT name, artwork_url, genre, born_or_formed, origin, artist_bio, is_group, musicbrainz_id"
            " FROM artists WHERE artist_id = ?",
            (artist_id,),
        ).fetchone()
        return dict(row) if row else {}


def update_artist_musicbrainz_id(artist_id: str, musicbrainz_id: str | None):
    with get_conn() as conn:
        conn.execute("UPDATE artists SET musicbrainz_id = ? WHERE artist_id = ?", (musicbrainz_id, artist_id))


def get_watched_artist_ids() -> set:
    with get_conn() as conn:
        rows = conn.execute("SELECT artist_id FROM watched_artists").fetchall()
        return {r["artist_id"] for r in rows}


def get_artists_needing_refresh(batch_size: int = 5, refresh_interval_days: int = 7) -> list:
    """Return up to batch_size watched artists that haven't been refreshed within refresh_interval_days."""
    cutoff = int(time.time()) - (refresh_interval_days * 86400)
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM watched_artists
               WHERE last_refreshed IS NULL OR last_refreshed < ?
               ORDER BY last_refreshed ASC NULLS FIRST
               LIMIT ?""",
            (cutoff, batch_size),
        ).fetchall()
        return [dict(r) for r in rows]


def count_artists_needing_refresh(refresh_interval_days: int = 7) -> int:
    """Return total count of watched artists that need refreshing."""
    cutoff = int(time.time()) - (refresh_interval_days * 86400)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM watched_artists WHERE last_refreshed IS NULL OR last_refreshed < ?",
            (cutoff,),
        ).fetchone()
        return row[0] if row else 0


def update_preferred_source(artist_id: str, preferred_source):
    """Set (or clear) the preferred metadata source for a watched artist."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE watched_artists SET preferred_source = ? WHERE artist_id = ?",
            (preferred_source, artist_id),
        )


def update_watchlist_alt_name(artist_id: str, alt_name):
    """Set (or clear) the user-defined alternate name for a watched artist."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE watched_artists SET alt_name = ? WHERE artist_id = ?",
            (alt_name, artist_id),
        )


def mark_artist_refreshed(artist_id: str):
    now = int(time.time())
    with get_conn() as conn:
        conn.execute(
            "UPDATE watched_artists SET last_refreshed = ? WHERE artist_id = ?",
            (now, artist_id),
        )


def update_collection_status(artist_id: str, new_status: str) -> bool:
    """Update the collection status for a watched artist, enforcing valid transitions.

    Returns True if the status was updated, False if the transition is not allowed.
    """
    if new_status not in COLLECTION_STATUSES:
        return False
    now = int(time.time())
    with get_conn() as conn:
        row = conn.execute(
            "SELECT collection_status FROM watched_artists WHERE artist_id = ?",
            (artist_id,),
        ).fetchone()
        if not row:
            return False
        current = row["collection_status"] or "new"
        if new_status not in COLLECTION_TRANSITIONS.get(current, set()):
            return False
        conn.execute(
            "UPDATE watched_artists SET collection_status = ?, collection_status_updated_at = ? WHERE artist_id = ?",
            (new_status, now, artist_id),
        )
        return True


def get_latest_release_date(artist_id: str) -> str | None:
    """Return the latest release_date (ISO string) for an artist, or None."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT MAX(release_date) AS latest FROM albums WHERE artist_id = ? AND release_date IS NOT NULL",
            (artist_id,),
        ).fetchone()
        return row["latest"] if row and row["latest"] else None


def check_and_update_new_releases(artist_id: str) -> str | None:
    """If a release exists newer than the artist's status baseline, fire notifications.

    Fires for every ``collection_status`` (``new``, ``in_progress``, ``complete``,
    ``new_release``). The baseline is ``collection_status_updated_at`` — set
    when the artist was added or last transitioned — and advances every time
    this function fires, so each new album triggers exactly one notification
    batch.

    Status side-effect: only ``complete`` transitions to ``new_release`` (the
    one user-visible state change driven by this function). Other statuses are
    preserved so user-driven curation flows (``in_progress``) and the initial
    ``new`` state are not disturbed.

    Returns the cutoff date string (YYYY-MM-DD) used for the comparison if a
    fire occurred, otherwise None. Callers can pass the returned date to
    :func:`get_new_releases_since` to enumerate the releases that triggered it.
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT collection_status, collection_status_updated_at FROM watched_artists WHERE artist_id = ?",
            (artist_id,),
        ).fetchone()
        if not row:
            return None
        status = row["collection_status"] or "new"
        baseline_at = row["collection_status_updated_at"]
        if not baseline_at:
            return None
        # Convert unix timestamp to ISO date for comparison with release_date strings
        baseline_date = datetime.fromtimestamp(baseline_at, tz=UTC).strftime("%Y-%m-%d")
        latest = conn.execute(
            "SELECT MAX(release_date) AS latest FROM albums WHERE artist_id = ? AND release_date > ?",
            (artist_id, baseline_date),
        ).fetchone()
        if latest and latest["latest"]:
            now = int(time.time())
            new_status = "new_release" if status == "complete" else status
            conn.execute(
                """UPDATE watched_artists SET collection_status = ?,
                   collection_status_updated_at = ? WHERE artist_id = ?""",
                (new_status, now, artist_id),
            )
            return baseline_date
        return None


def get_new_releases_since(artist_id: str, since_date: str) -> list[dict]:
    """Return albums for ``artist_id`` with ``release_date > since_date``, newest first."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM albums
               WHERE artist_id = ? AND release_date > ?
               ORDER BY release_date DESC""",
            (artist_id, since_date),
        ).fetchall()
        return [dict(r) for r in rows]


def get_albums_first_seen_after(since_ts: int, min_release_date: str) -> list[dict]:
    """Return albums whose ``first_seen`` is strictly greater than ``since_ts`` and
    whose ``release_date`` is on or after ``min_release_date``. NULL ``release_date``
    is excluded (no date → can't gate by age). Future release dates are allowed.

    Used by the notification scanner to find newly-inserted albums worth notifying on.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM albums
               WHERE first_seen > ?
                 AND release_date IS NOT NULL
                 AND release_date >= ?
               ORDER BY first_seen ASC""",
            (since_ts, min_release_date),
        ).fetchall()
        return [dict(r) for r in rows]


def export_watchlist() -> list:
    """Export the full watchlist as a list of dicts suitable for JSON serialization."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT artist_id, name, url, preferred_source,
                      collection_status, collection_status_updated_at, alt_name
               FROM watched_artists ORDER BY name""",
        ).fetchall()
        return [dict(r) for r in rows]


def import_watchlist(artists: list):
    """Import a list of artist dicts into the watchlist. Uses upsert semantics."""
    now = int(time.time())
    with get_conn() as conn:
        for a in artists:
            conn.execute(
                """INSERT INTO watched_artists
                       (artist_id, name, url, added_at, preferred_source,
                        collection_status, collection_status_updated_at, alt_name)
                   VALUES (?,?,?,?,?, ?,?,?)
                   ON CONFLICT(artist_id) DO UPDATE SET
                       name=excluded.name,
                       url=excluded.url,
                       preferred_source=coalesce(excluded.preferred_source, preferred_source),
                       collection_status=coalesce(excluded.collection_status, collection_status),
                       collection_status_updated_at=coalesce(
                           excluded.collection_status_updated_at, collection_status_updated_at
                       ),
                       alt_name=coalesce(excluded.alt_name, alt_name)""",
                (
                    a["artist_id"],
                    a["name"],
                    a.get("url"),
                    now,
                    a.get("preferred_source"),
                    a.get("collection_status", "new"),
                    a.get("collection_status_updated_at", now),
                    a.get("alt_name"),
                ),
            )


def log_discovery_run(
    storefront: str,
    room_id: str,
    new_count: int,
    total_count: int,
    room_last_modified: str | None = None,
    ran_at: int | None = None,
):
    when = int(time.time()) if ran_at is None else int(ran_at)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO discovery_runs "
            "(ran_at, storefront, room_id, room_last_modified, new_count, total_count) "
            "VALUES (?,?,?,?,?,?)",
            (when, storefront, room_id, room_last_modified, new_count, total_count),
        )


def get_last_run():
    """Return an aggregated view of the most recent poll.

    A single poll now writes one row per storefront (all sharing the same
    ran_at), so we collapse them back into one logical run with a
    per-storefront breakdown.
    """
    with get_conn() as conn:
        latest = conn.execute("SELECT MAX(ran_at) AS ts FROM discovery_runs").fetchone()
        if not latest or latest["ts"] is None:
            return None
        ran_at = latest["ts"]
        rows = conn.execute(
            "SELECT * FROM discovery_runs WHERE ran_at = ? ORDER BY id ASC",
            (ran_at,),
        ).fetchall()
    if not rows:
        return None
    per_storefront = [
        {
            "storefront": r["storefront"],
            "room_id": r["room_id"],
            "room_last_modified": r["room_last_modified"],
            "new_count": r["new_count"],
        }
        for r in rows
    ]
    return {
        "ran_at": ran_at,
        "new_count": sum(r["new_count"] or 0 for r in rows),
        "total_count": max((r["total_count"] or 0) for r in rows),
        "storefronts": per_storefront,
    }


def get_discovery_runs(limit: int = 200) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM discovery_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]


WATCHLIST_RUNS_RETENTION_DAYS = 30


def log_watchlist_run(
    *,
    batch_size: int,
    refreshed_artists: list[str],
    failed_artists: list[str],
    pending_count: int,
    next_run_at: int,
    ran_at: int | None = None,
):
    when = int(time.time()) if ran_at is None else int(ran_at)
    cutoff = when - WATCHLIST_RUNS_RETENTION_DAYS * 86400
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO watchlist_runs "
            "(ran_at, batch_size, refreshed_count, error_count, "
            "refreshed_artists, failed_artists, pending_count, next_run_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                when,
                batch_size,
                len(refreshed_artists),
                len(failed_artists),
                json.dumps(refreshed_artists),
                json.dumps(failed_artists),
                pending_count,
                int(next_run_at),
            ),
        )
        # Auto-prune rows older than the retention window on every write.
        # Watchlist batches run ~every 10 min, so this costs ~microseconds.
        conn.execute("DELETE FROM watchlist_runs WHERE ran_at < ?", (cutoff,))


def get_watchlist_runs(limit: int = 200) -> list[dict]:
    """Return recent watchlist batch runs, most recent first.

    ``refreshed_artists`` and ``failed_artists`` are deserialised from JSON.
    """
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM watchlist_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for key in ("refreshed_artists", "failed_artists"):
            raw = d.get(key)
            try:
                d[key] = json.loads(raw) if raw else []
            except (TypeError, ValueError):
                d[key] = []
        out.append(d)
    return out


def search_albums(
    query: str,
    page: int = 1,
    per_page: int = 50,
    storefront: str = "",
    discovered_only: bool = False,
    watched_only: bool = False,
    release_type: str = "",
    sort: str = "release_date",
):
    if sort not in ALBUM_SORT_OPTIONS:
        sort = "release_date"
    order_by = "release_date DESC, first_seen DESC" if sort == "release_date" else "first_seen DESC, release_date DESC"
    offset = (page - 1) * per_page
    q = f"%{query}%"
    with get_conn() as conn:
        conditions = ["(title LIKE ? OR artist LIKE ?)"]
        params: list = [q, q]
        if storefront:
            conditions.append("storefronts LIKE ?")
            params.append(f'%"{storefront.lower()}"%')
        if discovered_only:
            conditions.append("source = 'discovered'")
        if watched_only:
            conditions.append(
                "(artist_id IN (SELECT artist_id FROM watched_artists)"
                " OR EXISTS (SELECT 1 FROM json_each(albums.artists_json)"
                "  WHERE json_extract(value, '$.id') IN (SELECT artist_id FROM watched_artists)))"
            )
        if release_type:
            conditions.append("release_type = ?")
            params.append(release_type)
        where = "WHERE " + " AND ".join(conditions)
        total = conn.execute(f"SELECT COUNT(*) FROM albums {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM albums {where} ORDER BY {order_by} LIMIT ? OFFSET ?",
            params + [per_page, offset],
        ).fetchall()
        return [dict(r) for r in rows], total


def search_artists_local(query: str, limit: int = 25) -> list[dict]:
    """Search the local database for artists by name, bio, genre, or origin.

    Results are ranked by match quality (best first):
      1. Exact name match (case-insensitive)
      2. Name starts with the query (prefix match)
      3. Name contains the query anywhere
      4. Query found in artist_bio, genre, or origin (name does not match)

    Artists from the ``artists`` metadata table are searched first.  Artists
    that appear only in the ``albums`` table (i.e. their full metadata has not
    yet been fetched) are included as a fallback with minimal fields.

    Args:
        query: The search term.
        limit: Maximum number of results to return (default 25).

    Returns:
        A list of artist dicts, each containing ``artist_id``, ``name``,
        ``artwork_url``, ``genre``, ``born_or_formed``, ``origin``,
        ``artist_bio``, ``is_group``, ``watched`` (bool), ``collection_status``,
        and ``match_reason`` (one of ``name_exact``, ``name_prefix``,
        ``name_contains``, ``info_contains``).
    """
    q_lower = query.lower()
    q_contains = f"%{q_lower}%"
    with get_conn() as conn:
        rows_artists = conn.execute(
            """SELECT ar.artist_id, ar.name, ar.artwork_url, ar.genre,
                      ar.born_or_formed, ar.origin, ar.artist_bio, ar.is_group,
                      (w.artist_id IS NOT NULL) AS watched, w.collection_status, w.alt_name
               FROM artists ar
               LEFT JOIN watched_artists w ON ar.artist_id = w.artist_id
               WHERE LOWER(ar.name) LIKE ?
                  OR LOWER(ar.artist_bio) LIKE ?
                  OR LOWER(ar.genre) LIKE ?
                  OR LOWER(ar.origin) LIKE ?
                  OR LOWER(w.alt_name) LIKE ?""",
            (q_contains, q_contains, q_contains, q_contains, q_contains),
        ).fetchall()

        rows_albums = conn.execute(
            """SELECT DISTINCT alb.artist_id, alb.artist AS name,
                      NULL AS artwork_url, NULL AS genre, NULL AS born_or_formed,
                      NULL AS origin, NULL AS artist_bio, NULL AS is_group,
                      (w.artist_id IS NOT NULL) AS watched, w.collection_status, w.alt_name
               FROM albums alb
               LEFT JOIN watched_artists w ON alb.artist_id = w.artist_id
               WHERE alb.artist_id IS NOT NULL
                 AND alb.artist_id NOT IN (SELECT artist_id FROM artists)
                 AND (LOWER(alb.artist) LIKE ? OR LOWER(w.alt_name) LIKE ?)""",
            (q_contains, q_contains),
        ).fetchall()

    def _rank(row: dict) -> tuple:
        alt = (row.get("alt_name") or "").lower()
        n = (row["name"] or "").lower()
        sort_key = alt if alt else n
        if alt and alt == q_lower:
            return (1, sort_key)
        if alt and alt.startswith(q_lower):
            return (2, sort_key)
        if n == q_lower:
            return (3, sort_key)
        if n.startswith(q_lower):
            return (4, sort_key)
        if q_lower in n:
            return (5, sort_key)
        return (6, sort_key)

    def _match_reason(row: dict) -> str:
        alt = (row.get("alt_name") or "").lower()
        n = (row["name"] or "").lower()
        if alt and alt == q_lower:
            return "name_exact"
        if alt and alt.startswith(q_lower):
            return "name_prefix"
        if n == q_lower:
            return "name_exact"
        if n.startswith(q_lower):
            return "name_prefix"
        if q_lower in n:
            return "name_contains"
        return "info_contains"

    seen: set = set()
    combined: list[dict] = []
    for r in [dict(r) for r in rows_artists] + [dict(r) for r in rows_albums]:
        if r["artist_id"] not in seen:
            seen.add(r["artist_id"])
            r["match_reason"] = _match_reason(r)
            combined.append(r)

    combined.sort(key=_rank)
    return combined[:limit]


def get_db_stats() -> dict:
    """Return database file sizes and per-table row/page statistics."""
    db_size = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    wal_size = os.path.getsize(DB_PATH + "-wal") if os.path.exists(DB_PATH + "-wal") else 0
    shm_size = os.path.getsize(DB_PATH + "-shm") if os.path.exists(DB_PATH + "-shm") else 0

    with get_conn() as conn:
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        page_count = conn.execute("PRAGMA page_count").fetchone()[0]

        table_names = [
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        ]

        # dbstat gives per-page storage breakdown per table/index
        dbstat_rows = conn.execute(
            "SELECT name, SUM(pgsize) as size_bytes, COUNT(*) as page_count FROM dbstat GROUP BY name"
        ).fetchall()
        dbstat_map = {r["name"]: {"size_bytes": r["size_bytes"], "page_count": r["page_count"]} for r in dbstat_rows}

        table_stats = []
        for name in table_names:
            row_count = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]  # noqa: S608
            stat = dbstat_map.get(name, {})
            table_stats.append(
                {
                    "name": name,
                    "row_count": row_count,
                    "size_bytes": stat.get("size_bytes", 0),
                    "page_count": stat.get("page_count", 0),
                }
            )

        table_stats.sort(key=lambda x: x["size_bytes"], reverse=True)

    return {
        "db_path": DB_PATH,
        "db_size_bytes": db_size,
        "wal_size_bytes": wal_size,
        "shm_size_bytes": shm_size,
        "total_size_bytes": db_size + wal_size + shm_size,
        "page_size_bytes": page_size,
        "page_count": page_count,
        "tables": table_stats,
    }
