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
                    "min_crossing_distance_px": 5.0,
                    "reset_distance_px": 8.0,
                    "min_displacement_px": 10.0,
                    "min_observations": 2,
                }
            ],
            min_crossing_distance_px=5.0,
        )

    def test_emits_crossing_once_for_single_direction(self):
        first = self.counter.process_tracks("cam_1", 1, [
            {"object_id": 1, "class_name": "car", "bbox": [60.0, 50.0, 80.0, 90.0]}
        ], "2025-01-01T12:00:00+00:00")
        second = self.counter.process_tracks("cam_1", 2, [
            {"object_id": 1, "class_name": "car", "bbox": [70.0, 50.0, 90.0, 90.0]}
        ], "2025-01-01T12:00:01+00:00")
        third = self.counter.process_tracks("cam_1", 3, [
            {"object_id": 1, "class_name": "car", "bbox": [120.0, 50.0, 140.0, 90.0]}
        ], "2025-01-01T12:00:02+00:00")

        self.assertEqual(len(first), 0)
        self.assertEqual(len(second), 0)
        self.assertEqual(len(third), 1)
        self.assertEqual(third[0].direction, "a_to_b")

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
        self.counter.process_tracks("cam_1", 2, [
            {"object_id": 2, "class_name": "car", "bbox": [110.0, 50.0, 130.0, 90.0]}
        ], "2025-01-01T12:00:01+00:00")
        result = self.counter.process_tracks("cam_1", 3, [
            {"object_id": 2, "class_name": "car", "bbox": [60.0, 50.0, 80.0, 90.0]}
        ], "2025-01-01T12:00:02+00:00")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].direction, "b_to_a")

    def test_no_duplicate_while_oscillating_near_line(self):
        self.counter.process_tracks("cam_1", 1, [
            {"object_id": 3, "class_name": "car", "bbox": [60.0, 50.0, 80.0, 90.0]}
        ], "2025-01-01T12:00:00+00:00")
        self.counter.process_tracks("cam_1", 2, [
            {"object_id": 3, "class_name": "car", "bbox": [70.0, 50.0, 90.0, 90.0]}
        ], "2025-01-01T12:00:01+00:00")
        first_cross = self.counter.process_tracks("cam_1", 3, [
            {"object_id": 3, "class_name": "car", "bbox": [120.0, 50.0, 140.0, 90.0]}
        ], "2025-01-01T12:00:02+00:00")
        near_line = self.counter.process_tracks("cam_1", 4, [
            {"object_id": 3, "class_name": "car", "bbox": [96.0, 50.0, 104.0, 90.0]}
        ], "2025-01-01T12:00:03+00:00")

        self.assertEqual(len(first_cross), 1)
        self.assertEqual(near_line, [])

    def test_no_count_for_short_jitter_across_line(self):
        self.counter.process_tracks("cam_1", 1, [
            {"object_id": 5, "class_name": "car", "bbox": [88.0, 50.0, 98.0, 90.0]}
        ], "2025-01-01T12:00:00+00:00")
        result = self.counter.process_tracks("cam_1", 2, [
            {"object_id": 5, "class_name": "car", "bbox": [101.0, 50.0, 111.0, 90.0]}
        ], "2025-01-01T12:00:01+00:00")
        self.assertEqual(result, [])

    def test_no_count_when_motion_crosses_infinite_line_outside_segment(self):
        self.counter.process_tracks("cam_1", 1, [
            {"object_id": 6, "class_name": "car", "bbox": [60.0, 220.0, 80.0, 260.0]}
        ], "2025-01-01T12:00:00+00:00")
        self.counter.process_tracks("cam_1", 2, [
            {"object_id": 6, "class_name": "car", "bbox": [70.0, 220.0, 90.0, 260.0]}
        ], "2025-01-01T12:00:01+00:00")
        result = self.counter.process_tracks("cam_1", 3, [
            {"object_id": 6, "class_name": "car", "bbox": [120.0, 220.0, 140.0, 260.0]}
        ], "2025-01-01T12:00:02+00:00")
        self.assertEqual(result, [])

    def test_retrigger_after_reset_on_same_direction(self):
        self.counter.process_tracks("cam_1", 1, [
            {"object_id": 7, "class_name": "car", "bbox": [60.0, 50.0, 80.0, 90.0]}
        ], "2025-01-01T12:00:00+00:00")
        self.counter.process_tracks("cam_1", 2, [
            {"object_id": 7, "class_name": "car", "bbox": [70.0, 50.0, 90.0, 90.0]}
        ], "2025-01-01T12:00:01+00:00")
        first_cross = self.counter.process_tracks("cam_1", 3, [
            {"object_id": 7, "class_name": "car", "bbox": [120.0, 50.0, 140.0, 90.0]}
        ], "2025-01-01T12:00:02+00:00")
        self.counter.process_tracks("cam_1", 4, [
            {"object_id": 7, "class_name": "car", "bbox": [150.0, 50.0, 170.0, 90.0]}
        ], "2025-01-01T12:00:03+00:00")
        self.counter.process_tracks("cam_1", 5, [
            {"object_id": 7, "class_name": "car", "bbox": [70.0, 50.0, 90.0, 90.0]}
        ], "2025-01-01T12:00:04+00:00")
        self.counter.process_tracks("cam_1", 6, [
            {"object_id": 7, "class_name": "car", "bbox": [80.0, 50.0, 100.0, 90.0]}
        ], "2025-01-01T12:00:05+00:00")
        second_cross = self.counter.process_tracks("cam_1", 7, [
            {"object_id": 7, "class_name": "car", "bbox": [130.0, 50.0, 150.0, 90.0]}
        ], "2025-01-01T12:00:06+00:00")

        self.assertEqual(len(first_cross), 1)
        self.assertEqual(len(second_cross), 1)

    def test_person_alias_counts_as_pedestrian(self):
        self.counter.process_tracks("cam_1", 1, [
            {"object_id": 8, "class_name": "person", "bbox": [60.0, 50.0, 80.0, 90.0]}
        ], "2025-01-01T12:00:00+00:00")
        self.counter.process_tracks("cam_1", 2, [
            {"object_id": 8, "class_name": "person", "bbox": [70.0, 50.0, 90.0, 90.0]}
        ], "2025-01-01T12:00:01+00:00")
        result = self.counter.process_tracks("cam_1", 3, [
            {"object_id": 8, "class_name": "person", "bbox": [120.0, 50.0, 140.0, 90.0]}
        ], "2025-01-01T12:00:02+00:00")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].class_name, "pedestrian")

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
