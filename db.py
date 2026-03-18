"""
SQLite database layer for AM Discovery.
"""

import sqlite3
import json
import os
from contextlib import contextmanager
from datetime import datetime

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


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS albums (
                store_adam_id  TEXT PRIMARY KEY,
                title          TEXT NOT NULL,
                artist         TEXT,
                artist_id      TEXT,
                artist_url     TEXT,
                url            TEXT,
                storefronts    TEXT DEFAULT '[]',
                release_date   TEXT,
                artwork_url    TEXT,
                track_count    INTEGER,
                genre          TEXT,
                description    TEXT,
                info_fetched   INTEGER DEFAULT 0,
                tracks_fetched INTEGER DEFAULT 0,
                audio_formats  TEXT,
                first_seen     TEXT,
                last_seen      TEXT
            );

            CREATE TABLE IF NOT EXISTS tracks (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                store_adam_id TEXT NOT NULL,
                track_number  INTEGER,
                title         TEXT NOT NULL,
                duration_ms   INTEGER
            );

            CREATE TABLE IF NOT EXISTS watched_artists (
                artist_id TEXT PRIMARY KEY,
                name      TEXT NOT NULL,
                url       TEXT,
                added_at  TEXT
            );

            CREATE TABLE IF NOT EXISTS discovery_runs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ran_at      TEXT,
                new_count   INTEGER DEFAULT 0,
                total_count INTEGER DEFAULT 0
            );
        """)
        # Migrations for existing databases
        for stmt in [
            "ALTER TABLE albums ADD COLUMN tracks_fetched INTEGER DEFAULT 0",
            "ALTER TABLE albums ADD COLUMN audio_formats TEXT",
        ]:
            try:
                conn.execute(stmt)
            except Exception:
                pass


def get_album(store_adam_id: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM albums WHERE store_adam_id = ?", (store_adam_id,)
        ).fetchone()
        return dict(row) if row else None


def upsert_album(data: dict):
    """Insert or update an album row."""
    now = datetime.utcnow().isoformat()
    storefronts = json.dumps(data.get("storefronts", []))
    audio_formats = json.dumps(data["audio_formats"]) if data.get("audio_formats") is not None else None
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT store_adam_id, storefronts, first_seen FROM albums WHERE store_adam_id = ?",
            (data["store_adam_id"],),
        ).fetchone()

        if existing:
            # Merge storefronts
            old_sf = json.loads(existing["storefronts"])
            new_sf = data.get("storefronts", [])
            merged = list(dict.fromkeys(old_sf + new_sf))
            conn.execute(
                """UPDATE albums SET
                    title=coalesce(?, title),
                    artist=coalesce(?, artist),
                    artist_id=coalesce(?, artist_id),
                    artist_url=coalesce(?, artist_url),
                    url=coalesce(?, url),
                    storefronts=?,
                    release_date=coalesce(?, release_date),
                    artwork_url=coalesce(?, artwork_url),
                    track_count=coalesce(?, track_count),
                    genre=coalesce(?, genre),
                    description=coalesce(?, description),
                    info_fetched=max(info_fetched, ?),
                    audio_formats=coalesce(?, audio_formats),
                    last_seen=?
                WHERE store_adam_id=?""",
                (
                    data.get("title"),
                    data.get("artist"),
                    data.get("artist_id"),
                    data.get("artist_url"),
                    data.get("url"),
                    json.dumps(merged),
                    data.get("release_date"),
                    data.get("artwork_url"),
                    data.get("track_count"),
                    data.get("genre"),
                    data.get("description"),
                    1 if data.get("info_fetched") else 0,
                    audio_formats,
                    now,
                    data["store_adam_id"],
                ),
            )
        else:
            conn.execute(
                """INSERT INTO albums
                    (store_adam_id, title, artist, artist_id, artist_url, url,
                     storefronts, release_date, artwork_url, track_count, genre,
                     description, info_fetched, audio_formats, first_seen, last_seen)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    data["store_adam_id"],
                    data.get("title"),
                    data.get("artist"),
                    data.get("artist_id"),
                    data.get("artist_url"),
                    data.get("url"),
                    storefronts,
                    data.get("release_date"),
                    data.get("artwork_url"),
                    data.get("track_count"),
                    data.get("genre"),
                    data.get("description"),
                    1 if data.get("info_fetched") else 0,
                    audio_formats,
                    now,
                    now,
                ),
            )


def list_albums(page: int = 1, per_page: int = 50, storefront: str = ""):
    offset = (page - 1) * per_page
    with get_conn() as conn:
        if storefront:
            sf = f'%"{storefront.lower()}"%'
            total = conn.execute("SELECT COUNT(*) FROM albums WHERE storefronts LIKE ?", (sf,)).fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM albums WHERE storefronts LIKE ? ORDER BY release_date DESC, first_seen DESC LIMIT ? OFFSET ?",
                (sf, per_page, offset),
            ).fetchall()
        else:
            total = conn.execute("SELECT COUNT(*) FROM albums").fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM albums ORDER BY release_date DESC, first_seen DESC LIMIT ? OFFSET ?",
                (per_page, offset),
            ).fetchall()
        return [dict(r) for r in rows], total


def upsert_tracks(store_adam_id: str, tracks: list):
    """Replace all tracks for an album and mark tracks_fetched."""
    with get_conn() as conn:
        conn.execute("DELETE FROM tracks WHERE store_adam_id = ?", (store_adam_id,))
        for t in tracks:
            if not t.get("title"):
                continue
            conn.execute(
                "INSERT INTO tracks (store_adam_id, track_number, title, duration_ms) VALUES (?,?,?,?)",
                (store_adam_id, t.get("track_number"), t["title"], t.get("duration_ms")),
            )
        conn.execute(
            "UPDATE albums SET tracks_fetched = 1 WHERE store_adam_id = ?",
            (store_adam_id,),
        )


def get_tracks(store_adam_id: str) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT track_number, title, duration_ms FROM tracks "
            "WHERE store_adam_id = ? ORDER BY track_number, rowid",
            (store_adam_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_artist_albums(artist_id: str):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM albums WHERE artist_id = ? ORDER BY release_date DESC",
            (artist_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_watchlist():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM watched_artists ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]


def add_to_watchlist(artist_id: str, name: str, url: str = None):
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO watched_artists (artist_id, name, url, added_at)
               VALUES (?,?,?,?)
               ON CONFLICT(artist_id) DO UPDATE SET name=excluded.name, url=excluded.url""",
            (artist_id, name, url, now),
        )


def remove_from_watchlist(artist_id: str):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM watched_artists WHERE artist_id = ?", (artist_id,)
        )


def get_watched_artist_ids() -> set:
    with get_conn() as conn:
        rows = conn.execute("SELECT artist_id FROM watched_artists").fetchall()
        return {r["artist_id"] for r in rows}


def log_discovery_run(new_count: int, total_count: int):
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO discovery_runs (ran_at, new_count, total_count) VALUES (?,?,?)",
            (now, new_count, total_count),
        )


def get_last_run():
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM discovery_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def search_albums(query: str, page: int = 1, per_page: int = 50, storefront: str = ""):
    offset = (page - 1) * per_page
    q = f"%{query}%"
    with get_conn() as conn:
        if storefront:
            sf = f'%"{storefront.lower()}"%'
            total = conn.execute(
                "SELECT COUNT(*) FROM albums WHERE (title LIKE ? OR artist LIKE ?) AND storefronts LIKE ?", (q, q, sf)
            ).fetchone()[0]
            rows = conn.execute(
                """SELECT * FROM albums WHERE (title LIKE ? OR artist LIKE ?) AND storefronts LIKE ?
                   ORDER BY release_date DESC LIMIT ? OFFSET ?""",
                (q, q, sf, per_page, offset),
            ).fetchall()
        else:
            total = conn.execute(
                "SELECT COUNT(*) FROM albums WHERE title LIKE ? OR artist LIKE ?", (q, q)
            ).fetchone()[0]
            rows = conn.execute(
                """SELECT * FROM albums WHERE title LIKE ? OR artist LIKE ?
                   ORDER BY release_date DESC LIMIT ? OFFSET ?""",
                (q, q, per_page, offset),
            ).fetchall()
        return [dict(r) for r in rows], total


# Seed the database from the existing aggregated_new_releases.json if it exists
def seed_from_json(json_path: str = "aggregated_new_releases.json"):
    if not os.path.exists(json_path):
        return 0
    with open(json_path, encoding="utf-8") as f:
        releases = json.load(f)
    count = 0
    for r in releases:
        if not get_album(r.get("storeAdamID", "")):
            upsert_album({
                "store_adam_id": r.get("storeAdamID", ""),
                "title": r.get("title"),
                "artist": r.get("artist"),
                "url": r.get("url"),
                "storefronts": r.get("storefronts", []),
                "release_date": r.get("releaseDate"),
                "info_fetched": 0,
            })
            count += 1
    return count
