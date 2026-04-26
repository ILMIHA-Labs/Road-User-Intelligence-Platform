import unittest
from fastapi.testclient import TestClient
import sys
import os
import tempfile
from pathlib import Path

# Ensure src is in the path for importing backend_api
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import backend_api.main as backend_main
from backend_api.database import init_db
from backend_api.main import app, engine
from backend_api.models import Base

class TestBackendAPI(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        init_db()
        self.live_preview_tmp = tempfile.TemporaryDirectory()
        self.evidence_tmp = tempfile.TemporaryDirectory()
        self.original_live_frames_dir = backend_main._LIVE_FRAMES_DIR
        self.original_violation_evidence_dir = backend_main._VIOLATION_EVIDENCE_DIR
        backend_main._LIVE_FRAMES_DIR = Path(self.live_preview_tmp.name)
        backend_main._VIOLATION_EVIDENCE_DIR = Path(self.evidence_tmp.name)
        self.client_cm = TestClient(app)
        self.client = self.client_cm.__enter__()

    def tearDown(self):
        self.client_cm.__exit__(None, None, None)
        backend_main._LIVE_FRAMES_DIR = self.original_live_frames_dir
        backend_main._VIOLATION_EVIDENCE_DIR = self.original_violation_evidence_dir
        self.live_preview_tmp.cleanup()
        self.evidence_tmp.cleanup()
        Base.metadata.drop_all(bind=engine)

    def test_read_root(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("status", response.json())

    def test_dashboard_static_page_serves(self):
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Traffic Operations Dashboard", response.text)

    def test_camera_config_endpoint_returns_defaults_and_merged_profiles(self):
        response = self.client.get("/cameras/config")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("defaults", data)
        self.assertIn("cameras", data)
        self.assertGreaterEqual(len(data["cameras"]), 1)
        first_camera = data["cameras"][0]
        self.assertEqual(first_camera["id"], "sample_video_01")
        self.assertIn("speed_limit_kmh", first_camera)
        self.assertIn("max_motorcycle_riders", first_camera)
        self.assertIn("zones", first_camera)

    def test_live_camera_snapshot_endpoints(self):
        camera_dir = Path(self.live_preview_tmp.name) / "sample_video_01"
        camera_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = camera_dir / "latest.jpg"
        snapshot_path.write_bytes(b"\xff\xd8\xff\xd9")
        self.client.post("/detections", json={
            "camera_id": "sample_video_01",
            "timestamp": "2023-10-27T10:00:00Z",
            "object_id": 1,
            "class": "car",
            "helmet_status": "unknown",
            "bbox": [0.0, 0.0, 10.0, 10.0],
            "confidence": 0.9,
            "source": "edge",
        })

        response = self.client.get("/live/cameras")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        sample_status = next(item for item in data["cameras"] if item["camera_id"] == "sample_video_01")
        self.assertTrue(sample_status["snapshot_available"])
        self.assertEqual(sample_status["snapshot_url"], "/live/cameras/sample_video_01/snapshot")
        self.assertIn("health", sample_status)
        self.assertIn("last_detection_at", sample_status)
        self.assertIn("snapshot_age_seconds", sample_status)

        detail_response = self.client.get("/live/cameras/sample_video_01")
        self.assertEqual(detail_response.status_code, 200)
        self.assertTrue(detail_response.json()["snapshot_available"])

        image_response = self.client.get("/live/cameras/sample_video_01/snapshot")
        self.assertEqual(image_response.status_code, 200)
        self.assertEqual(image_response.headers["content-type"], "image/jpeg")

    def test_live_camera_snapshot_missing_returns_404(self):
        response = self.client.get("/live/cameras/missing_cam/snapshot")
        self.assertEqual(response.status_code, 404)

    def test_create_detection(self):
        payload = {
            "camera_id": "test_cam",
            "timestamp": "2023-10-27T10:00:00Z",
            "object_id": 99,
            "class": "motorcycle",
            "helmet_status": "no_helmet",
            "bbox": [10.5, 20.0, 30.5, 40.0],
            "confidence": 0.95,
            "frame_number": 1,
            "source": "rtsp"
        }
        response = self.client.post("/detections", json=payload)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"message": "Detection stored"})

    def test_create_speed(self):
        payload = {
            "camera_id": "test_cam",
            "object_id": 99,
            "speed_kmh": 65.4,
            "timestamp": "2023-10-27T10:00:01Z"
        }
        response = self.client.post("/speeds", json=payload)
        self.assertEqual(response.status_code, 201)

    def test_create_violation(self):
        payload = {
            "violation_type": "helmet_violation",
            "object_id": 99,
            "camera_id": "test_cam",
            "timestamp": "2023-10-27T10:00:02Z",
        }
        response = self.client.post("/violations", json=payload)
        self.assertEqual(response.status_code, 201)

    def test_violation_evidence_is_captured_and_served(self):
        camera_dir = Path(self.live_preview_tmp.name) / "test_cam"
        camera_dir.mkdir(parents=True, exist_ok=True)
        (camera_dir / "latest.jpg").write_bytes(b"\xff\xd8\xff\xd9")

        response = self.client.post("/violations", json={
            "violation_type": "speed_violation",
            "object_id": 99,
            "camera_id": "test_cam",
            "timestamp": "2023-10-27T10:00:02Z",
        })
        self.assertEqual(response.status_code, 201)

        recent_response = self.client.get("/events/recent?camera_id=test_cam")
        self.assertEqual(recent_response.status_code, 200)
        recent_data = recent_response.json()
        self.assertEqual(len(recent_data["violations"]), 1)
        evidence_url = recent_data["violations"][0]["evidence_url"]
        self.assertTrue(evidence_url)

        evidence_response = self.client.get(evidence_url)
        self.assertEqual(evidence_response.status_code, 200)
        self.assertEqual(evidence_response.headers["content-type"], "image/jpeg")

    def test_violation_log_returns_evidence_url_when_available(self):
        camera_dir = Path(self.live_preview_tmp.name) / "cam_recent"
        camera_dir.mkdir(parents=True, exist_ok=True)
        (camera_dir / "latest.jpg").write_bytes(b"\xff\xd8\xff\xd9")
        self.client.post("/violations", json={
            "violation_type": "speed_violation",
            "object_id": 1,
            "camera_id": "cam_recent",
            "timestamp": "2023-10-27T10:00:02Z",
        })

        response = self.client.get("/violations/log?camera_id=cam_recent")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["items"]), 1)
        self.assertTrue(data["items"][0]["evidence_url"])

    def test_analytics_by_camera(self):
        self.client.post("/detections", json={
            "camera_id": "cam_a",
            "timestamp": "2023-10-27T10:00:00Z",
            "object_id": 1,
            "class": "car",
            "helmet_status": "unknown",
            "bbox": [0.0, 0.0, 10.0, 10.0],
            "confidence": 0.9,
            "source": "edge",
        })
        self.client.post("/speeds", json={
            "camera_id": "cam_a",
            "object_id": 1,
            "speed_kmh": 40.0,
            "timestamp": "2023-10-27T10:00:01Z",
            "source": "edge",
        })
        self.client.post("/violations", json={
            "violation_type": "speed_violation",
            "object_id": 1,
            "camera_id": "cam_b",
            "timestamp": "2023-10-27T10:00:02Z",
        })

        response = self.client.get("/analytics/by-camera")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        cameras = {item["camera_id"]: item for item in data["cameras"]}
        self.assertEqual(cameras["cam_a"]["detections"], 1)
        self.assertEqual(cameras["cam_a"]["speeds"], 1)
        self.assertEqual(cameras["cam_a"]["violations"], 0)
        self.assertEqual(cameras["cam_b"]["violations"], 1)

    def test_analytics_violation_breakdown(self):
        self.client.post("/violations", json={
            "violation_type": "speed_violation",
            "object_id": 1,
            "camera_id": "cam_a",
            "timestamp": "2023-10-27T10:00:02Z",
        })
        self.client.post("/violations", json={
            "violation_type": "helmet_violation",
            "object_id": 2,
            "camera_id": "cam_a",
            "timestamp": "2023-10-27T10:00:03Z",
        })
        self.client.post("/violations", json={
            "violation_type": "speed_violation",
            "object_id": 3,
            "camera_id": "cam_b",
            "timestamp": "2023-10-27T10:00:04Z",
        })

        response = self.client.get("/analytics/violations?camera_id=cam_a")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        violations = {item["violation_type"]: item["count"] for item in data["violations"]}
        self.assertEqual(violations["speed_violation"], 1)
        self.assertEqual(violations["helmet_violation"], 1)

    def test_recent_events(self):
        self.client.post("/detections", json={
            "camera_id": "cam_recent",
            "timestamp": "2023-10-27T10:00:00Z",
            "object_id": 1,
            "class": "car",
            "helmet_status": "unknown",
            "bbox": [0.0, 0.0, 10.0, 10.0],
            "confidence": 0.9,
            "source": "edge",
        })
        self.client.post("/speeds", json={
            "camera_id": "cam_recent",
            "object_id": 1,
            "speed_kmh": 44.0,
            "timestamp": "2023-10-27T10:00:01Z",
            "source": "edge",
        })
        self.client.post("/violations", json={
            "violation_type": "speed_violation",
            "object_id": 1,
            "camera_id": "cam_recent",
            "timestamp": "2023-10-27T10:00:02Z",
        })

        response = self.client.get("/events/recent?camera_id=cam_recent&limit=5")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["detections"]), 1)
        self.assertEqual(len(data["speeds"]), 1)
        self.assertEqual(len(data["violations"]), 1)
        self.assertEqual(data["detections"][0]["class"], "car")

    def test_recent_events_support_time_filters(self):
        self.client.post("/violations", json={
            "violation_type": "speed_violation",
            "object_id": 1,
            "camera_id": "cam_recent",
            "timestamp": "2023-10-27T09:00:02Z",
        })
        self.client.post("/violations", json={
            "violation_type": "helmet_violation",
            "object_id": 2,
            "camera_id": "cam_recent",
            "timestamp": "2023-10-27T11:00:02Z",
        })

        response = self.client.get(
            "/events/recent?camera_id=cam_recent&start=2023-10-27T10:00:00Z&end=2023-10-27T12:00:00Z"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["violations"]), 1)
        self.assertEqual(data["violations"][0]["violation_type"], "helmet_violation")

    def test_summary_filters(self):
        self.client.post("/detections", json={
            "camera_id": "cam_filter",
            "timestamp": "2023-10-27T10:00:00Z",
            "object_id": 1,
            "class": "car",
            "helmet_status": "unknown",
            "bbox": [0.0, 0.0, 10.0, 10.0],
            "confidence": 0.9,
            "source": "edge",
        })
        self.client.post("/detections", json={
            "camera_id": "cam_filter",
            "timestamp": "2023-10-27T11:00:00Z",
            "object_id": 2,
            "class": "car",
            "helmet_status": "unknown",
            "bbox": [0.0, 0.0, 10.0, 10.0],
            "confidence": 0.9,
            "source": "edge",
        })

        response = self.client.get(
            "/analytics/summary?camera_id=cam_filter&start=2023-10-27T10:30:00Z&end=2023-10-27T11:30:00Z"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_detections_logged"], 1)
        self.assertEqual(data["camera_id"], "cam_filter")

    def test_z_analytics_summary(self):
        self.client.post("/detections", json={
            "camera_id": "test_cam",
            "timestamp": "2023-10-27T10:00:00Z",
            "object_id": 99,
            "class": "motorcycle",
            "helmet_status": "no_helmet",
            "bbox": [10.5, 20.0, 30.5, 40.0],
            "confidence": 0.95,
            "frame_number": 1,
            "source": "rtsp"
        })
        response = self.client.get("/analytics/summary")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("total_detections_logged", data)
        self.assertEqual(data["total_detections_logged"], 1)
        self.assertEqual(data["total_speeds_logged"], 0)
        self.assertIn("total_speeds_logged", data)

if __name__ == '__main__':
    unittest.main()
