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

    def _prime_crossing_vehicle(self, engine, object_id, camera_id, timestamp_start, timestamp_end):
        engine.update_state(
            object_id,
            detection_event={
                "class": "car",
                "camera_id": camera_id,
                "bbox": [60.0, 170.0, 140.0, 245.0],
                "timestamp": timestamp_start,
            },
        )
        engine.update_state(
            object_id,
            detection_event={
                "class": "car",
                "camera_id": camera_id,
                "bbox": [120.0, 180.0, 220.0, 260.0],
                "timestamp": timestamp_end,
            },
        )
        engine.update_state(
            object_id,
            speed_event={"speed_kmh": 14.0, "timestamp": timestamp_end},
        )

    def _prime_crossing_pedestrian(self, engine, object_id, camera_id, timestamp_start, timestamp_end):
        engine.update_state(
            object_id,
            detection_event={
                "class": "pedestrian",
                "camera_id": camera_id,
                "bbox": [150.0, 220.0, 190.0, 300.0],
                "timestamp": timestamp_start,
            },
        )
        engine.update_state(
            object_id,
            detection_event={
                "class": "pedestrian",
                "camera_id": camera_id,
                "bbox": [152.0, 220.0, 192.0, 300.0],
                "timestamp": timestamp_end,
            },
        )

    def _build_crossing_engine(self, category, zones=None):
        return ViolationRulesEngine(
            speed_limit_kmh=60.0,
            pedestrian_crossing_min_speed_kmh=5.0,
            pedestrian_crossing_window_seconds=2.0,
            crossing_min_presence_seconds=0.5,
            crossing_min_observations=2,
            crossing_vehicle_min_displacement_px=12.0,
            zones=zones or [
                {
                    "id": "crossing_demo",
                    "category": category,
                    "points": [[100.0, 220.0], [260.0, 220.0], [260.0, 320.0], [100.0, 320.0]],
                }
            ],
        )
    
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
            zones=[
                {
                    "id": "zebra_demo",
                    "category": "zebra_crossing",
                    "points": [[250.0, 360.0], [540.0, 360.0], [540.0, 560.0], [250.0, 560.0]],
                }
            ],
        )

        obj_id = 5
        engine.update_state(
            obj_id,
            detection_event={
                "class": "car",
                "camera_id": "cam_04",
                "timestamp": "2025-01-01T10:00:00Z",
                "bbox": [300.0, 420.0, 500.0, 520.0],
            },
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
        self.assertEqual(engine.object_states[obj_id]["stopped_vehicle_zone_id"], "zebra_demo")

    def test_stopped_vehicle_violation_requires_zebra_zone(self):
        engine = ViolationRulesEngine(
            speed_limit_kmh=60.0,
            stopped_speed_threshold_kmh=3.0,
            stopped_duration_seconds=20,
            stopped_resume_speed_kmh=8.0,
            zones=[
                {
                    "id": "zebra_demo",
                    "category": "zebra_crossing",
                    "points": [[250.0, 360.0], [540.0, 360.0], [540.0, 560.0], [250.0, 560.0]],
                }
            ],
        )

        obj_id = 501
        engine.update_state(
            obj_id,
            detection_event={
                "class": "car",
                "camera_id": "cam_04",
                "timestamp": "2025-01-01T10:00:00Z",
                "bbox": [50.0, 120.0, 180.0, 220.0],
            },
        )
        engine.update_state(
            obj_id,
            speed_event={"speed_kmh": 0.0, "timestamp": "2025-01-01T10:00:25Z"},
        )
        self.assertEqual(engine.evaluate_violations(obj_id), [])

    def test_stop_line_violation(self):
        engine = ViolationRulesEngine(
            speed_limit_kmh=60.0,
            stop_line_min_speed_kmh=5.0,
            zones=[
                {
                    "id": "north_stop_line",
                    "category": "stop_line",
                    "points": [[100.0, 180.0], [220.0, 180.0], [220.0, 230.0], [100.0, 230.0]],
                },
                {
                    "id": "north_zebra",
                    "category": "zebra_crossing",
                    "points": [[100.0, 140.0], [220.0, 140.0], [220.0, 230.0], [100.0, 230.0]],
                },
            ],
        )

        obj_id = 55
        engine.update_state(
            obj_id,
            detection_event={
                "class": "car",
                "camera_id": "cam_stop",
                "bbox": [120.0, 140.0, 200.0, 200.0],
                "timestamp": "2025-01-01T10:00:00Z",
            },
        )
        engine.update_state(
            obj_id,
            speed_event={"speed_kmh": 12.0, "timestamp": "2025-01-01T10:00:00Z"},
        )
        self.assertIn("stop_line_violation", engine.evaluate_violations(obj_id))
        self.assertEqual(engine.object_states[obj_id]["stop_line_zone_id"], "north_stop_line")

        self.assertEqual(engine.evaluate_violations(obj_id), [])

        engine.update_state(
            obj_id,
            detection_event={
                "class": "car",
                "camera_id": "cam_stop",
                "bbox": [240.0, 140.0, 320.0, 200.0],
                "timestamp": "2025-01-01T10:00:01Z",
            },
        )
        self.assertEqual(engine.evaluate_violations(obj_id), [])

        engine.update_state(
            obj_id,
            detection_event={
                "class": "car",
                "camera_id": "cam_stop",
                "bbox": [120.0, 150.0, 200.0, 205.0],
                "timestamp": "2025-01-01T10:00:02Z",
            },
        )
        self.assertIn("stop_line_violation", engine.evaluate_violations(obj_id))

        engine.update_state(
            obj_id,
            speed_event={"speed_kmh": 0.2, "timestamp": "2025-01-01T10:00:31Z"},
        )
        self.assertEqual(engine.evaluate_violations(obj_id), [])

        engine.update_state(
            obj_id,
            speed_event={"speed_kmh": 12.0, "timestamp": "2025-01-01T10:00:40Z"},
        )
        self.assertIn("stop_line_violation", engine.evaluate_violations(obj_id))

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

    def test_pedestrian_crossing_violation(self):
        engine = ViolationRulesEngine(
            speed_limit_kmh=60.0,
            pedestrian_crossing_min_speed_kmh=5.0,
            pedestrian_crossing_window_seconds=2.0,
            crossing_min_presence_seconds=0.5,
            crossing_min_observations=2,
            crossing_vehicle_min_displacement_px=12.0,
            zones=[
                {
                    "id": "school_crossing",
                    "category": "pedestrian_crossing",
                    "points": [[100.0, 220.0], [260.0, 220.0], [260.0, 320.0], [100.0, 320.0]],
                }
            ],
        )

        vehicle_id = 56
        pedestrian_id = 57
        self._prime_crossing_vehicle(
            engine,
            vehicle_id,
            "cam_cross",
            "2025-01-01T10:00:00Z",
            "2025-01-01T10:00:01Z",
        )
        self._prime_crossing_pedestrian(
            engine,
            pedestrian_id,
            "cam_cross",
            "2025-01-01T10:00:00Z",
            "2025-01-01T10:00:01Z",
        )

        self.assertIn("pedestrian_crossing_violation", engine.evaluate_violations(vehicle_id))
        self.assertEqual(
            engine.object_states[vehicle_id]["pedestrian_crossing_zone_id"],
            "school_crossing",
        )
        self.assertEqual(engine.evaluate_violations(vehicle_id), [])

    def test_zebra_crossing_violation(self):
        engine = ViolationRulesEngine(
            speed_limit_kmh=60.0,
            pedestrian_crossing_min_speed_kmh=5.0,
            pedestrian_crossing_window_seconds=2.0,
            crossing_min_presence_seconds=0.5,
            crossing_min_observations=2,
            crossing_vehicle_min_displacement_px=12.0,
            zones=[
                {
                    "id": "zebra_demo",
                    "category": "zebra_crossing",
                    "points": [[100.0, 220.0], [260.0, 220.0], [260.0, 320.0], [100.0, 320.0]],
                }
            ],
        )

        vehicle_id = 58
        pedestrian_id = 59
        self._prime_crossing_vehicle(
            engine,
            vehicle_id,
            "cam_zebra",
            "2025-01-01T10:00:00Z",
            "2025-01-01T10:00:01Z",
        )
        self._prime_crossing_pedestrian(
            engine,
            pedestrian_id,
            "cam_zebra",
            "2025-01-01T10:00:00Z",
            "2025-01-01T10:00:01Z",
        )

        self.assertIn("zebra_crossing_violation", engine.evaluate_violations(vehicle_id))
        self.assertEqual(
            engine.object_states[vehicle_id]["zebra_crossing_zone_id"],
            "zebra_demo",
        )
        self.assertEqual(engine.evaluate_violations(vehicle_id), [])

        engine.update_state(
            pedestrian_id,
            detection_event={
                "class": "pedestrian",
                "camera_id": "cam_cross",
                "bbox": [300.0, 220.0, 340.0, 300.0],
                "timestamp": "2025-01-01T10:00:05Z",
            },
        )
        self.assertEqual(engine.evaluate_violations(vehicle_id), [])

    def test_zebra_crossing_violation_requires_real_presence_and_motion(self):
        engine = ViolationRulesEngine(
            speed_limit_kmh=60.0,
            pedestrian_crossing_min_speed_kmh=5.0,
            pedestrian_crossing_window_seconds=2.0,
            crossing_min_presence_seconds=0.5,
            crossing_min_observations=2,
            crossing_vehicle_min_displacement_px=12.0,
            zones=[
                {
                    "id": "zebra_demo",
                    "category": "zebra_crossing",
                    "points": [[100.0, 220.0], [260.0, 220.0], [260.0, 320.0], [100.0, 320.0]],
                }
            ],
        )

        vehicle_id = 63
        pedestrian_id = 64

        engine.update_state(
            vehicle_id,
            detection_event={
                "class": "car",
                "camera_id": "cam_zebra",
                "bbox": [120.0, 180.0, 220.0, 260.0],
                "timestamp": "2025-01-01T10:00:00Z",
            },
        )
        engine.update_state(
            vehicle_id,
            speed_event={"speed_kmh": 15.0, "timestamp": "2025-01-01T10:00:00Z"},
        )
        engine.update_state(
            pedestrian_id,
            detection_event={
                "class": "pedestrian",
                "camera_id": "cam_zebra",
                "bbox": [150.0, 220.0, 190.0, 300.0],
                "timestamp": "2025-01-01T10:00:00Z",
            },
        )
        self.assertEqual(engine.evaluate_violations(vehicle_id), [])

        self._prime_crossing_pedestrian(
            engine,
            pedestrian_id,
            "cam_zebra",
            "2025-01-01T10:00:00Z",
            "2025-01-01T10:00:01Z",
        )
        self.assertEqual(engine.evaluate_violations(vehicle_id), [])

        self._prime_crossing_vehicle(
            engine,
            vehicle_id,
            "cam_zebra",
            "2025-01-01T10:00:00Z",
            "2025-01-01T10:00:01Z",
        )
        self.assertIn("zebra_crossing_violation", engine.evaluate_violations(vehicle_id))

    def test_crossing_violations_reject_recent_but_non_overlapping_presence(self):
        for category, violation_type in (
            ("pedestrian_crossing", "pedestrian_crossing_violation"),
            ("zebra_crossing", "zebra_crossing_violation"),
        ):
            with self.subTest(category=category):
                engine = self._build_crossing_engine(category)
                self._prime_crossing_pedestrian(
                    engine,
                    101,
                    "cam_conflict",
                    "2025-01-01T10:00:00Z",
                    "2025-01-01T10:00:01Z",
                )
                self._prime_crossing_vehicle(
                    engine,
                    100,
                    "cam_conflict",
                    "2025-01-01T10:00:01Z",
                    "2025-01-01T10:00:02Z",
                )

                self.assertNotIn(violation_type, engine.evaluate_violations(100))

    def test_crossing_violations_reject_stopped_vehicle(self):
        for category, violation_type in (
            ("pedestrian_crossing", "pedestrian_crossing_violation"),
            ("zebra_crossing", "zebra_crossing_violation"),
        ):
            with self.subTest(category=category):
                engine = self._build_crossing_engine(category)
                self._prime_crossing_vehicle(
                    engine,
                    102,
                    "cam_conflict",
                    "2025-01-01T10:00:00Z",
                    "2025-01-01T10:00:01Z",
                )
                engine.update_state(
                    102,
                    speed_event={"speed_kmh": 0.0, "timestamp": "2025-01-01T10:00:01Z"},
                )
                self._prime_crossing_pedestrian(
                    engine,
                    103,
                    "cam_conflict",
                    "2025-01-01T10:00:00Z",
                    "2025-01-01T10:00:01Z",
                )

                self.assertNotIn(violation_type, engine.evaluate_violations(102))

    def test_crossing_violations_require_stable_pedestrian_presence(self):
        for category, violation_type in (
            ("pedestrian_crossing", "pedestrian_crossing_violation"),
            ("zebra_crossing", "zebra_crossing_violation"),
        ):
            with self.subTest(category=category):
                engine = self._build_crossing_engine(category)
                self._prime_crossing_vehicle(
                    engine,
                    108,
                    "cam_conflict",
                    "2025-01-01T10:00:00Z",
                    "2025-01-01T10:00:01Z",
                )
                engine.update_state(
                    109,
                    detection_event={
                        "class": "pedestrian",
                        "camera_id": "cam_conflict",
                        "bbox": [150.0, 220.0, 190.0, 300.0],
                        "timestamp": "2025-01-01T10:00:01Z",
                    },
                )

                self.assertNotIn(violation_type, engine.evaluate_violations(108))

    def test_crossing_violations_require_same_zone(self):
        for category, violation_type in (
            ("pedestrian_crossing", "pedestrian_crossing_violation"),
            ("zebra_crossing", "zebra_crossing_violation"),
        ):
            with self.subTest(category=category):
                engine = self._build_crossing_engine(
                    category,
                    zones=[
                        {
                            "id": "zone_a",
                            "category": category,
                            "points": [[100.0, 220.0], [260.0, 220.0], [260.0, 320.0], [100.0, 320.0]],
                        },
                        {
                            "id": "zone_b",
                            "category": category,
                            "points": [[300.0, 220.0], [460.0, 220.0], [460.0, 320.0], [300.0, 320.0]],
                        },
                    ],
                )
                self._prime_crossing_vehicle(
                    engine,
                    104,
                    "cam_conflict",
                    "2025-01-01T10:00:00Z",
                    "2025-01-01T10:00:01Z",
                )
                for bbox, timestamp in (
                    ([320.0, 220.0, 360.0, 300.0], "2025-01-01T10:00:00Z"),
                    ([322.0, 220.0, 362.0, 300.0], "2025-01-01T10:00:01Z"),
                ):
                    engine.update_state(
                        105,
                        detection_event={
                            "class": "pedestrian",
                            "camera_id": "cam_conflict",
                            "bbox": bbox,
                            "timestamp": timestamp,
                        },
                    )

                self.assertNotIn(violation_type, engine.evaluate_violations(104))

    def test_crossing_violations_accept_adjacent_live_frames(self):
        for category, violation_type in (
            ("pedestrian_crossing", "pedestrian_crossing_violation"),
            ("zebra_crossing", "zebra_crossing_violation"),
        ):
            with self.subTest(category=category):
                engine = self._build_crossing_engine(category)
                engine.update_state(
                    106,
                    detection_event={
                        "class": "car",
                        "camera_id": "cam_conflict",
                        "bbox": [60.0, 170.0, 140.0, 245.0],
                        "timestamp": "2025-01-01T10:00:00Z",
                        "frame_number": 10,
                    },
                )
                engine.update_state(
                    106,
                    detection_event={
                        "class": "car",
                        "camera_id": "cam_conflict",
                        "bbox": [120.0, 180.0, 220.0, 260.0],
                        "timestamp": "2025-01-01T10:00:01Z",
                        "frame_number": 11,
                    },
                )
                engine.update_state(
                    106,
                    speed_event={"speed_kmh": 14.0, "timestamp": "2025-01-01T10:00:01Z"},
                )
                for frame_number, timestamp in (
                    (11, "2025-01-01T10:00:00Z"),
                    (12, "2025-01-01T10:00:01Z"),
                ):
                    engine.update_state(
                        107,
                        detection_event={
                            "class": "pedestrian",
                            "camera_id": "cam_conflict",
                            "bbox": [150.0, 220.0, 190.0, 300.0],
                            "timestamp": timestamp,
                            "frame_number": frame_number,
                        },
                    )

                self.assertIn(violation_type, engine.evaluate_violations(106))

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

    def test_rider_association_picks_single_best_motorcycle(self):
        engine = ViolationRulesEngine(
            speed_limit_kmh=60.0,
            max_motorcycle_riders=1,
        )

        engine.update_state(
            80,
            detection_event={
                "class": "motorcycle",
                "camera_id": "cam_assoc",
                "bbox": [100.0, 100.0, 200.0, 200.0],
                "timestamp": "2025-01-01T10:00:00Z",
            },
        )
        engine.update_state(
            81,
            detection_event={
                "class": "motorcycle",
                "camera_id": "cam_assoc",
                "bbox": [230.0, 100.0, 330.0, 200.0],
                "timestamp": "2025-01-01T10:00:00Z",
            },
        )
        engine.update_state(
            82,
            detection_event={
                "class": "pedestrian",
                "camera_id": "cam_assoc",
                "bbox": [115.0, 75.0, 155.0, 155.0],
                "timestamp": "2025-01-01T10:00:01Z",
            },
        )

        self.assertEqual(engine._best_motorcycle_match(82), 80)
        self.assertEqual(engine._count_motorcycle_riders(80), 2)
        self.assertEqual(engine._count_motorcycle_riders(81), 1)
        self.assertIn("multiple_riders_violation", engine.evaluate_violations(80))
        self.assertEqual(engine.evaluate_violations(81), [])

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

    def test_service_emits_stop_line_violation_from_detection_and_speed(self):
        service = ViolationDetectionService(
            broker_host="localhost",
            broker_port=1883,
            speed_limit=60.0,
            stop_line_min_speed_kmh=5.0,
            camera_profiles={
                "cam_stop": {
                    "zones": [
                        {
                            "id": "north_stop_line",
                            "category": "stop_line",
                            "points": [[100.0, 180.0], [220.0, 180.0], [220.0, 230.0], [100.0, 230.0]],
                        }
                    ]
                }
            },
        )
        service.client = FakeMQTTClient()

        service.on_message(
            None,
            None,
            FakeMessage(
                "camera/detections",
                {
                    "camera_id": "cam_stop",
                    "timestamp": "2025-01-01T10:00:00Z",
                    "object_id": 90,
                    "class": "car",
                    "helmet_status": "unknown",
                    "bbox": [120.0, 140.0, 200.0, 200.0],
                    "confidence": 0.92,
                    "source": "edge",
                },
            ),
        )
        service.on_message(
            None,
            None,
            FakeMessage(
                "camera/speeds",
                {
                    "camera_id": "cam_stop",
                    "timestamp": "2025-01-01T10:00:00Z",
                    "object_id": 90,
                    "speed_kmh": 12.0,
                    "source": "edge",
                },
            ),
        )

        published_payloads = [json.loads(payload) for _, payload in service.client.published]
        violation_types = {payload["violation_type"] for payload in published_payloads}
        self.assertIn("stop_line_violation", violation_types)

    def test_service_emits_pedestrian_crossing_violation_from_detection_flow(self):
        service = ViolationDetectionService(
            broker_host="localhost",
            broker_port=1883,
            speed_limit=60.0,
            pedestrian_crossing_min_speed_kmh=5.0,
            pedestrian_crossing_window_seconds=2.0,
            crossing_min_presence_seconds=0.5,
            crossing_min_observations=2,
            crossing_vehicle_min_displacement_px=12.0,
            camera_profiles={
                "cam_cross": {
                    "zones": [
                        {
                            "id": "school_crossing",
                            "category": "pedestrian_crossing",
                            "points": [[100.0, 220.0], [260.0, 220.0], [260.0, 320.0], [100.0, 320.0]],
                        }
                    ]
                }
            },
        )
        service.client = FakeMQTTClient()

        service.on_message(
            None,
            None,
            FakeMessage(
                "camera/detections",
                {
                    "camera_id": "cam_cross",
                    "timestamp": "2025-01-01T10:00:00Z",
                    "object_id": 91,
                    "class": "car",
                    "helmet_status": "unknown",
                    "bbox": [60.0, 170.0, 140.0, 245.0],
                    "confidence": 0.95,
                    "source": "edge",
                },
            ),
        )
        service.on_message(
            None,
            None,
            FakeMessage(
                "camera/detections",
                {
                    "camera_id": "cam_cross",
                    "timestamp": "2025-01-01T10:00:01Z",
                    "object_id": 91,
                    "class": "car",
                    "helmet_status": "unknown",
                    "bbox": [120.0, 180.0, 220.0, 260.0],
                    "confidence": 0.95,
                    "source": "edge",
                },
            ),
        )
        service.on_message(
            None,
            None,
            FakeMessage(
                "camera/speeds",
                {
                    "camera_id": "cam_cross",
                    "timestamp": "2025-01-01T10:00:01Z",
                    "object_id": 91,
                    "speed_kmh": 15.0,
                    "source": "edge",
                },
            ),
        )
        service.on_message(
            None,
            None,
            FakeMessage(
                "camera/detections",
                {
                    "camera_id": "cam_cross",
                    "timestamp": "2025-01-01T10:00:00Z",
                    "object_id": 92,
                    "class": "pedestrian",
                    "helmet_status": "unknown",
                    "bbox": [150.0, 220.0, 190.0, 300.0],
                    "confidence": 0.96,
                    "source": "edge",
                },
            ),
        )
        service.on_message(
            None,
            None,
            FakeMessage(
                "camera/detections",
                {
                    "camera_id": "cam_cross",
                    "timestamp": "2025-01-01T10:00:01Z",
                    "object_id": 92,
                    "class": "pedestrian",
                    "helmet_status": "unknown",
                    "bbox": [152.0, 220.0, 192.0, 300.0],
                    "confidence": 0.96,
                    "source": "edge",
                },
            ),
        )

        published_payloads = [json.loads(payload) for _, payload in service.client.published]
        violation_types = {payload["violation_type"] for payload in published_payloads}
        self.assertIn("pedestrian_crossing_violation", violation_types)

    def test_service_emits_zebra_crossing_violation_from_detection_flow(self):
        service = ViolationDetectionService(
            broker_host="localhost",
            broker_port=1883,
            speed_limit=60.0,
            pedestrian_crossing_min_speed_kmh=5.0,
            pedestrian_crossing_window_seconds=2.0,
            crossing_min_presence_seconds=0.5,
            crossing_min_observations=2,
            crossing_vehicle_min_displacement_px=12.0,
            camera_profiles={
                "cam_zebra": {
                    "zones": [
                        {
                            "id": "zebra_demo",
                            "category": "zebra_crossing",
                            "points": [[100.0, 220.0], [260.0, 220.0], [260.0, 320.0], [100.0, 320.0]],
                        }
                    ]
                }
            },
        )
        service.client = FakeMQTTClient()

        service.on_message(
            None,
            None,
            FakeMessage(
                "camera/detections",
                {
                    "camera_id": "cam_zebra",
                    "timestamp": "2025-01-01T10:00:00Z",
                    "object_id": 93,
                    "class": "car",
                    "helmet_status": "unknown",
                    "bbox": [60.0, 170.0, 140.0, 245.0],
                    "confidence": 0.95,
                    "source": "edge",
                },
            ),
        )
        service.on_message(
            None,
            None,
            FakeMessage(
                "camera/detections",
                {
                    "camera_id": "cam_zebra",
                    "timestamp": "2025-01-01T10:00:01Z",
                    "object_id": 93,
                    "class": "car",
                    "helmet_status": "unknown",
                    "bbox": [120.0, 180.0, 220.0, 260.0],
                    "confidence": 0.95,
                    "source": "edge",
                },
            ),
        )
        service.on_message(
            None,
            None,
            FakeMessage(
                "camera/speeds",
                {
                    "camera_id": "cam_zebra",
                    "timestamp": "2025-01-01T10:00:01Z",
                    "object_id": 93,
                    "speed_kmh": 15.0,
                    "source": "edge",
                },
            ),
        )
        service.on_message(
            None,
            None,
            FakeMessage(
                "camera/detections",
                {
                    "camera_id": "cam_zebra",
                    "timestamp": "2025-01-01T10:00:00Z",
                    "object_id": 94,
                    "class": "pedestrian",
                    "helmet_status": "unknown",
                    "bbox": [150.0, 220.0, 190.0, 300.0],
                    "confidence": 0.96,
                    "source": "edge",
                },
            ),
        )
        service.on_message(
            None,
            None,
            FakeMessage(
                "camera/detections",
                {
                    "camera_id": "cam_zebra",
                    "timestamp": "2025-01-01T10:00:01Z",
                    "object_id": 94,
                    "class": "pedestrian",
                    "helmet_status": "unknown",
                    "bbox": [152.0, 220.0, 192.0, 300.0],
                    "confidence": 0.96,
                    "source": "edge",
                },
            ),
        )

        published_payloads = [json.loads(payload) for _, payload in service.client.published]
        violation_types = {payload["violation_type"] for payload in published_payloads}
        self.assertIn("zebra_crossing_violation", violation_types)

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
                    "stop_line_min_speed_kmh": 7.0,
                    "pedestrian_crossing_min_speed_kmh": 9.0,
                    "pedestrian_crossing_window_seconds": 3.5,
                    "crossing_min_presence_seconds": 1.0,
                    "crossing_min_observations": 3,
                    "crossing_vehicle_min_displacement_px": 18.0,
                    "zones": [
                        {
                            "id": "north_stop_line",
                            "category": "stop_line",
                            "points": [[100.0, 180.0], [220.0, 180.0], [220.0, 230.0], [100.0, 230.0]],
                        },
                        {
                            "id": "school_crossing",
                            "category": "pedestrian_crossing",
                            "points": [[100.0, 220.0], [260.0, 220.0], [260.0, 320.0], [100.0, 320.0]],
                        }
                    ],
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
        self.assertEqual(school_zone_engine.stop_line_min_speed_kmh, 7.0)
        self.assertEqual(school_zone_engine.pedestrian_crossing_min_speed_kmh, 9.0)
        self.assertEqual(school_zone_engine.pedestrian_crossing_window_seconds, 3.5)
        self.assertEqual(school_zone_engine.crossing_min_presence_seconds, 1.0)
        self.assertEqual(school_zone_engine.crossing_min_observations, 3)
        self.assertEqual(school_zone_engine.crossing_vehicle_min_displacement_px, 18.0)
        self.assertEqual(len(school_zone_engine.zones), 2)

if __name__ == '__main__':
    unittest.main()
