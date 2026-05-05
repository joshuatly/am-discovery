"""Tests for api_debug.py — Apple Music raw debug endpoints."""

import contextlib
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch


class DebugEndpointTestCase(unittest.TestCase):
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

    # ------------------------------------------------------------------
    # /api/debug/apple-music/artist
    # ------------------------------------------------------------------

    def test_artist_missing_id_returns_400(self):
        resp = self.client.get("/api/debug/apple-music/artist")
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn("error", data)

    def test_artist_invalid_storefront_returns_400(self):
        resp = self.client.get("/api/debug/apple-music/artist?id=12345&storefront=toolong")
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn("error", data)

    @patch("api_debug.AppleMusicClient")
    def test_artist_returns_raw_payload(self, MockClient):
        raw_payload = {"data": [{"id": "12345", "attributes": {"name": "Test Artist"}}]}
        instance = MagicMock()
        instance.catalog_get_raw.return_value = (200, raw_payload)
        MockClient.return_value = instance

        resp = self.client.get("/api/debug/apple-music/artist?id=12345&storefront=us")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), raw_payload)
        instance.catalog_get_raw.assert_called_once_with("/v1/catalog/us/artists/12345", None)

    @patch("api_debug.AppleMusicClient")
    def test_artist_forwards_include_and_extend(self, MockClient):
        instance = MagicMock()
        instance.catalog_get_raw.return_value = (200, {"data": []})
        MockClient.return_value = instance

        resp = self.client.get("/api/debug/apple-music/artist?id=99&storefront=jp&include=albums&extend=artistBio")
        self.assertEqual(resp.status_code, 200)
        instance.catalog_get_raw.assert_called_once_with(
            "/v1/catalog/jp/artists/99",
            {"include": "albums", "extend": "artistBio"},
        )

    @patch("api_debug.AppleMusicClient")
    def test_artist_propagates_error_status(self, MockClient):
        instance = MagicMock()
        instance.catalog_get_raw.return_value = (404, {"errors": [{"status": "404"}]})
        MockClient.return_value = instance

        resp = self.client.get("/api/debug/apple-music/artist?id=0&storefront=us")
        self.assertEqual(resp.status_code, 404)

    @patch("api_debug.AppleMusicClient")
    def test_artist_defaults_storefront_from_config(self, MockClient):
        import json

        with open(self._cfg_path, "w") as f:
            json.dump({"home_storefront": "hk"}, f)

        instance = MagicMock()
        instance.catalog_get_raw.return_value = (200, {"data": []})
        MockClient.return_value = instance

        resp = self.client.get("/api/debug/apple-music/artist?id=123")
        self.assertEqual(resp.status_code, 200)
        instance.catalog_get_raw.assert_called_once_with("/v1/catalog/hk/artists/123", None)

    # ------------------------------------------------------------------
    # /api/debug/apple-music/album
    # ------------------------------------------------------------------

    def test_album_missing_id_returns_400(self):
        resp = self.client.get("/api/debug/apple-music/album")
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn("error", data)

    def test_album_invalid_storefront_returns_400(self):
        resp = self.client.get("/api/debug/apple-music/album?id=12345&storefront=TOOLONG")
        self.assertEqual(resp.status_code, 400)

    @patch("api_debug.AppleMusicClient")
    def test_album_returns_raw_payload(self, MockClient):
        raw_payload = {"data": [{"id": "999", "attributes": {"name": "Test Album"}}]}
        instance = MagicMock()
        instance.catalog_get_raw.return_value = (200, raw_payload)
        MockClient.return_value = instance

        resp = self.client.get("/api/debug/apple-music/album?id=999&storefront=us")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), raw_payload)
        instance.catalog_get_raw.assert_called_once_with("/v1/catalog/us/albums/999", None)

    @patch("api_debug.AppleMusicClient")
    def test_album_forwards_include_and_extend(self, MockClient):
        instance = MagicMock()
        instance.catalog_get_raw.return_value = (200, {"data": []})
        MockClient.return_value = instance

        resp = self.client.get(
            "/api/debug/apple-music/album?id=42&storefront=tw&include=tracks,artists&extend=extendedAssetUrls"
        )
        self.assertEqual(resp.status_code, 200)
        instance.catalog_get_raw.assert_called_once_with(
            "/v1/catalog/tw/albums/42",
            {"include": "tracks,artists", "extend": "extendedAssetUrls"},
        )

    @patch("api_debug.AppleMusicClient")
    def test_album_propagates_error_status(self, MockClient):
        instance = MagicMock()
        instance.catalog_get_raw.return_value = (404, {"errors": [{"status": "404"}]})
        MockClient.return_value = instance

        resp = self.client.get("/api/debug/apple-music/album?id=0&storefront=us")
        self.assertEqual(resp.status_code, 404)

    @patch("api_debug.AppleMusicClient")
    def test_album_defaults_storefront_from_config(self, MockClient):
        import json

        with open(self._cfg_path, "w") as f:
            json.dump({"home_storefront": "my"}, f)

        instance = MagicMock()
        instance.catalog_get_raw.return_value = (200, {"data": []})
        MockClient.return_value = instance

        resp = self.client.get("/api/debug/apple-music/album?id=55")
        self.assertEqual(resp.status_code, 200)
        instance.catalog_get_raw.assert_called_once_with("/v1/catalog/my/albums/55", None)

    @patch("api_debug.AppleMusicClient")
    def test_connection_error_returns_502(self, MockClient):
        instance = MagicMock()
        instance.catalog_get_raw.return_value = (0, {"error": "connection refused"})
        MockClient.return_value = instance

        resp = self.client.get("/api/debug/apple-music/album?id=1&storefront=us")
        self.assertEqual(resp.status_code, 502)


if __name__ == "__main__":
    unittest.main()
