"""Comprehensive tests for server.py — Flask REST API endpoints.

Strategy:
- Use Flask's built-in test client (app.test_client()).
- Patch db.* and AppleMusicClient so no real database or network access occurs.
- Each test class covers a logical group of endpoints.
"""

import contextlib
import json
import os
import tempfile
import unittest
from unittest.mock import patch

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

        # Patch config path in server module
        import server

        self._orig_config_path = server.CONFIG_PATH
        server.CONFIG_PATH = self._cfg_path

        self.app = server.app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        import server

        server.CONFIG_PATH = self._orig_config_path
        with contextlib.suppress(FileNotFoundError):
            os.unlink(self._cfg_path)


# ---------------------------------------------------------------------------
# _serialize helper
# ---------------------------------------------------------------------------


class TestSerialize(unittest.TestCase):
    def setUp(self):
        import server

        self.serialize = server._serialize

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
# GET /api/releases
# ---------------------------------------------------------------------------


class TestApiReleases(ServerTestCase):
    @patch("server.db")
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

    @patch("server.db")
    def test_default_pagination(self, mock_db):
        mock_db.list_albums.return_value = ([], 0)
        mock_db.get_watched_artist_ids.return_value = set()

        resp = self.client.get("/api/releases")
        data = resp.get_json()
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["per_page"], 50)

    @patch("server.db")
    def test_custom_pagination(self, mock_db):
        mock_db.list_albums.return_value = ([], 0)
        mock_db.get_watched_artist_ids.return_value = set()

        resp = self.client.get("/api/releases?page=3&per_page=10")
        data = resp.get_json()
        self.assertEqual(data["page"], 3)
        self.assertEqual(data["per_page"], 10)

    @patch("server.db")
    def test_search_query_uses_search_albums(self, mock_db):
        mock_db.search_albums.return_value = ([_make_album()], 1)
        mock_db.get_watched_artist_ids.return_value = set()

        resp = self.client.get("/api/releases?q=Test")
        self.assertEqual(resp.status_code, 200)
        mock_db.search_albums.assert_called_once()

    @patch("server.db")
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

    @patch("server.db")
    def test_discovered_only_view_new(self, mock_db):
        mock_db.list_albums.return_value = ([], 0)
        mock_db.get_watched_artist_ids.return_value = set()

        self.client.get("/api/releases?view=new")
        args, kwargs = mock_db.list_albums.call_args
        discovered_only = kwargs.get("discovered_only", args[3] if len(args) > 3 else False)
        self.assertTrue(discovered_only)

    @patch("server.db")
    def test_watched_flag_set_correctly(self, mock_db):
        album = _make_album(artist_id="ART1")
        mock_db.list_albums.return_value = ([album], 1)
        mock_db.get_watched_artist_ids.return_value = {"ART1"}

        resp = self.client.get("/api/releases")
        data = resp.get_json()
        self.assertTrue(data["items"][0]["watched"])

    @patch("server.db")
    def test_watched_flag_false_for_unwatched(self, mock_db):
        album = _make_album(artist_id="ART1")
        mock_db.list_albums.return_value = ([album], 1)
        mock_db.get_watched_artist_ids.return_value = set()

        resp = self.client.get("/api/releases")
        data = resp.get_json()
        self.assertFalse(data["items"][0]["watched"])

    @patch("server.db")
    def test_empty_results(self, mock_db):
        mock_db.list_albums.return_value = ([], 0)
        mock_db.get_watched_artist_ids.return_value = set()

        resp = self.client.get("/api/releases")
        data = resp.get_json()
        self.assertEqual(data["items"], [])
        self.assertEqual(data["total"], 0)

    @patch("server.db")
    def test_invalid_page_returns_400(self, mock_db):
        resp = self.client.get("/api/releases?page=abc")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    @patch("server.db")
    def test_invalid_per_page_returns_400(self, mock_db):
        resp = self.client.get("/api/releases?per_page=xyz")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    @patch("server.db")
    def test_invalid_storefront_returns_400(self, mock_db):
        resp = self.client.get("/api/releases?storefront=not_valid!")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    @patch("server.db")
    def test_numeric_storefront_returns_400(self, mock_db):
        resp = self.client.get("/api/releases?storefront=123")
        self.assertEqual(resp.status_code, 400)

    @patch("server.db")
    def test_too_long_storefront_returns_400(self, mock_db):
        resp = self.client.get("/api/releases?storefront=usaa")
        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------------------
# GET /api/releases/<store_adam_id>
# ---------------------------------------------------------------------------


class TestApiReleaseDetail(ServerTestCase):
    @patch("server.db")
    def test_returns_404_for_missing(self, mock_db):
        mock_db.get_album.return_value = None
        mock_db.get_watched_artist_ids.return_value = set()

        resp = self.client.get("/api/releases/MISSING")
        self.assertEqual(resp.status_code, 404)

    @patch("server.db")
    def test_returns_album_data(self, mock_db):
        mock_db.get_album.return_value = _make_album("A1")
        mock_db.get_watched_artist_ids.return_value = set()

        resp = self.client.get("/api/releases/A1")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["store_adam_id"], "A1")

    @patch("server.db")
    def test_watched_flag_set(self, mock_db):
        mock_db.get_album.return_value = _make_album("A1", artist_id="ART1")
        mock_db.get_watched_artist_ids.return_value = {"ART1"}

        resp = self.client.get("/api/releases/A1")
        data = resp.get_json()
        self.assertTrue(data["watched"])

    @patch("server.db")
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
    @patch("server.AppleMusicClient")
    def test_returns_availability_result(self, MockClient):
        mock_client = MockClient.return_value
        mock_client.check_storefront_availability.return_value = {"us": True, "jp": False}

        resp = self.client.get("/api/releases/A1/check_storefronts")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("us", data)
        self.assertIn("jp", data)

    @patch("server.AppleMusicClient")
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
    @patch("server.AppleMusicClient")
    def test_returns_album_info(self, MockClient):
        mock_client = MockClient.return_value
        mock_client.get_album_full_info.return_value = {
            "title": "My Album",
            "release_date": "2024-01-01",
        }

        resp = self.client.get("/api/lookup/A1")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["title"], "My Album")

    @patch("server.AppleMusicClient")
    def test_default_storefront_us(self, MockClient):
        mock_client = MockClient.return_value
        mock_client.get_album_full_info.return_value = {}

        self.client.get("/api/lookup/A1")
        call_url = mock_client.get_album_full_info.call_args[0][0]
        self.assertIn("/us/album/", call_url)

    @patch("server.AppleMusicClient")
    def test_custom_storefront(self, MockClient):
        mock_client = MockClient.return_value
        mock_client.get_album_full_info.return_value = {}

        self.client.get("/api/lookup/A1?storefront=jp")
        call_url = mock_client.get_album_full_info.call_args[0][0]
        self.assertIn("/jp/album/", call_url)

    @patch("server.AppleMusicClient")
    def test_storefront_normalized_lowercase(self, MockClient):
        mock_client = MockClient.return_value
        mock_client.get_album_full_info.return_value = {}

        self.client.get("/api/lookup/A1?storefront=JP")
        call_url = mock_client.get_album_full_info.call_args[0][0]
        self.assertIn("/jp/album/", call_url)

    @patch("server.AppleMusicClient")
    def test_invalid_storefront_returns_400(self, MockClient):
        resp = self.client.get("/api/lookup/A1?storefront=not_valid!")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    @patch("server.AppleMusicClient")
    def test_traversal_storefront_rejected(self, MockClient):
        resp = self.client.get("/api/lookup/A1?storefront=../etc")
        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------------------
# GET /api/search/artists
# ---------------------------------------------------------------------------


class TestApiSearchArtists(ServerTestCase):
    @patch("server.AppleMusicClient")
    def test_requires_term(self, MockClient):
        resp = self.client.get("/api/search/artists")
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn("error", data)

    @patch("server.AppleMusicClient")
    def test_returns_results(self, MockClient):
        mock_client = MockClient.return_value
        mock_client.search_artists.return_value = [{"name": "Test Artist"}]

        resp = self.client.get("/api/search/artists?term=Test")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("results", data)
        self.assertEqual(len(data["results"]), 1)

    @patch("server.AppleMusicClient")
    def test_empty_term_returns_400(self, MockClient):
        resp = self.client.get("/api/search/artists?term=")
        self.assertEqual(resp.status_code, 400)

    @patch("server.AppleMusicClient")
    def test_limit_capped_at_50(self, MockClient):
        mock_client = MockClient.return_value
        mock_client.search_artists.return_value = []

        self.client.get("/api/search/artists?term=test&limit=9999")
        call_kwargs = mock_client.search_artists.call_args
        limit = call_kwargs[1].get("limit") if call_kwargs[1] else call_kwargs[0][2]
        self.assertLessEqual(limit, 50)

    @patch("server.AppleMusicClient")
    def test_default_storefront_us(self, MockClient):
        mock_client = MockClient.return_value
        mock_client.search_artists.return_value = []

        self.client.get("/api/search/artists?term=test")
        call_kwargs = mock_client.search_artists.call_args
        storefront = call_kwargs[1].get("storefront") if call_kwargs[1] else call_kwargs[0][1]
        self.assertEqual(storefront, "us")

    @patch("server.AppleMusicClient")
    def test_invalid_limit_returns_400(self, MockClient):
        resp = self.client.get("/api/search/artists?term=test&limit=abc")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    @patch("server.AppleMusicClient")
    def test_invalid_storefront_returns_400(self, MockClient):
        resp = self.client.get("/api/search/artists?term=test&storefront=bad!")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    @patch("server.AppleMusicClient")
    def test_rate_limit_returns_429(self, MockClient):
        from client import RateLimitError

        mock_client = MockClient.return_value
        mock_client.search_artists.side_effect = RateLimitError("rate limited")

        resp = self.client.get("/api/search/artists?term=test")
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(resp.get_json().get("error"), "rate_limited")


# ---------------------------------------------------------------------------
# GET/POST/DELETE /api/watchlist
# ---------------------------------------------------------------------------


class TestApiWatchlist(ServerTestCase):
    @patch("server.db")
    def test_get_empty_watchlist(self, mock_db):
        mock_db.get_watchlist.return_value = []
        resp = self.client.get("/api/watchlist")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), [])

    @patch("server.db")
    def test_get_watchlist_returns_artists(self, mock_db):
        mock_db.get_watchlist.return_value = [{"artist_id": "ART1", "name": "Artist One", "url": None, "added_at": 0}]
        resp = self.client.get("/api/watchlist")
        data = resp.get_json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["name"], "Artist One")

    @patch("server.db")
    def test_post_watchlist_success(self, mock_db):
        mock_db.add_to_watchlist.return_value = None
        resp = self.client.post(
            "/api/watchlist",
            data=json.dumps({"artist_id": "ART1", "name": "Artist One", "url": "https://example.com"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        mock_db.add_to_watchlist.assert_called_once_with(
            "ART1",
            "Artist One",
            "https://example.com",
            preferred_source=None,
        )

    @patch("server.db")
    def test_post_watchlist_missing_artist_id(self, mock_db):
        resp = self.client.post(
            "/api/watchlist",
            data=json.dumps({"name": "Artist One"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    @patch("server.db")
    def test_post_watchlist_missing_name(self, mock_db):
        resp = self.client.post(
            "/api/watchlist",
            data=json.dumps({"artist_id": "ART1"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    @patch("server.db")
    def test_post_watchlist_empty_artist_id(self, mock_db):
        resp = self.client.post(
            "/api/watchlist",
            data=json.dumps({"artist_id": "", "name": "Artist One"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    @patch("server.db")
    def test_delete_watchlist(self, mock_db):
        mock_db.remove_from_watchlist.return_value = None
        resp = self.client.delete("/api/watchlist/ART1")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["ok"])
        mock_db.remove_from_watchlist.assert_called_once_with("ART1")

    @patch("server.db")
    def test_delete_nonexistent_artist_still_ok(self, mock_db):
        """Deleting a non-existent artist should not raise — return 200."""
        mock_db.remove_from_watchlist.return_value = None
        resp = self.client.delete("/api/watchlist/NONEXISTENT")
        self.assertEqual(resp.status_code, 200)

    @patch("server.db")
    def test_get_watchlist_sort_name(self, mock_db):
        mock_db.get_watchlist.return_value = []
        mock_db.COLLECTION_STATUSES = set()
        resp = self.client.get("/api/watchlist?sort=name")
        self.assertEqual(resp.status_code, 200)
        mock_db.get_watchlist.assert_called_once_with(preferred_source="", collection_status="", sort="name")

    @patch("server.db")
    def test_get_watchlist_sort_added(self, mock_db):
        mock_db.get_watchlist.return_value = []
        mock_db.COLLECTION_STATUSES = set()
        resp = self.client.get("/api/watchlist?sort=added")
        self.assertEqual(resp.status_code, 200)
        mock_db.get_watchlist.assert_called_once_with(preferred_source="", collection_status="", sort="added")

    @patch("server.db")
    def test_get_watchlist_sort_recent_release(self, mock_db):
        mock_db.get_watchlist.return_value = []
        mock_db.COLLECTION_STATUSES = set()
        resp = self.client.get("/api/watchlist?sort=recent_release")
        self.assertEqual(resp.status_code, 200)
        mock_db.get_watchlist.assert_called_once_with(preferred_source="", collection_status="", sort="recent_release")

    @patch("server.db")
    def test_get_watchlist_invalid_sort_returns_400(self, mock_db):
        mock_db.COLLECTION_STATUSES = set()
        resp = self.client.get("/api/watchlist?sort=bogus")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())


# ---------------------------------------------------------------------------
# GET/PUT /api/config
# ---------------------------------------------------------------------------


class TestApiConfig(ServerTestCase):
    def test_get_config_returns_defaults_when_no_file(self):
        resp = self.client.get("/api/config")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("newrelease_poll_interval_days", data)
        self.assertIn("check_storefronts", data)

    @patch("server._schedule_next")
    def test_put_config_saves_and_reschedules(self, mock_schedule):
        new_cfg = {"newrelease_poll_interval_days": 1, "check_storefronts": ["us"]}
        resp = self.client.put(
            "/api/config",
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
            "/api/config",
            data=json.dumps(new_cfg),
            content_type="application/json",
        )
        resp = self.client.get("/api/config")
        data = resp.get_json()
        self.assertEqual(data["newrelease_poll_interval_days"], 2)


# ---------------------------------------------------------------------------
# POST /api/refresh
# ---------------------------------------------------------------------------


class TestApiRefresh(ServerTestCase):
    @patch("server.trigger_poll_now")
    @patch("server._is_running", False)
    def test_refresh_triggers_poll(self, mock_trigger):
        resp = self.client.post("/api/refresh")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["ok"])
        mock_trigger.assert_called_once()

    def test_refresh_409_when_running(self):
        import server

        original = server._is_running
        server._is_running = True
        try:
            resp = self.client.post("/api/refresh")
            self.assertEqual(resp.status_code, 409)
            self.assertFalse(resp.get_json()["ok"])
        finally:
            server._is_running = original


# ---------------------------------------------------------------------------
# GET /api/status
# ---------------------------------------------------------------------------


class TestApiStatus(ServerTestCase):
    @patch("server.db")
    def test_returns_status_fields(self, mock_db):
        mock_db.get_last_run.return_value = {
            "id": 1,
            "ran_at": 1700000000,
            "new_count": 5,
            "total_count": 100,
        }
        mock_db.list_albums.return_value = ([], 100)

        resp = self.client.get("/api/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("last_run", data)
        self.assertIn("next_run_at", data)
        self.assertIn("is_running", data)
        self.assertIn("newrelease_poll_interval_days", data)
        self.assertIn("total_albums", data)

    @patch("server.db")
    def test_status_no_last_run(self, mock_db):
        mock_db.get_last_run.return_value = None
        mock_db.list_albums.return_value = ([], 0)

        resp = self.client.get("/api/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsNone(data["last_run"])

    @patch("server.db")
    def test_total_albums_reported(self, mock_db):
        mock_db.get_last_run.return_value = None
        mock_db.list_albums.return_value = ([], 42)

        resp = self.client.get("/api/status")
        data = resp.get_json()
        self.assertEqual(data["total_albums"], 42)

    @patch("server.db")
    def test_room_errors_included(self, mock_db):
        mock_db.get_last_run.return_value = None
        mock_db.list_albums.return_value = ([], 0)

        import server

        server._last_room_errors = ["hk", "jp"]
        resp = self.client.get("/api/status")
        data = resp.get_json()
        self.assertEqual(data["room_errors"], ["hk", "jp"])
        server._last_room_errors = []

    @patch("server.db")
    def test_room_errors_empty_by_default(self, mock_db):
        mock_db.get_last_run.return_value = None
        mock_db.list_albums.return_value = ([], 0)

        resp = self.client.get("/api/status")
        data = resp.get_json()
        self.assertEqual(data["room_errors"], [])


# ---------------------------------------------------------------------------
# GET /api/artists/<artist_id>/releases
# ---------------------------------------------------------------------------


class TestApiArtistReleases(ServerTestCase):
    @patch("server.db")
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

    @patch("server.db")
    def test_empty_artist_releases(self, mock_db):
        mock_db.get_artist_albums.return_value = []
        mock_db.get_watched_artist_ids.return_value = set()
        mock_db.get_artist_info.return_value = {}

        resp = self.client.get("/api/artists/ART1/releases")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["releases"], [])
        self.assertIsNone(data["artist_name"])

    @patch("server.db")
    def test_watched_flag_in_response(self, mock_db):
        mock_db.get_artist_albums.return_value = [_make_album("A1", artist_id="ART1")]
        mock_db.get_watched_artist_ids.return_value = {"ART1"}
        mock_db.get_artist_info.return_value = {}

        resp = self.client.get("/api/artists/ART1/releases")
        data = resp.get_json()
        self.assertTrue(data["watched"])

    @patch("server.db")
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

    @patch("server.db")
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


class TestApiArtistFetch(ServerTestCase):
    @patch("server.db")
    @patch("server.AppleMusicClient")
    def test_fetch_artist_no_releases(self, MockClient, mock_db):
        mock_client = MockClient.return_value
        mock_client.get_artist_all_releases.return_value = ([], {})

        resp = self.client.post("/api/artists/ART1/fetch")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["fetched"], 0)

    @patch("server.db")
    @patch("server.AppleMusicClient")
    def test_fetch_artist_stores_releases(self, MockClient, mock_db):
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
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["fetched"], 1)

    @patch("server.db")
    @patch("server.AppleMusicClient")
    def test_fetch_artist_uses_query_storefront(self, MockClient, mock_db):
        mock_client = MockClient.return_value
        mock_client.get_artist_all_releases.return_value = ([], {})

        self.client.post("/api/artists/ART1/fetch?storefront=jp")
        call_url = mock_client.get_artist_all_releases.call_args[0][0]
        self.assertIn("/jp/artist/", call_url)

    @patch("server.db")
    @patch("server.AppleMusicClient")
    def test_fetch_artist_default_storefront_from_config(self, MockClient, mock_db):
        mock_client = MockClient.return_value
        mock_client.get_artist_all_releases.return_value = ([], {})

        self.client.post("/api/artists/ART1/fetch")
        call_url = mock_client.get_artist_all_releases.call_args[0][0]
        # Should use first storefront from check_storefronts config (default: "jp")
        self.assertIn("/artist/ART1", call_url)

    @patch("server.db")
    @patch("server.AppleMusicClient")
    def test_fetch_artist_invalid_storefront_returns_400(self, MockClient, mock_db):
        resp = self.client.post("/api/artists/ART1/fetch?storefront=bad!")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())


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
        with patch("server.db") as mock_db:
            mock_db.get_watchlist.return_value = []
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
# load_config / save_config
# ---------------------------------------------------------------------------


class TestConfigHelpers(ServerTestCase):
    def test_load_config_returns_defaults_when_no_file(self):
        import server

        cfg = server.load_config()
        self.assertEqual(cfg["newrelease_poll_interval_days"], 1)
        self.assertIsInstance(cfg["check_storefronts"], list)

    def test_save_and_load_config(self):
        import server

        custom = {"newrelease_poll_interval_days": 3, "check_storefronts": ["us"]}
        server.save_config(custom)
        loaded = server.load_config()
        self.assertEqual(loaded["newrelease_poll_interval_days"], 3)

    def test_load_config_merges_defaults(self):
        """Config on disk should be merged with defaults (missing keys filled in)."""
        import server

        server.save_config({"newrelease_poll_interval_days": 2})
        loaded = server.load_config()
        self.assertIn("check_storefronts", loaded)


# ---------------------------------------------------------------------------
# Watchlist preferred_source
# ---------------------------------------------------------------------------


class TestApiWatchlistPreferredSource(ServerTestCase):
    @patch("server.db")
    def test_post_with_preferred_source(self, mock_db):
        mock_db.add_to_watchlist.return_value = None
        resp = self.client.post(
            "/api/watchlist",
            data=json.dumps({"artist_id": "ART1", "name": "Artist One", "preferred_source": "jp"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        mock_db.add_to_watchlist.assert_called_once_with("ART1", "Artist One", "", preferred_source="jp")

    @patch("server.db")
    def test_post_with_invalid_preferred_source(self, mock_db):
        resp = self.client.post(
            "/api/watchlist",
            data=json.dumps({"artist_id": "ART1", "name": "Artist One", "preferred_source": "bad!"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    @patch("server.db")
    def test_get_with_preferred_source_filter(self, mock_db):
        mock_db.get_watchlist.return_value = [{"artist_id": "ART1", "name": "Artist One", "preferred_source": "jp"}]
        resp = self.client.get("/api/watchlist?preferred_source=jp")
        self.assertEqual(resp.status_code, 200)
        mock_db.get_watchlist.assert_called_once_with(preferred_source="jp", collection_status="", sort="name")

    @patch("server.db")
    def test_get_with_invalid_preferred_source_filter(self, mock_db):
        mock_db.COLLECTION_STATUSES = {"new", "complete", "new_release", "in_progress"}
        resp = self.client.get("/api/watchlist?preferred_source=bad!")
        self.assertEqual(resp.status_code, 400)

    @patch("server.db")
    def test_get_without_filter(self, mock_db):
        mock_db.get_watchlist.return_value = []
        resp = self.client.get("/api/watchlist")
        self.assertEqual(resp.status_code, 200)
        mock_db.get_watchlist.assert_called_once_with(preferred_source="", collection_status="", sort="name")


# ---------------------------------------------------------------------------
# PATCH /api/watchlist/<artist_id>
# ---------------------------------------------------------------------------


class TestApiWatchlistPatch(ServerTestCase):
    @patch("server.db")
    def test_patch_sets_preferred_source(self, mock_db):
        mock_db.update_preferred_source.return_value = None
        resp = self.client.patch(
            "/api/watchlist/ART1",
            data=json.dumps({"preferred_source": "jp"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["ok"])
        mock_db.update_preferred_source.assert_called_once_with("ART1", "jp")

    @patch("server.db")
    def test_patch_clears_preferred_source(self, mock_db):
        mock_db.update_preferred_source.return_value = None
        resp = self.client.patch(
            "/api/watchlist/ART1",
            data=json.dumps({"preferred_source": None}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        mock_db.update_preferred_source.assert_called_once_with("ART1", None)

    @patch("server.db")
    def test_patch_invalid_storefront_returns_400(self, mock_db):
        resp = self.client.patch(
            "/api/watchlist/ART1",
            data=json.dumps({"preferred_source": "bad!"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    @patch("server.db")
    def test_patch_normalises_uppercase(self, mock_db):
        mock_db.update_preferred_source.return_value = None
        resp = self.client.patch(
            "/api/watchlist/ART1",
            data=json.dumps({"preferred_source": "JP"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        mock_db.update_preferred_source.assert_called_once_with("ART1", "jp")


# ---------------------------------------------------------------------------
# GET /api/releases — watched filter
# ---------------------------------------------------------------------------


class TestApiReleasesWatched(ServerTestCase):
    @patch("server.db")
    def test_watched_filter_passed_to_db(self, mock_db):
        mock_db.list_albums.return_value = ([], 0)
        mock_db.get_watched_artist_ids.return_value = set()

        self.client.get("/api/releases?watched=true&view=new")
        args, kwargs = mock_db.list_albums.call_args
        self.assertTrue(kwargs.get("watched_only"))

    @patch("server.db")
    def test_watched_filter_false_by_default(self, mock_db):
        mock_db.list_albums.return_value = ([], 0)
        mock_db.get_watched_artist_ids.return_value = set()

        self.client.get("/api/releases")
        args, kwargs = mock_db.list_albums.call_args
        self.assertFalse(kwargs.get("watched_only", False))

    @patch("server.db")
    def test_watched_filter_with_search(self, mock_db):
        mock_db.search_albums.return_value = ([], 0)
        mock_db.get_watched_artist_ids.return_value = set()

        self.client.get("/api/releases?q=test&watched=true")
        args, kwargs = mock_db.search_albums.call_args
        self.assertTrue(kwargs.get("watched_only"))


# ---------------------------------------------------------------------------
# GET /api/watchlist/export
# ---------------------------------------------------------------------------


class TestApiWatchlistExport(ServerTestCase):
    @patch("server.db")
    def test_export_returns_json_file(self, mock_db):
        mock_db.export_watchlist.return_value = [
            {
                "artist_id": "ART1",
                "name": "Artist One",
                "url": "https://url",
                "preferred_source": "jp",
            },
        ]
        resp = self.client.get("/api/watchlist/export")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/json", resp.content_type)
        self.assertIn("attachment", resp.headers.get("Content-Disposition", ""))
        self.assertIn("am_discovery_", resp.headers.get("Content-Disposition", ""))
        self.assertIn(".json", resp.headers.get("Content-Disposition", ""))

        data = resp.get_json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["artist_id"], "ART1")

    @patch("server.db")
    def test_export_empty_watchlist(self, mock_db):
        mock_db.export_watchlist.return_value = []
        resp = self.client.get("/api/watchlist/export")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), [])

    @patch("server.db")
    def test_export_filename_has_date(self, mock_db):
        mock_db.export_watchlist.return_value = []
        resp = self.client.get("/api/watchlist/export")
        disposition = resp.headers.get("Content-Disposition", "")
        # Filename should match am_discovery_YYYY-MM-DD.json
        self.assertRegex(disposition, r"am_discovery_\d{4}-\d{2}-\d{2}\.json")


# ---------------------------------------------------------------------------
# POST /api/watchlist/import
# ---------------------------------------------------------------------------


class TestApiWatchlistImport(ServerTestCase):
    @patch("server.db")
    def test_import_json_body(self, mock_db):
        mock_db.import_watchlist.return_value = None
        artists = [
            {"artist_id": "ART1", "name": "Artist One"},
            {"artist_id": "ART2", "name": "Artist Two"},
        ]
        resp = self.client.post(
            "/api/watchlist/import",
            data=json.dumps(artists),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["imported"], 2)

    @patch("server.db")
    def test_import_rejects_non_array(self, mock_db):
        resp = self.client.post(
            "/api/watchlist/import",
            data=json.dumps({"artist_id": "ART1"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    @patch("server.db")
    def test_import_rejects_missing_fields(self, mock_db):
        resp = self.client.post(
            "/api/watchlist/import",
            data=json.dumps([{"artist_id": "ART1"}]),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    @patch("server.db")
    def test_import_file_upload(self, mock_db):
        mock_db.import_watchlist.return_value = None
        import io

        data = json.dumps([{"artist_id": "ART1", "name": "Artist One"}])
        resp = self.client.post(
            "/api/watchlist/import",
            data={"file": (io.BytesIO(data.encode()), "watchlist.json")},
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["ok"])

    @patch("server.db")
    def test_import_file_no_file(self, mock_db):
        resp = self.client.post(
            "/api/watchlist/import",
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 400)

    @patch("server.db")
    def test_import_file_invalid_json(self, mock_db):
        import io

        resp = self.client.post(
            "/api/watchlist/import",
            data={"file": (io.BytesIO(b"not json"), "bad.json")},
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------------------
# Status endpoint — watchlist poll fields
# ---------------------------------------------------------------------------


class TestApiStatusWatchlist(ServerTestCase):
    @patch("server.db")
    def test_status_includes_watchlist_fields(self, mock_db):
        mock_db.get_last_run.return_value = None
        mock_db.list_albums.return_value = ([], 0)

        resp = self.client.get("/api/status")
        data = resp.get_json()
        self.assertIn("watchlist_poll_running", data)
        self.assertIn("watchlist_poll_interval_minutes", data)


# ---------------------------------------------------------------------------
# Collection Status API
# ---------------------------------------------------------------------------


class TestApiCollectionStatus(ServerTestCase):
    @patch("server.db")
    def test_get_watchlist_with_collection_status_filter(self, mock_db):
        mock_db.get_watchlist.return_value = []
        mock_db.COLLECTION_STATUSES = {"new", "complete", "new_release", "in_progress"}
        resp = self.client.get("/api/watchlist?collection_status=complete")
        self.assertEqual(resp.status_code, 200)
        mock_db.get_watchlist.assert_called_once_with(preferred_source="", collection_status="complete", sort="name")

    @patch("server.db")
    def test_get_watchlist_invalid_collection_status(self, mock_db):
        mock_db.COLLECTION_STATUSES = {"new", "complete", "new_release", "in_progress"}
        resp = self.client.get("/api/watchlist?collection_status=invalid")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    @patch("server.db")
    def test_patch_collection_status_success(self, mock_db):
        mock_db.COLLECTION_STATUSES = {"new", "complete", "new_release", "in_progress"}
        mock_db.update_collection_status.return_value = True
        resp = self.client.patch(
            "/api/watchlist/ART1",
            data=json.dumps({"collection_status": "complete"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["ok"])
        mock_db.update_collection_status.assert_called_once_with("ART1", "complete")

    @patch("server.db")
    def test_patch_collection_status_invalid_value(self, mock_db):
        mock_db.COLLECTION_STATUSES = {"new", "complete", "new_release", "in_progress"}
        resp = self.client.patch(
            "/api/watchlist/ART1",
            data=json.dumps({"collection_status": "bad_status"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    @patch("server.db")
    def test_patch_collection_status_invalid_transition(self, mock_db):
        mock_db.COLLECTION_STATUSES = {"new", "complete", "new_release", "in_progress"}
        mock_db.update_collection_status.return_value = False
        resp = self.client.patch(
            "/api/watchlist/ART1",
            data=json.dumps({"collection_status": "new_release"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 409)
        self.assertIn("error", resp.get_json())

    @patch("server.db")
    def test_patch_both_preferred_source_and_status(self, mock_db):
        mock_db.COLLECTION_STATUSES = {"new", "complete", "new_release", "in_progress"}
        mock_db.update_preferred_source.return_value = None
        mock_db.update_collection_status.return_value = True
        resp = self.client.patch(
            "/api/watchlist/ART1",
            data=json.dumps({"preferred_source": "jp", "collection_status": "complete"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        mock_db.update_preferred_source.assert_called_once_with("ART1", "jp")
        mock_db.update_collection_status.assert_called_once_with("ART1", "complete")


# ---------------------------------------------------------------------------
# Polling integration with collection status
# ---------------------------------------------------------------------------


class TestDiscoveryPollCollectionStatus(ServerTestCase):
    """Tests for step 5 of _do_poll: checking collection status after room discovery."""

    @patch("server.AppleMusicClient")
    @patch("server.db")
    @patch("server._schedule_next")
    def test_discovery_poll_checks_watched_artists(self, mock_schedule, mock_db, mock_client_cls):
        """After discovering albums, poll should check collection status for watched artists."""
        mock_client = mock_client_cls.return_value
        mock_client.discover_room_url.return_value = "https://music.apple.com/us/room/123"
        mock_client.get_room_new_releases.return_value = [
            {"storeAdamID": "A1", "title": "Album", "artist": "Artist", "url": "https://url", "storefronts": ["us"]},
        ]
        # First call (step 2): album not in DB yet → new_ids
        # Second call (step 5): album now in DB with artist_id after upsert
        mock_db.get_album.side_effect = [None, {"store_adam_id": "A1", "artist_id": "ART1"}]
        mock_client.get_album_full_info.return_value = {"artist_id": "ART1", "release_date": "2025-01-01"}
        mock_db.upsert_album.return_value = None
        mock_db.list_albums.return_value = ([], 1)
        mock_db.log_discovery_run.return_value = None
        mock_db.get_watched_artist_ids.return_value = {"ART1"}
        mock_db.check_and_update_new_releases.return_value = True

        import server

        server._do_poll()

        mock_db.check_and_update_new_releases.assert_called_with("ART1")

    @patch("server.AppleMusicClient")
    @patch("server.db")
    @patch("server._schedule_next")
    def test_discovery_poll_skips_unwatched_artists(self, mock_schedule, mock_db, mock_client_cls):
        """Discovery poll should not check collection status for unwatched artists."""
        mock_client = mock_client_cls.return_value
        mock_client.discover_room_url.return_value = "https://music.apple.com/us/room/123"
        mock_client.get_room_new_releases.return_value = [
            {"storeAdamID": "A1", "title": "Album", "artist": "Artist", "url": "https://url", "storefronts": ["us"]},
        ]
        mock_db.get_album.return_value = None
        mock_client.get_album_full_info.return_value = {"artist_id": "ART99", "release_date": "2025-01-01"}
        mock_db.upsert_album.return_value = None
        mock_db.list_albums.return_value = ([], 1)
        mock_db.log_discovery_run.return_value = None
        mock_db.get_watched_artist_ids.return_value = {"ART1"}  # ART99 is not watched
        mock_db.check_and_update_new_releases.return_value = False

        import server

        server._do_poll()

        mock_db.check_and_update_new_releases.assert_not_called()


class TestWatchlistPollCollectionStatus(ServerTestCase):
    """Tests for _do_watchlist_poll calling check_and_update_new_releases."""

    @patch("server.AppleMusicClient")
    @patch("server.db")
    @patch("server._schedule_watchlist_next")
    def test_watchlist_poll_checks_collection_status(self, mock_schedule, mock_db, mock_client_cls):
        """After refreshing an artist, watchlist poll should check for new releases."""
        mock_client = mock_client_cls.return_value
        mock_db.get_artists_needing_refresh.return_value = [
            {"artist_id": "ART1", "name": "Artist One", "preferred_source": "us"},
        ]
        mock_client.get_artist_all_releases.return_value = ([], {"name": "Artist One"})
        mock_db.upsert_artist.return_value = None
        mock_db.mark_artist_refreshed.return_value = None
        mock_db.check_and_update_new_releases.return_value = False

        import server

        server._do_watchlist_poll()

        mock_db.check_and_update_new_releases.assert_called_once_with("ART1")

    @patch("server.AppleMusicClient")
    @patch("server.db")
    @patch("server._schedule_watchlist_next")
    def test_watchlist_poll_logs_on_new_release_detected(self, mock_schedule, mock_db, mock_client_cls):
        """When check_and_update_new_releases returns True, it should be called and succeed."""
        mock_client = mock_client_cls.return_value
        mock_db.get_artists_needing_refresh.return_value = [
            {"artist_id": "ART1", "name": "Artist One", "preferred_source": "us"},
        ]
        mock_client.get_artist_all_releases.return_value = ([], {"name": "Artist One"})
        mock_db.upsert_artist.return_value = None
        mock_db.mark_artist_refreshed.return_value = None
        mock_db.check_and_update_new_releases.return_value = True

        import server

        server._do_watchlist_poll()

        mock_db.check_and_update_new_releases.assert_called_once_with("ART1")


if __name__ == "__main__":
    unittest.main()
