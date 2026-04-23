import unittest
import sys
import os
import json

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from violation_detection.violation_rules import ViolationRulesEngine
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

class TestViolationDetection(unittest.TestCase):
    
    def test_speed_violation(self):
        engine = ViolationRulesEngine(speed_limit_kmh=60.0)
        
        obj_id = 1
        
        # Initial detection
        engine.update_state(obj_id, detection_event={"class": "car", "camera_id": "cam_01"})
        
        # Speed event below limit
        engine.update_state(obj_id, speed_event={"speed_kmh": 50.0})
        violations = engine.evaluate_violations(obj_id)
        self.assertEqual(len(violations), 0)
        
        # Speed event above limit
        engine.update_state(obj_id, speed_event={"speed_kmh": 80.0})
        violations = engine.evaluate_violations(obj_id)
        self.assertIn("speed_violation", violations)
        
        # Verify it doesn't trigger again immediately (state caching logic built in)
        engine.update_state(obj_id, speed_event={"speed_kmh": 85.0})
        violations2 = engine.evaluate_violations(obj_id)
        self.assertEqual(len(violations2), 0) # Already triggered

    def test_helmet_violation(self):
        engine = ViolationRulesEngine(speed_limit_kmh=60.0)
        
        obj_id = 2
        
        # Motorcycle with helmet -> no violation
        engine.update_state(obj_id, detection_event={"class": "motorcycle", "helmet_status": "helmet", "camera_id": "cam_01"})
        violations = engine.evaluate_violations(obj_id)
        self.assertEqual(len(violations), 0)
        
        # Motorcycle without helmet -> violation
        engine.update_state(obj_id, detection_event={"class": "motorcycle", "helmet_status": "no_helmet"})
        violations2 = engine.evaluate_violations(obj_id)
        self.assertIn("helmet_violation", violations2)

    def test_speed_violation_can_retrigger_after_reset(self):
        engine = ViolationRulesEngine(
            speed_limit_kmh=60.0,
            speed_reset_delta_kmh=5.0,
        )

        obj_id = 3
        engine.update_state(obj_id, detection_event={"class": "car", "camera_id": "cam_02"})

        engine.update_state(obj_id, speed_event={"speed_kmh": 75.0, "timestamp": "2025-01-01T10:00:00Z"})
        self.assertIn("speed_violation", engine.evaluate_violations(obj_id))

        engine.update_state(obj_id, speed_event={"speed_kmh": 76.0, "timestamp": "2025-01-01T10:00:01Z"})
        self.assertEqual(engine.evaluate_violations(obj_id), [])

        engine.update_state(obj_id, speed_event={"speed_kmh": 54.0, "timestamp": "2025-01-01T10:00:02Z"})
        self.assertEqual(engine.evaluate_violations(obj_id), [])

        engine.update_state(obj_id, speed_event={"speed_kmh": 78.0, "timestamp": "2025-01-01T10:00:03Z"})
        self.assertIn("speed_violation", engine.evaluate_violations(obj_id))

    def test_severe_speed_violation(self):
        engine = ViolationRulesEngine(
            speed_limit_kmh=60.0,
            severe_speed_delta_kmh=20.0,
        )

        obj_id = 4
        engine.update_state(obj_id, detection_event={"class": "car", "camera_id": "cam_03"})
        engine.update_state(obj_id, speed_event={"speed_kmh": 95.0, "timestamp": "2025-01-01T10:00:00Z"})
        self.assertIn("severe_speed_violation", engine.evaluate_violations(obj_id))

    def test_stopped_vehicle_violation(self):
        engine = ViolationRulesEngine(
            speed_limit_kmh=60.0,
            stopped_speed_threshold_kmh=3.0,
            stopped_duration_seconds=20,
            stopped_resume_speed_kmh=8.0,
        )

        obj_id = 5
        engine.update_state(
            obj_id,
            detection_event={"class": "car", "camera_id": "cam_04", "timestamp": "2025-01-01T10:00:00Z"},
        )
        engine.update_state(
            obj_id,
            speed_event={"speed_kmh": 1.0, "timestamp": "2025-01-01T10:00:05Z"},
        )
        self.assertEqual(engine.evaluate_violations(obj_id), [])

        engine.update_state(
            obj_id,
            speed_event={"speed_kmh": 0.5, "timestamp": "2025-01-01T10:00:30Z"},
        )
        self.assertIn("stopped_vehicle_violation", engine.evaluate_violations(obj_id))

        engine.update_state(
            obj_id,
            speed_event={"speed_kmh": 0.2, "timestamp": "2025-01-01T10:00:31Z"},
        )
        self.assertEqual(engine.evaluate_violations(obj_id), [])

        engine.update_state(
            obj_id,
            speed_event={"speed_kmh": 12.0, "timestamp": "2025-01-01T10:00:40Z"},
        )
        self.assertEqual(engine.evaluate_violations(obj_id), [])

        engine.update_state(
            obj_id,
            speed_event={"speed_kmh": 0.0, "timestamp": "2025-01-01T10:01:10Z"},
        )
        self.assertEqual(engine.evaluate_violations(obj_id), [])

        engine.update_state(
            obj_id,
            speed_event={"speed_kmh": 0.0, "timestamp": "2025-01-01T10:01:35Z"},
        )
        self.assertIn("stopped_vehicle_violation", engine.evaluate_violations(obj_id))

    def test_multiple_riders_violation(self):
        engine = ViolationRulesEngine(
            speed_limit_kmh=60.0,
            max_motorcycle_riders=2,
        )

        bike_id = 6
        engine.update_state(
            bike_id,
            detection_event={
                "class": "motorcycle",
                "camera_id": "cam_bike",
                "bbox": [100.0, 100.0, 200.0, 200.0],
                "timestamp": "2025-01-01T10:00:00Z",
            },
        )
        engine.update_state(
            61,
            detection_event={
                "class": "pedestrian",
                "camera_id": "cam_bike",
                "bbox": [110.0, 70.0, 150.0, 150.0],
                "timestamp": "2025-01-01T10:00:00Z",
            },
        )
        self.assertEqual(engine.evaluate_violations(bike_id), [])

        engine.update_state(
            62,
            detection_event={
                "class": "pedestrian",
                "camera_id": "cam_bike",
                "bbox": [150.0, 80.0, 190.0, 160.0],
                "timestamp": "2025-01-01T10:00:01Z",
            },
        )
        self.assertIn("multiple_riders_violation", engine.evaluate_violations(bike_id))
        self.assertEqual(engine.object_states[bike_id]["estimated_rider_count"], 3)

    def test_service_emits_multiple_riders_violation_from_detection_flow(self):
        service = ViolationDetectionService(
            broker_host="localhost",
            broker_port=1883,
            speed_limit=60.0,
        )
        service.client = FakeMQTTClient()

        detections = [
            {
                "camera_id": "cam_bike",
                "timestamp": "2025-01-01T10:00:00Z",
                "object_id": 70,
                "class": "motorcycle",
                "helmet_status": "helmet",
                "bbox": [100.0, 100.0, 200.0, 200.0],
                "confidence": 0.98,
                "source": "edge",
            },
            {
                "camera_id": "cam_bike",
                "timestamp": "2025-01-01T10:00:00Z",
                "object_id": 71,
                "class": "pedestrian",
                "helmet_status": "unknown",
                "bbox": [110.0, 70.0, 150.0, 150.0],
                "confidence": 0.95,
                "source": "edge",
            },
            {
                "camera_id": "cam_bike",
                "timestamp": "2025-01-01T10:00:01Z",
                "object_id": 72,
                "class": "pedestrian",
                "helmet_status": "unknown",
                "bbox": [150.0, 80.0, 190.0, 160.0],
                "confidence": 0.94,
                "source": "edge",
            },
        ]

        for detection in detections:
            service.on_message(None, None, FakeMessage("camera/detections", detection))

        published_payloads = [json.loads(payload) for _, payload in service.client.published]
        violation_types = {payload["violation_type"] for payload in published_payloads}
        self.assertIn("multiple_riders_violation", violation_types)

    def test_service_uses_per_camera_speed_limit(self):
        service = ViolationDetectionService(
            broker_host="localhost",
            broker_port=1883,
            speed_limit=60.0,
            camera_profiles={"school_zone": {"speed_limit_kmh": 30.0}},
        )

        school_zone_engine = service._get_engine("school_zone")
        self.assertEqual(school_zone_engine.speed_limit_kmh, 30.0)

        default_engine = service._get_engine("main_road")
        self.assertEqual(default_engine.speed_limit_kmh, 60.0)

    def test_service_uses_per_camera_violation_overrides(self):
        service = ViolationDetectionService(
            broker_host="localhost",
            broker_port=1883,
            speed_limit=60.0,
            speed_tolerance_kmh=0.0,
            severe_speed_delta_kmh=20.0,
            speed_reset_delta_kmh=5.0,
            max_motorcycle_riders=2,
            rider_association_window_seconds=2,
            rider_horizontal_margin_ratio=0.35,
            rider_upper_margin_ratio=0.75,
            rider_lower_margin_ratio=0.25,
            state_ttl_seconds=120,
            camera_profiles={
                "school_zone": {
                    "speed_limit_kmh": 30.0,
                    "speed_tolerance_kmh": 2.0,
                    "severe_speed_delta_kmh": 12.0,
                    "speed_reset_delta_kmh": 3.0,
                    "stopped_speed_threshold_kmh": 2.5,
                    "stopped_duration_seconds": 15,
                    "stopped_resume_speed_kmh": 7.0,
                    "max_motorcycle_riders": 3,
                    "rider_association_window_seconds": 3,
                    "rider_horizontal_margin_ratio": 0.45,
                    "rider_upper_margin_ratio": 0.9,
                    "rider_lower_margin_ratio": 0.2,
                    "state_ttl_seconds": 45,
                }
            },
        )

        school_zone_engine = service._get_engine("school_zone")
        self.assertEqual(school_zone_engine.speed_limit_kmh, 30.0)
        self.assertEqual(school_zone_engine.speed_tolerance_kmh, 2.0)
        self.assertEqual(school_zone_engine.severe_speed_delta_kmh, 12.0)
        self.assertEqual(school_zone_engine.speed_reset_delta_kmh, 3.0)
        self.assertEqual(school_zone_engine.stopped_speed_threshold_kmh, 2.5)
        self.assertEqual(school_zone_engine.stopped_duration_seconds, 15)
        self.assertEqual(school_zone_engine.stopped_resume_speed_kmh, 7.0)
        self.assertEqual(school_zone_engine.max_motorcycle_riders, 3)
        self.assertEqual(school_zone_engine.rider_association_window_seconds, 3)
        self.assertEqual(school_zone_engine.rider_horizontal_margin_ratio, 0.45)
        self.assertEqual(school_zone_engine.rider_upper_margin_ratio, 0.9)
        self.assertEqual(school_zone_engine.rider_lower_margin_ratio, 0.2)
        self.assertEqual(school_zone_engine.state_ttl_seconds, 45)

if __name__ == '__main__':
    unittest.main()
