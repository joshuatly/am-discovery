"""Tests for notifications.py — queue, sender, CRUD, failure handling."""

import contextlib
import json
import os
import queue
import tempfile
import time
import unittest
import urllib.error
from unittest.mock import MagicMock, patch


class NotificationsTestCase(unittest.TestCase):
    """Base class isolating config.json + notifications module state per test."""

    def setUp(self):
        self._cfg_fd, self._cfg_path = tempfile.mkstemp(suffix=".json")
        os.close(self._cfg_fd)
        os.unlink(self._cfg_path)

        import config

        self._orig_config_path = config.CONFIG_PATH
        config.CONFIG_PATH = self._cfg_path

        # Reset module-level state so each test starts fresh.
        import notifications

        notifications._queue = None
        notifications._thread = None
        notifications._started = False
        notifications._last_notify_at = None
        if notifications._scan_timer is not None:
            notifications._scan_timer.cancel()
        notifications._scan_timer = None
        notifications._scanner_started = False

    def tearDown(self):
        import config
        import notifications

        config.CONFIG_PATH = self._orig_config_path
        if notifications._scan_timer is not None:
            notifications._scan_timer.cancel()
            notifications._scan_timer = None
        notifications._scanner_started = False
        with contextlib.suppress(FileNotFoundError):
            os.unlink(self._cfg_path)


# ---------------------------------------------------------------------------
# _safe_format
# ---------------------------------------------------------------------------


class TestSafeFormat(NotificationsTestCase):
    def test_known_placeholder_renders(self):
        from notifications import _safe_format

        self.assertEqual(_safe_format("Hi {name}", {"name": "Bob"}), "Hi Bob")

    def test_unknown_placeholder_renders_empty(self):
        from notifications import _safe_format

        self.assertEqual(_safe_format("Hi {name}, {missing}!", {"name": "Bob"}), "Hi Bob, !")

    def test_malformed_template_returns_raw(self):
        from notifications import _safe_format

        # Single brace is malformed; should return the raw string rather than crash.
        self.assertEqual(_safe_format("Hi {name", {"name": "Bob"}), "Hi {name")


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


class TestCRUD(NotificationsTestCase):
    def test_create_event_assigns_id_and_defaults(self):
        import notifications

        ev = notifications.create_event(
            {"event_type": "onArtistNewSingle", "apprise_url": "http://x/notify/y"},
        )
        self.assertIn("id", ev)
        self.assertTrue(ev["enabled"])
        self.assertEqual(ev["consecutive_failures"], 0)
        self.assertEqual(ev["notification_type"], "success")
        self.assertIn("{artist}", ev["title_template"])
        self.assertIn("{artist}", ev["body_template"])

    def test_update_event_partial_patch(self):
        import notifications

        ev = notifications.create_event(
            {"event_type": "onArtistNewSingle", "apprise_url": "http://x/notify/y"},
        )
        updated = notifications.update_event(ev["id"], {"enabled": False})
        self.assertIsNotNone(updated)
        self.assertFalse(updated["enabled"])
        # Other fields preserved
        self.assertEqual(updated["apprise_url"], "http://x/notify/y")

    def test_update_event_returns_none_for_unknown(self):
        import notifications

        self.assertIsNone(notifications.update_event("does-not-exist", {"enabled": False}))

    def test_delete_event(self):
        import notifications

        ev = notifications.create_event(
            {"event_type": "onArtistNewSingle", "apprise_url": "http://x"},
        )
        self.assertTrue(notifications.delete_event(ev["id"]))
        self.assertFalse(notifications.delete_event(ev["id"]))
        self.assertEqual(notifications.list_events(), [])

    def test_event_types_meta_includes_all_four(self):
        import notifications

        meta = notifications.get_event_types_meta()
        types = [t["event_type"] for t in meta["types"]]
        self.assertEqual(set(types), set(notifications.EVENT_TYPES))
        self.assertIn("info", meta["notification_types"])


# ---------------------------------------------------------------------------
# enqueue filtering + queue overflow
# ---------------------------------------------------------------------------


class TestEnqueue(NotificationsTestCase):
    def _make_queue(self, maxsize=10):
        import notifications

        notifications._queue = queue.Queue(maxsize=maxsize)
        return notifications._queue

    def test_enqueue_skips_disabled_events(self):
        import notifications

        notifications.create_event(
            {
                "event_type": "onArtistNewSingle",
                "apprise_url": "http://x",
                "enabled": False,
            },
        )
        q = self._make_queue()
        notifications.enqueue("onArtistNewSingle", {"artist": "A"})
        self.assertEqual(q.qsize(), 0)

    def test_enqueue_skips_other_event_types(self):
        import notifications

        notifications.create_event(
            {"event_type": "onArtistNewSingle", "apprise_url": "http://x"},
        )
        q = self._make_queue()
        notifications.enqueue("onDiscoveryComplete", {"new_count": 1})
        self.assertEqual(q.qsize(), 0)

    def test_enqueue_renders_template_with_variables(self):
        import notifications

        notifications.create_event(
            {
                "event_type": "onArtistNewSingle",
                "apprise_url": "http://x",
                "title_template": "Hi {artist}",
                "body_template": "{title}",
            },
        )
        q = self._make_queue()
        notifications.enqueue("onArtistNewSingle", {"artist": "Bob", "title": "Song"})
        self.assertEqual(q.qsize(), 1)
        item = q.get()
        self.assertEqual(item["title"], "Hi Bob")
        self.assertEqual(item["body"], "Song")

    def test_queue_overflow_drops_oldest(self):
        import notifications

        notifications.create_event(
            {"event_type": "onArtistNewSingle", "apprise_url": "http://x"},
        )
        q = self._make_queue(maxsize=1)
        notifications.enqueue("onArtistNewSingle", {"artist": "First"})
        notifications.enqueue("onArtistNewSingle", {"artist": "Second"})
        # Queue still has size 1 — newest item retained
        self.assertEqual(q.qsize(), 1)
        item = q.get()
        self.assertIn("Second", item["title"])

    def test_enqueue_watchlist_batch_complete_renders(self):
        import notifications

        notifications.create_event(
            {
                "event_type": "onWatchlistBatchComplete",
                "apprise_url": "http://x",
                "title_template": "batch {refreshed_count}/{batch_size}",
                "body_template": "did {refreshed_artists}; pending {pending_count}; next {next_run_at}",
            },
        )
        q = self._make_queue()
        notifications.enqueue(
            "onWatchlistBatchComplete",
            {
                "run_at": "2026-04-24 14:30 UTC",
                "batch_size": 3,
                "refreshed_count": 2,
                "error_count": 1,
                "refreshed_artists": "Alice, Bob",
                "failed_artists": "Carol",
                "pending_count": 7,
                "next_run_at": "2026-04-24 14:40 UTC",
            },
        )
        self.assertEqual(q.qsize(), 1)
        item = q.get()
        self.assertEqual(item["title"], "batch 2/3")
        self.assertEqual(item["body"], "did Alice, Bob; pending 7; next 2026-04-24 14:40 UTC")


# ---------------------------------------------------------------------------
# send_test
# ---------------------------------------------------------------------------


class TestSendTest(NotificationsTestCase):
    def _mock_response(self, status=200):
        resp = MagicMock()
        resp.status = status
        resp.__enter__ = lambda self_: self_
        resp.__exit__ = lambda self_, *a: None
        return resp

    def test_uses_sample_variables_when_none_provided(self):
        import notifications

        ev = notifications.create_event(
            {
                "event_type": "onArtistNewSingle",
                "apprise_url": "http://x/notify/y",
                "title_template": "Hi {artist}",
                "body_template": "{title}",
            },
        )
        with patch("urllib.request.urlopen", return_value=self._mock_response()) as m:
            ok, msg = notifications.send_test(ev)
        self.assertTrue(ok)
        sent = m.call_args[0][0]
        body = json.loads(sent.data.decode())
        self.assertTrue(body["title"].startswith("[TEST] Hi "))
        # Sample variables for onArtistNewSingle have title="Sample Single"
        self.assertEqual(body["body"], "Sample Single")

    def test_returns_error_on_http_failure(self):
        import notifications

        ev = notifications.create_event(
            {"event_type": "onArtistNewSingle", "apprise_url": "http://x/notify/y"},
        )
        err = urllib.error.HTTPError("http://x", 500, "Server Error", {}, None)
        with patch("urllib.request.urlopen", side_effect=err):
            ok, msg = notifications.send_test(ev)
        self.assertFalse(ok)
        self.assertIn("500", msg)

    def test_empty_url_returns_error(self):
        import notifications

        ev = notifications.create_event({"event_type": "onArtistNewSingle"})
        ok, msg = notifications.send_test(ev)
        self.assertFalse(ok)
        self.assertIn("empty", msg)

    def test_test_notification_uses_configured_timezone(self):
        import config
        import notifications

        config.save_config({"timezone": "Asia/Hong_Kong"})
        ev = notifications.create_event(
            {
                "event_type": "onWatchlistBatchComplete",
                "apprise_url": "http://x/notify/y",
                "title_template": "{run_at}",
                "body_template": "next {next_run_at}",
            },
        )
        with patch("urllib.request.urlopen", return_value=self._mock_response()) as m:
            ok, _ = notifications.send_test(ev)
        self.assertTrue(ok)
        sent = m.call_args[0][0]
        body = json.loads(sent.data.decode())
        self.assertIn("HKT", body["title"])
        self.assertIn("HKT", body["body"])


# ---------------------------------------------------------------------------
# Failure counter / auto-disable
# ---------------------------------------------------------------------------


class TestFailureHandling(NotificationsTestCase):
    def test_failure_increments_counter(self):
        import notifications

        ev = notifications.create_event(
            {"event_type": "onArtistNewSingle", "apprise_url": "http://x"},
        )
        notifications._on_send_failure(ev["id"], "boom")
        notifications._on_send_failure(ev["id"], "boom")
        loaded = notifications.get_event(ev["id"])
        self.assertEqual(loaded["consecutive_failures"], 2)
        self.assertTrue(loaded["enabled"])

    def test_max_failures_disables_event(self):
        import notifications

        # Set max_failures=3 in config
        from config import load_config, save_config

        cfg = load_config()
        cfg["notifications"]["max_failures"] = 3
        save_config(cfg)

        ev = notifications.create_event(
            {"event_type": "onArtistNewSingle", "apprise_url": "http://x"},
        )
        for _ in range(3):
            notifications._on_send_failure(ev["id"], "boom")
        loaded = notifications.get_event(ev["id"])
        self.assertEqual(loaded["consecutive_failures"], 3)
        self.assertFalse(loaded["enabled"])
        self.assertEqual(loaded["disabled_reason"], "max_failures")

    def test_success_resets_counter(self):
        import notifications

        ev = notifications.create_event(
            {"event_type": "onArtistNewSingle", "apprise_url": "http://x"},
        )
        notifications._on_send_failure(ev["id"], "boom")
        notifications._on_send_failure(ev["id"], "boom")
        notifications._on_send_success(ev["id"])
        loaded = notifications.get_event(ev["id"])
        self.assertEqual(loaded["consecutive_failures"], 0)
        self.assertIsNone(loaded["disabled_reason"])


# ---------------------------------------------------------------------------
# _ids_from_artists_json
# ---------------------------------------------------------------------------


class TestIdsFromArtistsJson(NotificationsTestCase):
    def test_none_returns_empty_set(self):
        from notifications import _ids_from_artists_json

        self.assertEqual(_ids_from_artists_json(None), set())

    def test_empty_string_returns_empty_set(self):
        from notifications import _ids_from_artists_json

        self.assertEqual(_ids_from_artists_json(""), set())

    def test_malformed_json_returns_empty_set(self):
        from notifications import _ids_from_artists_json

        self.assertEqual(_ids_from_artists_json("{not json"), set())

    def test_extracts_ids_from_list_of_dicts(self):
        from notifications import _ids_from_artists_json

        blob = json.dumps([{"id": "A1", "name": "x"}, {"id": "B2"}])
        self.assertEqual(_ids_from_artists_json(blob), {"A1", "B2"})

    def test_skips_entries_without_id(self):
        from notifications import _ids_from_artists_json

        blob = json.dumps([{"id": "A1"}, {"name": "no-id"}, "string-entry"])
        self.assertEqual(_ids_from_artists_json(blob), {"A1"})


# ---------------------------------------------------------------------------
# enqueue_album_notification (event-type dispatch)
# ---------------------------------------------------------------------------


class TestEnqueueAlbumNotification(NotificationsTestCase):
    def _setup_event(self, event_type):
        import notifications

        notifications._queue = queue.Queue(maxsize=10)
        notifications.create_event(
            {
                "event_type": event_type,
                "apprise_url": "http://x/notify/y",
                "title_template": "{title}",
                "body_template": "{artist} {release_type}",
            },
        )

    def test_singles_eps_uses_new_single(self):
        import notifications

        self._setup_event("onArtistNewSingle")
        album = {
            "store_adam_id": "1",
            "title": "Hit",
            "release_type": "singles-eps",
            "release_date": "2026-04-30",
        }
        notifications.enqueue_album_notification(album, "Test Artist")
        self.assertEqual(notifications._queue.qsize(), 1)
        item = notifications._queue.get()
        self.assertEqual(item["title"], "Hit")
        self.assertEqual(item["body"], "Test Artist singles-eps")

    def test_main_albums_uses_new_release(self):
        import notifications

        self._setup_event("onArtistNewRelease")
        album = {"store_adam_id": "1", "title": "Album", "release_type": "main-albums"}
        notifications.enqueue_album_notification(album, "X")
        self.assertEqual(notifications._queue.qsize(), 1)

    def test_null_release_type_uses_new_release(self):
        import notifications

        self._setup_event("onArtistNewRelease")
        album = {"store_adam_id": "1", "title": "Mystery"}  # no release_type
        notifications.enqueue_album_notification(album, "X")
        self.assertEqual(notifications._queue.qsize(), 1)

    def test_storefronts_string_blob_decoded(self):
        import notifications

        notifications._queue = queue.Queue(maxsize=10)
        notifications.create_event(
            {
                "event_type": "onArtistNewRelease",
                "apprise_url": "http://x/notify/y",
                "title_template": "{storefronts}",
                "body_template": "x",
            },
        )
        notifications.enqueue_album_notification(
            {"title": "T", "storefronts": json.dumps(["us", "jp"])},
            "Artist",
        )
        item = notifications._queue.get()
        self.assertEqual(item["title"], "us, jp")


# ---------------------------------------------------------------------------
# _run_scan (the watched-artist scanner)
# ---------------------------------------------------------------------------


class TestRunScan(NotificationsTestCase):
    def setUp(self):
        super().setUp()
        import notifications

        notifications._queue = queue.Queue(maxsize=50)
        # Arm an event so enqueue() actually queues something. Apprise URL is
        # never hit because _run_scan does not call _post_apprise.
        notifications.create_event(
            {
                "event_type": "onArtistNewRelease",
                "apprise_url": "http://x/notify/y",
                "title_template": "{title}",
                "body_template": "{artist} {release_type}",
            },
        )
        notifications.create_event(
            {
                "event_type": "onArtistNewSingle",
                "apprise_url": "http://x/notify/y",
                "title_template": "single:{title}",
                "body_template": "{artist}",
            },
        )

    def _patches(
        self,
        *,
        rows: list[dict],
        watched: set[str] | None = None,
        artist_name: str = "Test Artist",
    ):
        watched_set = watched if watched is not None else {"A1"}
        return (
            patch("notifications.db.get_albums_first_seen_after", return_value=rows),
            patch("notifications.db.get_watched_artist_ids", return_value=watched_set),
            patch("notifications.db.get_artist_info", return_value={"name": artist_name}),
            patch("notifications._schedule_next_scan", lambda: None),
        )

    def _run_with(self, *, rows, watched=None, artist_name="Test Artist"):
        import notifications

        ps = self._patches(rows=rows, watched=watched, artist_name=artist_name)
        with ps[0], ps[1], ps[2], ps[3]:
            notifications._run_scan()

    def _drain(self):
        import notifications

        items = []
        while not notifications._queue.empty():
            items.append(notifications._queue.get())
        return items

    def test_no_rows_no_notifications(self):
        import notifications

        self._run_with(rows=[])
        self.assertEqual(notifications._queue.qsize(), 0)

    def test_unwatched_artist_no_notification(self):
        rows = [
            {
                "store_adam_id": "1",
                "title": "X",
                "artist_id": "OTHER",
                "artists_json": json.dumps([{"id": "OTHER"}]),
                "release_type": "main-albums",
                "release_date": "2026-04-29",
                "storefronts": json.dumps(["us"]),
            },
        ]
        self._run_with(rows=rows, watched={"A1"})
        self.assertEqual(self._drain(), [])

    def test_match_via_primary_artist_id(self):
        rows = [
            {
                "store_adam_id": "1",
                "title": "Album X",
                "artist_id": "A1",
                "artists_json": None,
                "release_type": "main-albums",
                "release_date": "2026-04-29",
                "storefronts": json.dumps(["us"]),
            },
        ]
        self._run_with(rows=rows, watched={"A1"})
        items = self._drain()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Album X")

    def test_match_via_artists_json_featured_artist(self):
        rows = [
            {
                "store_adam_id": "2",
                "title": "Collab",
                "artist_id": "PRIMARY",
                "artists_json": json.dumps([{"id": "PRIMARY"}, {"id": "FEATURED"}]),
                "release_type": "main-albums",
                "release_date": "2026-04-29",
                "storefronts": "[]",
            },
        ]
        self._run_with(rows=rows, watched={"FEATURED"})
        self.assertEqual(len(self._drain()), 1)

    def test_singles_eps_dispatches_single_event(self):
        rows = [
            {
                "store_adam_id": "3",
                "title": "Hit",
                "artist_id": "A1",
                "artists_json": None,
                "release_type": "singles-eps",
                "release_date": "2026-04-29",
                "storefronts": "[]",
            },
        ]
        self._run_with(rows=rows, watched={"A1"})
        items = self._drain()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "single:Hit")

    def test_null_release_type_dispatches_release_event(self):
        rows = [
            {
                "store_adam_id": "4",
                "title": "Mystery",
                "artist_id": "A1",
                "artists_json": None,
                "release_type": None,
                "release_date": "2026-04-29",
                "storefronts": "[]",
            },
        ]
        self._run_with(rows=rows, watched={"A1"})
        items = self._drain()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Mystery")

    def test_sets_last_notify_at_to_now(self):
        import notifications

        self._run_with(rows=[])
        self.assertIsNotNone(notifications._last_notify_at)
        # Within a few seconds of test execution time.
        self.assertGreater(notifications._last_notify_at, int(time.time()) - 5)

    def test_scan_failure_still_advances_last_notify_at_to_none_safe(self):
        # Even if get_albums_first_seen_after raises, the scan must not crash;
        # it must log and reschedule. _last_notify_at is unchanged.
        import notifications

        notifications._last_notify_at = 12345
        with (
            patch(
                "notifications.db.get_albums_first_seen_after",
                side_effect=RuntimeError("db down"),
            ),
            patch("notifications._schedule_next_scan", lambda: None),
        ):
            notifications._run_scan()
        # Should still be the prior value because we set _last_notify_at = now
        # only on success path — verify the function did not crash.
        self.assertEqual(notifications._last_notify_at, 12345)


# ---------------------------------------------------------------------------
# init_scanner / get_last_notify_at
# ---------------------------------------------------------------------------


class TestInitScanner(NotificationsTestCase):
    def test_get_last_notify_at_none_before_init(self):
        import notifications

        self.assertIsNone(notifications.get_last_notify_at())

    def test_init_scanner_sets_last_notify_at_and_arms_timer(self):
        import notifications

        with patch("notifications._schedule_next_scan") as mock_sched:
            notifications.init_scanner()
        self.assertIsNotNone(notifications._last_notify_at)
        self.assertTrue(notifications._scanner_started)
        mock_sched.assert_called_once()

    def test_init_scanner_idempotent(self):
        import notifications

        with patch("notifications._schedule_next_scan") as mock_sched:
            notifications.init_scanner()
            notifications.init_scanner()
        self.assertEqual(mock_sched.call_count, 1)


# ---------------------------------------------------------------------------
# Integration: query window math (uses time.time mock)
# ---------------------------------------------------------------------------


class TestScanWindow(NotificationsTestCase):
    def test_query_uses_now_minus_interval_seconds(self):
        import config
        import notifications

        config.save_config(
            {"notification_scan_interval_minutes": 10, "notification_max_release_age_days": 7},
        )
        notifications._queue = queue.Queue(maxsize=10)
        captured = {}

        def fake_query(since_ts, min_release_date):
            captured["since_ts"] = since_ts
            captured["min_release_date"] = min_release_date
            return []

        with (
            patch("notifications.db.get_albums_first_seen_after", side_effect=fake_query),
            patch("notifications.db.get_watched_artist_ids", return_value=set()),
            patch("notifications._schedule_next_scan", lambda: None),
            patch("notifications.time.time", return_value=2_000_000),
        ):
            notifications._run_scan()
        # since_ts should be now - 600 (10 min × 60s).
        self.assertEqual(captured["since_ts"], 2_000_000 - 600)
        # min_release_date is 7 days before 2_000_000's local date.
        # 2_000_000 unix is 1970-01-24 UTC; minus 7 days is 1970-01-17.
        self.assertEqual(captured["min_release_date"], "1970-01-17")


if __name__ == "__main__":
    unittest.main()
