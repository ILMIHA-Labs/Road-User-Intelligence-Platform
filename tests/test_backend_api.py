import unittest
from fastapi.testclient import TestClient
import sys
import os

# Ensure src is in the path for importing backend_api
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from backend_api.main import app, engine
from backend_api.models import Base

class TestBackendAPI(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        # Create tables
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        # Drop tables
        Base.metadata.drop_all(bind=engine)

    def test_read_root(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("status", response.json())

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

    def test_z_analytics_summary(self):
        # We prefix with z_ so it runs after test_create_detection
        response = self.client.get("/analytics/summary")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("total_detections_logged", data)
        self.assertEqual(data["total_detections_logged"], 1)

if __name__ == '__main__':
    unittest.main()
