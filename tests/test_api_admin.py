"""Unit tests for api_admin.py — admin (MusicBrainz seeding) routes.

Uses the shared Flask test client with db, musicbrainz, and seeding mocked at
the api_admin module boundary.
"""

import contextlib
import os
import tempfile
import unittest
from unittest.mock import patch


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


class TestApiAdminArtists(ServerTestCase):
    @patch("api_admin.db")
    def test_lists_unlinked_artists(self, mock_db):
        mock_db.get_unlinked_watchlist_artists.return_value = [
            {
                "artist_id": "ART1",
                "name": "Jay",
                "alt_name": None,
                "url": None,
                "preferred_source": "tw",
                "suggested_mbid": "mbid-1",
                "suggested_name": "Jay Chou",
                "score": 99,
                "candidates": [{"id": "mbid-1", "type": "Person", "area": "Taiwan", "disambiguation": "singer"}],
                "suggestion_status": "pending",
                "mbid_checked_at": 123,
            }
        ]
        resp = self.client.get("/api/admin/artists")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["total"], 1)
        item = data["items"][0]
        self.assertEqual(item["mb_url"], "https://musicbrainz.org/artist/mbid-1")
        self.assertEqual(item["am_discovery_url"], "#/artist/ART1")
        self.assertTrue(item["am_url"].endswith("/artist/ART1"))
        # Richer descriptors are surfaced from the top candidate.
        self.assertEqual(item["suggested_type"], "Person")
        self.assertEqual(item["suggested_area"], "Taiwan")
        self.assertEqual(item["suggested_disambiguation"], "singer")

    @patch("api_admin.db")
    def test_null_suggestion_has_no_mb_url(self, mock_db):
        mock_db.get_unlinked_watchlist_artists.return_value = [
            {
                "artist_id": "ART1",
                "name": "Jay",
                "alt_name": None,
                "url": None,
                "preferred_source": None,
                "suggested_mbid": None,
                "suggested_name": None,
                "score": None,
                "candidates": [],
                "suggestion_status": None,
                "mbid_checked_at": None,
            }
        ]
        resp = self.client.get("/api/admin/artists")
        self.assertIsNone(resp.get_json()["items"][0]["mb_url"])


class TestApiAdminLookup(ServerTestCase):
    @patch("api_admin.mb")
    @patch("api_admin.db")
    def test_lookup_stores_suggestion(self, mock_db, mock_mb):
        mock_db.get_artist_info.return_value = {"name": "Jay Chou"}
        mock_mb.MusicBrainzRateLimitError = Exception
        mock_mb.MusicBrainzError = Exception
        mock_mb.search_artist.return_value = [{"id": "mbid-1", "name": "Jay Chou", "score": 100}]
        resp = self.client.post("/api/admin/artists/ART1/lookup", json={})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["candidates"][0]["id"], "mbid-1")
        mock_db.upsert_mbid_suggestion.assert_called_once()
        mock_db.mark_mbid_checked.assert_called_once_with("ART1")

    @patch("api_admin.mb")
    @patch("api_admin.db")
    def test_lookup_rate_limited(self, mock_db, mock_mb):
        mock_db.get_artist_info.return_value = {"name": "Jay"}

        class RLE(Exception):
            pass

        mock_mb.MusicBrainzRateLimitError = RLE
        mock_mb.MusicBrainzError = Exception
        mock_mb.search_artist.side_effect = RLE("busy")
        resp = self.client.post("/api/admin/artists/ART1/lookup", json={})
        self.assertEqual(resp.status_code, 429)

    @patch("api_admin.mb")
    @patch("api_admin.db")
    def test_lookup_no_name(self, mock_db, mock_mb):
        mock_db.get_artist_info.return_value = {}
        mock_db.get_unlinked_watchlist_artists.return_value = []
        resp = self.client.post("/api/admin/artists/ART1/lookup", json={})
        self.assertEqual(resp.status_code, 400)


class TestApiAdminSearchAll(ServerTestCase):
    @patch("api_admin.seeding")
    def test_search_all_triggers(self, mock_seeding):
        mock_seeding.trigger_bulk_mbid_search.return_value = {"running": True, "total": 0, "done": 0}
        resp = self.client.post("/api/admin/artists/search-all", json={})
        self.assertEqual(resp.status_code, 202)
        mock_seeding.trigger_bulk_mbid_search.assert_called_once()

    @patch("api_admin.seeding")
    def test_search_all_status(self, mock_seeding):
        mock_seeding.bulk_mbid_search_status.return_value = {"running": False, "done": 3, "total": 3, "found": 2}
        resp = self.client.get("/api/admin/artists/search-all/status")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["found"], 2)


class TestApiAdminApprove(ServerTestCase):
    @patch("api_admin.db")
    def test_approve_with_explicit_mbid(self, mock_db):
        resp = self.client.post("/api/admin/artists/ART1/approve", json={"musicbrainz_id": "mbid-9"})
        self.assertEqual(resp.status_code, 200)
        mock_db.upsert_artist.assert_called_once_with("ART1", musicbrainz_id="mbid-9")
        mock_db.set_suggestion_status.assert_called_once_with("ART1", "approved")

    @patch("api_admin.db")
    def test_approve_uses_suggestion_when_no_mbid(self, mock_db):
        mock_db.get_mbid_suggestion.return_value = {"suggested_mbid": "mbid-sug"}
        resp = self.client.post("/api/admin/artists/ART1/approve", json={})
        self.assertEqual(resp.status_code, 200)
        mock_db.upsert_artist.assert_called_once_with("ART1", musicbrainz_id="mbid-sug")

    @patch("api_admin.db")
    def test_approve_no_mbid_available(self, mock_db):
        mock_db.get_mbid_suggestion.return_value = None
        resp = self.client.post("/api/admin/artists/ART1/approve", json={})
        self.assertEqual(resp.status_code, 400)


class TestApiAdminDeny(ServerTestCase):
    @patch("api_admin.db")
    def test_deny_existing_suggestion(self, mock_db):
        mock_db.get_mbid_suggestion.return_value = {"suggested_mbid": "x"}
        resp = self.client.post("/api/admin/artists/ART1/deny", json={})
        self.assertEqual(resp.status_code, 200)
        mock_db.set_suggestion_status.assert_called_once_with("ART1", "denied")

    @patch("api_admin.db")
    def test_deny_creates_denied_row_when_none(self, mock_db):
        mock_db.get_mbid_suggestion.return_value = None
        resp = self.client.post("/api/admin/artists/ART1/deny", json={})
        self.assertEqual(resp.status_code, 200)
        mock_db.upsert_mbid_suggestion.assert_called_once_with("ART1", None, None, None, None, status="denied")


class TestApiAdminReleases(ServerTestCase):
    @patch("api_admin.db")
    def test_lists_releases(self, mock_db):
        mock_db.get_seeding_releases.return_value = [
            {
                "store_adam_id": "A1",
                "title": "Album",
                "storefronts": '["tw"]',
                "artist_name": "Jay",
                "preferred_source": "tw",
                "artist_musicbrainz_id": "m",
                "upc": "111",
            }
        ]
        resp = self.client.get("/api/admin/releases?sort=release_date")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["storefronts"], ["tw"])
        mock_db.get_seeding_releases.assert_called_once_with(sort="release_date", include_hidden=False)

    @patch("api_admin.db")
    def test_invalid_sort(self, mock_db):
        resp = self.client.get("/api/admin/releases?sort=bogus")
        self.assertEqual(resp.status_code, 400)

    @patch("api_admin.db")
    def test_include_hidden(self, mock_db):
        mock_db.get_seeding_releases.return_value = []
        self.client.get("/api/admin/releases?include_hidden=true")
        mock_db.get_seeding_releases.assert_called_once_with(sort="release_date", include_hidden=True)

    @patch("api_admin.db")
    def test_hide(self, mock_db):
        resp = self.client.post("/api/admin/releases/A1/hide", json={})
        self.assertEqual(resp.status_code, 200)
        mock_db.set_album_hidden_from_seeding.assert_called_once_with("A1", True)

    @patch("api_admin.db")
    def test_unhide(self, mock_db):
        resp = self.client.post("/api/admin/releases/A1/unhide", json={})
        self.assertEqual(resp.status_code, 200)
        mock_db.set_album_hidden_from_seeding.assert_called_once_with("A1", False)


class TestApiAdminScanStatus(ServerTestCase):
    @patch("api_admin.seeding")
    def test_status(self, mock_seeding):
        mock_seeding.status.return_value = {"enabled": True, "seeding_release_count": 3}
        resp = self.client.get("/api/admin/status")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["seeding_release_count"], 3)

    @patch("api_admin.seeding")
    def test_scan_now(self, mock_seeding):
        resp = self.client.post("/api/admin/scan", json={})
        self.assertEqual(resp.status_code, 202)
        mock_seeding.trigger_scan_now.assert_called_once()


if __name__ == "__main__":
    unittest.main()
