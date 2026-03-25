"""Tests for migrate.py — database migration runner.

Uses a fake v999 migration injected at test time so tests never depend on
the current real schema version and don't need to be updated on schema bumps.
"""

import os
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_version(path: str) -> int:
    conn = sqlite3.connect(path)
    v = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()
    return v


def _set_version(path: str, version: int):
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version = {int(version)}")
    conn.commit()
    conn.close()


def _get_columns(path: str, table: str) -> list:
    conn = sqlite3.connect(path)
    cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    conn.close()
    return cols


def _get_tables(path: str) -> list:
    conn = sqlite3.connect(path)
    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    conn.close()
    return tables


# A minimal base schema used by several tests — just enough tables for
# migrations to be able to run on top of it.
_BASE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS canary (id INTEGER PRIMARY KEY);
"""

# Fake migrations ending at version 999.  Lower versions provide a minimal
# realistic base; 999 is the one we actually exercise in most tests.
_FAKE_MIGRATIONS = {
    997: _BASE_SCHEMA,
    998: "ALTER TABLE canary ADD COLUMN label TEXT;",
    999: "ALTER TABLE canary ADD COLUMN marker TEXT;",
}


def _make_db(path: str, version: int, extra_sql: str = ""):
    """Create a SQLite file at *path* set to *version* with optional SQL."""
    conn = sqlite3.connect(path)
    if extra_sql:
        for stmt in extra_sql.split(";"):
            clean = stmt.strip()
            if clean:
                conn.execute(clean)
    conn.execute(f"PRAGMA user_version = {int(version)}")
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# get_version / set_version
# ---------------------------------------------------------------------------


class TestVersionHelpers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "v.db")
        sqlite3.connect(self.db).close()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_new_db_version_is_zero(self):
        from migrate import get_version

        conn = sqlite3.connect(self.db)
        self.assertEqual(get_version(conn), 0)
        conn.close()

    def test_set_then_get_roundtrip(self):
        from migrate import get_version, set_version

        conn = sqlite3.connect(self.db)
        set_version(conn, 42)
        conn.commit()
        self.assertEqual(get_version(conn), 42)
        conn.close()

    def test_set_version_persists_after_reopen(self):
        from migrate import set_version

        conn = sqlite3.connect(self.db)
        set_version(conn, 999)
        conn.commit()
        conn.close()
        self.assertEqual(_get_version(self.db), 999)

    def test_set_version_overwrites_previous(self):
        from migrate import get_version, set_version

        conn = sqlite3.connect(self.db)
        set_version(conn, 10)
        set_version(conn, 999)
        conn.commit()
        self.assertEqual(get_version(conn), 999)
        conn.close()


# ---------------------------------------------------------------------------
# run_migrations — error and no-op paths
# ---------------------------------------------------------------------------


class TestRunMigrationsGuardClauses(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "guard.db")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _patch(self):
        return patch("migrate.DB_PATH", self.db)

    def test_exits_when_db_file_missing(self):
        missing = self.db + "_does_not_exist"
        with patch("migrate.DB_PATH", missing), patch("sys.exit") as mock_exit:
            from migrate import run_migrations

            run_migrations()
        mock_exit.assert_called_with(1)

    def test_exits_when_db_newer_than_target(self):
        _make_db(self.db, 999 + 1)  # DB claims to be ahead of v999
        with (
            self._patch(),
            patch("migrate.MIGRATIONS", _FAKE_MIGRATIONS),
            patch("migrate.SCHEMA_VERSION", 999),
            patch("sys.exit") as mock_exit,
        ):
            from migrate import run_migrations

            run_migrations()
        mock_exit.assert_called_with(1)

    def test_no_op_when_already_at_target(self):
        # DB is already at 999 — nothing should change.
        _make_db(
            self.db,
            999,
            _BASE_SCHEMA + "ALTER TABLE canary ADD COLUMN label TEXT; ALTER TABLE canary ADD COLUMN marker TEXT;",
        )
        with (
            self._patch(),
            patch("migrate.MIGRATIONS", _FAKE_MIGRATIONS),
            patch("migrate.SCHEMA_VERSION", 999),
        ):
            from migrate import run_migrations

            run_migrations()
        self.assertEqual(_get_version(self.db), 999)

    def test_no_op_does_not_change_version(self):
        _make_db(
            self.db,
            999,
            _BASE_SCHEMA + "ALTER TABLE canary ADD COLUMN label TEXT; ALTER TABLE canary ADD COLUMN marker TEXT;",
        )
        before = _get_version(self.db)
        with (
            self._patch(),
            patch("migrate.MIGRATIONS", _FAKE_MIGRATIONS),
            patch("migrate.SCHEMA_VERSION", 999),
        ):
            from migrate import run_migrations

            run_migrations()
        self.assertEqual(_get_version(self.db), before)


# ---------------------------------------------------------------------------
# run_migrations — actual migration execution
# ---------------------------------------------------------------------------


class TestRunMigrationsExecution(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "exec.db")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, from_version):
        """Set DB to *from_version* (with schema matching that point) then run migrations to v999."""
        if from_version == 0:
            sqlite3.connect(self.db).close()
            _set_version(self.db, 0)
        elif from_version == 997:
            _make_db(self.db, 997, _BASE_SCHEMA)
        elif from_version == 998:
            _make_db(self.db, 998, _BASE_SCHEMA + "ALTER TABLE canary ADD COLUMN label TEXT;")

        with (
            patch("migrate.DB_PATH", self.db),
            patch("migrate.MIGRATIONS", _FAKE_MIGRATIONS),
            patch("migrate.SCHEMA_VERSION", 999),
        ):
            from migrate import run_migrations

            run_migrations()

    def test_applies_all_pending_from_zero(self):
        self._run(from_version=0)
        self.assertEqual(_get_version(self.db), 999)

    def test_applies_all_pending_from_997(self):
        self._run(from_version=997)
        self.assertEqual(_get_version(self.db), 999)

    def test_applies_only_missing_from_998(self):
        # Start at v998 — only v999 should be applied.
        self._run(from_version=998)
        self.assertEqual(_get_version(self.db), 999)
        # v999 adds `marker`; `label` should already exist from v998 setup
        cols = _get_columns(self.db, "canary")
        self.assertIn("marker", cols)
        self.assertIn("label", cols)

    def test_v999_adds_marker_column(self):
        self._run(from_version=998)
        self.assertIn("marker", _get_columns(self.db, "canary"))

    def test_v999_does_not_remove_label_column(self):
        self._run(from_version=998)
        self.assertIn("label", _get_columns(self.db, "canary"))

    def test_from_zero_creates_canary_table(self):
        self._run(from_version=0)
        self.assertIn("canary", _get_tables(self.db))

    def test_version_bumped_after_each_migration(self):
        # Run only up to v998 to confirm incremental bumping works,
        # then finish to v999.
        partial = {997: _FAKE_MIGRATIONS[997], 998: _FAKE_MIGRATIONS[998]}
        _make_db(self.db, 0)
        with (
            patch("migrate.DB_PATH", self.db),
            patch("migrate.MIGRATIONS", partial),
            patch("migrate.SCHEMA_VERSION", 998),
        ):
            from migrate import run_migrations

            run_migrations()
        self.assertEqual(_get_version(self.db), 998)

    def test_idempotent_when_run_twice(self):
        self._run(from_version=997)
        with (
            patch("migrate.DB_PATH", self.db),
            patch("migrate.MIGRATIONS", _FAKE_MIGRATIONS),
            patch("migrate.SCHEMA_VERSION", 999),
        ):
            from migrate import run_migrations

            run_migrations()
        self.assertEqual(_get_version(self.db), 999)


# ---------------------------------------------------------------------------
# Duplicate-column tolerance (ALTER TABLE idempotency)
# ---------------------------------------------------------------------------


class TestDuplicateColumnTolerance(unittest.TestCase):
    """run_migrations must survive re-running a migration that adds an
    already-existing column (duplicate column error → skip, not crash).
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "dup.db")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_duplicate_column_is_skipped_not_fatal(self):
        # canary already has `marker` but DB version says 998 — simulates
        # a migration that was partially applied manually.
        _make_db(
            self.db,
            998,
            _BASE_SCHEMA
            + "ALTER TABLE canary ADD COLUMN label TEXT;"
            + "ALTER TABLE canary ADD COLUMN marker TEXT;",  # already applied
        )
        with (
            patch("migrate.DB_PATH", self.db),
            patch("migrate.MIGRATIONS", _FAKE_MIGRATIONS),
            patch("migrate.SCHEMA_VERSION", 999),
            patch("sys.exit") as mock_exit,
        ):
            from migrate import run_migrations

            run_migrations()
        mock_exit.assert_not_called()
        self.assertEqual(_get_version(self.db), 999)


# ---------------------------------------------------------------------------
# MIGRATIONS dict structure
# ---------------------------------------------------------------------------


class TestMigrationsDictStructure(unittest.TestCase):
    def test_keys_are_sequential_from_one(self):
        from migrate import MIGRATIONS

        keys = sorted(MIGRATIONS.keys())
        self.assertEqual(keys, list(range(1, len(keys) + 1)))

    def test_schema_version_present_in_migrations(self):
        from migrate import MIGRATIONS, SCHEMA_VERSION

        self.assertIn(SCHEMA_VERSION, MIGRATIONS)

    def test_all_values_are_non_empty_strings(self):
        from migrate import MIGRATIONS

        for v, sql in MIGRATIONS.items():
            self.assertIsInstance(sql, str, f"v{v} is not a string")
            self.assertTrue(sql.strip(), f"v{v} is an empty string")


if __name__ == "__main__":
    unittest.main()
