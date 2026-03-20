"""Unit tests for AppleMusicClient in client.py."""

import base64
import json
import time
import unittest
from unittest.mock import MagicMock, mock_open, patch

from client import AppleMusicClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_jwt(exp: int) -> str:
    """Build a minimal JWT-like string with the given expiry timestamp."""
    header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').rstrip(b"=").decode()
    payload_bytes = json.dumps({"exp": exp}).encode()
    payload = base64.urlsafe_b64encode(payload_bytes).rstrip(b"=").decode()
    return f"{header}.{payload}.fakesig"


def _make_client(bearer_token="test-token", user_token=None):
    """Return an AppleMusicClient with _get_bearer_token and _load_cors_proxy short-circuited."""
    with patch("client._load_cors_proxy", return_value=""), \
         patch.object(AppleMusicClient, "_get_bearer_token", return_value=bearer_token):
        return AppleMusicClient(user_token=user_token)


ROOM_HTML_TEMPLATE = """
<script type="application/json" id="serialized-server-data">{payload}</script>
"""


def _make_room_payload(sections):
    data = [{"data": {"data": [{"data": {"sections": sections}}]}}]
    return json.dumps(data)


def _make_album_api_response(name="Test Album", artist="Test Artist", release_date="2026-03-01",
                              track_count=10, adam_id="111222333", artwork_url=None,
                              genre_names=None, audio_traits=None, mastered_for_itunes=False,
                              tracks=None, artists=None):
    attrs = {
        "name": name,
        "artistName": artist,
        "releaseDate": release_date,
        "trackCount": track_count,
        "genreNames": genre_names if genre_names is not None else ["Pop"],
        "audioTraits": audio_traits or [],
        "isMasteredForItunes": mastered_for_itunes,
        "editorialNotes": {"standard": "Great album."},
    }
    if artwork_url:
        attrs["artwork"] = {"url": artwork_url}

    artist_rel = artists or [
        {"id": "artist-id-1", "attributes": {"url": "https://music.apple.com/us/artist/test/1"}}
    ]

    track_data = [
        {
            "attributes": {
                "name": t["name"],
                "trackNumber": t.get("trackNumber", 1),
                "durationInMillis": t.get("durationInMillis", 200000),
            }
        }
        for t in (tracks or [])
    ]

    return {
        "data": [{
            "id": adam_id,
            "attributes": attrs,
            "relationships": {
                "artists": {"data": artist_rel},
                "tracks": {"data": track_data},
            },
        }]
    }


def _make_artist_views_response(albums=None, singles=None, compilations=None, live=None):
    def _item(adam_id, name, artist, url):
        return {"id": adam_id, "attributes": {"name": name, "artistName": artist, "url": url}}

    return {
        "data": [{
            "views": {
                "full-albums":        {"data": [_item(*a) for a in (albums or [])]},
                "compilation-albums": {"data": [_item(*a) for a in (compilations or [])]},
                "live-albums":        {"data": [_item(*a) for a in (live or [])]},
                "singles":            {"data": [_item(*a) for a in (singles or [])]},
            }
        }]
    }


# ---------------------------------------------------------------------------
# _is_jwt_expired
# ---------------------------------------------------------------------------

class TestIsJwtExpired(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()

    def test_valid_token_returns_false(self):
        token = _make_jwt(int(time.time()) + 3600)
        self.assertFalse(self.client._is_jwt_expired(token))

    def test_expired_token_returns_true(self):
        token = _make_jwt(int(time.time()) - 3600)
        self.assertTrue(self.client._is_jwt_expired(token))

    def test_malformed_token_returns_true(self):
        self.assertTrue(self.client._is_jwt_expired("not.a.jwt"))

    def test_empty_string_returns_true(self):
        self.assertTrue(self.client._is_jwt_expired(""))

    def test_missing_exp_field_returns_true(self):
        header = base64.urlsafe_b64encode(b'{}').rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(b'{}').rstrip(b"=").decode()
        # exp defaults to 0 -> always expired
        self.assertTrue(self.client._is_jwt_expired(f"{header}.{payload}.sig"))


# ---------------------------------------------------------------------------
# _apply_proxy
# ---------------------------------------------------------------------------

class TestApplyProxy(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()

    def test_no_proxy_returns_url_unchanged(self):
        url = "https://music.apple.com/us/browse"
        self.assertEqual(self.client._apply_proxy(url), url)

    def test_proxy_prepends_encoded_url(self):
        self.client._cors_proxy = "https://proxy.example.com/"
        url = "https://music.apple.com/us/browse"
        result = self.client._apply_proxy(url)
        self.assertTrue(result.startswith("https://proxy.example.com/"))
        # The original URL should be percent-encoded in the suffix
        self.assertNotIn("://", result[len("https://proxy.example.com/"):])
        self.assertIn("music.apple.com", result)


# ---------------------------------------------------------------------------
# _web_get
# ---------------------------------------------------------------------------

class TestWebGet(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()

    def _mock_urlopen(self, body: bytes):
        resp = MagicMock()
        resp.read.return_value = body
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    @patch("urllib.request.urlopen")
    def test_returns_decoded_response_body(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_urlopen(b"Hello World")
        self.assertEqual(self.client._web_get("https://example.com"), "Hello World")

    @patch("urllib.request.urlopen", side_effect=Exception("network error"))
    def test_returns_none_on_exception(self, _):
        self.assertIsNone(self.client._web_get("https://example.com"))

    @patch("urllib.request.urlopen")
    def test_uses_web_headers_by_default(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_urlopen(b"ok")
        self.client._web_get("https://example.com")
        req = mock_urlopen.call_args[0][0]
        self.assertIn("User-agent", req.headers)

    @patch("urllib.request.urlopen")
    def test_uses_custom_headers_when_provided(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_urlopen(b"ok")
        self.client._web_get("https://example.com", headers={"X-Custom": "yes"})
        req = mock_urlopen.call_args[0][0]
        self.assertIn("X-custom", req.headers)


# ---------------------------------------------------------------------------
# _amp_api_get
# ---------------------------------------------------------------------------

class TestAmpApiGet(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()

    def _mock_urlopen(self, data: dict):
        resp = MagicMock()
        resp.read.return_value = json.dumps(data).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    @patch("urllib.request.urlopen")
    def test_returns_parsed_json(self, mock_urlopen):
        payload = {"data": [{"id": "123"}]}
        mock_urlopen.return_value = self._mock_urlopen(payload)
        result = self.client._amp_api_get("/v1/catalog/us/albums/123")
        self.assertEqual(result, payload)

    @patch("urllib.request.urlopen", side_effect=Exception("network error"))
    def test_returns_empty_dict_on_exception(self, _):
        self.assertEqual(self.client._amp_api_get("/v1/catalog/us/albums/123"), {})

    @patch("urllib.request.urlopen")
    def test_includes_query_params_in_url(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_urlopen({})
        self.client._amp_api_get("/v1/catalog/us/albums/123", {"include": "tracks"})
        req = mock_urlopen.call_args[0][0]
        self.assertIn("include=tracks", req.full_url)


# ---------------------------------------------------------------------------
# _fetch_new_bearer_token
# ---------------------------------------------------------------------------

class TestFetchNewBearerToken(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()

    def test_extracts_token_from_js(self):
        fake_token = "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0In0.fakesig"
        html = '<script src="/assets/index-abc.js"></script>'
        js = f'var t="{fake_token}"'

        def side_effect(url, headers=None, timeout=10):
            return html if "browse" in url else js

        with patch.object(self.client, "_web_get", side_effect=side_effect):
            result = self.client._fetch_new_bearer_token()
        self.assertEqual(result, fake_token)

    def test_returns_none_when_html_fetch_fails(self):
        with patch.object(self.client, "_web_get", return_value=None):
            self.assertIsNone(self.client._fetch_new_bearer_token())

    def test_returns_none_when_no_script_tag(self):
        with patch.object(self.client, "_web_get", return_value="<html>no script</html>"):
            self.assertIsNone(self.client._fetch_new_bearer_token())

    def test_returns_none_when_js_has_no_token(self):
        html = '<script src="/assets/index-abc.js"></script>'

        def side_effect(url, headers=None, timeout=10):
            return html if "browse" in url else "var x = 'nothing here';"

        with patch.object(self.client, "_web_get", side_effect=side_effect):
            self.assertIsNone(self.client._fetch_new_bearer_token())

    def test_returns_none_when_js_fetch_fails(self):
        html = '<script src="/assets/index-abc.js"></script>'
        calls = [0]

        def side_effect(url, headers=None, timeout=10):
            calls[0] += 1
            return html if calls[0] == 1 else None

        with patch.object(self.client, "_web_get", side_effect=side_effect):
            self.assertIsNone(self.client._fetch_new_bearer_token())


# ---------------------------------------------------------------------------
# _get_bearer_token
# ---------------------------------------------------------------------------

class TestGetBearerToken(unittest.TestCase):

    def _uncached_client(self):
        """Instantiate without running __init__ (bypasses all side effects)."""
        return AppleMusicClient.__new__(AppleMusicClient)

    def test_returns_cached_valid_token(self):
        client = self._uncached_client()
        token = _make_jwt(int(time.time()) + 3600)
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=token)):
            self.assertEqual(client._get_bearer_token(), token)

    def test_fetches_new_token_when_cache_expired(self):
        client = self._uncached_client()
        expired = _make_jwt(int(time.time()) - 3600)
        fresh = "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJuZXcifQ.newsig"
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=expired)), \
             patch.object(AppleMusicClient, "_fetch_new_bearer_token", return_value=fresh):
            self.assertEqual(client._get_bearer_token(), fresh)

    def test_fetches_new_token_when_no_cache_file(self):
        client = self._uncached_client()
        fresh = "brandnewtoken"
        with patch("os.path.exists", return_value=False), \
             patch("builtins.open", mock_open()), \
             patch.object(AppleMusicClient, "_fetch_new_bearer_token", return_value=fresh):
            self.assertEqual(client._get_bearer_token(), fresh)

    def test_returns_none_when_fetch_fails(self):
        client = self._uncached_client()
        with patch("os.path.exists", return_value=False), \
             patch.object(AppleMusicClient, "_fetch_new_bearer_token", return_value=None):
            self.assertIsNone(client._get_bearer_token())


# ---------------------------------------------------------------------------
# get_album_full_info
# ---------------------------------------------------------------------------

class TestGetAlbumFullInfo(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()

    def test_returns_empty_result_for_invalid_url(self):
        result = self.client.get_album_full_info("https://example.com/not-apple-music")
        self.assertIsNone(result["title"])
        self.assertEqual(result["tracks"], [])

    def test_extracts_basic_fields(self):
        api_data = _make_album_api_response()
        with patch.object(self.client, "_amp_api_get", return_value=api_data):
            result = self.client.get_album_full_info("https://music.apple.com/us/album/test/111222333")
        self.assertEqual(result["title"], "Test Album")
        self.assertEqual(result["artist"], "Test Artist")
        self.assertEqual(result["release_date"], "2026-03-01")
        self.assertEqual(result["track_count"], 10)
        self.assertEqual(result["genre"], "Pop")
        self.assertEqual(result["description"], "Great album.")

    def test_formats_artwork_url(self):
        raw = "https://is1-ssl.mzstatic.com/image/thumb/Music116/{w}x{h}bb.jpg"
        api_data = _make_album_api_response(artwork_url=raw)
        with patch.object(self.client, "_amp_api_get", return_value=api_data):
            result = self.client.get_album_full_info("https://music.apple.com/us/album/test/111222333")
        self.assertIn("500x500bb.jpg", result["artwork_url"])
        self.assertNotIn("{w}", result["artwork_url"])

    def test_extracts_tracks(self):
        tracks = [
            {"name": "Track 1", "trackNumber": 1, "durationInMillis": 180000},
            {"name": "Track 2", "trackNumber": 2, "durationInMillis": 240000},
        ]
        api_data = _make_album_api_response(tracks=tracks)
        with patch.object(self.client, "_amp_api_get", return_value=api_data):
            result = self.client.get_album_full_info("https://music.apple.com/us/album/test/111222333")
        self.assertEqual(len(result["tracks"]), 2)
        self.assertEqual(result["tracks"][0]["title"], "Track 1")
        self.assertEqual(result["tracks"][1]["track_number"], 2)
        self.assertEqual(result["tracks"][0]["duration_ms"], 180000)

    def test_audio_formats_include_lossless_and_mastered(self):
        api_data = _make_album_api_response(audio_traits=["lossless"], mastered_for_itunes=True)
        with patch.object(self.client, "_amp_api_get", return_value=api_data):
            result = self.client.get_album_full_info("https://music.apple.com/us/album/test/111222333")
        self.assertIn("lossless", result["audio_formats"])
        self.assertIn("adm", result["audio_formats"])

    def test_audio_formats_none_when_empty_and_not_mastered(self):
        api_data = _make_album_api_response(audio_traits=[], mastered_for_itunes=False)
        with patch.object(self.client, "_amp_api_get", return_value=api_data):
            result = self.client.get_album_full_info("https://music.apple.com/us/album/test/111222333")
        self.assertIsNone(result["audio_formats"])

    def test_extracts_artist_id_and_url(self):
        api_data = _make_album_api_response()
        with patch.object(self.client, "_amp_api_get", return_value=api_data):
            result = self.client.get_album_full_info("https://music.apple.com/us/album/test/111222333")
        self.assertEqual(result["artist_id"], "artist-id-1")
        self.assertIsNotNone(result["artist_url"])

    def test_returns_empty_result_on_api_failure(self):
        with patch.object(self.client, "_amp_api_get", return_value={}):
            result = self.client.get_album_full_info("https://music.apple.com/us/album/test/111222333")
        self.assertIsNone(result["title"])
        self.assertEqual(result["tracks"], [])

    def test_accepts_url_without_slug(self):
        """URL format: /us/album/111222333 (no slug before ID)."""
        api_data = _make_album_api_response()
        with patch.object(self.client, "_amp_api_get", return_value=api_data) as mock_api:
            self.client.get_album_full_info("https://music.apple.com/us/album/111222333")
        mock_api.assert_called_once()
        path = mock_api.call_args[0][0]
        self.assertIn("111222333", path)


# ---------------------------------------------------------------------------
# get_room_new_releases
# ---------------------------------------------------------------------------

class TestGetRoomNewReleases(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()

    @patch.object(AppleMusicClient, "_web_get")
    def test_extracts_releases_from_new_section(self, mock_web_get):
        sections = [{
            "header": "New in Music",
            "items": [{
                "item": {
                    "attributes": {
                        "title": "Test Album",
                        "artistName": "Test Artist",
                        "url": "https://music.apple.com/us/album/test/123456789",
                    }
                }
            }],
        }]
        mock_web_get.return_value = ROOM_HTML_TEMPLATE.format(payload=_make_room_payload(sections))

        releases = self.client.get_room_new_releases("https://example.com", "us")

        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0]["title"], "Test Album")
        self.assertEqual(releases[0]["storeAdamID"], "123456789")
        self.assertEqual(releases[0]["storefronts"], ["us"])

    @patch.object(AppleMusicClient, "_web_get")
    def test_ignores_non_new_release_sections(self, mock_web_get):
        sections = [{
            "header": "Featured Playlists",
            "items": [{"item": {"attributes": {
                "title": "Chill Hits", "artistName": "Various",
                "url": "https://music.apple.com/us/playlist/test/999",
            }}}],
        }]
        mock_web_get.return_value = ROOM_HTML_TEMPLATE.format(payload=_make_room_payload(sections))

        self.assertEqual(self.client.get_room_new_releases("https://example.com", "us"), [])

    @patch.object(AppleMusicClient, "_web_get")
    def test_returns_empty_when_no_script_tag(self, mock_web_get):
        mock_web_get.return_value = "<html>no data</html>"
        self.assertEqual(self.client.get_room_new_releases("https://example.com", "us"), [])

    @patch.object(AppleMusicClient, "_web_get")
    def test_returns_empty_when_web_get_fails(self, mock_web_get):
        mock_web_get.return_value = None
        self.assertEqual(self.client.get_room_new_releases("https://example.com", "us"), [])


# ---------------------------------------------------------------------------
# get_artist_all_releases
# ---------------------------------------------------------------------------

_ARTIST_URL = "https://music.apple.com/us/artist/test-artist/12345"


class TestGetArtistAllReleases(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()

    def test_returns_empty_for_invalid_url(self):
        result = self.client.get_artist_all_releases("https://example.com/not-an-artist", "us")
        self.assertEqual(result, [])

    def test_extracts_albums_and_singles(self):
        api_data = _make_artist_views_response(
            albums=[("111", "Album One", "Artist A", "https://music.apple.com/us/album/one/111")],
            singles=[("222", "Single One", "Artist A", "https://music.apple.com/us/album/s1/222")],
        )
        with patch.object(self.client, "_amp_api_get", return_value=api_data):
            releases = self.client.get_artist_all_releases(_ARTIST_URL, "us")
        self.assertEqual(len(releases), 2)
        titles = {r["title"] for r in releases}
        self.assertIn("Album One", titles)
        self.assertIn("Single One", titles)

    def test_assigns_correct_release_types(self):
        api_data = _make_artist_views_response(
            albums=[("111", "Album One", "Artist", "https://music.apple.com/us/album/one/111")],
            singles=[("222", "Single One", "Artist", "https://music.apple.com/us/album/s1/222")],
        )
        with patch.object(self.client, "_amp_api_get", return_value=api_data):
            releases = self.client.get_artist_all_releases(_ARTIST_URL, "us")
        by_id = {r["storeAdamID"]: r for r in releases}
        self.assertEqual(by_id["111"]["release_type"], "main-albums")
        self.assertEqual(by_id["222"]["release_type"], "singles-eps")

    def test_deduplicates_across_views(self):
        dup_item = {"id": "111", "attributes": {"name": "Dup Album", "artistName": "Artist", "url": "..."}}
        api_data = {
            "data": [{
                "views": {
                    "full-albums":        {"data": [dup_item]},
                    "compilation-albums": {"data": [dup_item]},
                    "live-albums":        {"data": []},
                    "singles":            {"data": []},
                }
            }]
        }
        with patch.object(self.client, "_amp_api_get", return_value=api_data):
            releases = self.client.get_artist_all_releases(_ARTIST_URL, "us")
        ids = [r["storeAdamID"] for r in releases]
        self.assertEqual(len(ids), len(set(ids)))

    def test_returns_empty_on_api_failure(self):
        with patch.object(self.client, "_amp_api_get", return_value={}):
            self.assertEqual(self.client.get_artist_all_releases(_ARTIST_URL, "us"), [])


# ---------------------------------------------------------------------------
# get_artist_new_releases
# ---------------------------------------------------------------------------

class TestGetArtistNewReleases(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()

    def test_returns_empty_for_invalid_url(self):
        result = self.client.get_artist_new_releases("https://example.com/not-an-artist", "us")
        self.assertEqual(result, [])

    def test_extracts_releases_from_api(self):
        api_data = {
            "data": [{
                "id": "111222333",
                "attributes": {
                    "name": "Great Album",
                    "artistName": "Great Artist",
                    "url": "https://music.apple.com/us/album/great/111222333",
                },
            }]
        }
        with patch.object(self.client, "_amp_api_get", return_value=api_data):
            releases = self.client.get_artist_new_releases(_ARTIST_URL, "us")
        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0]["title"], "Great Album")
        self.assertEqual(releases[0]["storeAdamID"], "111222333")
        self.assertEqual(releases[0]["storefronts"], ["us"])

    def test_returns_empty_when_data_key_missing(self):
        with patch.object(self.client, "_amp_api_get", return_value={}):
            self.assertEqual(self.client.get_artist_new_releases(_ARTIST_URL, "us"), [])

    def test_returns_empty_when_data_is_empty_list(self):
        with patch.object(self.client, "_amp_api_get", return_value={"data": []}):
            self.assertEqual(self.client.get_artist_new_releases(_ARTIST_URL, "us"), [])

    def test_skips_items_without_id(self):
        api_data = {
            "data": [
                {"attributes": {"name": "No ID Album", "artistName": "Artist", "url": "..."}},
                {"id": "999", "attributes": {"name": "Has ID", "artistName": "Artist", "url": "..."}},
            ]
        }
        with patch.object(self.client, "_amp_api_get", return_value=api_data):
            releases = self.client.get_artist_new_releases(_ARTIST_URL, "us")
        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0]["storeAdamID"], "999")


# ---------------------------------------------------------------------------
# check_storefront_availability
# ---------------------------------------------------------------------------

class TestCheckStorefrontAvailability(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()

    def test_all_available(self):
        with patch.object(self.client, "_web_get", return_value="some html"):
            result = self.client.check_storefront_availability("123", ["us", "jp"])
        self.assertCountEqual(result["available"], ["us", "jp"])
        self.assertEqual(result["unavailable"], [])

    def test_some_unavailable(self):
        def side_effect(url, headers=None, timeout=10):
            return None if "/jp/" in url else "some html"

        with patch.object(self.client, "_web_get", side_effect=side_effect):
            result = self.client.check_storefront_availability("123", ["us", "jp"])
        self.assertIn("us", result["available"])
        self.assertIn("jp", result["unavailable"])

    def test_all_unavailable(self):
        with patch.object(self.client, "_web_get", return_value=None):
            result = self.client.check_storefront_availability("123", ["us", "jp", "gb"])
        self.assertEqual(result["available"], [])
        self.assertCountEqual(result["unavailable"], ["us", "jp", "gb"])

    def test_empty_storefronts_list(self):
        result = self.client.check_storefront_availability("123", [])
        self.assertEqual(result["available"], [])
        self.assertEqual(result["unavailable"], [])


if __name__ == "__main__":
    unittest.main()
