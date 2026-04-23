"""Tests for notifications.py — queue, sender, CRUD, failure handling."""

import contextlib
import json
import os
import queue
import tempfile
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

    def tearDown(self):
        import config

        config.CONFIG_PATH = self._orig_config_path
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


if __name__ == "__main__":
    unittest.main()
