"""Tests for api_watchlist.py — watchlist REST API routes."""

import contextlib
import json
import os
import tempfile
import unittest
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Base class — sets up Flask test client with mocked config & db
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
# GET/POST/DELETE /api/watchlist
# ---------------------------------------------------------------------------


class TestApiWatchlist(ServerTestCase):
    @patch("api_watchlist.db")
    def test_get_empty_watchlist(self, mock_db):
        mock_db.get_watchlist.return_value = []
        mock_db.COLLECTION_STATUSES = set()
        resp = self.client.get("/api/watchlist")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), [])

    @patch("api_watchlist.db")
    def test_get_watchlist_returns_artists(self, mock_db):
        mock_db.get_watchlist.return_value = [{"artist_id": "ART1", "name": "Artist One", "url": None, "added_at": 0}]
        mock_db.COLLECTION_STATUSES = set()
        resp = self.client.get("/api/watchlist")
        data = resp.get_json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["name"], "Artist One")

    @patch("api_watchlist.db")
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

    @patch("api_watchlist.db")
    def test_post_watchlist_missing_artist_id(self, mock_db):
        resp = self.client.post(
            "/api/watchlist",
            data=json.dumps({"name": "Artist One"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    @patch("api_watchlist.db")
    def test_post_watchlist_missing_name(self, mock_db):
        resp = self.client.post(
            "/api/watchlist",
            data=json.dumps({"artist_id": "ART1"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    @patch("api_watchlist.db")
    def test_post_watchlist_empty_artist_id(self, mock_db):
        resp = self.client.post(
            "/api/watchlist",
            data=json.dumps({"artist_id": "", "name": "Artist One"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    @patch("api_watchlist.db")
    def test_delete_watchlist(self, mock_db):
        mock_db.remove_from_watchlist.return_value = None
        resp = self.client.delete("/api/watchlist/ART1")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["ok"])
        mock_db.remove_from_watchlist.assert_called_once_with("ART1")

    @patch("api_watchlist.db")
    def test_delete_nonexistent_artist_still_ok(self, mock_db):
        """Deleting a non-existent artist should not raise — return 200."""
        mock_db.remove_from_watchlist.return_value = None
        resp = self.client.delete("/api/watchlist/NONEXISTENT")
        self.assertEqual(resp.status_code, 200)

    @patch("api_watchlist.db")
    def test_get_watchlist_sort_name(self, mock_db):
        mock_db.get_watchlist.return_value = []
        mock_db.COLLECTION_STATUSES = set()
        resp = self.client.get("/api/watchlist?sort=name")
        self.assertEqual(resp.status_code, 200)
        mock_db.get_watchlist.assert_called_once_with(preferred_source="", collection_status="", sort="name")

    @patch("api_watchlist.db")
    def test_get_watchlist_sort_added(self, mock_db):
        mock_db.get_watchlist.return_value = []
        mock_db.COLLECTION_STATUSES = set()
        resp = self.client.get("/api/watchlist?sort=added")
        self.assertEqual(resp.status_code, 200)
        mock_db.get_watchlist.assert_called_once_with(preferred_source="", collection_status="", sort="added")

    @patch("api_watchlist.db")
    def test_get_watchlist_sort_recent_release(self, mock_db):
        mock_db.get_watchlist.return_value = []
        mock_db.COLLECTION_STATUSES = set()
        resp = self.client.get("/api/watchlist?sort=recent_release")
        self.assertEqual(resp.status_code, 200)
        mock_db.get_watchlist.assert_called_once_with(preferred_source="", collection_status="", sort="recent_release")

    @patch("api_watchlist.db")
    def test_get_watchlist_invalid_sort_returns_400(self, mock_db):
        mock_db.COLLECTION_STATUSES = set()
        resp = self.client.get("/api/watchlist?sort=bogus")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())


# ---------------------------------------------------------------------------
# GET /api/watchlist/ids
# ---------------------------------------------------------------------------


class TestApiWatchlistIds(ServerTestCase):
    @patch("api_watchlist.db")
    def test_get_ids_returns_list(self, mock_db):
        mock_db.get_watchlist_ids.return_value = ["ART1", "ART2"]
        resp = self.client.get("/api/watchlist/ids")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), ["ART1", "ART2"])

    @patch("api_watchlist.db")
    def test_get_ids_empty(self, mock_db):
        mock_db.get_watchlist_ids.return_value = []
        resp = self.client.get("/api/watchlist/ids")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), [])


# ---------------------------------------------------------------------------
# Watchlist preferred_source
# ---------------------------------------------------------------------------


class TestApiWatchlistPreferredSource(ServerTestCase):
    @patch("api_watchlist.db")
    def test_post_with_preferred_source(self, mock_db):
        mock_db.add_to_watchlist.return_value = None
        resp = self.client.post(
            "/api/watchlist",
            data=json.dumps({"artist_id": "ART1", "name": "Artist One", "preferred_source": "jp"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        mock_db.add_to_watchlist.assert_called_once_with("ART1", "Artist One", "", preferred_source="jp")

    @patch("api_watchlist.db")
    def test_post_with_invalid_preferred_source(self, mock_db):
        resp = self.client.post(
            "/api/watchlist",
            data=json.dumps({"artist_id": "ART1", "name": "Artist One", "preferred_source": "bad!"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    @patch("api_watchlist.db")
    def test_get_with_preferred_source_filter(self, mock_db):
        mock_db.get_watchlist.return_value = [{"artist_id": "ART1", "name": "Artist One", "preferred_source": "jp"}]
        mock_db.COLLECTION_STATUSES = set()
        resp = self.client.get("/api/watchlist?preferred_source=jp")
        self.assertEqual(resp.status_code, 200)
        mock_db.get_watchlist.assert_called_once_with(preferred_source="jp", collection_status="", sort="name")

    @patch("api_watchlist.db")
    def test_get_with_invalid_preferred_source_filter(self, mock_db):
        mock_db.COLLECTION_STATUSES = {"new", "complete", "new_release", "in_progress"}
        resp = self.client.get("/api/watchlist?preferred_source=bad!")
        self.assertEqual(resp.status_code, 400)

    @patch("api_watchlist.db")
    def test_get_without_filter(self, mock_db):
        mock_db.get_watchlist.return_value = []
        mock_db.COLLECTION_STATUSES = set()
        resp = self.client.get("/api/watchlist")
        self.assertEqual(resp.status_code, 200)
        mock_db.get_watchlist.assert_called_once_with(preferred_source="", collection_status="", sort="name")


# ---------------------------------------------------------------------------
# PATCH /api/watchlist/<artist_id>
# ---------------------------------------------------------------------------


class TestApiWatchlistPatch(ServerTestCase):
    @patch("api_watchlist.db")
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

    @patch("api_watchlist.db")
    def test_patch_clears_preferred_source(self, mock_db):
        mock_db.update_preferred_source.return_value = None
        resp = self.client.patch(
            "/api/watchlist/ART1",
            data=json.dumps({"preferred_source": None}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        mock_db.update_preferred_source.assert_called_once_with("ART1", None)

    @patch("api_watchlist.db")
    def test_patch_invalid_storefront_returns_400(self, mock_db):
        resp = self.client.patch(
            "/api/watchlist/ART1",
            data=json.dumps({"preferred_source": "bad!"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    @patch("api_watchlist.db")
    def test_patch_normalises_uppercase(self, mock_db):
        mock_db.update_preferred_source.return_value = None
        resp = self.client.patch(
            "/api/watchlist/ART1",
            data=json.dumps({"preferred_source": "JP"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        mock_db.update_preferred_source.assert_called_once_with("ART1", "jp")

    @patch("api_watchlist.db")
    def test_patch_sets_alt_name(self, mock_db):
        mock_db.update_watchlist_alt_name.return_value = None
        resp = self.client.patch(
            "/api/watchlist/ART1",
            data=json.dumps({"alt_name": "Hitsujibungaku"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["ok"])
        mock_db.update_watchlist_alt_name.assert_called_once_with("ART1", "Hitsujibungaku")

    @patch("api_watchlist.db")
    def test_patch_clears_alt_name_with_null(self, mock_db):
        mock_db.update_watchlist_alt_name.return_value = None
        resp = self.client.patch(
            "/api/watchlist/ART1",
            data=json.dumps({"alt_name": None}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        mock_db.update_watchlist_alt_name.assert_called_once_with("ART1", None)

    @patch("api_watchlist.db")
    def test_patch_clears_alt_name_with_empty_string(self, mock_db):
        mock_db.update_watchlist_alt_name.return_value = None
        resp = self.client.patch(
            "/api/watchlist/ART1",
            data=json.dumps({"alt_name": ""}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        mock_db.update_watchlist_alt_name.assert_called_once_with("ART1", None)

    @patch("api_watchlist.db")
    def test_patch_alt_name_too_long_returns_400(self, mock_db):
        resp = self.client.patch(
            "/api/watchlist/ART1",
            data=json.dumps({"alt_name": "x" * 201}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    @patch("api_watchlist.db")
    def test_patch_alt_name_strips_whitespace(self, mock_db):
        mock_db.update_watchlist_alt_name.return_value = None
        resp = self.client.patch(
            "/api/watchlist/ART1",
            data=json.dumps({"alt_name": "  Hitsujibungaku  "}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        mock_db.update_watchlist_alt_name.assert_called_once_with("ART1", "Hitsujibungaku")


# ---------------------------------------------------------------------------
# GET /api/watchlist/export
# ---------------------------------------------------------------------------


class TestApiWatchlistExport(ServerTestCase):
    @patch("api_watchlist.db")
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

    @patch("api_watchlist.db")
    def test_export_empty_watchlist(self, mock_db):
        mock_db.export_watchlist.return_value = []
        resp = self.client.get("/api/watchlist/export")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), [])

    @patch("api_watchlist.db")
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
    @patch("api_watchlist.db")
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

    @patch("api_watchlist.db")
    def test_import_rejects_non_array(self, mock_db):
        resp = self.client.post(
            "/api/watchlist/import",
            data=json.dumps({"artist_id": "ART1"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    @patch("api_watchlist.db")
    def test_import_rejects_missing_fields(self, mock_db):
        resp = self.client.post(
            "/api/watchlist/import",
            data=json.dumps([{"artist_id": "ART1"}]),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    @patch("api_watchlist.db")
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

    @patch("api_watchlist.db")
    def test_import_file_no_file(self, mock_db):
        resp = self.client.post(
            "/api/watchlist/import",
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 400)

    @patch("api_watchlist.db")
    def test_import_file_invalid_json(self, mock_db):
        import io

        resp = self.client.post(
            "/api/watchlist/import",
            data={"file": (io.BytesIO(b"not json"), "bad.json")},
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------------------
# Collection Status API
# ---------------------------------------------------------------------------


class TestApiCollectionStatus(ServerTestCase):
    @patch("api_watchlist.db")
    def test_get_watchlist_with_collection_status_filter(self, mock_db):
        mock_db.get_watchlist.return_value = []
        mock_db.COLLECTION_STATUSES = {"new", "complete", "new_release", "in_progress"}
        resp = self.client.get("/api/watchlist?collection_status=complete")
        self.assertEqual(resp.status_code, 200)
        mock_db.get_watchlist.assert_called_once_with(preferred_source="", collection_status="complete", sort="name")

    @patch("api_watchlist.db")
    def test_get_watchlist_invalid_collection_status(self, mock_db):
        mock_db.COLLECTION_STATUSES = {"new", "complete", "new_release", "in_progress"}
        resp = self.client.get("/api/watchlist?collection_status=invalid")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    @patch("api_watchlist.db")
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

    @patch("api_watchlist.db")
    def test_patch_collection_status_invalid_value(self, mock_db):
        mock_db.COLLECTION_STATUSES = {"new", "complete", "new_release", "in_progress"}
        resp = self.client.patch(
            "/api/watchlist/ART1",
            data=json.dumps({"collection_status": "bad_status"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    @patch("api_watchlist.db")
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

    @patch("api_watchlist.db")
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


if __name__ == "__main__":
    unittest.main()
