"""Tests for api_notifications.py — Flask routes for notification CRUD + test."""

import contextlib
import os
import tempfile
import unittest
from unittest.mock import patch


class NotificationsApiTestCase(unittest.TestCase):
    def setUp(self):
        self._cfg_fd, self._cfg_path = tempfile.mkstemp(suffix=".json")
        os.close(self._cfg_fd)
        os.unlink(self._cfg_path)

        import config

        self._orig_config_path = config.CONFIG_PATH
        config.CONFIG_PATH = self._cfg_path

        import notifications

        notifications._queue = None
        notifications._thread = None
        notifications._started = False

        import server

        self.app = server.app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        import config

        config.CONFIG_PATH = self._orig_config_path
        with contextlib.suppress(FileNotFoundError):
            os.unlink(self._cfg_path)


class TestList(NotificationsApiTestCase):
    def test_GET_returns_empty_initially(self):
        resp = self.client.get("/api/notifications")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["events"], [])
        self.assertIn("queue_max_size", body)
        self.assertIn("max_failures", body)
        self.assertIn("rate_limit_per_sec", body)


class TestCreate(NotificationsApiTestCase):
    def test_POST_creates_event_with_id(self):
        resp = self.client.post(
            "/api/notifications",
            json={"event_type": "onArtistNewSingle", "apprise_url": "http://x"},
        )
        self.assertEqual(resp.status_code, 201)
        ev = resp.get_json()
        self.assertIn("id", ev)
        self.assertEqual(ev["event_type"], "onArtistNewSingle")

    def test_POST_rejects_invalid_event_type(self):
        resp = self.client.post(
            "/api/notifications",
            json={"event_type": "bogus", "apprise_url": "http://x"},
        )
        self.assertEqual(resp.status_code, 400)


class TestUpdate(NotificationsApiTestCase):
    def _create(self):
        return self.client.post(
            "/api/notifications",
            json={"event_type": "onArtistNewSingle", "apprise_url": "http://x"},
        ).get_json()

    def test_PUT_updates_existing(self):
        ev = self._create()
        resp = self.client.put(
            f"/api/notifications/{ev['id']}",
            json={"enabled": False},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.get_json()["enabled"])

    def test_PUT_rejects_invalid_event_type(self):
        ev = self._create()
        resp = self.client.put(
            f"/api/notifications/{ev['id']}",
            json={"event_type": "bogus"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_PUT_returns_404_for_unknown(self):
        resp = self.client.put("/api/notifications/missing", json={"enabled": False})
        self.assertEqual(resp.status_code, 404)


class TestDelete(NotificationsApiTestCase):
    def test_DELETE_removes_event(self):
        ev = self.client.post(
            "/api/notifications",
            json={"event_type": "onArtistNewSingle", "apprise_url": "http://x"},
        ).get_json()
        resp = self.client.delete(f"/api/notifications/{ev['id']}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.client.get("/api/notifications").get_json()["events"], [])

    def test_DELETE_returns_404_for_unknown(self):
        resp = self.client.delete("/api/notifications/missing")
        self.assertEqual(resp.status_code, 404)


class TestTest(NotificationsApiTestCase):
    def test_POST_test_unsaved_calls_send_test(self):
        with patch("notifications.send_test", return_value=(True, "OK")) as m:
            resp = self.client.post(
                "/api/notifications/test",
                json={"event_type": "onArtistNewSingle", "apprise_url": "http://x"},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"ok": True, "message": "OK"})
        m.assert_called_once()

    def test_POST_test_unsaved_rejects_invalid_type(self):
        resp = self.client.post(
            "/api/notifications/test",
            json={"event_type": "bogus", "apprise_url": "http://x"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_POST_test_saved_loads_and_sends(self):
        ev = self.client.post(
            "/api/notifications",
            json={"event_type": "onArtistNewSingle", "apprise_url": "http://x"},
        ).get_json()
        with patch("notifications.send_test", return_value=(True, "OK")) as m:
            resp = self.client.post(f"/api/notifications/{ev['id']}/test")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["ok"], True)
        m.assert_called_once()

    def test_POST_test_saved_returns_404_for_unknown(self):
        resp = self.client.post("/api/notifications/missing/test")
        self.assertEqual(resp.status_code, 404)


class TestEventTypes(NotificationsApiTestCase):
    def test_GET_event_types_returns_all_known(self):
        resp = self.client.get("/api/notifications/event-types")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        types = [t["event_type"] for t in body["types"]]
        self.assertEqual(
            set(types),
            {
                "onDiscoveryComplete",
                "onDiscoveryFailed",
                "onArtistNewRelease",
                "onArtistNewSingle",
                "onWatchlistBatchComplete",
            },
        )


if __name__ == "__main__":
    unittest.main()
