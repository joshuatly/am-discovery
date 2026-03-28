"""Comprehensive unit tests for db.py — SQLite database layer.

Strategy:
- Override DB_PATH via os.environ before importing db, so every test gets an
  isolated in-memory / temp-file database.
- Each test class reinitialises the database to guarantee a clean slate.
"""

import json
import os
import shutil
import sqlite3
import tempfile
import time
import unittest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_temp_db():
    """Return (tmpdir, db_path) for an isolated, fresh database.

    Each call produces a unique temp directory so tearDown can safely
    shutil.rmtree the whole directory — removing the main .db file plus
    any SQLite WAL artefacts (.db-wal, .db-shm) without risking touching
    files that belong to other tests.
    """
    tmpdir = tempfile.mkdtemp()
    return tmpdir, os.path.join(tmpdir, "test.db")


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
        self.db_dir, self.db_path = _make_temp_db()
        os.environ["AM_DB_PATH"] = self.db_path
        # Re-import to pick up the new path
        import importlib

        import db

        importlib.reload(db)
        db.init_db()
        self.db = db

    def tearDown(self):
        shutil.rmtree(self.db_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# init_db
# ---------------------------------------------------------------------------


class TestInitDb(DBTestCase):
    def test_fresh_db_creates_all_tables(self):
        """All expected tables exist after init_db on a fresh database."""
        with self.db.get_conn() as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
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

        import importlib

        import db

        db.DB_PATH = path
        importlib.reload(db)
        db.DB_PATH = path  # reload resets env; set explicitly

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

    def test_artists_json_stored_as_json_string(self):
        """artists_json is serialized to a JSON string in the DB."""
        artists = [
            {
                "id": "A1",
                "name": "Artist One",
                "url": "https://music.apple.com/us/artist/1",
                "artwork_url": "https://example.com/art.jpg",
                "genre": "Pop",
            },
        ]
        self.db.upsert_album(_minimal_album(artists_json=artists))
        row = self.db.get_album("123456")
        parsed = json.loads(row["artists_json"])
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["id"], "A1")
        self.assertEqual(parsed[0]["name"], "Artist One")
        self.assertEqual(parsed[0]["artwork_url"], "https://example.com/art.jpg")
        self.assertEqual(parsed[0]["genre"], "Pop")

    def test_artists_json_multiple_artists(self):
        """artists_json stores all artists for a collab album."""
        artists = [
            {"id": "A1", "name": "Artist One", "url": "https://music.apple.com/us/artist/1"},
            {"id": "A2", "name": "Artist Two", "url": "https://music.apple.com/us/artist/2"},
        ]
        self.db.upsert_album(_minimal_album(artists_json=artists))
        row = self.db.get_album("123456")
        parsed = json.loads(row["artists_json"])
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[1]["id"], "A2")

    def test_artists_json_coalesce_does_not_overwrite_with_none(self):
        """artists_json=None in an upsert should not overwrite existing value."""
        artists = [{"id": "A1", "name": "Artist One", "url": None}]
        self.db.upsert_album(_minimal_album(artists_json=artists))
        self.db.upsert_album(_minimal_album(artists_json=None))
        row = self.db.get_album("123456")
        parsed = json.loads(row["artists_json"])
        self.assertEqual(parsed[0]["id"], "A1")

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
        self.db.upsert_album(
            _minimal_album(
                "A1",
                title="Alpha",
                artist="Zara",
                release_date="2024-03-01",
                source="discovered",
                storefronts=["us"],
            ),
        )
        self.db.upsert_album(
            _minimal_album(
                "A2",
                title="Beta",
                artist="Adam",
                release_date="2024-01-01",
                source="artist_fetch",
                storefronts=["jp"],
            ),
        )
        self.db.upsert_album(
            _minimal_album(
                "A3",
                title="Gamma",
                artist="Zara",
                release_date="2024-02-01",
                source="discovered",
                storefronts=["us", "jp"],
            ),
        )

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
        self.db.upsert_album(
            _minimal_album("A1", title="Blue Skies", artist="Alice", storefronts=["us"], source="discovered"),
        )
        self.db.upsert_album(
            _minimal_album("A2", title="Red Roses", artist="Bob", storefronts=["jp"], source="artist_fetch"),
        )
        self.db.upsert_album(
            _minimal_album(
                "A3",
                title="Green Fields",
                artist="Alice",
                storefronts=["us"],
                source="artist_fetch",
            ),
        )

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
        rows, total = self.db.search_albums("e")  # matches Alice, Green, Blue, Red
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

    def test_returns_album_where_artist_is_secondary_in_artists_json(self):
        # Album's primary artist_id is ART_PRIMARY, but ART_SECONDARY appears in artists_json
        artists = [
            {"id": "ART_PRIMARY", "name": "Primary Artist", "url": "", "artwork_url": None, "genre": None},
            {"id": "ART_SECONDARY", "name": "Secondary Artist", "url": "", "artwork_url": None, "genre": None},
        ]
        self.db.upsert_album(
            _minimal_album("COLLAB1", artist_id="ART_PRIMARY", artists_json=artists)
        )
        # Should appear when querying primary artist
        rows = self.db.get_artist_albums("ART_PRIMARY")
        self.assertEqual(len(rows), 1)
        # Should also appear when querying secondary artist
        rows = self.db.get_artist_albums("ART_SECONDARY")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["store_adam_id"], "COLLAB1")

    def test_no_duplicate_when_artist_is_both_primary_and_in_artists_json(self):
        artists = [
            {"id": "ART1", "name": "Artist One", "url": "", "artwork_url": None, "genre": None},
        ]
        self.db.upsert_album(
            _minimal_album("A1", artist_id="ART1", artists_json=artists)
        )
        rows = self.db.get_artist_albums("ART1")
        self.assertEqual(len(rows), 1)


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

    def test_watchlist_sort_by_added(self):
        self.db.add_to_watchlist("A1", "Alice", None)
        self.db.add_to_watchlist("A2", "Bob", None)
        self.db.add_to_watchlist("A3", "Charlie", None)
        # Set distinct added_at values directly so sort order is deterministic
        with self.db.get_conn() as conn:
            conn.execute("UPDATE watched_artists SET added_at = 100 WHERE artist_id = 'A1'")
            conn.execute("UPDATE watched_artists SET added_at = 200 WHERE artist_id = 'A2'")
            conn.execute("UPDATE watched_artists SET added_at = 300 WHERE artist_id = 'A3'")
        wl = self.db.get_watchlist(sort="added")
        names = [w["name"] for w in wl]
        self.assertEqual(names, ["Charlie", "Bob", "Alice"])

    def test_watchlist_sort_by_recent_release(self):
        self.db.add_to_watchlist("A1", "Alice", None)
        self.db.add_to_watchlist("A2", "Bob", None)
        self.db.add_to_watchlist("A3", "Charlie", None)
        self.db.upsert_album(_minimal_album(store_adam_id="R1", artist_id="A1", release_date="2024-06-01"))
        self.db.upsert_album(_minimal_album(store_adam_id="R2", artist_id="A2", release_date="2024-12-01"))
        wl = self.db.get_watchlist(sort="recent_release")
        names = [w["name"] for w in wl]
        # Bob has newest release, Alice next, Charlie has no release (NULLS LAST)
        self.assertEqual(names[0], "Bob")
        self.assertEqual(names[1], "Alice")
        self.assertEqual(names[2], "Charlie")

    def test_watchlist_includes_latest_release_date(self):
        self.db.add_to_watchlist("A1", "Alice", None)
        self.db.upsert_album(_minimal_album(store_adam_id="R1", artist_id="A1", release_date="2024-03-15"))
        self.db.upsert_album(_minimal_album(store_adam_id="R2", artist_id="A1", release_date="2024-11-20"))
        wl = self.db.get_watchlist()
        self.assertEqual(wl[0]["latest_release_date"], "2024-11-20")

    def test_watchlist_latest_release_date_none_when_no_albums(self):
        self.db.add_to_watchlist("A1", "Alice", None)
        wl = self.db.get_watchlist()
        self.assertIsNone(wl[0]["latest_release_date"])

    def test_watchlist_invalid_sort_defaults_to_name(self):
        self.db.add_to_watchlist("C", "Charlie", None)
        self.db.add_to_watchlist("A", "Alice", None)
        wl = self.db.get_watchlist(sort="bogus")
        names = [w["name"] for w in wl]
        self.assertEqual(names, sorted(names))

    def test_watchlist_includes_artist_artwork(self):
        self.db.add_to_watchlist("ART1", "Artist One")
        self.db.upsert_artist("ART1", artwork_url="https://art.jpg", genre="Pop")
        wl = self.db.get_watchlist()
        self.assertEqual(wl[0]["artwork_url"], "https://art.jpg")

    def test_watchlist_includes_artist_bio(self):
        self.db.add_to_watchlist("ART1", "Artist One")
        self.db.upsert_artist("ART1", artist_bio="A pioneering rock band from London.")
        wl = self.db.get_watchlist()
        self.assertEqual(wl[0]["artist_bio"], "A pioneering rock band from London.")

    def test_watchlist_artist_bio_none_when_not_set(self):
        self.db.add_to_watchlist("ART1", "Artist One")
        wl = self.db.get_watchlist()
        self.assertIsNone(wl[0]["artist_bio"])

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
        self.db.upsert_artist("ART1", name="Jay Chou", artwork_url="https://art.jpg", genre="Pop")
        info = self.db.get_artist_info("ART1")
        self.assertEqual(info["name"], "Jay Chou")
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
        """Upserting with None values should not overwrite existing values."""
        self.db.upsert_artist("ART1", name="Jay Chou", artwork_url="https://art.jpg")
        self.db.upsert_artist("ART1", name=None, artwork_url=None)
        info = self.db.get_artist_info("ART1")
        self.assertEqual(info["name"], "Jay Chou")
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
        # We can't easily check updated_at without exposing it; just verify no crash
        self.db.upsert_artist("ART1", genre="Rock")
        info = self.db.get_artist_info("ART1")
        self.assertEqual(info["genre"], "Rock")

    def test_upsert_and_get_born_or_formed_origin_bio(self):
        self.db.upsert_artist(
            "ART1",
            born_or_formed="Born July 27, 1974",
            origin="Hong Kong",
            artist_bio="Legendary Cantopop artist.",
            is_group=False,
        )
        info = self.db.get_artist_info("ART1")
        self.assertEqual(info["born_or_formed"], "Born July 27, 1974")
        self.assertEqual(info["origin"], "Hong Kong")
        self.assertEqual(info["artist_bio"], "Legendary Cantopop artist.")
        self.assertEqual(info["is_group"], 0)

    def test_upsert_artist_is_group_true(self):
        self.db.upsert_artist("ART1", is_group=True)
        info = self.db.get_artist_info("ART1")
        self.assertEqual(info["is_group"], 1)

    def test_upsert_artist_coalesce_new_fields(self):
        """None values for the new fields should not overwrite existing values."""
        self.db.upsert_artist("ART1", born_or_formed="Formed 2016", origin="Newcastle, England", is_group=True)
        self.db.upsert_artist("ART1", born_or_formed=None, origin=None, artist_bio=None, is_group=None)
        info = self.db.get_artist_info("ART1")
        self.assertEqual(info["born_or_formed"], "Formed 2016")
        self.assertEqual(info["origin"], "Newcastle, England")
        self.assertEqual(info["is_group"], 1)


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


# ---------------------------------------------------------------------------
# Watchlist — preferred_source and last_refreshed
# ---------------------------------------------------------------------------


class TestWatchlistPreferredSource(DBTestCase):
    def test_add_with_preferred_source(self):
        self.db.add_to_watchlist("ART1", "Artist One", "https://url", preferred_source="jp")
        wl = self.db.get_watchlist()
        self.assertEqual(wl[0]["preferred_source"], "jp")

    def test_add_without_preferred_source(self):
        self.db.add_to_watchlist("ART1", "Artist One")
        wl = self.db.get_watchlist()
        self.assertIsNone(wl[0]["preferred_source"])

    def test_update_preserves_preferred_source_when_not_provided(self):
        self.db.add_to_watchlist("ART1", "Artist One", preferred_source="jp")
        self.db.add_to_watchlist("ART1", "Artist One Updated")
        wl = self.db.get_watchlist()
        self.assertEqual(wl[0]["preferred_source"], "jp")

    def test_update_overrides_preferred_source_when_provided(self):
        self.db.add_to_watchlist("ART1", "Artist One", preferred_source="jp")
        self.db.add_to_watchlist("ART1", "Artist One", preferred_source="us")
        wl = self.db.get_watchlist()
        self.assertEqual(wl[0]["preferred_source"], "us")

    def test_filter_by_preferred_source(self):
        self.db.add_to_watchlist("ART1", "Artist One", preferred_source="jp")
        self.db.add_to_watchlist("ART2", "Artist Two", preferred_source="us")
        self.db.add_to_watchlist("ART3", "Artist Three")

        jp_list = self.db.get_watchlist(preferred_source="jp")
        self.assertEqual(len(jp_list), 1)
        self.assertEqual(jp_list[0]["artist_id"], "ART1")

        us_list = self.db.get_watchlist(preferred_source="us")
        self.assertEqual(len(us_list), 1)
        self.assertEqual(us_list[0]["artist_id"], "ART2")

    def test_filter_empty_returns_all(self):
        self.db.add_to_watchlist("ART1", "Artist One", preferred_source="jp")
        self.db.add_to_watchlist("ART2", "Artist Two")
        wl = self.db.get_watchlist(preferred_source="")
        self.assertEqual(len(wl), 2)


# ---------------------------------------------------------------------------
# update_preferred_source
# ---------------------------------------------------------------------------


class TestUpdatePreferredSource(DBTestCase):
    def test_set_preferred_source(self):
        self.db.add_to_watchlist("ART1", "Artist One")
        self.db.update_preferred_source("ART1", "jp")
        wl = self.db.get_watchlist()
        self.assertEqual(wl[0]["preferred_source"], "jp")

    def test_change_preferred_source(self):
        self.db.add_to_watchlist("ART1", "Artist One", preferred_source="jp")
        self.db.update_preferred_source("ART1", "us")
        wl = self.db.get_watchlist()
        self.assertEqual(wl[0]["preferred_source"], "us")

    def test_clear_preferred_source(self):
        """Setting to None explicitly clears the value."""
        self.db.add_to_watchlist("ART1", "Artist One", preferred_source="jp")
        self.db.update_preferred_source("ART1", None)
        wl = self.db.get_watchlist()
        self.assertIsNone(wl[0]["preferred_source"])

    def test_noop_for_nonexistent_artist(self):
        """Updating a non-existent artist should not raise."""
        self.db.update_preferred_source("NONEXISTENT", "jp")


# ---------------------------------------------------------------------------
# get_artists_needing_refresh / mark_artist_refreshed
# ---------------------------------------------------------------------------


class TestArtistRefresh(DBTestCase):
    def test_returns_unrefreshed_artists(self):
        self.db.add_to_watchlist("ART1", "Artist One")
        self.db.add_to_watchlist("ART2", "Artist Two")
        artists = self.db.get_artists_needing_refresh(batch_size=10, refresh_interval_days=7)
        self.assertEqual(len(artists), 2)

    def test_respects_batch_size(self):
        self.db.add_to_watchlist("ART1", "Alice")
        self.db.add_to_watchlist("ART2", "Bob")
        self.db.add_to_watchlist("ART3", "Charlie")
        artists = self.db.get_artists_needing_refresh(batch_size=2, refresh_interval_days=7)
        self.assertEqual(len(artists), 2)

    def test_skips_recently_refreshed(self):
        self.db.add_to_watchlist("ART1", "Artist One")
        self.db.mark_artist_refreshed("ART1")
        artists = self.db.get_artists_needing_refresh(batch_size=10, refresh_interval_days=7)
        self.assertEqual(len(artists), 0)

    def test_includes_stale_artists(self):
        self.db.add_to_watchlist("ART1", "Artist One")
        # Set last_refreshed to 8 days ago
        with self.db.get_conn() as conn:
            old_ts = int(time.time()) - (8 * 86400)
            conn.execute(
                "UPDATE watched_artists SET last_refreshed = ? WHERE artist_id = ?",
                (old_ts, "ART1"),
            )
        artists = self.db.get_artists_needing_refresh(batch_size=10, refresh_interval_days=7)
        self.assertEqual(len(artists), 1)

    def test_mark_artist_refreshed(self):
        self.db.add_to_watchlist("ART1", "Artist One")
        self.db.mark_artist_refreshed("ART1")
        with self.db.get_conn() as conn:
            row = conn.execute("SELECT last_refreshed FROM watched_artists WHERE artist_id = ?", ("ART1",)).fetchone()
        self.assertIsNotNone(row["last_refreshed"])
        self.assertGreater(row["last_refreshed"], 0)

    def test_null_refreshed_ordered_first(self):
        """Artists with NULL last_refreshed should come before those with old timestamps."""
        self.db.add_to_watchlist("ART1", "Alice")
        self.db.add_to_watchlist("ART2", "Bob")
        # ART1 refreshed 10 days ago, ART2 never
        with self.db.get_conn() as conn:
            old_ts = int(time.time()) - (10 * 86400)
            conn.execute(
                "UPDATE watched_artists SET last_refreshed = ? WHERE artist_id = ?",
                (old_ts, "ART1"),
            )
        artists = self.db.get_artists_needing_refresh(batch_size=10, refresh_interval_days=7)
        self.assertEqual(artists[0]["artist_id"], "ART2")

    def test_preferred_source_returned(self):
        self.db.add_to_watchlist("ART1", "Artist One", preferred_source="jp")
        artists = self.db.get_artists_needing_refresh(batch_size=10, refresh_interval_days=7)
        self.assertEqual(artists[0]["preferred_source"], "jp")


# ---------------------------------------------------------------------------
# export_watchlist / import_watchlist
# ---------------------------------------------------------------------------


class TestWatchlistImportExport(DBTestCase):
    def test_export_empty(self):
        result = self.db.export_watchlist()
        self.assertEqual(result, [])

    def test_export_returns_correct_fields(self):
        self.db.add_to_watchlist("ART1", "Artist One", "https://url", preferred_source="jp")
        result = self.db.export_watchlist()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["artist_id"], "ART1")
        self.assertEqual(result[0]["name"], "Artist One")
        self.assertEqual(result[0]["url"], "https://url")
        self.assertEqual(result[0]["preferred_source"], "jp")

    def test_export_sorted_by_name(self):
        self.db.add_to_watchlist("C", "Charlie")
        self.db.add_to_watchlist("A", "Alice")
        self.db.add_to_watchlist("B", "Bob")
        result = self.db.export_watchlist()
        names = [r["name"] for r in result]
        self.assertEqual(names, ["Alice", "Bob", "Charlie"])

    def test_import_adds_artists(self):
        artists = [
            {
                "artist_id": "ART1",
                "name": "Artist One",
                "url": "https://url1",
                "preferred_source": "jp",
            },
            {"artist_id": "ART2", "name": "Artist Two", "url": "https://url2"},
        ]
        self.db.import_watchlist(artists)
        wl = self.db.get_watchlist()
        self.assertEqual(len(wl), 2)

    def test_import_upsert_semantics(self):
        self.db.add_to_watchlist("ART1", "Old Name", preferred_source="jp")
        artists = [{"artist_id": "ART1", "name": "New Name"}]
        self.db.import_watchlist(artists)
        wl = self.db.get_watchlist()
        self.assertEqual(len(wl), 1)
        self.assertEqual(wl[0]["name"], "New Name")
        # preferred_source preserved when not provided in import
        self.assertEqual(wl[0]["preferred_source"], "jp")

    def test_roundtrip_export_import(self):
        self.db.add_to_watchlist("ART1", "Artist One", "https://url1", preferred_source="jp")
        self.db.add_to_watchlist("ART2", "Artist Two", "https://url2", preferred_source="us")
        exported = self.db.export_watchlist()
        # Clear and reimport
        self.db.remove_from_watchlist("ART1")
        self.db.remove_from_watchlist("ART2")
        self.assertEqual(self.db.get_watchlist(), [])
        self.db.import_watchlist(exported)
        wl = self.db.get_watchlist()
        self.assertEqual(len(wl), 2)
        by_id = {a["artist_id"]: a for a in wl}
        self.assertEqual(by_id["ART1"]["preferred_source"], "jp")
        self.assertEqual(by_id["ART2"]["preferred_source"], "us")


# ---------------------------------------------------------------------------
# list_albums / search_albums — watched_only filter
# ---------------------------------------------------------------------------


class TestWatchedOnlyFilter(DBTestCase):
    def setUp(self):
        super().setUp()
        self.db.upsert_album(_minimal_album("A1", artist_id="ART1", title="Alpha"))
        self.db.upsert_album(_minimal_album("A2", artist_id="ART2", title="Beta"))
        self.db.upsert_album(_minimal_album("A3", artist_id="ART3", title="Gamma"))
        self.db.add_to_watchlist("ART1", "Artist One")
        self.db.add_to_watchlist("ART3", "Artist Three")

    def test_list_albums_watched_only(self):
        rows, total = self.db.list_albums(watched_only=True)
        self.assertEqual(total, 2)
        ids = {r["artist_id"] for r in rows}
        self.assertIn("ART1", ids)
        self.assertIn("ART3", ids)
        self.assertNotIn("ART2", ids)

    def test_list_albums_watched_only_false(self):
        rows, total = self.db.list_albums(watched_only=False)
        self.assertEqual(total, 3)

    def test_search_albums_watched_only(self):
        rows, total = self.db.search_albums("a", watched_only=True)
        for r in rows:
            self.assertIn(r["artist_id"], {"ART1", "ART3"})

    def test_list_albums_watched_only_combined_with_discovered(self):
        # setUp has A1(ART1,discovered), A2(ART2,discovered), A3(ART3,discovered)
        # Watchlist: ART1, ART3
        # Add a non-discovered album for ART1
        self.db.upsert_album(_minimal_album("D1", artist_id="ART1", source="artist_fetch"))
        # watched_only + discovered_only: A1 (ART1,discovered) and A3 (ART3,discovered)
        rows, total = self.db.list_albums(watched_only=True, discovered_only=True)
        self.assertEqual(total, 2)
        for r in rows:
            self.assertEqual(r["source"], "discovered")
            self.assertIn(r["artist_id"], {"ART1", "ART3"})


# ---------------------------------------------------------------------------
# Collection Status
# ---------------------------------------------------------------------------


class TestCollectionStatus(DBTestCase):
    def test_new_artist_has_new_status(self):
        self.db.add_to_watchlist("ART1", "Artist One")
        wl = self.db.get_watchlist()
        self.assertEqual(wl[0]["collection_status"], "new")
        self.assertIsNotNone(wl[0]["collection_status_updated_at"])

    def test_transition_new_to_complete(self):
        self.db.add_to_watchlist("ART1", "Artist One")
        result = self.db.update_collection_status("ART1", "complete")
        self.assertTrue(result)
        wl = self.db.get_watchlist()
        self.assertEqual(wl[0]["collection_status"], "complete")

    def test_transition_new_to_in_progress(self):
        self.db.add_to_watchlist("ART1", "Artist One")
        result = self.db.update_collection_status("ART1", "in_progress")
        self.assertTrue(result)
        wl = self.db.get_watchlist()
        self.assertEqual(wl[0]["collection_status"], "in_progress")

    def test_transition_new_to_new_release_blocked(self):
        self.db.add_to_watchlist("ART1", "Artist One")
        result = self.db.update_collection_status("ART1", "new_release")
        self.assertFalse(result)
        wl = self.db.get_watchlist()
        self.assertEqual(wl[0]["collection_status"], "new")

    def test_transition_complete_to_in_progress(self):
        """Complete can transition to in_progress per the state machine."""
        self.db.add_to_watchlist("ART1", "Artist One")
        self.db.update_collection_status("ART1", "complete")
        # complete -> in_progress is NOT in transitions (only complete -> new_release auto)
        # Actually per the plan, complete can go to in_progress. Let me check COLLECTION_TRANSITIONS.
        # complete -> {new_release, in_progress} is not set — let me check what we defined.
        # We defined: complete -> {new_release} only for auto, but user can't set new_release manually.
        # Wait, looking at COLLECTION_TRANSITIONS in db.py:
        # "complete": {"new_release", "in_progress"}
        # So complete -> in_progress IS allowed.
        result = self.db.update_collection_status("ART1", "in_progress")
        self.assertTrue(result)

    def test_transition_back_to_new_blocked(self):
        self.db.add_to_watchlist("ART1", "Artist One")
        self.db.update_collection_status("ART1", "complete")
        result = self.db.update_collection_status("ART1", "new")
        self.assertFalse(result)

    def test_transition_in_progress_to_complete(self):
        self.db.add_to_watchlist("ART1", "Artist One")
        self.db.update_collection_status("ART1", "in_progress")
        result = self.db.update_collection_status("ART1", "complete")
        self.assertTrue(result)

    def test_transition_new_release_to_complete(self):
        self.db.add_to_watchlist("ART1", "Artist One")
        self.db.update_collection_status("ART1", "complete")
        # Force new_release via direct SQL (simulating auto transition)
        import db as _db

        with _db.get_conn() as conn:
            conn.execute(
                "UPDATE watched_artists SET collection_status = 'new_release' WHERE artist_id = ?",
                ("ART1",),
            )
        result = self.db.update_collection_status("ART1", "complete")
        self.assertTrue(result)

    def test_transition_new_release_to_in_progress(self):
        self.db.add_to_watchlist("ART1", "Artist One")
        self.db.update_collection_status("ART1", "complete")
        import db as _db

        with _db.get_conn() as conn:
            conn.execute(
                "UPDATE watched_artists SET collection_status = 'new_release' WHERE artist_id = ?",
                ("ART1",),
            )
        result = self.db.update_collection_status("ART1", "in_progress")
        self.assertTrue(result)

    def test_invalid_status_value(self):
        self.db.add_to_watchlist("ART1", "Artist One")
        result = self.db.update_collection_status("ART1", "invalid_status")
        self.assertFalse(result)

    def test_update_nonexistent_artist(self):
        result = self.db.update_collection_status("MISSING", "complete")
        self.assertFalse(result)

    def test_filter_by_collection_status(self):
        self.db.add_to_watchlist("ART1", "Artist One")
        self.db.add_to_watchlist("ART2", "Artist Two")
        self.db.update_collection_status("ART1", "complete")
        wl = self.db.get_watchlist(collection_status="complete")
        self.assertEqual(len(wl), 1)
        self.assertEqual(wl[0]["artist_id"], "ART1")
        wl_new = self.db.get_watchlist(collection_status="new")
        self.assertEqual(len(wl_new), 1)
        self.assertEqual(wl_new[0]["artist_id"], "ART2")

    def test_status_updated_at_changes(self):
        self.db.add_to_watchlist("ART1", "Artist One")
        wl = self.db.get_watchlist()
        ts1 = wl[0]["collection_status_updated_at"]
        time.sleep(0.05)
        self.db.update_collection_status("ART1", "complete")
        wl = self.db.get_watchlist()
        ts2 = wl[0]["collection_status_updated_at"]
        self.assertGreaterEqual(ts2, ts1)

    def test_export_includes_collection_status(self):
        self.db.add_to_watchlist("ART1", "Artist One")
        self.db.update_collection_status("ART1", "complete")
        exported = self.db.export_watchlist()
        self.assertEqual(exported[0]["collection_status"], "complete")
        self.assertIn("collection_status_updated_at", exported[0])

    def test_import_preserves_collection_status(self):
        artists = [
            {
                "artist_id": "ART1",
                "name": "Artist One",
                "collection_status": "complete",
                "collection_status_updated_at": 1700000000,
            },
        ]
        self.db.import_watchlist(artists)
        wl = self.db.get_watchlist()
        self.assertEqual(wl[0]["collection_status"], "complete")
        self.assertEqual(wl[0]["collection_status_updated_at"], 1700000000)

    def test_import_defaults_to_new(self):
        artists = [{"artist_id": "ART1", "name": "Artist One"}]
        self.db.import_watchlist(artists)
        wl = self.db.get_watchlist()
        self.assertEqual(wl[0]["collection_status"], "new")


class TestCheckAndUpdateNewReleases(DBTestCase):
    def _add_album(self, store_id, artist_id, release_date):
        self.db.upsert_album(
            {
                "store_adam_id": store_id,
                "title": f"Album {store_id}",
                "artist_id": artist_id,
                "storefronts": [],
                "source": "artist_fetch",
            }
        )
        # Set release_date directly
        import db as _db

        with _db.get_conn() as conn:
            conn.execute(
                "UPDATE albums SET release_date = ? WHERE store_adam_id = ?",
                (release_date, store_id),
            )

    def test_no_change_when_status_not_complete(self):
        self.db.add_to_watchlist("ART1", "Artist One")
        self._add_album("A1", "ART1", "2025-06-01")
        result = self.db.check_and_update_new_releases("ART1")
        self.assertFalse(result)

    def test_no_change_when_no_newer_release(self):
        self.db.add_to_watchlist("ART1", "Artist One")
        self._add_album("A1", "ART1", "2020-01-01")
        self.db.update_collection_status("ART1", "complete")
        result = self.db.check_and_update_new_releases("ART1")
        self.assertFalse(result)

    def test_transitions_to_new_release_when_newer_exists(self):
        self.db.add_to_watchlist("ART1", "Artist One")
        self.db.update_collection_status("ART1", "complete")
        # Add album with future date
        self._add_album("A1", "ART1", "2099-01-01")
        result = self.db.check_and_update_new_releases("ART1")
        self.assertTrue(result)
        wl = self.db.get_watchlist()
        self.assertEqual(wl[0]["collection_status"], "new_release")

    def test_no_change_when_in_progress(self):
        self.db.add_to_watchlist("ART1", "Artist One")
        self.db.update_collection_status("ART1", "in_progress")
        self._add_album("A1", "ART1", "2099-01-01")
        result = self.db.check_and_update_new_releases("ART1")
        self.assertFalse(result)
        wl = self.db.get_watchlist()
        self.assertEqual(wl[0]["collection_status"], "in_progress")

    def test_nonexistent_artist(self):
        result = self.db.check_and_update_new_releases("MISSING")
        self.assertFalse(result)

    def test_get_latest_release_date(self):
        self.db.add_to_watchlist("ART1", "Artist One")
        self._add_album("A1", "ART1", "2024-01-15")
        self._add_album("A2", "ART1", "2024-06-20")
        self._add_album("A3", "ART1", "2023-12-01")
        latest = self.db.get_latest_release_date("ART1")
        self.assertEqual(latest, "2024-06-20")

    def test_get_latest_release_date_no_albums(self):
        latest = self.db.get_latest_release_date("ART1")
        self.assertIsNone(latest)


if __name__ == "__main__":
    unittest.main()
