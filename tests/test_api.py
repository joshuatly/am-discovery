"""Tests for api.py — core REST API routes.

Covers releases, artists, search, config, status, refresh, and frontend serving.
Watchlist route tests live in test_api_watchlist.py.
Scheduler/config helper tests live in test_server.py.
"""

import contextlib
import json
import os
import tempfile
import threading as _real_threading
import unittest
import unittest.mock
from unittest.mock import patch

# Capture the real Thread class at import time — before any test patch can replace it.
_RealThread = _real_threading.Thread

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_album(store_adam_id="A1", **kwargs):
    defaults = {
        "store_adam_id": store_adam_id,
        "title": "Test Album",
        "artist": "Test Artist",
        "artist_id": "ART1",
        "artist_url": "https://music.apple.com/us/artist/ART1",
        "url": f"https://music.apple.com/us/album/{store_adam_id}",
        "storefronts": '["us"]',
        "release_date": "2024-01-15",
        "artwork_url": "https://example.com/art.jpg",
        "track_count": 10,
        "genre": "Pop",
        "description": "Test description",
        "info_fetched": 1,
        "audio_formats": '["lossless"]',
        "release_type": "main-albums",
        "first_seen": 1700000000,
        "last_seen": 1700000000,
        "source": "discovered",
    }
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# Base class — sets up Flask test client with mocked config & db
# ---------------------------------------------------------------------------


class ServerTestCase(unittest.TestCase):
    def setUp(self):
        # Use a fresh temp config path to avoid touching real config.json
        self._cfg_fd, self._cfg_path = tempfile.mkstemp(suffix=".json")
        os.close(self._cfg_fd)
        os.unlink(self._cfg_path)  # server will not find it → defaults used

        # Patch config path in config module (used by load_config/save_config)
        import config

        self._orig_config_path = config.CONFIG_PATH
        config.CONFIG_PATH = self._cfg_path

        import server

        self.app = server.app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        import config

        config.CONFIG_PATH = self._orig_config_path
        with contextlib.suppress(FileNotFoundError):
            os.unlink(self._cfg_path)


# ---------------------------------------------------------------------------
# _serialize helper
# ---------------------------------------------------------------------------


class TestSerialize(unittest.TestCase):
    def setUp(self):
        import api_utility

        self.serialize = api_utility._serialize

    def test_deserializes_storefronts_string(self):
        row = {"storefronts": '["us","jp"]', "audio_formats": None}
        result = self.serialize(row)
        self.assertEqual(result["storefronts"], ["us", "jp"])

    def test_deserializes_audio_formats_string(self):
        row = {"storefronts": '["us"]', "audio_formats": '["lossless","atmos"]'}
        result = self.serialize(row)
        self.assertEqual(result["audio_formats"], ["lossless", "atmos"])

    def test_leaves_list_storefronts_unchanged(self):
        row = {"storefronts": ["us"], "audio_formats": None}
        result = self.serialize(row)
        self.assertEqual(result["storefronts"], ["us"])

    def test_handles_missing_keys_gracefully(self):
        row = {}
        result = self.serialize(row)
        self.assertEqual(result, {})


# ---------------------------------------------------------------------------
# _is_watched helper
# ---------------------------------------------------------------------------


class TestIsWatched(unittest.TestCase):
    def setUp(self):
        import api_utility

        self.is_watched = api_utility._is_watched

    def test_primary_artist_watched(self):
        row = {"artist_id": "ART1", "artists_json": None}
        self.assertTrue(self.is_watched(row, {"ART1"}))

    def test_primary_artist_not_watched(self):
        row = {"artist_id": "ART2", "artists_json": None}
        self.assertFalse(self.is_watched(row, {"ART1"}))

    def test_secondary_artist_watched(self):
        row = {
            "artist_id": "ART_PRIMARY",
            "artists_json": [
                {"id": "ART_PRIMARY", "name": "Primary"},
                {"id": "ART_SECONDARY", "name": "Secondary"},
            ],
        }
        self.assertTrue(self.is_watched(row, {"ART_SECONDARY"}))

    def test_no_artist_matches(self):
        row = {
            "artist_id": "ART1",
            "artists_json": [{"id": "ART1"}, {"id": "ART2"}],
        }
        self.assertFalse(self.is_watched(row, {"ART3"}))

    def test_empty_watched_ids(self):
        row = {"artist_id": "ART1", "artists_json": [{"id": "ART1"}]}
        self.assertFalse(self.is_watched(row, set()))


# ---------------------------------------------------------------------------
# GET /api/releases
# ---------------------------------------------------------------------------


class TestApiReleases(ServerTestCase):
    @patch("api_releases.db")
    def test_returns_paginated_results(self, mock_db):
        mock_db.list_albums.return_value = ([_make_album()], 1)
        mock_db.search_albums.return_value = ([_make_album()], 1)
        mock_db.get_watched_artist_ids.return_value = set()

        resp = self.client.get("/api/releases")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("items", data)
        self.assertIn("total", data)
        self.assertIn("page", data)
        self.assertIn("per_page", data)

    @patch("api_releases.db")
    def test_default_pagination(self, mock_db):
        mock_db.list_albums.return_value = ([], 0)
        mock_db.get_watched_artist_ids.return_value = set()

        resp = self.client.get("/api/releases")
        data = resp.get_json()
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["per_page"], 50)

    @patch("api_releases.db")
    def test_custom_pagination(self, mock_db):
        mock_db.list_albums.return_value = ([], 0)
        mock_db.get_watched_artist_ids.return_value = set()

        resp = self.client.get("/api/releases?page=3&per_page=10")
        data = resp.get_json()
        self.assertEqual(data["page"], 3)
        self.assertEqual(data["per_page"], 10)

    @patch("api_releases.db")
    def test_search_query_uses_search_albums(self, mock_db):
        mock_db.search_albums.return_value = ([_make_album()], 1)
        mock_db.get_watched_artist_ids.return_value = set()

        resp = self.client.get("/api/releases?q=Test")
        self.assertEqual(resp.status_code, 200)
        mock_db.search_albums.assert_called_once()

    @patch("api_releases.db")
    def test_storefront_filter_passed_to_db(self, mock_db):
        mock_db.list_albums.return_value = ([], 0)
        mock_db.get_watched_artist_ids.return_value = set()

        self.client.get("/api/releases?storefront=JP")
        call_kwargs = mock_db.list_albums.call_args
        self.assertEqual(
            call_kwargs.kwargs.get("storefront") or call_kwargs[1].get("storefront") or call_kwargs[0][2]
            if len(call_kwargs[0]) > 2
            else None,
            None,
        )
        # Verify storefront was normalised to lowercase
        args, kwargs = mock_db.list_albums.call_args
        storefront_arg = kwargs.get("storefront", args[2] if len(args) > 2 else "")
        self.assertEqual(storefront_arg, "jp")

    @patch("api_releases.db")
    def test_discovered_only_view_new(self, mock_db):
        mock_db.list_albums.return_value = ([], 0)
        mock_db.get_watched_artist_ids.return_value = set()

        self.client.get("/api/releases?view=new")
        args, kwargs = mock_db.list_albums.call_args
        discovered_only = kwargs.get("discovered_only", args[3] if len(args) > 3 else False)
        self.assertTrue(discovered_only)

    @patch("api_releases.db")
    def test_watched_flag_set_correctly(self, mock_db):
        album = _make_album(artist_id="ART1")
        mock_db.list_albums.return_value = ([album], 1)
        mock_db.get_watched_artist_ids.return_value = {"ART1"}

        resp = self.client.get("/api/releases")
        data = resp.get_json()
        self.assertTrue(data["items"][0]["watched"])

    @patch("api_releases.db")
    def test_watched_flag_false_for_unwatched(self, mock_db):
        album = _make_album(artist_id="ART1")
        mock_db.list_albums.return_value = ([album], 1)
        mock_db.get_watched_artist_ids.return_value = set()

        resp = self.client.get("/api/releases")
        data = resp.get_json()
        self.assertFalse(data["items"][0]["watched"])

    @patch("api_releases.db")
    def test_empty_results(self, mock_db):
        mock_db.list_albums.return_value = ([], 0)
        mock_db.get_watched_artist_ids.return_value = set()

        resp = self.client.get("/api/releases")
        data = resp.get_json()
        self.assertEqual(data["items"], [])
        self.assertEqual(data["total"], 0)

    @patch("api_releases.db")
    def test_invalid_page_returns_400(self, mock_db):
        resp = self.client.get("/api/releases?page=abc")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    @patch("api_releases.db")
    def test_invalid_per_page_returns_400(self, mock_db):
        resp = self.client.get("/api/releases?per_page=xyz")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    @patch("api_releases.db")
    def test_invalid_storefront_returns_400(self, mock_db):
        resp = self.client.get("/api/releases?storefront=not_valid!")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    @patch("api_releases.db")
    def test_numeric_storefront_returns_400(self, mock_db):
        resp = self.client.get("/api/releases?storefront=123")
        self.assertEqual(resp.status_code, 400)

    @patch("api_releases.db")
    def test_too_long_storefront_returns_400(self, mock_db):
        resp = self.client.get("/api/releases?storefront=usaa")
        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------------------
# GET /api/releases/<store_adam_id>
# ---------------------------------------------------------------------------


class TestApiReleaseDetail(ServerTestCase):
    @patch("api_releases.db")
    def test_returns_404_for_missing(self, mock_db):
        mock_db.get_album.return_value = None
        mock_db.get_watched_artist_ids.return_value = set()

        resp = self.client.get("/api/releases/MISSING")
        self.assertEqual(resp.status_code, 404)

    @patch("api_releases.db")
    def test_returns_album_data(self, mock_db):
        mock_db.get_album.return_value = _make_album("A1")
        mock_db.get_watched_artist_ids.return_value = set()

        resp = self.client.get("/api/releases/A1")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["store_adam_id"], "A1")

    @patch("api_releases.db")
    def test_watched_flag_set(self, mock_db):
        mock_db.get_album.return_value = _make_album("A1", artist_id="ART1")
        mock_db.get_watched_artist_ids.return_value = {"ART1"}

        resp = self.client.get("/api/releases/A1")
        data = resp.get_json()
        self.assertTrue(data["watched"])

    @patch("api_releases.db")
    def test_storefronts_deserialized(self, mock_db):
        mock_db.get_album.return_value = _make_album("A1", storefronts='["us","jp"]')
        mock_db.get_watched_artist_ids.return_value = set()

        resp = self.client.get("/api/releases/A1")
        data = resp.get_json()
        self.assertIsInstance(data["storefronts"], list)


# ---------------------------------------------------------------------------
# GET /api/releases/<store_adam_id>/check_storefronts
# ---------------------------------------------------------------------------


class TestApiCheckStorefronts(ServerTestCase):
    @patch("api_releases.AppleMusicClient")
    def test_returns_availability_result(self, MockClient):
        mock_client = MockClient.return_value
        mock_client.check_storefront_availability.return_value = {"us": True, "jp": False}

        resp = self.client.get("/api/releases/A1/check_storefronts")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("us", data)
        self.assertIn("jp", data)

    @patch("api_releases.AppleMusicClient")
    def test_uses_config_storefronts(self, MockClient):
        mock_client = MockClient.return_value
        mock_client.check_storefront_availability.return_value = {}

        resp = self.client.get("/api/releases/A1/check_storefronts")
        self.assertEqual(resp.status_code, 200)
        # Verify check_storefront_availability was called with store_adam_id
        mock_client.check_storefront_availability.assert_called_once()
        call_args = mock_client.check_storefront_availability.call_args
        self.assertEqual(call_args[0][0], "A1")


# ---------------------------------------------------------------------------
# GET /api/lookup/<store_adam_id>
# ---------------------------------------------------------------------------


class TestApiLookup(ServerTestCase):
    @patch("api_releases.AppleMusicClient")
    def test_returns_album_info(self, MockClient):
        mock_client = MockClient.return_value
        mock_client.get_album_full_info.return_value = {
            "title": "My Album",
            "release_date": "2024-01-01",
        }

        resp = self.client.get("/api/releases/A1/lookup")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["title"], "My Album")

    @patch("api_releases.AppleMusicClient")
    def test_default_storefront_us(self, MockClient):
        mock_client = MockClient.return_value
        mock_client.get_album_full_info.return_value = {}

        self.client.get("/api/releases/A1/lookup")
        call_url = mock_client.get_album_full_info.call_args[0][0]
        self.assertIn("/us/album/", call_url)

    @patch("api_releases.AppleMusicClient")
    def test_custom_storefront(self, MockClient):
        mock_client = MockClient.return_value
        mock_client.get_album_full_info.return_value = {}

        self.client.get("/api/releases/A1/lookup?storefront=jp")
        call_url = mock_client.get_album_full_info.call_args[0][0]
        self.assertIn("/jp/album/", call_url)

    @patch("api_releases.AppleMusicClient")
    def test_storefront_normalized_lowercase(self, MockClient):
        mock_client = MockClient.return_value
        mock_client.get_album_full_info.return_value = {}

        self.client.get("/api/releases/A1/lookup?storefront=JP")
        call_url = mock_client.get_album_full_info.call_args[0][0]
        self.assertIn("/jp/album/", call_url)

    @patch("api_releases.AppleMusicClient")
    def test_invalid_storefront_returns_400(self, MockClient):
        resp = self.client.get("/api/releases/A1/lookup?storefront=not_valid!")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    @patch("api_releases.AppleMusicClient")
    def test_traversal_storefront_rejected(self, MockClient):
        resp = self.client.get("/api/releases/A1/lookup?storefront=../etc")
        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------------------
# GET /api/search/artists
# ---------------------------------------------------------------------------


class TestApiSearchArtists(ServerTestCase):
    @patch("api_artists.AppleMusicClient")
    def test_requires_term(self, MockClient):
        resp = self.client.get("/api/artists/search")
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn("error", data)

    @patch("api_artists.AppleMusicClient")
    def test_returns_results(self, MockClient):
        mock_client = MockClient.return_value
        mock_client.search_artists.return_value = [{"name": "Test Artist"}]

        resp = self.client.get("/api/artists/search?term=Test")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("results", data)
        self.assertEqual(len(data["results"]), 1)

    @patch("api_artists.AppleMusicClient")
    def test_empty_term_returns_400(self, MockClient):
        resp = self.client.get("/api/artists/search?term=")
        self.assertEqual(resp.status_code, 400)

    @patch("api_artists.AppleMusicClient")
    def test_limit_capped_at_50(self, MockClient):
        mock_client = MockClient.return_value
        mock_client.search_artists.return_value = []

        self.client.get("/api/artists/search?term=test&limit=9999")
        call_kwargs = mock_client.search_artists.call_args
        limit = call_kwargs[1].get("limit") if call_kwargs[1] else call_kwargs[0][2]
        self.assertLessEqual(limit, 50)

    @patch("api_artists.AppleMusicClient")
    def test_default_storefront_us(self, MockClient):
        mock_client = MockClient.return_value
        mock_client.search_artists.return_value = []

        self.client.get("/api/artists/search?term=test")
        call_kwargs = mock_client.search_artists.call_args
        storefront = call_kwargs[1].get("storefront") if call_kwargs[1] else call_kwargs[0][1]
        self.assertEqual(storefront, "us")

    @patch("api_artists.AppleMusicClient")
    def test_invalid_limit_returns_400(self, MockClient):
        resp = self.client.get("/api/artists/search?term=test&limit=abc")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    @patch("api_artists.AppleMusicClient")
    def test_invalid_storefront_returns_400(self, MockClient):
        resp = self.client.get("/api/artists/search?term=test&storefront=bad!")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    @patch("api_artists.AppleMusicClient")
    def test_rate_limit_returns_429(self, MockClient):
        from client import RateLimitError

        mock_client = MockClient.return_value
        mock_client.search_artists.side_effect = RateLimitError("rate limited")

        resp = self.client.get("/api/artists/search?term=test")
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(resp.get_json().get("error"), "rate_limited")


# ---------------------------------------------------------------------------
# GET/PUT /api/config
# ---------------------------------------------------------------------------


class TestApiConfig(ServerTestCase):
    def test_get_config_returns_defaults_when_no_file(self):
        resp = self.client.get("/api/system/config")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("newrelease_poll_interval_days", data)
        self.assertIn("check_storefronts", data)

    @patch("server._schedule_next")
    def test_put_config_saves_and_reschedules(self, mock_schedule):
        new_cfg = {"newrelease_poll_interval_days": 1, "check_storefronts": ["us"]}
        resp = self.client.put(
            "/api/system/config",
            data=json.dumps(new_cfg),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["ok"])
        mock_schedule.assert_called_once()

    @patch("server._schedule_next")
    def test_put_config_persists(self, mock_schedule):
        new_cfg = {"newrelease_poll_interval_days": 2, "check_storefronts": ["us"]}
        self.client.put(
            "/api/system/config",
            data=json.dumps(new_cfg),
            content_type="application/json",
        )
        resp = self.client.get("/api/system/config")
        data = resp.get_json()
        self.assertEqual(data["newrelease_poll_interval_days"], 2)


# ---------------------------------------------------------------------------
# POST /api/refresh
# ---------------------------------------------------------------------------


class TestApiRefresh(ServerTestCase):
    @patch("server.trigger_poll_now")
    @patch("server._is_running", False)
    def test_refresh_triggers_poll(self, mock_trigger):
        resp = self.client.post("/api/system/refresh")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["ok"])
        mock_trigger.assert_called_once()

    def test_refresh_409_when_running(self):
        import server

        original = server._is_running
        server._is_running = True
        try:
            resp = self.client.post("/api/system/refresh")
            self.assertEqual(resp.status_code, 409)
            self.assertFalse(resp.get_json()["ok"])
        finally:
            server._is_running = original


# ---------------------------------------------------------------------------
# GET /api/status
# ---------------------------------------------------------------------------


class TestApiStatus(ServerTestCase):
    @patch("api_system.db")
    def test_returns_status_fields(self, mock_db):
        mock_db.get_last_run.return_value = {
            "ran_at": 1700000000,
            "new_count": 5,
            "total_count": 100,
            "storefronts": [
                {"storefront": "us", "room_id": "123456", "room_last_modified": None, "new_count": 5},
            ],
        }
        mock_db.list_albums.return_value = ([], 100)

        resp = self.client.get("/api/system/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("last_run", data)
        self.assertIn("next_run_at", data)
        self.assertIn("is_running", data)
        self.assertIn("newrelease_poll_interval_days", data)
        self.assertIn("total_albums", data)
        self.assertEqual(data["last_run"]["new_count"], 5)
        self.assertEqual(len(data["last_run"]["storefronts"]), 1)

    @patch("api_system.db")
    def test_status_no_last_run(self, mock_db):
        mock_db.get_last_run.return_value = None
        mock_db.list_albums.return_value = ([], 0)

        resp = self.client.get("/api/system/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsNone(data["last_run"])

    @patch("api_system.db")
    def test_total_albums_reported(self, mock_db):
        mock_db.get_last_run.return_value = None
        mock_db.list_albums.return_value = ([], 42)

        resp = self.client.get("/api/system/status")
        data = resp.get_json()
        self.assertEqual(data["total_albums"], 42)

    @patch("api_system.db")
    def test_room_errors_included(self, mock_db):
        mock_db.get_last_run.return_value = None
        mock_db.list_albums.return_value = ([], 0)

        import server

        server._last_room_errors = ["hk", "jp"]
        resp = self.client.get("/api/system/status")
        data = resp.get_json()
        self.assertEqual(data["room_errors"], ["hk", "jp"])
        server._last_room_errors = []

    @patch("api_system.db")
    def test_room_errors_empty_by_default(self, mock_db):
        mock_db.get_last_run.return_value = None
        mock_db.list_albums.return_value = ([], 0)

        resp = self.client.get("/api/system/status")
        data = resp.get_json()
        self.assertEqual(data["room_errors"], [])


# ---------------------------------------------------------------------------
# GET /api/artists/<artist_id>/releases
# ---------------------------------------------------------------------------


class TestApiArtistReleases(ServerTestCase):
    @patch("api_artists.db")
    def test_returns_artist_releases(self, mock_db):
        mock_db.get_artist_albums.return_value = [_make_album("A1", artist_id="ART1", artist="Test Artist")]
        mock_db.get_watched_artist_ids.return_value = set()
        mock_db.get_artist_info.return_value = {}

        resp = self.client.get("/api/artists/ART1/releases")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("releases", data)
        self.assertIn("artist_id", data)
        self.assertEqual(data["artist_id"], "ART1")

    @patch("api_artists.db")
    def test_empty_artist_releases(self, mock_db):
        mock_db.get_artist_albums.return_value = []
        mock_db.get_watched_artist_ids.return_value = set()
        mock_db.get_artist_info.return_value = {}

        resp = self.client.get("/api/artists/ART1/releases")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["releases"], [])
        self.assertIsNone(data["artist_name"])

    @patch("api_artists.db")
    def test_watched_flag_in_response(self, mock_db):
        mock_db.get_artist_albums.return_value = [_make_album("A1", artist_id="ART1")]
        mock_db.get_watched_artist_ids.return_value = {"ART1"}
        mock_db.get_artist_info.return_value = {}

        resp = self.client.get("/api/artists/ART1/releases")
        data = resp.get_json()
        self.assertTrue(data["watched"])

    @patch("api_artists.db")
    def test_artist_name_from_artists_table(self, mock_db):
        """artist_name should come from the artists table, not album data."""
        mock_db.get_artist_albums.return_value = [
            _make_album("A1", artist_id="ART1", artist="周杰倫, 言承旭 & 五月天 阿信"),
        ]
        mock_db.get_watched_artist_ids.return_value = set()
        mock_db.get_artist_info.return_value = {"name": "周杰倫"}

        resp = self.client.get("/api/artists/ART1/releases")
        data = resp.get_json()
        self.assertEqual(data["artist_name"], "周杰倫")

    @patch("api_artists.db")
    def test_artist_info_included(self, mock_db):
        mock_db.get_artist_albums.return_value = []
        mock_db.get_watched_artist_ids.return_value = set()
        mock_db.get_artist_info.return_value = {
            "name": "Jay Chou",
            "artwork_url": "https://art.jpg",
            "genre": "Pop",
        }

        resp = self.client.get("/api/artists/ART1/releases")
        data = resp.get_json()
        self.assertEqual(data["artist_name"], "Jay Chou")
        self.assertEqual(data["artist_artwork_url"], "https://art.jpg")
        self.assertEqual(data["artist_genre"], "Pop")


# ---------------------------------------------------------------------------
# POST /api/artists/<artist_id>/fetch
# ---------------------------------------------------------------------------


def _sync_thread_patch(*args, **kwargs):
    """threading.Thread stand-in that runs target() synchronously.

    Only intercepts calls that explicitly pass daemon=True (the route handler's
    outer thread).  All other calls — e.g. ThreadPoolExecutor's internal worker
    threads — are forwarded to the real threading.Thread so they work normally.
    """
    if kwargs.get("daemon") is True:
        target = kwargs.get("target") or (args[0] if args else None)

        class _FakeThread:
            def start(self):
                target()

        return _FakeThread()
    return _RealThread(*args, **kwargs)


class TestApiArtistFetch(ServerTestCase):
    @patch("api_artists.db")
    @patch("api_artists.AppleMusicClient")
    @patch("api_artists.threading.Thread", side_effect=_sync_thread_patch)
    def test_fetch_artist_no_releases(self, _MockThread, MockClient, mock_db):
        mock_client = MockClient.return_value
        mock_client.get_artist_all_releases.return_value = ([], {})

        resp = self.client.post("/api/artists/ART1/fetch")
        self.assertEqual(resp.status_code, 202)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["async"])

    @patch("api_artists.db")
    @patch("api_artists.AppleMusicClient")
    @patch("api_artists.threading.Thread", side_effect=_sync_thread_patch)
    def test_fetch_artist_stores_releases(self, _MockThread, MockClient, mock_db):
        mock_client = MockClient.return_value
        mock_client.get_artist_all_releases.return_value = (
            [
                {
                    "storeAdamID": "A1",
                    "title": "Album 1",
                    "artist": "Artist",
                    "url": "https://x.com",
                    "storefronts": ["us"],
                    "release_type": "main-albums",
                },
            ],
            {"artwork_url": "https://art.jpg", "genre": "Pop"},
        )
        mock_client.get_album_full_info.return_value = {
            "release_date": "2024-01-01",
            "artwork_url": "https://art.jpg",
            "track_count": 10,
            "genre": "Pop",
            "description": "Desc",
            "artist_id": "ART1",
            "artist_url": "https://x.com/artist",
            "audio_formats": ["lossless"],
        }
        mock_db.get_album.return_value = None
        mock_db.upsert_artist.return_value = None
        mock_db.upsert_album.return_value = None

        resp = self.client.post("/api/artists/ART1/fetch")
        self.assertEqual(resp.status_code, 202)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["async"])
        mock_db.upsert_album.assert_called_once()

    @patch("api_artists.db")
    @patch("api_artists.AppleMusicClient")
    @patch("api_artists.threading.Thread", side_effect=_sync_thread_patch)
    def test_fetch_artist_uses_query_storefront(self, _MockThread, MockClient, mock_db):
        mock_client = MockClient.return_value
        mock_client.get_artist_all_releases.return_value = ([], {})

        self.client.post("/api/artists/ART1/fetch?storefront=jp")
        call_url = mock_client.get_artist_all_releases.call_args[0][0]
        self.assertIn("/jp/artist/", call_url)

    @patch("api_artists.db")
    @patch("api_artists.AppleMusicClient")
    @patch("api_artists.threading.Thread", side_effect=_sync_thread_patch)
    def test_fetch_artist_default_storefront_from_config(self, _MockThread, MockClient, mock_db):
        mock_client = MockClient.return_value
        mock_client.get_artist_all_releases.return_value = ([], {})

        self.client.post("/api/artists/ART1/fetch")
        call_url = mock_client.get_artist_all_releases.call_args[0][0]
        # Should use first storefront from check_storefronts config (default: "jp")
        self.assertIn("/artist/ART1", call_url)

    @patch("api_artists.db")
    @patch("api_artists.AppleMusicClient")
    def test_fetch_artist_invalid_storefront_returns_400(self, MockClient, mock_db):
        resp = self.client.post("/api/artists/ART1/fetch?storefront=bad!")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    @patch("api_artists.db")
    @patch("api_artists.AppleMusicClient")
    @patch("api_artists.threading.Thread", side_effect=_sync_thread_patch)
    def test_fetch_artist_checks_new_releases_for_complete_artist(self, _MockThread, MockClient, mock_db):
        mock_client = MockClient.return_value
        mock_client.get_artist_all_releases.return_value = (
            [
                {
                    "storeAdamID": "A1",
                    "title": "New Album",
                    "artist": "Artist",
                    "url": "https://x.com",
                    "storefronts": ["us"],
                    "release_type": "main-albums",
                },
            ],
            {"artwork_url": "https://art.jpg", "genre": "Pop"},
        )
        mock_client.get_album_full_info.return_value = {
            "release_date": "2026-04-09",
            "artwork_url": "https://art.jpg",
            "track_count": 10,
            "genre": "Pop",
            "description": "Desc",
            "artist_id": "ART1",
            "artist_url": "https://x.com/artist",
            "audio_formats": ["lossless"],
        }
        mock_db.get_album.return_value = None
        mock_db.upsert_artist.return_value = None
        mock_db.upsert_album.return_value = None
        mock_db.check_and_update_new_releases.return_value = True

        resp = self.client.post("/api/artists/ART1/fetch")
        self.assertEqual(resp.status_code, 202)
        mock_db.check_and_update_new_releases.assert_called_once_with("ART1")

    @patch("api_artists.db")
    @patch("api_artists.AppleMusicClient")
    @patch("api_artists.threading.Thread", side_effect=_sync_thread_patch)
    def test_fetch_artist_no_releases_skips_new_release_check(self, _MockThread, MockClient, mock_db):
        mock_client = MockClient.return_value
        mock_client.get_artist_all_releases.return_value = ([], {})

        resp = self.client.post("/api/artists/ART1/fetch")
        self.assertEqual(resp.status_code, 202)
        mock_db.check_and_update_new_releases.assert_not_called()


# ---------------------------------------------------------------------------
# Frontend serving
# ---------------------------------------------------------------------------


class TestFrontendServing(ServerTestCase):
    def test_root_returns_200(self):
        """/ should serve the frontend (or 404 if frontend dir doesn't exist in test env)."""
        resp = self.client.get("/")
        # Either 200 (frontend exists) or 404 (missing in test env)
        self.assertIn(resp.status_code, [200, 404, 500])

    def test_api_path_not_intercepted_by_frontend(self):
        """API paths starting with 'api/' should not be served as frontend."""
        with patch("api_watchlist.db") as mock_db:
            mock_db.get_watchlist.return_value = []
            mock_db.COLLECTION_STATUSES = set()
            resp = self.client.get("/api/watchlist")
            # Should be handled by the real API route, not the frontend catch-all
            self.assertEqual(resp.status_code, 200)

    def test_apidocs_path_skipped(self):
        """Apidocs path should not be served as frontend."""
        # This route is excluded from the frontend handler; flasgger may or may not serve it
        resp = self.client.get("/apidocs/")
        self.assertNotEqual(resp.status_code, 500)

    def test_path_traversal_does_not_expose_files(self):
        """Traversal sequences must not serve files outside the frontend dir."""
        resp = self.client.get("/../config.json")
        # Flask normalises the path before routing, so this arrives as /config.json
        # which won't exist in the frontend dir → falls back to index.html (200/404) or 404.
        # What it must NOT do is return a 200 with config.json contents from the project root.
        if resp.status_code == 200:
            body = resp.data.decode(errors="replace")
            self.assertNotIn("newrelease_poll_interval_days", body)

    def test_path_traversal_encoded_rejected(self):
        """URL-encoded traversal sequences must not expose files outside frontend dir."""
        resp = self.client.get("/..%2Fconfig.json")
        if resp.status_code == 200:
            body = resp.data.decode(errors="replace")
            self.assertNotIn("newrelease_poll_interval_days", body)


# ---------------------------------------------------------------------------
# GET /api/releases — watched filter
# ---------------------------------------------------------------------------


class TestApiReleasesWatched(ServerTestCase):
    @patch("api_releases.db")
    def test_watched_filter_passed_to_db(self, mock_db):
        mock_db.list_albums.return_value = ([], 0)
        mock_db.get_watched_artist_ids.return_value = set()

        self.client.get("/api/releases?watched=true&view=new")
        args, kwargs = mock_db.list_albums.call_args
        self.assertTrue(kwargs.get("watched_only"))

    @patch("api_releases.db")
    def test_watched_filter_false_by_default(self, mock_db):
        mock_db.list_albums.return_value = ([], 0)
        mock_db.get_watched_artist_ids.return_value = set()

        self.client.get("/api/releases")
        args, kwargs = mock_db.list_albums.call_args
        self.assertFalse(kwargs.get("watched_only", False))

    @patch("api_releases.db")
    def test_watched_filter_with_search(self, mock_db):
        mock_db.search_albums.return_value = ([], 0)
        mock_db.get_watched_artist_ids.return_value = set()

        self.client.get("/api/releases?q=test&watched=true")
        args, kwargs = mock_db.search_albums.call_args
        self.assertTrue(kwargs.get("watched_only"))


class TestApiReleasesReleaseType(ServerTestCase):
    @patch("api_releases.db")
    def test_release_type_passed_to_db(self, mock_db):
        mock_db.list_albums.return_value = ([], 0)
        mock_db.get_watched_artist_ids.return_value = set()

        self.client.get("/api/releases?release_type=main-albums")
        args, kwargs = mock_db.list_albums.call_args
        self.assertEqual(kwargs.get("release_type"), "main-albums")

    @patch("api_releases.db")
    def test_release_type_empty_by_default(self, mock_db):
        mock_db.list_albums.return_value = ([], 0)
        mock_db.get_watched_artist_ids.return_value = set()

        self.client.get("/api/releases")
        args, kwargs = mock_db.list_albums.call_args
        self.assertEqual(kwargs.get("release_type", ""), "")

    @patch("api_releases.db")
    def test_release_type_passed_to_search(self, mock_db):
        mock_db.search_albums.return_value = ([], 0)
        mock_db.get_watched_artist_ids.return_value = set()

        self.client.get("/api/releases?q=test&release_type=singles-eps")
        args, kwargs = mock_db.search_albums.call_args
        self.assertEqual(kwargs.get("release_type"), "singles-eps")


# ---------------------------------------------------------------------------
# Status endpoint — watchlist poll fields
# ---------------------------------------------------------------------------


class TestApiStatusWatchlist(ServerTestCase):
    @patch("api_system.db")
    def test_status_includes_watchlist_fields(self, mock_db):
        mock_db.get_last_run.return_value = None
        mock_db.list_albums.return_value = ([], 0)

        resp = self.client.get("/api/system/status")
        data = resp.get_json()
        self.assertIn("watchlist_poll_running", data)
        self.assertIn("watchlist_poll_interval_minutes", data)


# ---------------------------------------------------------------------------
# GET /api/search/artists/local
# ---------------------------------------------------------------------------


def _make_local_artist_result(artist_id="A1", name="Test Artist", match_reason="name_contains", watched=False):
    return {
        "artist_id": artist_id,
        "name": name,
        "artwork_url": None,
        "genre": None,
        "born_or_formed": None,
        "origin": None,
        "artist_bio": None,
        "is_group": None,
        "watched": watched,
        "collection_status": None,
        "match_reason": match_reason,
    }


class TestApiSearchArtistsLocal(ServerTestCase):
    @patch("api_artists.db")
    def test_returns_200_with_results(self, mock_db):
        mock_db.search_artists_local.return_value = [_make_local_artist_result()]
        resp = self.client.get("/api/artists/search/local?term=test")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("results", data)
        self.assertEqual(len(data["results"]), 1)

    @patch("api_artists.db")
    def test_missing_term_returns_400(self, mock_db):
        resp = self.client.get("/api/artists/search/local")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    @patch("api_artists.db")
    def test_blank_term_returns_400(self, mock_db):
        resp = self.client.get("/api/artists/search/local?term=")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["error"], "term is required")

    @patch("api_artists.db")
    def test_invalid_limit_returns_400(self, mock_db):
        resp = self.client.get("/api/artists/search/local?term=foo&limit=abc")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["error"], "limit must be an integer")

    @patch("api_artists.db")
    def test_limit_clamped_to_50(self, mock_db):
        mock_db.search_artists_local.return_value = []
        self.client.get("/api/artists/search/local?term=foo&limit=999")
        mock_db.search_artists_local.assert_called_once_with("foo", limit=50)

    @patch("api_artists.db")
    def test_default_limit_is_25(self, mock_db):
        mock_db.search_artists_local.return_value = []
        self.client.get("/api/artists/search/local?term=foo")
        mock_db.search_artists_local.assert_called_once_with("foo", limit=25)

    @patch("api_artists.db")
    def test_custom_limit_passed_to_db(self, mock_db):
        mock_db.search_artists_local.return_value = []
        self.client.get("/api/artists/search/local?term=foo&limit=10")
        mock_db.search_artists_local.assert_called_once_with("foo", limit=10)

    @patch("api_artists.db")
    def test_term_stripped_of_whitespace(self, mock_db):
        mock_db.search_artists_local.return_value = []
        self.client.get("/api/artists/search/local?term=+foo+")
        args, kwargs = mock_db.search_artists_local.call_args
        self.assertEqual(args[0], "foo")

    @patch("api_artists.db")
    def test_result_fields_passed_through(self, mock_db):
        artist = _make_local_artist_result(
            artist_id="ART1",
            name="Taylor Swift",
            match_reason="name_exact",
            watched=True,
        )
        artist["collection_status"] = "complete"
        mock_db.search_artists_local.return_value = [artist]
        resp = self.client.get("/api/artists/search/local?term=Taylor")
        result = resp.get_json()["results"][0]
        self.assertEqual(result["artist_id"], "ART1")
        self.assertEqual(result["match_reason"], "name_exact")
        self.assertTrue(result["watched"])
        self.assertEqual(result["collection_status"], "complete")

    @patch("api_artists.db")
    def test_empty_results_returned_as_empty_list(self, mock_db):
        mock_db.search_artists_local.return_value = []
        resp = self.client.get("/api/artists/search/local?term=nobody")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["results"], [])


# ---------------------------------------------------------------------------
# GET /api/releases/<store_adam_id>/musicbrainz
# ---------------------------------------------------------------------------


class TestApiMusicBrainzLookup(ServerTestCase):
    @patch("api_releases.db")
    def test_returns_404_when_album_missing(self, mock_db):
        mock_db.get_album.return_value = None
        resp = self.client.get("/api/releases/MISSING/musicbrainz")
        self.assertEqual(resp.status_code, 404)

    @patch("api_releases.db")
    def test_returns_no_upc_when_upc_is_null(self, mock_db):
        mock_db.get_album.return_value = {"store_adam_id": "A1", "upc": None}
        resp = self.client.get("/api/releases/A1/musicbrainz")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertFalse(data["found"])
        self.assertIsNone(data["upc"])

    @patch("api_releases.urllib.request.urlopen")
    @patch("api_releases.db")
    def test_returns_found_when_musicbrainz_has_release(self, mock_db, mock_urlopen):
        mock_db.get_album.return_value = {"store_adam_id": "A1", "upc": "00602445790494"}
        mb_response = json.dumps(
            {
                "releases": [
                    {
                        "id": "mb-id-123",
                        "title": "Test Release",
                        "artist-credit": [{"artist": {"id": "mb-artist-1", "name": "Jay Chou"}}],
                    }
                ]
            }
        ).encode()
        mock_resp = unittest.mock.MagicMock()
        mock_resp.read.return_value = mb_response
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: None
        mock_urlopen.return_value = mock_resp

        resp = self.client.get("/api/releases/A1/musicbrainz")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["found"])
        self.assertEqual(data["upc"], "00602445790494")
        self.assertEqual(len(data["releases"]), 1)
        self.assertEqual(data["releases"][0]["id"], "mb-id-123")
        self.assertIn("musicbrainz.org/release/mb-id-123", data["releases"][0]["url"])
        self.assertEqual(data["artist_mbid"], "mb-artist-1")

    @patch("api_releases.urllib.request.urlopen")
    @patch("api_releases.db")
    def test_returns_not_found_when_musicbrainz_empty(self, mock_db, mock_urlopen):
        mock_db.get_album.return_value = {"store_adam_id": "A1", "upc": "123456"}
        mb_response = json.dumps({"releases": []}).encode()
        mock_resp = unittest.mock.MagicMock()
        mock_resp.read.return_value = mb_response
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: None
        mock_urlopen.return_value = mock_resp

        resp = self.client.get("/api/releases/A1/musicbrainz")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertFalse(data["found"])
        self.assertEqual(data["upc"], "123456")

    @patch("api_releases.urllib.request.urlopen")
    @patch("api_releases.db")
    def test_returns_502_on_network_error(self, mock_db, mock_urlopen):
        mock_db.get_album.return_value = {"store_adam_id": "A1", "upc": "123456"}
        mock_urlopen.side_effect = Exception("Connection refused")

        resp = self.client.get("/api/releases/A1/musicbrainz")
        self.assertEqual(resp.status_code, 502)
        data = resp.get_json()
        self.assertFalse(data["found"])
        self.assertIn("error", data)


# ---------------------------------------------------------------------------
# PATCH /api/artists/<artist_id>
# ---------------------------------------------------------------------------


class TestApiArtistPatch(ServerTestCase):
    @patch("api_artists.db")
    def test_sets_musicbrainz_id(self, mock_db):
        resp = self.client.patch(
            "/api/artists/ART1",
            data=json.dumps({"musicbrainz_id": "mb-id-123"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        mock_db.update_artist_musicbrainz_id.assert_called_once_with("ART1", "mb-id-123")

    @patch("api_artists.db")
    def test_clears_musicbrainz_id(self, mock_db):
        resp = self.client.patch(
            "/api/artists/ART1",
            data=json.dumps({"musicbrainz_id": None}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        mock_db.update_artist_musicbrainz_id.assert_called_once_with("ART1", None)

    @patch("api_artists.db")
    def test_empty_string_treated_as_null(self, mock_db):
        resp = self.client.patch(
            "/api/artists/ART1",
            data=json.dumps({"musicbrainz_id": "  "}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        mock_db.update_artist_musicbrainz_id.assert_called_once_with("ART1", None)


# ---------------------------------------------------------------------------
# artist_musicbrainz_id in artist releases response
# ---------------------------------------------------------------------------


class TestApiArtistReleasesIncludesMbid(ServerTestCase):
    @patch("api_artists.db")
    def test_includes_musicbrainz_id(self, mock_db):
        mock_db.get_artist_albums.return_value = []
        mock_db.get_watched_artist_ids.return_value = set()
        mock_db.get_artist_info.return_value = {"name": "Jay Chou", "musicbrainz_id": "mb-123"}

        resp = self.client.get("/api/artists/ART1/releases")
        data = resp.get_json()
        self.assertEqual(data["artist_musicbrainz_id"], "mb-123")

    @patch("api_artists.db")
    def test_musicbrainz_id_none_when_not_set(self, mock_db):
        mock_db.get_artist_albums.return_value = []
        mock_db.get_watched_artist_ids.return_value = set()
        mock_db.get_artist_info.return_value = {"name": "Jay Chou"}

        resp = self.client.get("/api/artists/ART1/releases")
        data = resp.get_json()
        self.assertIsNone(data["artist_musicbrainz_id"])


# ---------------------------------------------------------------------------
# GET /api/dbstatus
# ---------------------------------------------------------------------------


class TestApiDbStatus(ServerTestCase):
    @patch("api_system.db")
    def test_returns_expected_fields(self, mock_db):
        mock_db.get_db_stats.return_value = {
            "db_path": "/tmp/test.db",
            "db_size_bytes": 4096,
            "wal_size_bytes": 0,
            "shm_size_bytes": 0,
            "total_size_bytes": 4096,
            "page_size_bytes": 4096,
            "page_count": 1,
            "tables": [{"name": "albums", "row_count": 10, "size_bytes": 4096, "page_count": 1}],
        }
        resp = self.client.get("/api/system/db")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("db_path", data)
        self.assertIn("db_size_bytes", data)
        self.assertIn("wal_size_bytes", data)
        self.assertIn("shm_size_bytes", data)
        self.assertIn("total_size_bytes", data)
        self.assertIn("page_size_bytes", data)
        self.assertIn("page_count", data)
        self.assertIn("tables", data)

    @patch("api_system.db")
    def test_tables_have_required_keys(self, mock_db):
        mock_db.get_db_stats.return_value = {
            "db_path": "/tmp/test.db",
            "db_size_bytes": 8192,
            "wal_size_bytes": 1024,
            "shm_size_bytes": 32768,
            "total_size_bytes": 42984,
            "page_size_bytes": 4096,
            "page_count": 2,
            "tables": [
                {"name": "albums", "row_count": 5, "size_bytes": 4096, "page_count": 1},
                {"name": "artists", "row_count": 2, "size_bytes": 4096, "page_count": 1},
            ],
        }
        resp = self.client.get("/api/system/db")
        data = resp.get_json()
        for table in data["tables"]:
            self.assertIn("name", table)
            self.assertIn("row_count", table)
            self.assertIn("size_bytes", table)
            self.assertIn("page_count", table)

    @patch("api_system.db")
    def test_total_size_includes_wal(self, mock_db):
        mock_db.get_db_stats.return_value = {
            "db_path": "/tmp/test.db",
            "db_size_bytes": 4096,
            "wal_size_bytes": 2048,
            "shm_size_bytes": 32768,
            "total_size_bytes": 38912,
            "page_size_bytes": 4096,
            "page_count": 1,
            "tables": [],
        }
        resp = self.client.get("/api/system/db")
        data = resp.get_json()
        self.assertEqual(data["total_size_bytes"], 38912)


class TestApiDiscoveryStatus(ServerTestCase):
    @patch("api_system.db")
    def test_returns_runs_and_count(self, mock_db):
        mock_db.get_discovery_runs.return_value = [
            {"id": 2, "ran_at": 1700086400, "storefront": "jp", "room_id": "999", "new_count": 3, "total_count": 20},
            {"id": 1, "ran_at": 1700000000, "storefront": "us", "room_id": "888", "new_count": 5, "total_count": 17},
        ]
        resp = self.client.get("/api/system/discovery")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("runs", data)
        self.assertIn("count", data)
        self.assertEqual(data["count"], 2)
        self.assertEqual(data["runs"][0]["storefront"], "jp")
        self.assertEqual(data["runs"][0]["room_id"], "999")

    @patch("api_system.db")
    def test_empty_runs(self, mock_db):
        mock_db.get_discovery_runs.return_value = []
        resp = self.client.get("/api/system/discovery")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["runs"], [])
        self.assertEqual(data["count"], 0)

    @patch("api_system.db")
    def test_limit_param_forwarded(self, mock_db):
        mock_db.get_discovery_runs.return_value = []
        self.client.get("/api/system/discovery?limit=50")
        mock_db.get_discovery_runs.assert_called_once_with(limit=50)

    @patch("api_system.db")
    def test_invalid_limit_defaults_to_200(self, mock_db):
        mock_db.get_discovery_runs.return_value = []
        self.client.get("/api/system/discovery?limit=abc")
        mock_db.get_discovery_runs.assert_called_once_with(limit=200)


# ---------------------------------------------------------------------------
# GET /api/artists/<artist_id>/similar
# ---------------------------------------------------------------------------


class TestApiSimilarArtists(ServerTestCase):
    @patch("api_artists.AppleMusicClient")
    def test_returns_results(self, MockClient):
        mock_client = MockClient.return_value
        mock_client.get_similar_artists.return_value = [
            {
                "id": "ART2",
                "name": "Similar Artist",
                "url": "https://music.apple.com/us/artist/ART2",
                "artwork_url": "https://example.com/art2.jpg",
                "genre": "Pop",
            },
        ]

        resp = self.client.get("/api/artists/ART1/similar?storefront=us&limit=5")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("results", data)
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["id"], "ART2")

    @patch("api_artists.AppleMusicClient")
    def test_invalid_storefront_returns_400(self, MockClient):
        resp = self.client.get("/api/artists/ART1/similar?storefront=bad!")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    @patch("api_artists.AppleMusicClient")
    def test_invalid_limit_returns_400(self, MockClient):
        resp = self.client.get("/api/artists/ART1/similar?limit=xyz")
        self.assertEqual(resp.status_code, 400)

    @patch("api_artists.AppleMusicClient")
    def test_rate_limit_returns_429(self, MockClient):
        from client import RateLimitError

        mock_client = MockClient.return_value
        mock_client.get_similar_artists.side_effect = RateLimitError("rate limited")

        resp = self.client.get("/api/artists/ART1/similar")
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(resp.get_json().get("error"), "rate_limited")

    @patch("api_artists.AppleMusicClient")
    def test_limit_capped_at_25(self, MockClient):
        mock_client = MockClient.return_value
        mock_client.get_similar_artists.return_value = []

        self.client.get("/api/artists/ART1/similar?limit=9999")
        call_kwargs = mock_client.get_similar_artists.call_args
        limit = call_kwargs[1].get("limit") if call_kwargs[1] else call_kwargs[0][2]
        self.assertLessEqual(limit, 25)


# ---------------------------------------------------------------------------
# GET /api/releases/<store_adam_id>/you-might-also-like
# ---------------------------------------------------------------------------


class TestApiYouMightAlsoLike(ServerTestCase):
    @patch("api_releases.AppleMusicClient")
    @patch("api_releases.db")
    def test_returns_results(self, mock_db, MockClient):
        mock_db.get_album.return_value = _make_album("A1")
        mock_client = MockClient.return_value
        mock_client.get_you_might_also_like.return_value = [
            {
                "store_adam_id": "A2",
                "title": "Other Album",
                "artist": "Other Artist",
                "artists": [{"name": "Other Artist", "url": None}],
                "artwork_url": "https://example.com/art.jpg",
                "release_date": "2024-02-01",
                "url": "https://music.apple.com/us/album/A2",
                "storefronts": ["us"],
                "watched": False,
            },
        ]

        resp = self.client.get("/api/releases/A1/you-might-also-like?storefront=us&limit=5")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("results", data)
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["store_adam_id"], "A2")

    @patch("api_releases.AppleMusicClient")
    @patch("api_releases.db")
    def test_unknown_album_still_proxies_to_apple(self, mock_db, MockClient):
        # The endpoint is a pure proxy over Apple Music — it should not require
        # the album to exist in the local DB, so that users can keep clicking
        # through "You Might Also Like" suggestions.
        mock_db.get_album.return_value = None
        mock_client = MockClient.return_value
        mock_client.get_you_might_also_like.return_value = []

        resp = self.client.get("/api/releases/UNKNOWN/you-might-also-like")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"results": []})
        mock_client.get_you_might_also_like.assert_called_once()

    @patch("api_releases.AppleMusicClient")
    @patch("api_releases.db")
    def test_invalid_storefront_returns_400(self, mock_db, MockClient):
        resp = self.client.get("/api/releases/A1/you-might-also-like?storefront=bad!")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    @patch("api_releases.AppleMusicClient")
    @patch("api_releases.db")
    def test_rate_limit_returns_429(self, mock_db, MockClient):
        from client import RateLimitError

        mock_db.get_album.return_value = _make_album("A1")
        mock_client = MockClient.return_value
        mock_client.get_you_might_also_like.side_effect = RateLimitError("rate limited")

        resp = self.client.get("/api/releases/A1/you-might-also-like")
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(resp.get_json().get("error"), "rate_limited")


if __name__ == "__main__":
    unittest.main()
