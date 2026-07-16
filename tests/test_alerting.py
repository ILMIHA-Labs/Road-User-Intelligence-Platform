import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

# Isolate the alerting tests from any operator runtime database.
_TEST_DATABASE_DIR = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_TEST_DATABASE_DIR.name) / 'alerting_test.db'}"

from fastapi.testclient import TestClient

from backend_api import alerting
from backend_api.database import SessionLocal, engine, init_db
from backend_api.main import app
from backend_api.models import Base, DBDetection
from backend_api.routes import _config
from backend_api.routes.cameras import _upsert_camera_profile


class TestCameraHealthTransitions(unittest.TestCase):
    def _snap(self, age):
        return {"camera_id": "cam", "activity_age_seconds": age, "last_activity_at": "t"}

    def test_first_observation_never_alerts(self):
        alert, state = alerting.evaluate_camera_health(None, self._snap(999), 60.0)
        self.assertIsNone(alert)
        self.assertEqual(state, "offline")

    def test_online_to_offline_fires_once(self):
        alert, state = alerting.evaluate_camera_health("online", self._snap(120), 60.0)
        self.assertIsNotNone(alert)
        self.assertEqual(alert.alert_type, "camera_offline")
        self.assertEqual(state, "offline")
        # staying offline does not re-fire
        alert2, state2 = alerting.evaluate_camera_health(state, self._snap(150), 60.0)
        self.assertIsNone(alert2)
        self.assertEqual(state2, "offline")

    def test_offline_to_online_recovery(self):
        alert, state = alerting.evaluate_camera_health("offline", self._snap(5), 60.0, recovery_enabled=True)
        self.assertEqual(alert.alert_type, "camera_recovered")
        self.assertEqual(state, "online")

    def test_recovery_can_be_disabled(self):
        alert, state = alerting.evaluate_camera_health("offline", self._snap(5), 60.0, recovery_enabled=False)
        self.assertIsNone(alert)
        self.assertEqual(state, "online")

    def test_unknown_activity_keeps_previous_state(self):
        alert, state = alerting.evaluate_camera_health("online", self._snap(None), 60.0)
        self.assertIsNone(alert)
        self.assertEqual(state, "online")


class _AlertingTestBase(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        init_db()
        self._orig = {
            "enabled": _config._ALERTS_ENABLED,
            "url": _config._ALERT_WEBHOOK_URL,
            "debounce": _config._ALERT_DEBOUNCE_SECONDS,
            "types": _config._ALERT_VIOLATION_TYPES,
            "offline_after": _config._CAMERA_OFFLINE_AFTER_SECONDS,
            "sync": alerting.SYNCHRONOUS_DELIVERY,
            "send": alerting._send_webhook,
        }
        _config._ALERTS_ENABLED = True
        _config._ALERT_WEBHOOK_URL = "https://example.test/hook"
        _config._ALERT_DEBOUNCE_SECONDS = 60.0
        _config._ALERT_VIOLATION_TYPES = frozenset()
        alerting.SYNCHRONOUS_DELIVERY = True
        alerting.reset_debounce()
        self.sent = []
        alerting._send_webhook = lambda url, payload, timeout: self.sent.append((url, payload))
        # No context manager: avoids firing the startup camera-monitor thread.
        self.client = TestClient(app)

    def tearDown(self):
        _config._ALERTS_ENABLED = self._orig["enabled"]
        _config._ALERT_WEBHOOK_URL = self._orig["url"]
        _config._ALERT_DEBOUNCE_SECONDS = self._orig["debounce"]
        _config._ALERT_VIOLATION_TYPES = self._orig["types"]
        _config._CAMERA_OFFLINE_AFTER_SECONDS = self._orig["offline_after"]
        alerting.SYNCHRONOUS_DELIVERY = self._orig["sync"]
        alerting._send_webhook = self._orig["send"]
        alerting.reset_debounce()
        Base.metadata.drop_all(bind=engine)

    def _post_violation(self, object_id, vtype="speed_violation", camera_id="camA", ts="2026-07-08T08:00:00Z"):
        return self.client.post("/violations", json={
            "violation_type": vtype, "object_id": object_id,
            "camera_id": camera_id, "timestamp": ts,
        })


class TestViolationAlerts(_AlertingTestBase):
    def test_violation_creates_and_delivers_alert(self):
        self.assertEqual(self._post_violation(1).status_code, 201)
        self.assertEqual(len(self.sent), 1)
        data = self.client.get("/alerts").json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["alerts"][0]["alert_type"], "violation")
        self.assertTrue(data["alerts"][0]["delivered"])

    def test_debounce_suppresses_duplicate(self):
        self._post_violation(1)
        self.sent.clear()
        self._post_violation(2)  # same camera + type within debounce window
        self.assertEqual(len(self.sent), 0)
        self.assertEqual(self.client.get("/alerts").json()["total"], 1)

    def test_disabled_produces_no_alert(self):
        _config._ALERTS_ENABLED = False
        self.assertEqual(self._post_violation(1).status_code, 201)
        self.assertEqual(len(self.sent), 0)
        self.assertEqual(self.client.get("/alerts").json()["total"], 0)

    def test_violation_type_filter(self):
        _config._ALERT_VIOLATION_TYPES = frozenset({"helmet_violation"})
        self._post_violation(1, vtype="speed_violation")
        self.assertEqual(self.client.get("/alerts").json()["total"], 0)
        self._post_violation(2, vtype="helmet_violation")
        self.assertEqual(self.client.get("/alerts").json()["total"], 1)

    def test_webhook_failure_is_recorded_not_raised(self):
        def boom(url, payload, timeout):
            raise RuntimeError("connection refused")
        alerting._send_webhook = boom
        self.assertEqual(self._post_violation(1).status_code, 201)
        alert = self.client.get("/alerts").json()["alerts"][0]
        self.assertFalse(alert["delivered"])
        self.assertIn("webhook", alert["delivery_error"])


class TestAlertEndpoints(_AlertingTestBase):
    def test_config_redacts_secrets(self):
        cfg = self.client.get("/alerts/config").json()
        self.assertTrue(cfg["alerts_enabled"])
        self.assertTrue(cfg["webhook_configured"])
        self.assertEqual(cfg["webhook_target"], "https://example.test")
        self.assertNotIn("/hook", cfg["webhook_target"])

    def test_test_alert_delivers(self):
        response = self.client.post("/alerts/test")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.json()["created"]), 1)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.client.get("/alerts?alert_type=test").json()["total"], 1)


class TestCameraMonitorRunOnce(_AlertingTestBase):
    def test_run_once_emits_offline_alert(self):
        _config._CAMERA_OFFLINE_AFTER_SECONDS = 60.0
        db = SessionLocal()
        try:
            _upsert_camera_profile(db, {"id": "cam_mon"}, source="test")
            old = datetime.now(timezone.utc) - timedelta(minutes=10)
            db.add(DBDetection(camera_id="cam_mon", timestamp=old, object_id=1, class_name="car"))
            db.commit()
        finally:
            db.close()

        monitor = alerting.CameraHealthMonitor()
        monitor._states["cam_mon"] = "online"  # was online, now stale -> offline
        created = monitor.run_once()
        self.assertEqual(len(created), 1)
        offline = self.client.get("/alerts?alert_type=camera_offline").json()
        self.assertEqual(offline["total"], 1)
        self.assertEqual(offline["alerts"][0]["camera_id"], "cam_mon")


if __name__ == "__main__":
    unittest.main()
