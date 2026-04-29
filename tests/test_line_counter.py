import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from edge_vision.line_counter import LineCrossingCounter


class TestLineCounter(unittest.TestCase):
    def setUp(self):
        self.counter = LineCrossingCounter(
            counting_lines=[
                {
                    "id": "main_gate",
                    "label": "Main Gate",
                    "points": [[100.0, 0.0], [100.0, 200.0]],
                    "enabled": True,
                    "classes": ["car", "pedestrian"],
                }
            ],
            min_crossing_distance_px=5.0,
        )

    def test_emits_crossing_once_for_single_direction(self):
        first = self.counter.process_tracks("cam_1", 1, [
            {"object_id": 1, "class_name": "car", "bbox": [60.0, 50.0, 80.0, 90.0]}
        ], "2025-01-01T12:00:00+00:00")
        second = self.counter.process_tracks("cam_1", 2, [
            {"object_id": 1, "class_name": "car", "bbox": [120.0, 50.0, 140.0, 90.0]}
        ], "2025-01-01T12:00:01+00:00")

        self.assertEqual(len(first), 0)
        self.assertEqual(len(second), 1)
        self.assertEqual(second[0].direction, "a_to_b")

    def test_no_event_when_object_stays_on_same_side(self):
        self.counter.process_tracks("cam_1", 1, [
            {"object_id": 1, "class_name": "car", "bbox": [60.0, 50.0, 80.0, 90.0]}
        ], "2025-01-01T12:00:00+00:00")
        result = self.counter.process_tracks("cam_1", 2, [
            {"object_id": 1, "class_name": "car", "bbox": [62.0, 50.0, 82.0, 90.0]}
        ], "2025-01-01T12:00:01+00:00")
        self.assertEqual(result, [])

    def test_direction_detected_for_reverse_crossing(self):
        self.counter.process_tracks("cam_1", 1, [
            {"object_id": 2, "class_name": "car", "bbox": [120.0, 50.0, 140.0, 90.0]}
        ], "2025-01-01T12:00:00+00:00")
        result = self.counter.process_tracks("cam_1", 2, [
            {"object_id": 2, "class_name": "car", "bbox": [60.0, 50.0, 80.0, 90.0]}
        ], "2025-01-01T12:00:01+00:00")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].direction, "b_to_a")

    def test_no_duplicate_while_oscillating_near_line(self):
        self.counter.process_tracks("cam_1", 1, [
            {"object_id": 3, "class_name": "car", "bbox": [60.0, 50.0, 80.0, 90.0]}
        ], "2025-01-01T12:00:00+00:00")
        first_cross = self.counter.process_tracks("cam_1", 2, [
            {"object_id": 3, "class_name": "car", "bbox": [120.0, 50.0, 140.0, 90.0]}
        ], "2025-01-01T12:00:01+00:00")
        near_line = self.counter.process_tracks("cam_1", 3, [
            {"object_id": 3, "class_name": "car", "bbox": [96.0, 50.0, 104.0, 90.0]}
        ], "2025-01-01T12:00:02+00:00")

        self.assertEqual(len(first_cross), 1)
        self.assertEqual(near_line, [])

    def test_class_filter_excludes_unsupported_types(self):
        self.counter.process_tracks("cam_1", 1, [
            {"object_id": 4, "class_name": "bus", "bbox": [60.0, 50.0, 80.0, 90.0]}
        ], "2025-01-01T12:00:00+00:00")
        result = self.counter.process_tracks("cam_1", 2, [
            {"object_id": 4, "class_name": "bus", "bbox": [120.0, 50.0, 140.0, 90.0]}
        ], "2025-01-01T12:00:01+00:00")
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
