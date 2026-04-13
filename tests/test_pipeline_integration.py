import json
import os
import sys
import unittest

from fastapi.testclient import TestClient

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from backend_api.database import SessionLocal
from backend_api.main import app, engine
from backend_api.models import Base, DBDetection, DBSpeed, DBViolation
from data_streaming import mqtt_forwarder as mqtt_forwarder_module
from data_streaming.mqtt_forwarder import MQTTForwarder
from speed_estimation.main import SpeedEstimationService
from violation_detection.main import ViolationDetectionService


class FakeMQTTClient:
    def __init__(self):
        self.published = []

    def publish(self, topic, payload):
        self.published.append((topic, payload))


class FakeMessage:
    def __init__(self, topic, payload):
        self.topic = topic
        self.payload = json.dumps(payload).encode("utf-8")


class TestPipelineIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.api_client = TestClient(app)

        self.speed_service = SpeedEstimationService(
            broker_host="localhost",
            broker_port=1883,
            pixels_per_meter=25.0,
            camera_profiles={"cam_int": {"pixels_per_meter": 10.0}},
        )
        self.speed_service.client = FakeMQTTClient()

        self.violation_service = ViolationDetectionService(
            broker_host="localhost",
            broker_port=1883,
            speed_limit=60.0,
            camera_profiles={"cam_int": {"speed_limit_kmh": 30.0}},
        )
        self.violation_service.client = FakeMQTTClient()

        self.forwarder = MQTTForwarder(
            broker_host="localhost",
            broker_port=1883,
            api_url="http://testserver",
        )

    def tearDown(self):
        self.api_client.close()
        Base.metadata.drop_all(bind=engine)

    def _forward_with_test_client(self, topic, payload):
        original_post = mqtt_forwarder_module.requests.post

        def fake_post(url, json, timeout):
            path = url.replace("http://testserver", "", 1)
            return self.api_client.post(path, json=json)

        try:
            mqtt_forwarder_module.requests.post = fake_post
            self.forwarder.on_message(None, None, FakeMessage(topic, payload))
        finally:
            mqtt_forwarder_module.requests.post = original_post

    def _flush_published_events(self, service, also_to_violation_service=False):
        published = list(service.client.published)
        service.client.published.clear()

        for topic, raw_payload in published:
            payload = json.loads(raw_payload)
            self._forward_with_test_client(topic, payload)
            if also_to_violation_service:
                self.violation_service.on_message(None, None, FakeMessage(topic, payload))

    def test_detection_speed_violation_flow_persists_events(self):
        detections = [
            {
                "camera_id": "cam_int",
                "timestamp": "2025-01-01T12:00:00+00:00",
                "object_id": 101,
                "class": "motorcycle",
                "helmet_status": "no_helmet",
                "bbox": [50.0, 100.0, 150.0, 200.0],
                "confidence": 0.95,
                "frame_number": 1,
                "source": "edge",
            },
            {
                "camera_id": "cam_int",
                "timestamp": "2025-01-01T12:00:01+00:00",
                "object_id": 101,
                "class": "motorcycle",
                "helmet_status": "no_helmet",
                "bbox": [150.0, 100.0, 250.0, 200.0],
                "confidence": 0.96,
                "frame_number": 2,
                "source": "edge",
            },
        ]

        for detection in detections:
            self._forward_with_test_client("camera/detections", detection)
            self.violation_service.on_message(None, None, FakeMessage("camera/detections", detection))
            self._flush_published_events(self.violation_service)

            self.speed_service.on_message(None, None, FakeMessage("camera/detections", detection))
            self._flush_published_events(self.speed_service, also_to_violation_service=True)
            self._flush_published_events(self.violation_service)

        with SessionLocal() as db:
            self.assertEqual(db.query(DBDetection).count(), 2)
            self.assertEqual(db.query(DBSpeed).count(), 1)
            self.assertEqual(db.query(DBViolation).count(), 2)

            speed = db.query(DBSpeed).one()
            self.assertAlmostEqual(speed.speed_kmh, 36.0)

            violation_types = {row.violation_type for row in db.query(DBViolation).all()}
            self.assertEqual(violation_types, {"helmet_violation", "speed_violation"})

        summary = self.api_client.get("/analytics/summary")
        self.assertEqual(summary.status_code, 200)
        data = summary.json()
        self.assertEqual(data["total_detections_logged"], 2)
        self.assertEqual(data["total_speeds_logged"], 1)
        self.assertEqual(data["total_violations_logged"], 2)


if __name__ == "__main__":
    unittest.main()
