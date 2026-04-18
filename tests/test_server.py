"""Tests for server.py — config helpers and background polling scheduler.

API route tests live in test_api.py and test_api_watchlist.py.
"""

import contextlib
import os
import tempfile
import unittest
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Base class — sets up Flask test client with mocked config
# ---------------------------------------------------------------------------


class ServerTestCase(unittest.TestCase):
    def setUp(self):
        self._cfg_fd, self._cfg_path = tempfile.mkstemp(suffix=".json")
        os.close(self._cfg_fd)
        os.unlink(self._cfg_path)

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
# load_config / save_config
# ---------------------------------------------------------------------------


class TestConfigHelpers(ServerTestCase):
    def test_load_config_returns_defaults_when_no_file(self):
        import config

        cfg = config.load_config()
        self.assertEqual(cfg["newrelease_poll_interval_days"], 1)
        self.assertIsInstance(cfg["check_storefronts"], list)

    def test_save_and_load_config(self):
        import config

        custom = {"newrelease_poll_interval_days": 3, "check_storefronts": ["us"]}
        config.save_config(custom)
        loaded = config.load_config()
        self.assertEqual(loaded["newrelease_poll_interval_days"], 3)

    def test_load_config_merges_defaults(self):
        """Config on disk should be merged with defaults (missing keys filled in)."""
        import config

        config.save_config({"newrelease_poll_interval_days": 2})
        loaded = config.load_config()
        self.assertIn("check_storefronts", loaded)


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
        mock_client.discover_new_releases.return_value = (
            [
                {
                    "storeAdamID": "A1",
                    "title": "Album",
                    "artist": "Artist",
                    "url": "https://url",
                    "storefronts": ["us"],
                },
            ],
            "123",
            "2026-04-18T00:00:00Z",
        )
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
        mock_client.discover_new_releases.return_value = (
            [
                {
                    "storeAdamID": "A1",
                    "title": "Album",
                    "artist": "Artist",
                    "url": "https://url",
                    "storefronts": ["us"],
                },
            ],
            "123",
            None,
        )
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
