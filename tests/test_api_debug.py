"""Tests for api_debug.py — Apple Music raw debug endpoints."""

import contextlib
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from client import _VIEW_MAP

_ARTIST_DEFAULTS = {
    "views": ",".join(_VIEW_MAP),
    **{f"limit[{v}]": "100" for v in _VIEW_MAP},
    "extend": "bornOrFormed,origin,artistBio",
}

_ALBUM_DEFAULTS = {
    "include": "tracks,artists",
    "extend": "extendedAssetUrls",
}


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
        self.assertIn("error", resp.get_json())

    def test_artist_invalid_storefront_returns_400(self):
        resp = self.client.get("/api/debug/apple-music/artist?id=12345&storefront=toolong")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    @patch("api_debug.AppleMusicClient")
    def test_artist_uses_app_defaults(self, MockClient):
        instance = MagicMock()
        instance.catalog_get_raw.return_value = (200, {"data": []})
        MockClient.return_value = instance

        resp = self.client.get("/api/debug/apple-music/artist?id=12345&storefront=us")
        self.assertEqual(resp.status_code, 200)
        instance.catalog_get_raw.assert_called_once_with(
            "/v1/catalog/us/artists/12345",
            _ARTIST_DEFAULTS,
        )

    @patch("api_debug.AppleMusicClient")
    def test_artist_extend_overrides_default(self, MockClient):
        instance = MagicMock()
        instance.catalog_get_raw.return_value = (200, {"data": []})
        MockClient.return_value = instance

        resp = self.client.get("/api/debug/apple-music/artist?id=99&storefront=jp&extend=artistBio")
        self.assertEqual(resp.status_code, 200)
        _, called_params = instance.catalog_get_raw.call_args[0]
        self.assertEqual(called_params["extend"], "artistBio")
        # views and limits still present
        self.assertIn("views", called_params)

    @patch("api_debug.AppleMusicClient")
    def test_artist_views_override_rebuilds_limits(self, MockClient):
        instance = MagicMock()
        instance.catalog_get_raw.return_value = (200, {"data": []})
        MockClient.return_value = instance

        resp = self.client.get("/api/debug/apple-music/artist?id=1&storefront=us&views=full-albums")
        self.assertEqual(resp.status_code, 200)
        _, called_params = instance.catalog_get_raw.call_args[0]
        self.assertEqual(called_params["views"], "full-albums")
        self.assertIn("limit[full-albums]", called_params)
        # limits for other views should be gone
        self.assertNotIn("limit[singles]", called_params)

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
        called_path, _ = instance.catalog_get_raw.call_args[0]
        self.assertIn("/hk/artists/123", called_path)

    # ------------------------------------------------------------------
    # /api/debug/apple-music/album
    # ------------------------------------------------------------------

    def test_album_missing_id_returns_400(self):
        resp = self.client.get("/api/debug/apple-music/album")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    def test_album_invalid_storefront_returns_400(self):
        resp = self.client.get("/api/debug/apple-music/album?id=12345&storefront=TOOLONG")
        self.assertEqual(resp.status_code, 400)

    @patch("api_debug.AppleMusicClient")
    def test_album_uses_app_defaults(self, MockClient):
        instance = MagicMock()
        instance.catalog_get_raw.return_value = (200, {"data": []})
        MockClient.return_value = instance

        resp = self.client.get("/api/debug/apple-music/album?id=999&storefront=us")
        self.assertEqual(resp.status_code, 200)
        instance.catalog_get_raw.assert_called_once_with(
            "/v1/catalog/us/albums/999",
            _ALBUM_DEFAULTS,
        )

    @patch("api_debug.AppleMusicClient")
    def test_album_include_overrides_default(self, MockClient):
        instance = MagicMock()
        instance.catalog_get_raw.return_value = (200, {"data": []})
        MockClient.return_value = instance

        resp = self.client.get("/api/debug/apple-music/album?id=42&storefront=tw&include=tracks")
        self.assertEqual(resp.status_code, 200)
        _, called_params = instance.catalog_get_raw.call_args[0]
        self.assertEqual(called_params["include"], "tracks")
        self.assertEqual(called_params["extend"], "extendedAssetUrls")  # default preserved

    @patch("api_debug.AppleMusicClient")
    def test_album_extend_overrides_default(self, MockClient):
        instance = MagicMock()
        instance.catalog_get_raw.return_value = (200, {"data": []})
        MockClient.return_value = instance

        resp = self.client.get("/api/debug/apple-music/album?id=42&storefront=tw&extend=foo")
        self.assertEqual(resp.status_code, 200)
        _, called_params = instance.catalog_get_raw.call_args[0]
        self.assertEqual(called_params["extend"], "foo")
        self.assertEqual(called_params["include"], "tracks,artists")  # default preserved

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
        called_path, _ = instance.catalog_get_raw.call_args[0]
        self.assertIn("/my/albums/55", called_path)

    @patch("api_debug.AppleMusicClient")
    def test_connection_error_returns_502(self, MockClient):
        instance = MagicMock()
        instance.catalog_get_raw.return_value = (0, {"error": "connection refused"})
        MockClient.return_value = instance

        resp = self.client.get("/api/debug/apple-music/album?id=1&storefront=us")
        self.assertEqual(resp.status_code, 502)


if __name__ == "__main__":
    unittest.main()
