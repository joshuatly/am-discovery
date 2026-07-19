"""Unit tests for seeding.py — the background MusicBrainz seeding scanner.

Per-artist scan functions run against a real temp DB with MusicBrainz mocked.
The cycle orchestration is tested with both db and mb mocked.
"""

import importlib
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch


class SeedingDBTestCase(unittest.TestCase):
    """Fresh temp DB shared by db and seeding (module identity preserved on reload)."""

    def setUp(self):
        self.db_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.db_dir, "test.db")
        os.environ["AM_DB_PATH"] = self.db_path
        import db

        importlib.reload(db)
        db.init_db()
        self.db = db
        import seeding

        importlib.reload(seeding)
        self.seeding = seeding

    def tearDown(self):
        shutil.rmtree(self.db_dir, ignore_errors=True)

    def _album(self, aid, title, **kw):
        self.db.upsert_album({"store_adam_id": aid, "title": title, "info_fetched": 1, **kw})


class TestScanReleasesForArtist(SeedingDBTestCase):
    def _run(self, groups, barcodes_map=None):
        barcodes_map = barcodes_map or {}
        with (
            patch.object(self.seeding.mb, "browse_release_groups", return_value=groups),
            patch.object(
                self.seeding.mb,
                "get_release_group_barcodes",
                side_effect=lambda rg: (barcodes_map.get(rg, set()), "rel-" + rg),
            ),
        ):
            return self.seeding.scan_releases_for_artist({"artist_id": "ART1", "musicbrainz_id": "mbid", "name": "Jay"})

    def _groups(self, *titles):
        import musicbrainz as mb

        return [
            {"id": f"rg{i}", "title": t, "norm_title": mb.normalize_title(t), "primary_type": "album"}
            for i, t in enumerate(titles)
        ]

    def test_missing_release_group_flagged(self):
        self._album("A1", "Unknown Album", artist_id="ART1", release_type="Album")
        flagged = self._run(self._groups("Other Album"))
        self.assertEqual(flagged, 1)
        self.assertEqual(self.db.get_album("A1")["mb_seed_status"], "needs_seeding")

    def test_single_is_skipped(self):
        self._album("A1", "Some Single", artist_id="ART1", release_type="Single")
        flagged = self._run(self._groups())
        self.assertEqual(flagged, 0)
        self.assertIsNone(self.db.get_album("A1")["mb_seed_status"])

    def test_group_exists_no_upc_marked_known(self):
        self._album("A1", "Real Album", artist_id="ART1", release_type="Album")
        flagged = self._run(self._groups("Real Album"))
        self.assertEqual(flagged, 0)
        self.assertEqual(self.db.get_album("A1")["mb_seed_status"], "known")

    def test_group_exists_upc_present_marked_known(self):
        self._album("A1", "Real Album", artist_id="ART1", release_type="Album", upc="111")
        flagged = self._run(self._groups("Real Album"), {"rg0": {"111"}})
        self.assertEqual(flagged, 0)
        self.assertEqual(self.db.get_album("A1")["mb_seed_status"], "known")

    def test_group_exists_upc_missing_flagged(self):
        self._album("A1", "Real Album", artist_id="ART1", release_type="Album", upc="999")
        flagged = self._run(self._groups("Real Album"), {"rg0": {"111"}})
        self.assertEqual(flagged, 1)
        self.assertEqual(self.db.get_album("A1")["mb_seed_status"], "needs_seeding")

    def test_known_album_not_requeried(self):
        self._album("A1", "Real Album", artist_id="ART1", release_type="Album", upc="111")
        self.db.set_album_seed_status("A1", "known")
        with (
            patch.object(self.seeding.mb, "browse_release_groups", return_value=self._groups("Real Album")) as _b,
            patch.object(self.seeding.mb, "get_release_group_barcodes") as bc,
        ):
            self.seeding.scan_releases_for_artist({"artist_id": "ART1", "musicbrainz_id": "mbid", "name": "Jay"})
        bc.assert_not_called()

    def test_marks_release_checked(self):
        self._album("A1", "Unknown", artist_id="ART1", release_type="Album")
        self._run(self._groups())
        # After a scan the artist is guarded out of the next batch.
        self.assertEqual(self.db.get_artists_for_release_scan(recheck_days=7), [])


class TestSuggestMbidForArtist(SeedingDBTestCase):
    def test_stores_suggestion_and_marks_checked(self):
        self.db.add_to_watchlist("ART1", "Jay Chou")
        candidates = [{"id": "mbid-1", "name": "Jay Chou", "score": 100}]
        with patch.object(self.seeding.mb, "search_artist", return_value=candidates):
            ok = self.seeding.suggest_mbid_for_artist({"artist_id": "ART1", "name": "Jay Chou"})
        self.assertTrue(ok)
        s = self.db.get_mbid_suggestion("ART1")
        self.assertEqual(s["suggested_mbid"], "mbid-1")
        self.assertEqual(self.db.get_artists_for_mbid_scan(recheck_days=7), [])

    def test_no_candidates_still_marks_checked(self):
        self.db.add_to_watchlist("ART1", "Nobody")
        with patch.object(self.seeding.mb, "search_artist", return_value=[]):
            self.seeding.suggest_mbid_for_artist({"artist_id": "ART1", "name": "Nobody"})
        self.assertIsNone(self.db.get_mbid_suggestion("ART1"))
        self.assertEqual(self.db.get_artists_for_mbid_scan(recheck_days=7), [])


class TestRunSeedingCycle(unittest.TestCase):
    @patch("seeding.load_config", return_value={"mb_scan_artist_batch": 2, "mb_artist_recheck_days": 7})
    @patch("seeding.db")
    def test_orchestrates_both_phases(self, mock_db, _cfg):
        import seeding

        mock_db.get_artists_for_mbid_scan.return_value = [{"artist_id": "ART1", "name": "Jay"}]
        mock_db.get_artists_for_release_scan.return_value = [
            {"artist_id": "ART2", "name": "Bob", "musicbrainz_id": "m"}
        ]
        with (
            patch.object(seeding, "suggest_mbid_for_artist", return_value=True) as sug,
            patch.object(seeding, "scan_releases_for_artist", return_value=3) as scan,
        ):
            summary = seeding.run_seeding_cycle()
        sug.assert_called_once()
        scan.assert_called_once()
        self.assertEqual(summary, {"mbid_suggested": 1, "releases_scanned": 1, "flagged": 3})

    @patch("seeding.load_config", return_value={"mb_scan_artist_batch": 2, "mb_artist_recheck_days": 7})
    @patch("seeding.db")
    def test_rate_limit_propagates(self, mock_db, _cfg):
        import musicbrainz as mb
        import seeding

        mock_db.get_artists_for_mbid_scan.return_value = [{"artist_id": "ART1", "name": "Jay"}]
        mock_db.get_artists_for_release_scan.return_value = []
        with (
            patch.object(seeding, "suggest_mbid_for_artist", side_effect=mb.MusicBrainzRateLimitError("busy")),
            self.assertRaises(mb.MusicBrainzRateLimitError),
        ):
            seeding.run_seeding_cycle()


class TestStatus(unittest.TestCase):
    @patch(
        "seeding.load_config",
        return_value={
            "mb_scan_enabled": True,
            "mb_scan_interval_minutes": 60,
            "mb_scan_artist_batch": 3,
            "mb_artist_recheck_days": 7,
        },
    )
    @patch("seeding.db")
    def test_status_shape(self, mock_db, _cfg):
        import seeding

        mock_db.count_artists_pending_mbid_scan.return_value = 4
        mock_db.count_seeding_releases.return_value = 7
        s = seeding.status()
        self.assertTrue(s["enabled"])
        self.assertEqual(s["pending_mbid_scan"], 4)
        self.assertEqual(s["seeding_release_count"], 7)


if __name__ == "__main__":
    unittest.main()
