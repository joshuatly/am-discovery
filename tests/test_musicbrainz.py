"""Unit tests for musicbrainz.py — MusicBrainz web-service client.

Network is never touched: ``_request`` is patched so tests exercise parsing,
title normalisation, and retry/backoff behaviour deterministically.
"""

import unittest
from unittest.mock import patch

import musicbrainz as mb


class TestNormalizeTitle(unittest.TestCase):
    def test_strips_bracketed_qualifiers(self):
        self.assertEqual(mb.normalize_title("Greatest Works (Deluxe Edition)"), "greatest works")

    def test_strips_edition_suffix(self):
        self.assertEqual(mb.normalize_title("Album Name - Remastered 2020"), "album name")

    def test_case_and_punctuation_insensitive(self):
        self.assertEqual(mb.normalize_title("Hello, World!"), mb.normalize_title("hello world"))

    def test_keeps_cjk(self):
        self.assertEqual(mb.normalize_title("范特西"), "范特西")

    def test_empty(self):
        self.assertEqual(mb.normalize_title(""), "")
        self.assertEqual(mb.normalize_title(None), "")


class TestSearchArtist(unittest.TestCase):
    @patch("musicbrainz._request")
    def test_parses_candidates(self, mock_req):
        mock_req.return_value = {
            "artists": [
                {
                    "id": "mbid-1",
                    "name": "Jay Chou",
                    "score": 100,
                    "type": "Person",
                    "country": "TW",
                    "area": {"name": "Taiwan"},
                },
                {"id": "mbid-2", "name": "Jay", "score": 60, "disambiguation": "other", "country": "US"},
            ]
        }
        out = mb.search_artist("Jay Chou")
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["id"], "mbid-1")
        self.assertEqual(out[0]["url"], "https://musicbrainz.org/artist/mbid-1")
        self.assertEqual(out[0]["type"], "Person")
        # Prefers the human-readable area name over the ISO country code.
        self.assertEqual(out[0]["area"], "Taiwan")
        self.assertEqual(out[1]["disambiguation"], "other")
        # Falls back to country code when no area object is present.
        self.assertEqual(out[1]["area"], "US")

    def test_blank_name_returns_empty(self):
        self.assertEqual(mb.search_artist("  "), [])


class TestBrowseReleaseGroups(unittest.TestCase):
    @patch("musicbrainz._request")
    def test_collects_and_normalises(self, mock_req):
        mock_req.return_value = {
            "release-groups": [
                {"id": "rg1", "title": "First (Deluxe)", "primary-type": "Album"},
                {"id": "rg2", "title": "Second", "primary-type": "EP"},
            ],
            "release-group-count": 2,
        }
        groups = mb.browse_release_groups("artist-mbid")
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0]["norm_title"], "first")
        self.assertEqual(groups[1]["primary_type"], "ep")

    @patch("musicbrainz._request")
    def test_paginates_when_more_than_one_page(self, mock_req):
        page1 = {
            "release-groups": [{"id": f"rg{i}", "title": f"T{i}", "primary-type": "album"} for i in range(100)],
            "release-group-count": 150,
        }
        page2 = {
            "release-groups": [{"id": f"rg{i}", "title": f"T{i}", "primary-type": "album"} for i in range(100, 150)],
            "release-group-count": 150,
        }
        mock_req.side_effect = [page1, page2]
        groups = mb.browse_release_groups("artist-mbid")
        self.assertEqual(len(groups), 150)
        self.assertEqual(mock_req.call_count, 2)

    def test_no_mbid(self):
        self.assertEqual(mb.browse_release_groups(""), [])


class TestReleaseGroupBarcodes(unittest.TestCase):
    @patch("musicbrainz._request")
    def test_collects_barcodes(self, mock_req):
        mock_req.return_value = {
            "releases": [
                {"id": "rel1", "barcode": "111"},
                {"id": "rel2", "barcode": ""},
                {"id": "rel3", "barcode": "222"},
            ]
        }
        barcodes, first = mb.get_release_group_barcodes("rg1")
        self.assertEqual(barcodes, {"111", "222"})
        self.assertEqual(first, "rel1")


class TestSearchRelease(unittest.TestCase):
    @patch("musicbrainz._request")
    def test_builds_title_and_artist_query(self, mock_req):
        mock_req.return_value = {"releases": [{"id": "rel-1", "title": "Album"}]}
        out = mb.search_release("Album", "Jay Chou")
        self.assertEqual(out[0]["id"], "rel-1")
        query = mock_req.call_args[0][1]["query"]
        self.assertIn('release:"Album"', query)
        self.assertIn('artist:"Jay Chou"', query)

    @patch("musicbrainz._request")
    def test_title_only_when_no_artist(self, mock_req):
        mock_req.return_value = {"releases": []}
        mb.search_release("Album")
        query = mock_req.call_args[0][1]["query"]
        self.assertIn("release:", query)
        self.assertNotIn("artist:", query)

    def test_blank_title_returns_empty(self):
        self.assertEqual(mb.search_release("  "), [])


class TestRequestRetry(unittest.TestCase):
    @patch("musicbrainz.time.sleep", return_value=None)
    @patch("musicbrainz.urllib.request.urlopen")
    def test_503_then_raises_rate_limit(self, mock_urlopen, _sleep):
        import urllib.error

        mock_urlopen.side_effect = urllib.error.HTTPError("u", 503, "busy", {}, None)
        with self.assertRaises(mb.MusicBrainzRateLimitError):
            mb._request("artist", {"query": "x"})
        # Retries MAX_RETRIES times
        self.assertEqual(mock_urlopen.call_count, mb.MAX_RETRIES)


if __name__ == "__main__":
    unittest.main()
