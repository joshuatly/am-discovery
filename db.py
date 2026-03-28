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


SCHEMA_VERSION = 11

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
                    genre          TEXT,
                    description    TEXT,
                    info_fetched   INTEGER DEFAULT 0,
                    audio_formats  TEXT,
                    release_type   TEXT,
                    first_seen     INTEGER,
                    last_seen      INTEGER,
                    source         TEXT
                );

                CREATE TABLE IF NOT EXISTS watched_artists (
                    artist_id                    TEXT PRIMARY KEY,
                    name                         TEXT NOT NULL,
                    url                          TEXT,
                    added_at                     INTEGER,
                    preferred_source             TEXT,
                    last_refreshed               INTEGER,
                    collection_status            TEXT DEFAULT 'new',
                    collection_status_updated_at INTEGER
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
                    updated_at     INTEGER
                );

                CREATE TABLE IF NOT EXISTS discovery_runs (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    ran_at      INTEGER,
                    new_count   INTEGER DEFAULT 0,
                    total_count INTEGER DEFAULT 0
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
                genre=coalesce(?, genre),
                description=coalesce(?, description),
                info_fetched=max(info_fetched, ?),
                audio_formats=coalesce(?, audio_formats),
                release_type=coalesce(?, release_type),
                source=CASE WHEN ? = 'discovered' THEN 'discovered' ELSE source END,
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
                data.get("genre"),
                data.get("description"),
                1 if data.get("info_fetched") else 0,
                audio_formats,
                data.get("release_type"),
                data.get("source"),
                now,
                data["store_adam_id"],
            ),
        )


def list_albums(
    page: int = 1,
    per_page: int = 50,
    storefront: str = "",
    discovered_only: bool = False,
    watched_only: bool = False,
):
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
            conditions.append("artist_id IN (SELECT artist_id FROM watched_artists)")
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        total = conn.execute(f"SELECT COUNT(*) FROM albums {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM albums {where} ORDER BY release_date DESC, first_seen DESC LIMIT ? OFFSET ?",
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


WATCHLIST_SORT_OPTIONS = {"name", "added", "recent_release"}


def get_watchlist(preferred_source: str = "", collection_status: str = "", sort: str = "name"):
    if sort not in WATCHLIST_SORT_OPTIONS:
        sort = "name"
    order_by = {
        "name": "w.name",
        "added": "w.added_at DESC",
        "recent_release": "latest_release_date DESC NULLS LAST, w.name",
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
            f"""SELECT w.*, ar.artwork_url, ar.genre, ar.artist_bio, MAX(alb.release_date) AS latest_release_date
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
):
    now = int(time.time())
    is_group_int = int(is_group) if is_group is not None else None
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO artists
               (artist_id, name, artwork_url, genre, born_or_formed, origin, artist_bio, is_group, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(artist_id) DO UPDATE SET
                   name           = coalesce(excluded.name, name),
                   artwork_url    = coalesce(excluded.artwork_url, artwork_url),
                   genre          = coalesce(excluded.genre, genre),
                   born_or_formed = coalesce(excluded.born_or_formed, born_or_formed),
                   origin         = coalesce(excluded.origin, origin),
                   artist_bio     = coalesce(excluded.artist_bio, artist_bio),
                   is_group       = coalesce(excluded.is_group, is_group),
                   updated_at     = excluded.updated_at""",
            (artist_id, name, artwork_url, genre, born_or_formed, origin, artist_bio, is_group_int, now),
        )


def get_artist_artwork(artist_id: str):
    with get_conn() as conn:
        row = conn.execute("SELECT artwork_url FROM artists WHERE artist_id = ?", (artist_id,)).fetchone()
        return row["artwork_url"] if row else None


def get_artist_info(artist_id: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT name, artwork_url, genre, born_or_formed, origin, artist_bio, is_group"
            " FROM artists WHERE artist_id = ?",
            (artist_id,),
        ).fetchone()
        return dict(row) if row else {}


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


def update_preferred_source(artist_id: str, preferred_source):
    """Set (or clear) the preferred metadata source for a watched artist."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE watched_artists SET preferred_source = ? WHERE artist_id = ?",
            (preferred_source, artist_id),
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


def check_and_update_new_releases(artist_id: str) -> bool:
    """If artist status is 'complete' and a release exists newer than the completion date, set to 'new_release'.

    Returns True if the status was changed.
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT collection_status, collection_status_updated_at FROM watched_artists WHERE artist_id = ?",
            (artist_id,),
        ).fetchone()
        if not row or row["collection_status"] != "complete":
            return False
        completed_at = row["collection_status_updated_at"]
        if not completed_at:
            return False
        # Convert unix timestamp to ISO date for comparison with release_date strings
        completed_date = datetime.fromtimestamp(completed_at, tz=UTC).strftime("%Y-%m-%d")
        latest = conn.execute(
            "SELECT MAX(release_date) AS latest FROM albums WHERE artist_id = ? AND release_date > ?",
            (artist_id, completed_date),
        ).fetchone()
        if latest and latest["latest"]:
            now = int(time.time())
            conn.execute(
                """UPDATE watched_artists SET collection_status = 'new_release',
                   collection_status_updated_at = ? WHERE artist_id = ?""",
                (now, artist_id),
            )
            return True
        return False


def export_watchlist() -> list:
    """Export the full watchlist as a list of dicts suitable for JSON serialization."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT artist_id, name, url, preferred_source,
                      collection_status, collection_status_updated_at
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
                        collection_status, collection_status_updated_at)
                   VALUES (?,?,?,?,?, ?,?)
                   ON CONFLICT(artist_id) DO UPDATE SET
                       name=excluded.name,
                       url=excluded.url,
                       preferred_source=coalesce(excluded.preferred_source, preferred_source),
                       collection_status=coalesce(excluded.collection_status, collection_status),
                       collection_status_updated_at=coalesce(
                           excluded.collection_status_updated_at, collection_status_updated_at
                       )""",
                (
                    a["artist_id"],
                    a["name"],
                    a.get("url"),
                    now,
                    a.get("preferred_source"),
                    a.get("collection_status", "new"),
                    a.get("collection_status_updated_at", now),
                ),
            )


def log_discovery_run(new_count: int, total_count: int):
    now = int(time.time())
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO discovery_runs (ran_at, new_count, total_count) VALUES (?,?,?)",
            (now, new_count, total_count),
        )


def get_last_run():
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM discovery_runs ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else None


def search_albums(
    query: str,
    page: int = 1,
    per_page: int = 50,
    storefront: str = "",
    discovered_only: bool = False,
    watched_only: bool = False,
):
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
            conditions.append("artist_id IN (SELECT artist_id FROM watched_artists)")
        where = "WHERE " + " AND ".join(conditions)
        total = conn.execute(f"SELECT COUNT(*) FROM albums {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM albums {where} ORDER BY release_date DESC LIMIT ? OFFSET ?",
            params + [per_page, offset],
        ).fetchall()
        return [dict(r) for r in rows], total
