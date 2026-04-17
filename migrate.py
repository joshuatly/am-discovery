"""One-off database migration runner.

Usage:
    python migrate.py

Applies any pending migrations to bring the DB up to the current SCHEMA_VERSION,
then updates PRAGMA user_version. Safe to re-run — already-applied migrations are skipped.
"""

import os
import sqlite3
import sys

# Import the version target and DB path from the main db module
from db import DB_PATH, SCHEMA_VERSION

# ---------------------------------------------------------------------------
# Migration definitions
# Each entry upgrades the DB from (version - 1) to version.
# Add new entries here whenever the schema changes.
# ---------------------------------------------------------------------------
MIGRATIONS = {
    1: """
        -- Version 1: baseline schema (for DBs created before versioning was introduced).
        -- These are CREATE IF NOT EXISTS so they are safe to run even if the table exists.
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
            audio_formats  TEXT,
            release_type   TEXT,
            first_seen     INTEGER,
            last_seen      INTEGER
        );
        CREATE TABLE IF NOT EXISTS watched_artists (
            artist_id TEXT PRIMARY KEY,
            name      TEXT NOT NULL,
            url       TEXT,
            added_at  INTEGER
        );
        CREATE TABLE IF NOT EXISTS discovery_runs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ran_at      INTEGER,
            new_count   INTEGER DEFAULT 0,
            total_count INTEGER DEFAULT 0
        );
    """,
    2: """
        -- Version 2: add artwork_url and genre to watched_artists.
        ALTER TABLE watched_artists ADD COLUMN artwork_url TEXT;
        ALTER TABLE watched_artists ADD COLUMN genre TEXT;
    """,
    3: """
        -- Version 3: add artists cache table for per-artist metadata.
        CREATE TABLE IF NOT EXISTS artists (
            artist_id   TEXT PRIMARY KEY,
            artwork_url TEXT,
            genre       TEXT,
            updated_at  INTEGER
        );
    """,
    4: """
        -- Version 4: drop redundant artwork_url and genre from watched_artists (now in artists table).
        ALTER TABLE watched_artists DROP COLUMN artwork_url;
        ALTER TABLE watched_artists DROP COLUMN genre;
    """,
    5: """
        -- Version 5: track how an album entered the DB (room discovery vs artist page fetch).
        ALTER TABLE albums ADD COLUMN source TEXT;
    """,
    6: """
        -- Version 6: add preferred metadata source and last refresh timestamp to watched_artists.
        ALTER TABLE watched_artists ADD COLUMN preferred_source TEXT;
        ALTER TABLE watched_artists ADD COLUMN last_refreshed INTEGER;
    """,
    7: """
        -- Version 7: add canonical artist name to artists table.
        ALTER TABLE artists ADD COLUMN name TEXT;
    """,
    8: """
        -- Version 8: store all artists for an album as a JSON array of {id, name, url} objects.
        ALTER TABLE albums ADD COLUMN artists_json TEXT;
    """,
    9: """
        -- Version 9: add collection status tracking to watched artists.
        ALTER TABLE watched_artists ADD COLUMN collection_status TEXT DEFAULT 'new';
        ALTER TABLE watched_artists ADD COLUMN collection_status_updated_at INTEGER;
    """,
    10: """
        -- Version 10: add born_or_formed, origin, and artist_bio to artists table.
        ALTER TABLE artists ADD COLUMN born_or_formed TEXT;
        ALTER TABLE artists ADD COLUMN origin TEXT;
        ALTER TABLE artists ADD COLUMN artist_bio TEXT;
    """,
    11: """
        -- Version 11: add is_group flag to artists table.
        ALTER TABLE artists ADD COLUMN is_group INTEGER;
    """,
    12: """
        -- Version 12: add user-defined alternate name to watched_artists.
        ALTER TABLE watched_artists ADD COLUMN alt_name TEXT;
    """,
    13: """
        -- Version 13: add UPC (barcode) to albums and MusicBrainz artist ID to artists.
        ALTER TABLE albums ADD COLUMN upc TEXT;
        ALTER TABLE artists ADD COLUMN musicbrainz_id TEXT;
    """,
    14: """
        -- Version 14: add storefront and room_id to discovery_runs for per-storefront tracking.
        ALTER TABLE discovery_runs ADD COLUMN storefront TEXT;
        ALTER TABLE discovery_runs ADD COLUMN room_id TEXT;
    """,
}


def get_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def set_version(conn: sqlite3.Connection, version: int):
    conn.execute(f"PRAGMA user_version = {int(version)}")


def run_migrations():
    if not os.path.exists(DB_PATH):
        print(f"No database found at {DB_PATH}. Start the server to create a fresh one.")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    current = get_version(conn)
    print(f"Current schema version : {current}")
    print(f"Target schema version  : {SCHEMA_VERSION}")

    if current > SCHEMA_VERSION:
        print(f"ERROR: DB version ({current}) is newer than this code ({SCHEMA_VERSION}). Update your code.")
        conn.close()
        sys.exit(1)

    if current == SCHEMA_VERSION:
        print("Already up to date. Nothing to do.")
        conn.close()
        return

    pending = sorted(v for v in MIGRATIONS if v > current)
    print(f"Migrations to apply    : {pending}\n")

    for target_version in pending:
        sql = MIGRATIONS[target_version]
        print(f"  Applying migration → v{target_version} …")
        # ALTER TABLE statements can't run inside a BEGIN block in sqlite3's executescript,
        # so we split on ';' and execute each statement individually.
        for stmt in sql.split(";"):
            # Strip comment lines before checking if the statement is empty
            clean = "\n".join(line for line in stmt.splitlines() if not line.strip().startswith("--")).strip()
            if not clean:
                continue
            try:
                conn.execute(clean)
                conn.commit()
            except sqlite3.OperationalError as e:
                if "duplicate column" in str(e).lower():
                    print("    (skipped — column already exists)")
                else:
                    print(f"    ERROR: {e}")
                    conn.close()
                    sys.exit(1)
        set_version(conn, target_version)
        conn.commit()
        print(f"  Done → v{target_version}")

    print(f"\nMigration complete. Schema is now at version {SCHEMA_VERSION}.")
    conn.close()


if __name__ == "__main__":
    run_migrations()
