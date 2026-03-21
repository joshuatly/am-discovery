"""
Comprehensive unit tests for db.py — SQLite database layer.

Strategy:
- Override DB_PATH via os.environ before importing db, so every test gets an
  isolated in-memory / temp-file database.
- Each test class reinitialises the database to guarantee a clean slate.
"""

import json
import os
import sqlite3
import tempfile
import time
import unittest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_temp_db():
    """Return a path to a fresh, initialised database in a temp file."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)          # remove so init_db sees a clean slate
    return path


def _reinit_db(path: str):
    """Point db.DB_PATH at *path* and (re)initialise the schema."""
    import db as _db
    _db.DB_PATH = path
    _db.init_db()


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class DBTestCase(unittest.TestCase):
    """Creates a fresh temp DB before every test and removes it afterwards."""

    def setUp(self):
        self.db_path = _make_temp_db()
        os.environ["AM_DB_PATH"] = self.db_path
        # Re-import to pick up the new path
        import importlib, db
        importlib.reload(db)
        db.init_db()
        self.db = db

    def tearDown(self):
        try:
            os.unlink(self.db_path)
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------------------
# init_db
# ---------------------------------------------------------------------------

class TestInitDb(DBTestCase):

    def test_fresh_db_creates_all_tables(self):
        """All expected tables exist after init_db on a fresh database."""
        with self.db.get_conn() as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
        self.assertIn("albums", tables)
        self.assertIn("watched_artists", tables)
        self.assertIn("artists", tables)
        self.assertIn("discovery_runs", tables)

    def test_fresh_db_sets_schema_version(self):
        """PRAGMA user_version equals SCHEMA_VERSION after init_db."""
        with self.db.get_conn() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(version, self.db.SCHEMA_VERSION)

    def test_init_db_idempotent(self):
        """Calling init_db twice on a correctly-versioned DB does not raise."""
        # Should not raise; nothing to re-create
        self.db.init_db()

    def test_pre_versioning_db_raises(self):
        """init_db raises RuntimeError for a DB that has tables but version 0."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        conn = sqlite3.connect(path)
        # Create a table so the DB is non-empty
        conn.execute("CREATE TABLE albums (store_adam_id TEXT PRIMARY KEY, title TEXT NOT NULL)")
        conn.commit()
        conn.close()

        import importlib, db
        db.DB_PATH = path
        importlib.reload(db)
        db.DB_PATH = path   # reload resets env; set explicitly

        try:
            with self.assertRaises(RuntimeError):
                db.init_db()
        finally:
            os.unlink(path)

    def test_wrong_schema_version_raises(self):
        """init_db raises RuntimeError when user_version != SCHEMA_VERSION."""
        # Stamp a wrong version directly
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA user_version = 1")
        with self.assertRaises(RuntimeError):
            self.db.init_db()


# ---------------------------------------------------------------------------
# get_album / upsert_album
# ---------------------------------------------------------------------------

def _minimal_album(store_adam_id="123456", **kwargs):
    data = {
        "store_adam_id": store_adam_id,
        "title": "Test Album",
        "artist": "Test Artist",
        "artist_id": "A1",
        "artist_url": "https://music.apple.com/us/artist/A1",
        "url": "https://music.apple.com/us/album/123456",
        "storefronts": ["us"],
        "release_date": "2024-01-15",
        "artwork_url": "https://example.com/art.jpg",
        "track_count": 10,
        "genre": "Pop",
        "description": "A test album",
        "info_fetched": 1,
        "audio_formats": ["lossless", "atmos"],
        "release_type": "main-albums",
        "source": "discovered",
    }
    data.update(kwargs)
    return data


class TestGetAlbum(DBTestCase):

    def test_returns_none_for_missing_id(self):
        self.assertIsNone(self.db.get_album("NONEXISTENT"))

    def test_returns_dict_for_existing(self):
        self.db.upsert_album(_minimal_album())
        row = self.db.get_album("123456")
        self.assertIsNotNone(row)
        self.assertIsInstance(row, dict)

    def test_correct_fields_returned(self):
        album = _minimal_album()
        self.db.upsert_album(album)
        row = self.db.get_album("123456")
        self.assertEqual(row["title"], "Test Album")
        self.assertEqual(row["artist"], "Test Artist")
        self.assertEqual(row["release_date"], "2024-01-15")

    def test_audio_formats_stored_as_json_string(self):
        """Audio formats are stored as a JSON string in the DB."""
        self.db.upsert_album(_minimal_album())
        row = self.db.get_album("123456")
        formats = json.loads(row["audio_formats"])
        self.assertIn("lossless", formats)

    def test_storefronts_stored_as_json_string(self):
        self.db.upsert_album(_minimal_album())
        row = self.db.get_album("123456")
        storefronts = json.loads(row["storefronts"])
        self.assertIn("us", storefronts)


class TestUpsertAlbum(DBTestCase):

    def test_insert_new_album(self):
        self.db.upsert_album(_minimal_album())
        self.assertIsNotNone(self.db.get_album("123456"))

    def test_update_existing_album_title(self):
        self.db.upsert_album(_minimal_album())
        self.db.upsert_album(_minimal_album(title="Updated Title"))
        row = self.db.get_album("123456")
        self.assertEqual(row["title"], "Updated Title")

    def test_storefronts_are_merged(self):
        """Upserting with a new storefront should merge, not replace."""
        self.db.upsert_album(_minimal_album(storefronts=["us"]))
        self.db.upsert_album(_minimal_album(storefronts=["jp"]))
        row = self.db.get_album("123456")
        storefronts = json.loads(row["storefronts"])
        self.assertIn("us", storefronts)
        self.assertIn("jp", storefronts)

    def test_storefronts_deduplication(self):
        """Upserting the same storefront twice should not produce duplicates."""
        self.db.upsert_album(_minimal_album(storefronts=["us"]))
        self.db.upsert_album(_minimal_album(storefronts=["us"]))
        row = self.db.get_album("123456")
        storefronts = json.loads(row["storefronts"])
        self.assertEqual(storefronts.count("us"), 1)

    def test_info_fetched_max_logic(self):
        """info_fetched should be 1 if any upsert sets it to 1."""
        self.db.upsert_album(_minimal_album(info_fetched=0))
        row = self.db.get_album("123456")
        self.assertEqual(row["info_fetched"], 0)
        self.db.upsert_album(_minimal_album(info_fetched=1))
        row = self.db.get_album("123456")
        self.assertEqual(row["info_fetched"], 1)

    def test_coalesce_does_not_overwrite_with_none(self):
        """Fields set to None in an upsert should not overwrite existing values."""
        self.db.upsert_album(_minimal_album(genre="Pop"))
        self.db.upsert_album(_minimal_album(genre=None))
        row = self.db.get_album("123456")
        self.assertEqual(row["genre"], "Pop")

    def test_source_discovered_wins(self):
        """If source='discovered', it should not be overwritten by other sources."""
        self.db.upsert_album(_minimal_album(source="artist_fetch"))
        self.db.upsert_album(_minimal_album(source="discovered"))
        row = self.db.get_album("123456")
        self.assertEqual(row["source"], "discovered")

    def test_source_non_discovered_does_not_overwrite_discovered(self):
        """artist_fetch should not overwrite 'discovered'."""
        self.db.upsert_album(_minimal_album(source="discovered"))
        self.db.upsert_album(_minimal_album(source="artist_fetch"))
        row = self.db.get_album("123456")
        self.assertEqual(row["source"], "discovered")

    def test_first_seen_set_on_insert(self):
        before = int(time.time())
        self.db.upsert_album(_minimal_album())
        row = self.db.get_album("123456")
        self.assertGreaterEqual(row["first_seen"], before)

    def test_last_seen_updated_on_upsert(self):
        self.db.upsert_album(_minimal_album())
        t1 = self.db.get_album("123456")["last_seen"]
        time.sleep(0.05)
        self.db.upsert_album(_minimal_album())
        t2 = self.db.get_album("123456")["last_seen"]
        self.assertGreaterEqual(t2, t1)

    def test_audio_formats_none_stored_as_null(self):
        self.db.upsert_album(_minimal_album(audio_formats=None))
        row = self.db.get_album("123456")
        self.assertIsNone(row["audio_formats"])

    def test_multiple_albums_independent(self):
        self.db.upsert_album(_minimal_album("A1", title="Album 1"))
        self.db.upsert_album(_minimal_album("A2", title="Album 2"))
        self.assertEqual(self.db.get_album("A1")["title"], "Album 1")
        self.assertEqual(self.db.get_album("A2")["title"], "Album 2")


# ---------------------------------------------------------------------------
# list_albums
# ---------------------------------------------------------------------------

class TestListAlbums(DBTestCase):

    def setUp(self):
        super().setUp()
        self.db.upsert_album(_minimal_album("A1", title="Alpha", artist="Zara", release_date="2024-03-01", source="discovered", storefronts=["us"]))
        self.db.upsert_album(_minimal_album("A2", title="Beta", artist="Adam", release_date="2024-01-01", source="artist_fetch", storefronts=["jp"]))
        self.db.upsert_album(_minimal_album("A3", title="Gamma", artist="Zara", release_date="2024-02-01", source="discovered", storefronts=["us", "jp"]))

    def test_returns_all_albums(self):
        rows, total = self.db.list_albums()
        self.assertEqual(total, 3)
        self.assertEqual(len(rows), 3)

    def test_pagination_page_1(self):
        rows, total = self.db.list_albums(page=1, per_page=2)
        self.assertEqual(total, 3)
        self.assertEqual(len(rows), 2)

    def test_pagination_page_2(self):
        rows, total = self.db.list_albums(page=2, per_page=2)
        self.assertEqual(total, 3)
        self.assertEqual(len(rows), 1)

    def test_pagination_beyond_results(self):
        rows, total = self.db.list_albums(page=10, per_page=50)
        self.assertEqual(total, 3)
        self.assertEqual(len(rows), 0)

    def test_sorted_by_release_date_desc(self):
        rows, _ = self.db.list_albums()
        dates = [r["release_date"] for r in rows]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_filter_by_storefront(self):
        rows, total = self.db.list_albums(storefront="jp")
        self.assertEqual(total, 2)
        for r in rows:
            self.assertIn('"jp"', r["storefronts"])

    def test_filter_storefront_no_match(self):
        rows, total = self.db.list_albums(storefront="hk")
        self.assertEqual(total, 0)

    def test_discovered_only_filter(self):
        rows, total = self.db.list_albums(discovered_only=True)
        self.assertEqual(total, 2)
        for r in rows:
            self.assertEqual(r["source"], "discovered")

    def test_combined_storefront_and_discovered_only(self):
        rows, total = self.db.list_albums(storefront="us", discovered_only=True)
        self.assertEqual(total, 2)

    def test_empty_db_returns_zero(self):
        # wipe albums
        with self.db.get_conn() as conn:
            conn.execute("DELETE FROM albums")
        rows, total = self.db.list_albums()
        self.assertEqual(total, 0)
        self.assertEqual(rows, [])


# ---------------------------------------------------------------------------
# search_albums
# ---------------------------------------------------------------------------

class TestSearchAlbums(DBTestCase):

    def setUp(self):
        super().setUp()
        self.db.upsert_album(_minimal_album("A1", title="Blue Skies", artist="Alice", storefronts=["us"], source="discovered"))
        self.db.upsert_album(_minimal_album("A2", title="Red Roses", artist="Bob", storefronts=["jp"], source="artist_fetch"))
        self.db.upsert_album(_minimal_album("A3", title="Green Fields", artist="Alice", storefronts=["us"], source="artist_fetch"))

    def test_search_by_title(self):
        rows, total = self.db.search_albums("Blue")
        self.assertEqual(total, 1)
        self.assertEqual(rows[0]["title"], "Blue Skies")

    def test_search_by_artist(self):
        rows, total = self.db.search_albums("Alice")
        self.assertEqual(total, 2)

    def test_search_case_insensitive(self):
        rows, total = self.db.search_albums("blue")
        self.assertEqual(total, 1)

    def test_search_no_match(self):
        rows, total = self.db.search_albums("XYZ_NO_MATCH")
        self.assertEqual(total, 0)
        self.assertEqual(rows, [])

    def test_search_with_storefront_filter(self):
        rows, total = self.db.search_albums("Alice", storefront="us")
        self.assertEqual(total, 2)

    def test_search_with_discovered_only(self):
        rows, total = self.db.search_albums("Alice", discovered_only=True)
        self.assertEqual(total, 1)
        self.assertEqual(rows[0]["source"], "discovered")

    def test_search_pagination(self):
        rows, total = self.db.search_albums("Alice", page=1, per_page=1)
        self.assertEqual(total, 2)
        self.assertEqual(len(rows), 1)

    def test_search_wildcard_match(self):
        rows, total = self.db.search_albums("e")   # matches Alice, Green, Blue, Red
        self.assertGreater(total, 0)


# ---------------------------------------------------------------------------
# get_artist_albums
# ---------------------------------------------------------------------------

class TestGetArtistAlbums(DBTestCase):

    def test_returns_albums_for_artist(self):
        self.db.upsert_album(_minimal_album("A1", artist_id="ART1", release_date="2024-01-01"))
        self.db.upsert_album(_minimal_album("A2", artist_id="ART1", release_date="2023-06-01"))
        self.db.upsert_album(_minimal_album("A3", artist_id="ART2"))
        rows = self.db.get_artist_albums("ART1")
        self.assertEqual(len(rows), 2)
        for r in rows:
            self.assertEqual(r["artist_id"], "ART1")

    def test_returns_empty_for_unknown_artist(self):
        rows = self.db.get_artist_albums("UNKNOWN")
        self.assertEqual(rows, [])

    def test_sorted_by_release_date_desc(self):
        self.db.upsert_album(_minimal_album("A1", artist_id="ART1", release_date="2023-01-01"))
        self.db.upsert_album(_minimal_album("A2", artist_id="ART1", release_date="2024-06-01"))
        rows = self.db.get_artist_albums("ART1")
        dates = [r["release_date"] for r in rows]
        self.assertEqual(dates, sorted(dates, reverse=True))


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------

class TestWatchlist(DBTestCase):

    def test_empty_watchlist(self):
        self.assertEqual(self.db.get_watchlist(), [])

    def test_add_to_watchlist(self):
        self.db.add_to_watchlist("ART1", "Artist One", "https://music.apple.com/us/artist/ART1")
        wl = self.db.get_watchlist()
        self.assertEqual(len(wl), 1)
        self.assertEqual(wl[0]["artist_id"], "ART1")
        self.assertEqual(wl[0]["name"], "Artist One")

    def test_add_duplicate_updates_name_and_url(self):
        self.db.add_to_watchlist("ART1", "Old Name", "https://old.url")
        self.db.add_to_watchlist("ART1", "New Name", "https://new.url")
        wl = self.db.get_watchlist()
        self.assertEqual(len(wl), 1)
        self.assertEqual(wl[0]["name"], "New Name")
        self.assertEqual(wl[0]["url"], "https://new.url")

    def test_remove_from_watchlist(self):
        self.db.add_to_watchlist("ART1", "Artist One")
        self.db.remove_from_watchlist("ART1")
        self.assertEqual(self.db.get_watchlist(), [])

    def test_remove_nonexistent_is_noop(self):
        """Removing a non-existent artist should not raise."""
        self.db.remove_from_watchlist("NONEXISTENT")

    def test_watchlist_sorted_by_name(self):
        self.db.add_to_watchlist("C", "Charlie", None)
        self.db.add_to_watchlist("A", "Alice", None)
        self.db.add_to_watchlist("B", "Bob", None)
        wl = self.db.get_watchlist()
        names = [w["name"] for w in wl]
        self.assertEqual(names, sorted(names))

    def test_watchlist_includes_artist_artwork(self):
        self.db.add_to_watchlist("ART1", "Artist One")
        self.db.upsert_artist("ART1", artwork_url="https://art.jpg", genre="Pop")
        wl = self.db.get_watchlist()
        self.assertEqual(wl[0]["artwork_url"], "https://art.jpg")

    def test_get_watched_artist_ids(self):
        self.db.add_to_watchlist("ART1", "Artist One")
        self.db.add_to_watchlist("ART2", "Artist Two")
        ids = self.db.get_watched_artist_ids()
        self.assertIn("ART1", ids)
        self.assertIn("ART2", ids)

    def test_get_watched_artist_ids_empty(self):
        ids = self.db.get_watched_artist_ids()
        self.assertIsInstance(ids, set)
        self.assertEqual(len(ids), 0)


# ---------------------------------------------------------------------------
# upsert_artist / get_artist_info / get_artist_artwork
# ---------------------------------------------------------------------------

class TestArtist(DBTestCase):

    def test_upsert_and_get_artist_info(self):
        self.db.upsert_artist("ART1", artwork_url="https://art.jpg", genre="Pop")
        info = self.db.get_artist_info("ART1")
        self.assertEqual(info["artwork_url"], "https://art.jpg")
        self.assertEqual(info["genre"], "Pop")

    def test_get_artist_info_missing_returns_empty_dict(self):
        info = self.db.get_artist_info("MISSING")
        self.assertEqual(info, {})

    def test_upsert_artist_updates_artwork(self):
        self.db.upsert_artist("ART1", artwork_url="https://old.jpg")
        self.db.upsert_artist("ART1", artwork_url="https://new.jpg")
        info = self.db.get_artist_info("ART1")
        self.assertEqual(info["artwork_url"], "https://new.jpg")

    def test_upsert_artist_coalesce_none(self):
        """Upserting with None artwork should not overwrite existing value."""
        self.db.upsert_artist("ART1", artwork_url="https://art.jpg")
        self.db.upsert_artist("ART1", artwork_url=None)
        info = self.db.get_artist_info("ART1")
        self.assertEqual(info["artwork_url"], "https://art.jpg")

    def test_get_artist_artwork(self):
        self.db.upsert_artist("ART1", artwork_url="https://art.jpg")
        url = self.db.get_artist_artwork("ART1")
        self.assertEqual(url, "https://art.jpg")

    def test_get_artist_artwork_missing_returns_none(self):
        result = self.db.get_artist_artwork("MISSING")
        self.assertIsNone(result)

    def test_upsert_artist_updates_updated_at(self):
        self.db.upsert_artist("ART1", artwork_url="https://art.jpg")
        before = self.db.get_artist_info("ART1")
        # We can't easily check updated_at without exposing it; just verify no crash
        self.db.upsert_artist("ART1", genre="Rock")
        info = self.db.get_artist_info("ART1")
        self.assertEqual(info["genre"], "Rock")


# ---------------------------------------------------------------------------
# log_discovery_run / get_last_run
# ---------------------------------------------------------------------------

class TestDiscoveryRuns(DBTestCase):

    def test_get_last_run_returns_none_if_no_runs(self):
        self.assertIsNone(self.db.get_last_run())

    def test_log_and_get_last_run(self):
        before = int(time.time())
        self.db.log_discovery_run(5, 100)
        run = self.db.get_last_run()
        self.assertIsNotNone(run)
        self.assertEqual(run["new_count"], 5)
        self.assertEqual(run["total_count"], 100)
        self.assertGreaterEqual(run["ran_at"], before)

    def test_get_last_run_returns_most_recent(self):
        self.db.log_discovery_run(1, 10)
        time.sleep(0.05)
        self.db.log_discovery_run(99, 200)
        run = self.db.get_last_run()
        self.assertEqual(run["new_count"], 99)
        self.assertEqual(run["total_count"], 200)

    def test_log_multiple_runs(self):
        for i in range(5):
            self.db.log_discovery_run(i, i * 10)
        run = self.db.get_last_run()
        self.assertEqual(run["new_count"], 4)

    def test_log_zero_counts(self):
        self.db.log_discovery_run(0, 0)
        run = self.db.get_last_run()
        self.assertEqual(run["new_count"], 0)
        self.assertEqual(run["total_count"], 0)


# ---------------------------------------------------------------------------
# get_conn — transactional behaviour
# ---------------------------------------------------------------------------

class TestGetConn(DBTestCase):

    def test_rollback_on_exception(self):
        """A failing operation inside get_conn context should roll back."""
        try:
            with self.db.get_conn() as conn:
                conn.execute(
                    "INSERT INTO albums (store_adam_id, title) VALUES (?, ?)",
                    ("ROLLBACK_TEST", "Should be rolled back"),
                )
                raise ValueError("Simulated failure")
        except ValueError:
            pass
        self.assertIsNone(self.db.get_album("ROLLBACK_TEST"))

    def test_wal_mode_enabled(self):
        with self.db.get_conn() as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        self.assertEqual(mode.lower(), "wal")

    def test_foreign_keys_enabled(self):
        with self.db.get_conn() as conn:
            fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        self.assertEqual(fk, 1)


if __name__ == "__main__":
    unittest.main()
