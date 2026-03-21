"""
Tests for migrate.py — database migration runner.

Strategy:
- Create isolated SQLite databases in temp files.
- Patch DB_PATH and sys.exit to avoid side-effects.
- Verify that migrations are applied correctly and idempotently.
"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_db(path: str, version: int = 0, with_tables: bool = False):
    """Create a SQLite DB at *path* with a given user_version."""
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version = {version}")
    if with_tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS albums (
                store_adam_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                artist TEXT, artist_id TEXT, artist_url TEXT, url TEXT,
                storefronts TEXT DEFAULT '[]',
                release_date TEXT, artwork_url TEXT, track_count INTEGER,
                genre TEXT, description TEXT, info_fetched INTEGER DEFAULT 0,
                audio_formats TEXT, release_type TEXT, first_seen INTEGER, last_seen INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS watched_artists (
                artist_id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT, added_at INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS discovery_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ran_at INTEGER,
                new_count INTEGER DEFAULT 0, total_count INTEGER DEFAULT 0
            )
        """)
    conn.commit()
    conn.close()


def _get_version(path: str) -> int:
    conn = sqlite3.connect(path)
    v = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()
    return v


def _get_columns(path: str, table: str) -> list:
    conn = sqlite3.connect(path)
    cursor = conn.execute(f"PRAGMA table_info({table})")
    cols = [row[1] for row in cursor.fetchall()]
    conn.close()
    return cols


def _get_tables(path: str) -> set:
    conn = sqlite3.connect(path)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    conn.close()
    return tables


# ---------------------------------------------------------------------------
# Tests for helper functions: get_version / set_version
# ---------------------------------------------------------------------------

class TestVersionHelpers(unittest.TestCase):

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        _create_db(self.db_path, version=0)

    def tearDown(self):
        try:
            os.unlink(self.db_path)
        except FileNotFoundError:
            pass

    def test_get_version_zero(self):
        from migrate import get_version
        conn = sqlite3.connect(self.db_path)
        v = get_version(conn)
        conn.close()
        self.assertEqual(v, 0)

    def test_set_and_get_version(self):
        from migrate import get_version, set_version
        conn = sqlite3.connect(self.db_path)
        set_version(conn, 3)
        v = get_version(conn)
        conn.commit()
        conn.close()
        self.assertEqual(v, 3)

    def test_set_version_max(self):
        from migrate import get_version, set_version, SCHEMA_VERSION
        conn = sqlite3.connect(self.db_path)
        set_version(conn, SCHEMA_VERSION)
        v = get_version(conn)
        conn.commit()
        conn.close()
        self.assertEqual(v, SCHEMA_VERSION)


# ---------------------------------------------------------------------------
# Tests for run_migrations
# ---------------------------------------------------------------------------

class TestRunMigrations(unittest.TestCase):

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)

    def tearDown(self):
        try:
            os.unlink(self.db_path)
        except FileNotFoundError:
            pass

    def _patch_db_path(self):
        """Return a context manager that patches DB_PATH in migrate module."""
        return patch("migrate.DB_PATH", self.db_path)

    def test_exits_when_no_db_file(self):
        """run_migrations should exit(1) if DB file doesn't exist."""
        missing = self.db_path + "_missing.db"
        with patch("migrate.DB_PATH", missing), \
             patch("sys.exit") as mock_exit:
            from migrate import run_migrations
            run_migrations()
            mock_exit.assert_called_with(1)

    def test_exits_when_db_newer_than_code(self):
        """run_migrations should exit(1) if DB version > SCHEMA_VERSION."""
        from migrate import SCHEMA_VERSION
        _create_db(self.db_path, version=SCHEMA_VERSION + 1)
        with self._patch_db_path(), patch("sys.exit") as mock_exit:
            from migrate import run_migrations
            run_migrations()
            mock_exit.assert_called_with(1)

    def test_already_up_to_date_no_op(self):
        """run_migrations should do nothing when DB is already at SCHEMA_VERSION."""
        from migrate import SCHEMA_VERSION
        _create_db(self.db_path, version=SCHEMA_VERSION)
        with self._patch_db_path():
            from migrate import run_migrations
            run_migrations()
        self.assertEqual(_get_version(self.db_path), SCHEMA_VERSION)

    def test_full_migration_from_v1_baseline(self):
        """Starting from a v0 pre-versioning DB with tables, all migrations apply."""
        _create_db(self.db_path, version=0, with_tables=True)
        # Stamp as version 1 (after baseline)
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        conn.close()

        from migrate import SCHEMA_VERSION
        with self._patch_db_path():
            from migrate import run_migrations
            run_migrations()

        self.assertEqual(_get_version(self.db_path), SCHEMA_VERSION)

    def test_migration_v3_creates_artists_table(self):
        """After running all migrations, the artists table should exist."""
        _create_db(self.db_path, version=0, with_tables=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        conn.close()

        with self._patch_db_path():
            from migrate import run_migrations
            run_migrations()

        tables = _get_tables(self.db_path)
        self.assertIn("artists", tables)

    def test_migration_v5_adds_source_column(self):
        """After migration v5, albums table should have a 'source' column."""
        _create_db(self.db_path, version=0, with_tables=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        conn.close()

        with self._patch_db_path():
            from migrate import run_migrations
            run_migrations()

        cols = _get_columns(self.db_path, "albums")
        self.assertIn("source", cols)

    def test_migration_v4_removes_old_watched_artists_columns(self):
        """After v4, watched_artists should NOT have artwork_url or genre columns."""
        _create_db(self.db_path, version=0, with_tables=True)
        # Add v2 columns manually
        conn = sqlite3.connect(self.db_path)
        conn.execute("ALTER TABLE watched_artists ADD COLUMN artwork_url TEXT")
        conn.execute("ALTER TABLE watched_artists ADD COLUMN genre TEXT")
        conn.execute("PRAGMA user_version = 2")
        conn.commit()
        conn.close()

        with self._patch_db_path():
            from migrate import run_migrations
            run_migrations()

        cols = _get_columns(self.db_path, "watched_artists")
        self.assertNotIn("artwork_url", cols)
        self.assertNotIn("genre", cols)

    def test_idempotent_migration(self):
        """Running migrations twice should not raise and should remain at SCHEMA_VERSION."""
        _create_db(self.db_path, version=0, with_tables=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        conn.close()

        from migrate import SCHEMA_VERSION
        with self._patch_db_path():
            from migrate import run_migrations
            run_migrations()
        # Run again — should be a no-op (already up to date)
        with self._patch_db_path():
            from migrate import run_migrations
            run_migrations()

        self.assertEqual(_get_version(self.db_path), SCHEMA_VERSION)

    def test_duplicate_column_skipped_gracefully(self):
        """Adding a column that already exists should be handled without crashing."""
        _create_db(self.db_path, version=0, with_tables=True)
        # Add the 'source' column manually (simulating v5 already applied manually)
        conn = sqlite3.connect(self.db_path)
        conn.execute("ALTER TABLE albums ADD COLUMN source TEXT")
        conn.execute("PRAGMA user_version = 4")
        conn.commit()
        conn.close()

        with self._patch_db_path():
            from migrate import run_migrations
            run_migrations()

        # Should complete without crash and be at SCHEMA_VERSION
        from migrate import SCHEMA_VERSION
        self.assertEqual(_get_version(self.db_path), SCHEMA_VERSION)

    def test_all_tables_exist_after_full_migration(self):
        """All expected tables are present after a full migration from v1."""
        _create_db(self.db_path, version=0, with_tables=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        conn.close()

        with self._patch_db_path():
            from migrate import run_migrations
            run_migrations()

        tables = _get_tables(self.db_path)
        for expected in ["albums", "watched_artists", "discovery_runs", "artists"]:
            self.assertIn(expected, tables)

    def test_partial_migration_applies_only_pending(self):
        """Migrations already applied should not be reapplied."""
        _create_db(self.db_path, version=0, with_tables=True)
        # Simulate state after v3: add v2 columns to watched_artists + create artists table
        conn = sqlite3.connect(self.db_path)
        conn.execute("ALTER TABLE watched_artists ADD COLUMN artwork_url TEXT")
        conn.execute("ALTER TABLE watched_artists ADD COLUMN genre TEXT")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS artists (
                artist_id TEXT PRIMARY KEY, artwork_url TEXT, genre TEXT, updated_at INTEGER
            )
        """)
        conn.execute("PRAGMA user_version = 3")
        conn.commit()
        conn.close()

        with self._patch_db_path():
            from migrate import run_migrations
            run_migrations()

        from migrate import SCHEMA_VERSION
        self.assertEqual(_get_version(self.db_path), SCHEMA_VERSION)


# ---------------------------------------------------------------------------
# MIGRATIONS dict structure
# ---------------------------------------------------------------------------

class TestMigrationsDict(unittest.TestCase):

    def test_migrations_are_sequential(self):
        from migrate import MIGRATIONS
        keys = sorted(MIGRATIONS.keys())
        self.assertEqual(keys, list(range(1, len(keys) + 1)))

    def test_migrations_keys_go_up_to_schema_version(self):
        from migrate import MIGRATIONS, SCHEMA_VERSION
        self.assertIn(SCHEMA_VERSION, MIGRATIONS)

    def test_all_migration_values_are_strings(self):
        from migrate import MIGRATIONS
        for v, sql in MIGRATIONS.items():
            self.assertIsInstance(sql, str, f"Migration v{v} is not a string")

    def test_no_empty_migrations(self):
        from migrate import MIGRATIONS
        for v, sql in MIGRATIONS.items():
            self.assertTrue(sql.strip(), f"Migration v{v} is empty")


if __name__ == "__main__":
    unittest.main()
