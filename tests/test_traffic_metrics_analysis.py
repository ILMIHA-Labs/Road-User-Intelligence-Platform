import csv
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

import yaml

from video_analysis.safety_measures import SafetyMeasuresTracker
from video_analysis.traffic_metrics import (
    TrafficMetricsAnalyzer,
    build_counting_lines,
    build_line_setup_config,
    build_zebra_setup_config,
    load_line_config,
    load_zebra_config,
    zebra_event_fieldnames,
)


class FakeDetector:
    def __init__(self, frames):
        self.frames = frames
        self.index = 0

    def detect(self, frame):
        if self.index >= len(self.frames):
            return []
        observations = self.frames[self.index]
        self.index += 1
        return observations


class TestTrafficMetricsAnalysis(unittest.TestCase):
    def _camera_profile(self):
        return {
            "pixels_per_meter": 10.0,
            "speed_history_size": 2,
            "zones": [],
            "counting_lines": [
                {
                    "id": "main_gate",
                    "label": "Main Gate",
                    "points": [[100.0, 0.0], [100.0, 240.0]],
                    "enabled": True,
                    "classes": ["car", "pedestrian"],
                    "min_crossing_distance_px": 5.0,
                    "reset_distance_px": 8.0,
                    "min_displacement_px": 10.0,
                    "min_observations": 2,
                }
            ],
        }

    def test_build_counting_lines_prefers_cli_line(self):
        lines = build_counting_lines(self._camera_profile(), line_points=[[10, 0], [10, 100]])
        self.assertEqual(lines[0]["points"], [[10, 0], [10, 100]])
        self.assertIn("car", lines[0]["classes"])
        self.assertEqual(lines[0]["line_window_margin_px"], 240.0)

    def test_clicked_line_counts_near_endpoint_crossing(self):
        detector = FakeDetector(
            [
                [{"object_id": 11, "class_name": "car", "bbox": [40.0, 250.0, 60.0, 290.0], "confidence": 0.95}],
                [{"object_id": 11, "class_name": "car", "bbox": [55.0, 250.0, 75.0, 290.0], "confidence": 0.95}],
                [{"object_id": 11, "class_name": "car", "bbox": [130.0, 250.0, 150.0, 290.0], "confidence": 0.95}],
            ]
        )
        counting_lines = build_counting_lines(self._camera_profile(), line_points=[[100.0, 0.0], [100.0, 120.0]])
        analyzer = TrafficMetricsAnalyzer(
            camera_id="cam_count",
            camera_profile=self._camera_profile(),
            detector=detector,
            counting_lines=counting_lines,
        )
        frame = np.zeros((320, 320, 3), dtype=np.uint8)

        analyzer.analyze_frame(frame, 1, 0.0)
        analyzer.analyze_frame(frame, 2, 1.0)
        analyzer.analyze_frame(frame, 3, 2.0)

        self.assertEqual(analyzer._metric_summary(duration_seconds=3.0)["total_crossings"], 1)

    def test_build_and_load_line_setup_config(self):
        setup = build_line_setup_config(
            camera_id="cam_count",
            line_points=[[20, 30], [120, 130]],
            line_id="clicked_line",
        )
        self.assertEqual(setup["camera_id"], "cam_count")
        self.assertEqual(setup["line_id"], "clicked_line")
        self.assertEqual(setup["line_points"], [[20.0, 30.0], [120.0, 130.0]])

        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            yaml.safe_dump(setup, f)
            path = f.name
        try:
            self.assertEqual(load_line_config(path), [[20.0, 30.0], [120.0, 130.0]])
        finally:
            os.remove(path)

    def test_build_and_load_zebra_setup_config(self):
        setup = build_zebra_setup_config(
            camera_id="cam_count",
            zebra_points=[[100, 100], [200, 100], [200, 200], [100, 200]],
            zone_id="clicked_zebra",
        )
        self.assertEqual(setup["camera_id"], "cam_count")
        self.assertEqual(setup["zebra_zones"][0]["id"], "clicked_zebra")

        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            yaml.safe_dump(setup, f)
            path = f.name
        try:
            zones = load_zebra_config(path)
            self.assertEqual(zones[0]["id"], "clicked_zebra")
            self.assertEqual(zones[0]["category"], "zebra_crossing")
        finally:
            os.remove(path)

    def test_zebra_events_are_emitted_with_tolerant_zone(self):
        detector = FakeDetector(
            [
                [
                    {"object_id": 21, "class_name": "car", "bbox": [20.0, 120.0, 60.0, 170.0], "confidence": 0.95},
                    {"object_id": 22, "class_name": "pedestrian", "bbox": [130.0, 120.0, 150.0, 180.0], "confidence": 0.95},
                ],
                [
                    {"object_id": 21, "class_name": "car", "bbox": [75.0, 120.0, 115.0, 170.0], "confidence": 0.95},
                    {"object_id": 22, "class_name": "pedestrian", "bbox": [130.0, 120.0, 150.0, 180.0], "confidence": 0.95},
                ],
                [
                    {"object_id": 21, "class_name": "car", "bbox": [140.0, 120.0, 180.0, 170.0], "confidence": 0.95},
                    {"object_id": 22, "class_name": "pedestrian", "bbox": [130.0, 120.0, 150.0, 180.0], "confidence": 0.95},
                ],
            ]
        )
        zebra_zones = [
            {
                "id": "zebra_test",
                "label": "Zebra Test",
                "category": "zebra_crossing",
                "points": [[100.0, 100.0], [200.0, 100.0], [200.0, 200.0], [100.0, 200.0]],
            }
        ]
        analyzer = TrafficMetricsAnalyzer(
            camera_id="cam_count",
            camera_profile=self._camera_profile(),
            detector=detector,
            counting_lines=self._camera_profile()["counting_lines"],
            zebra_zones=zebra_zones,
            zebra_speed_threshold_kmh=15.0,
        )
        frame = np.zeros((320, 320, 3), dtype=np.uint8)

        analyzer.analyze_frame(frame, 1, 0.0)
        analyzer.analyze_frame(frame, 2, 1.0)
        analyzer.analyze_frame(frame, 3, 2.0)

        event_types = {row["event_type"] for row in analyzer.zebra_event_rows}
        self.assertIn("zebra_yielding_risk", event_types)
        self.assertIn("zebra_crossing_violation", event_types)

    def test_multi_zebra_occupancy_counts_by_zone(self):
        detector = FakeDetector(
            [
                [
                    {"object_id": 31, "class_name": "car", "bbox": [120.0, 120.0, 160.0, 170.0], "confidence": 0.95},
                    {"object_id": 32, "class_name": "pedestrian", "bbox": [330.0, 120.0, 350.0, 180.0], "confidence": 0.95},
                    {"object_id": 33, "class_name": "bicycle", "bbox": [365.0, 155.0, 398.0, 195.0], "confidence": 0.95},
                ]
            ]
        )
        zebra_zones = [
            {
                "id": "zebra_1",
                "label": "Z1",
                "category": "zebra_crossing",
                "points": [[100.0, 100.0], [200.0, 100.0], [200.0, 200.0], [100.0, 200.0]],
            },
            {
                "id": "zebra_2",
                "label": "Z2",
                "category": "zebra_crossing",
                "points": [[300.0, 100.0], [400.0, 100.0], [400.0, 200.0], [300.0, 200.0]],
            },
        ]
        analyzer = TrafficMetricsAnalyzer(
            camera_id="cam_count",
            camera_profile=self._camera_profile(),
            detector=detector,
            counting_lines=self._camera_profile()["counting_lines"],
            zebra_zones=zebra_zones,
        )
        frame = np.zeros((320, 480, 3), dtype=np.uint8)

        analyzer.analyze_frame(frame, 1, 0.0)

        by_zone = {row["zone_id"]: row for row in analyzer.zebra_occupancy_rows}
        self.assertEqual(by_zone["zebra_1"]["vehicles_in_zone"], 1)
        self.assertEqual(by_zone["zebra_1"]["pedestrians_in_zone"], 0)
        self.assertEqual(by_zone["zebra_2"]["pedestrians_in_zone"], 1)
        self.assertEqual(by_zone["zebra_2"]["bikes_in_zone"], 1)

    def test_zebra_events_match_only_same_zone(self):
        detector = FakeDetector(
            [
                [
                    {"object_id": 41, "class_name": "car", "bbox": [20.0, 120.0, 60.0, 170.0], "confidence": 0.95},
                    {"object_id": 42, "class_name": "pedestrian", "bbox": [330.0, 120.0, 350.0, 180.0], "confidence": 0.95},
                ],
                [
                    {"object_id": 41, "class_name": "car", "bbox": [75.0, 120.0, 115.0, 170.0], "confidence": 0.95},
                    {"object_id": 42, "class_name": "pedestrian", "bbox": [330.0, 120.0, 350.0, 180.0], "confidence": 0.95},
                ],
                [
                    {"object_id": 41, "class_name": "car", "bbox": [140.0, 120.0, 180.0, 170.0], "confidence": 0.95},
                    {"object_id": 42, "class_name": "pedestrian", "bbox": [330.0, 120.0, 350.0, 180.0], "confidence": 0.95},
                ],
            ]
        )
        zebra_zones = [
            {
                "id": "zebra_1",
                "label": "Z1",
                "category": "zebra_crossing",
                "points": [[100.0, 100.0], [200.0, 100.0], [200.0, 200.0], [100.0, 200.0]],
            },
            {
                "id": "zebra_2",
                "label": "Z2",
                "category": "zebra_crossing",
                "points": [[300.0, 100.0], [400.0, 100.0], [400.0, 200.0], [300.0, 200.0]],
            },
        ]
        analyzer = TrafficMetricsAnalyzer(
            camera_id="cam_count",
            camera_profile=self._camera_profile(),
            detector=detector,
            counting_lines=self._camera_profile()["counting_lines"],
            zebra_zones=zebra_zones,
            zebra_speed_threshold_kmh=15.0,
        )
        frame = np.zeros((320, 480, 3), dtype=np.uint8)

        analyzer.analyze_frame(frame, 1, 0.0)
        analyzer.analyze_frame(frame, 2, 1.0)
        analyzer.analyze_frame(frame, 3, 2.0)

        self.assertEqual(analyzer.zebra_event_rows, [])

    def test_vehicle_approach_speed_trends(self):
        analyzer = TrafficMetricsAnalyzer(
            camera_id="cam_count",
            camera_profile=self._camera_profile(),
            detector=FakeDetector([]),
            counting_lines=self._camera_profile()["counting_lines"],
            zebra_zones=[
                {
                    "id": "zebra_1",
                    "label": "Z1",
                    "category": "zebra_crossing",
                    "points": [[100.0, 100.0], [200.0, 100.0], [200.0, 200.0], [100.0, 200.0]],
                }
            ],
            zebra_speed_trend_deadband_kmh=2.0,
        )
        analyzer.zebra_approach_samples[(1, "zebra_1")] = [{"speed_kmh": 30.0}, {"speed_kmh": 24.0}]
        analyzer.zebra_approach_samples[(2, "zebra_1")] = [{"speed_kmh": 20.0}, {"speed_kmh": 25.0}]
        analyzer.zebra_approach_samples[(3, "zebra_1")] = [{"speed_kmh": 20.0}, {"speed_kmh": 21.0}]

        self.assertEqual(analyzer._approach_trend_for_vehicle_zone(1, "zebra_1")["vehicle_speed_trend"], "decreased")
        self.assertEqual(analyzer._approach_trend_for_vehicle_zone(2, "zebra_1")["vehicle_speed_trend"], "increased")
        self.assertEqual(analyzer._approach_trend_for_vehicle_zone(3, "zebra_1")["vehicle_speed_trend"], "constant")
        self.assertEqual(analyzer._approach_trend_for_vehicle_zone(4, "zebra_1")["vehicle_speed_trend"], "insufficient_data")
        self.assertEqual(
            analyzer._zebra_metric_summary()["by_zone"]["zebra_1"]["vehicle_approach_trends"],
            {"constant": 1, "decreased": 1, "increased": 1},
        )

    def test_zebra_event_csv_exports_constant_approach_speed_tag(self):
        analyzer = TrafficMetricsAnalyzer(
            camera_id="cam_count",
            camera_profile=self._camera_profile(),
            detector=FakeDetector([]),
            counting_lines=self._camera_profile()["counting_lines"],
            zebra_zones=[
                {
                    "id": "zebra_1",
                    "label": "Z1",
                    "category": "zebra_crossing",
                    "points": [[100.0, 100.0], [200.0, 100.0], [200.0, 200.0], [100.0, 200.0]],
                }
            ],
            zebra_speed_threshold_kmh=15.0,
            zebra_speed_trend_deadband_kmh=2.0,
        )
        analyzer.zebra_approach_samples[(1, "zebra_1")] = [
            {"speed_kmh": 20.0},
            {"speed_kmh": 21.0},
        ]
        analyzer._update_zebra_events(
            frame_number=3,
            elapsed_seconds=2.0,
            frame_rows=[
                {
                    "object_id": 1,
                    "class": "car",
                    "speed_kmh": 21.0,
                    "_zebra_zone_states": [
                        {"zone_id": "zebra_1", "near": True, "inside": True, "distance_m": 0.0}
                    ],
                },
                {
                    "object_id": 2,
                    "class": "pedestrian",
                    "speed_kmh": 2.0,
                    "is_rider": False,
                    "_zebra_zone_states": [
                        {"zone_id": "zebra_1", "near": True, "inside": True, "distance_m": 0.0}
                    ],
                },
            ],
        )

        self.assertEqual(analyzer.zebra_event_rows[0]["vehicle_speed_trend"], "constant")
        with tempfile.TemporaryDirectory() as tmpdir:
            event_path = Path(tmpdir) / "zebra_events.csv"
            analyzer._write_csv(event_path, analyzer.zebra_event_rows, zebra_event_fieldnames())
            with open(event_path, newline="") as f:
                rows = list(csv.DictReader(f))
        self.assertEqual(rows[0]["vehicle_speed_trend"], "constant")

    def test_rider_filter_excludes_bike_rider_from_zebra_pedestrian_logic(self):
        detector = FakeDetector(
            [
                [
                    {"object_id": 51, "class_name": "motorcycle", "bbox": [120.0, 150.0, 190.0, 205.0], "confidence": 0.95},
                    {"object_id": 52, "class_name": "pedestrian", "bbox": [132.0, 105.0, 178.0, 185.0], "confidence": 0.95},
                    {"object_id": 53, "class_name": "car", "bbox": [20.0, 120.0, 60.0, 170.0], "confidence": 0.95},
                ],
                [
                    {"object_id": 51, "class_name": "motorcycle", "bbox": [120.0, 150.0, 190.0, 205.0], "confidence": 0.95},
                    {"object_id": 52, "class_name": "pedestrian", "bbox": [132.0, 105.0, 178.0, 185.0], "confidence": 0.95},
                    {"object_id": 53, "class_name": "car", "bbox": [75.0, 120.0, 115.0, 170.0], "confidence": 0.95},
                ],
                [
                    {"object_id": 51, "class_name": "motorcycle", "bbox": [120.0, 150.0, 190.0, 205.0], "confidence": 0.95},
                    {"object_id": 52, "class_name": "pedestrian", "bbox": [132.0, 105.0, 178.0, 185.0], "confidence": 0.95},
                    {"object_id": 53, "class_name": "car", "bbox": [140.0, 120.0, 180.0, 170.0], "confidence": 0.95},
                ],
            ]
        )
        zebra_zones = [
            {
                "id": "zebra_1",
                "label": "Z1",
                "category": "zebra_crossing",
                "points": [[100.0, 100.0], [200.0, 100.0], [200.0, 210.0], [100.0, 210.0]],
            }
        ]
        analyzer = TrafficMetricsAnalyzer(
            camera_id="cam_count",
            camera_profile=self._camera_profile(),
            detector=detector,
            counting_lines=self._camera_profile()["counting_lines"],
            zebra_zones=zebra_zones,
            zebra_speed_threshold_kmh=15.0,
        )
        frame = np.zeros((320, 320, 3), dtype=np.uint8)

        analyzer.analyze_frame(frame, 1, 0.0)
        analyzer.analyze_frame(frame, 2, 1.0)
        analyzer.analyze_frame(frame, 3, 2.0)

        self.assertGreater(analyzer.rider_filtered_pedestrians_count, 0)
        self.assertEqual(analyzer.zebra_event_rows, [])
        self.assertEqual(analyzer.zebra_occupancy_rows[-1]["pedestrians_in_zone"], 0)

    def test_counts_crossings_and_speed_metrics_by_class(self):
        detector = FakeDetector(
            [
                [{"object_id": 1, "class_name": "car", "bbox": [60.0, 40.0, 80.0, 80.0], "confidence": 0.95}],
                [{"object_id": 1, "class_name": "car", "bbox": [70.0, 40.0, 90.0, 80.0], "confidence": 0.95}],
                [{"object_id": 1, "class_name": "car", "bbox": [120.0, 40.0, 140.0, 80.0], "confidence": 0.95}],
            ]
        )
        analyzer = TrafficMetricsAnalyzer(
            camera_id="cam_count",
            camera_profile=self._camera_profile(),
            detector=detector,
            counting_lines=self._camera_profile()["counting_lines"],
        )
        frame = np.zeros((240, 320, 3), dtype=np.uint8)

        analyzer.analyze_frame(frame, 1, 0.0)
        analyzer.analyze_frame(frame, 2, 1.0)
        analyzer.analyze_frame(frame, 3, 2.0)
        metrics = analyzer._metric_summary(duration_seconds=3.0)

        self.assertEqual(metrics["total_crossings"], 1)
        self.assertEqual(metrics["counts_by_class"]["car"], 1)
        self.assertIn("car", metrics["speed_metrics_by_class"])
        running_metrics = analyzer._running_speed_metrics_by_class()
        self.assertIn("car", running_metrics)
        self.assertIn("max_speed_kmh", running_metrics["car"])
        self.assertIn("p85_speed_kmh", running_metrics["car"])

    def test_metrics_include_configured_lines_without_crossings(self):
        detector = FakeDetector(
            [
                [{"object_id": 1, "class_name": "car", "bbox": [60.0, 40.0, 80.0, 80.0], "confidence": 0.95}],
                [{"object_id": 1, "class_name": "car", "bbox": [70.0, 40.0, 90.0, 80.0], "confidence": 0.95}],
                [{"object_id": 1, "class_name": "car", "bbox": [120.0, 40.0, 140.0, 80.0], "confidence": 0.95}],
            ]
        )
        secondary_line = {
            **self._camera_profile()["counting_lines"][0],
            "id": "secondary_gate",
            "label": "Secondary Gate",
            "points": [[220.0, 0.0], [220.0, 240.0]],
        }
        analyzer = TrafficMetricsAnalyzer(
            camera_id="cam_count",
            camera_profile=self._camera_profile(),
            detector=detector,
            counting_lines=self._camera_profile()["counting_lines"] + [secondary_line],
        )
        frame = np.zeros((240, 320, 3), dtype=np.uint8)

        analyzer.analyze_frame(frame, 1, 0.0)
        analyzer.analyze_frame(frame, 2, 1.0)
        analyzer.analyze_frame(frame, 3, 2.0)

        self.assertEqual(
            analyzer._metric_summary(duration_seconds=3.0)["counts_by_line"],
            {"main_gate": 1, "secondary_gate": 0},
        )

    def test_analyze_video_writes_outputs_with_fake_detector(self):
        detector = FakeDetector(
            [
                [{"object_id": 1, "class_name": "car", "bbox": [60.0, 40.0, 80.0, 80.0], "confidence": 0.95}],
                [{"object_id": 1, "class_name": "car", "bbox": [70.0, 40.0, 90.0, 80.0], "confidence": 0.95}],
                [{"object_id": 1, "class_name": "car", "bbox": [120.0, 40.0, 140.0, 80.0], "confidence": 0.95}],
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = Path(tmpdir) / "input.mp4"
            writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 1.0, (320, 240))
            for _ in range(3):
                writer.write(np.zeros((240, 320, 3), dtype=np.uint8))
            writer.release()

            output_dir = Path(tmpdir) / "outputs"
            analyzer = TrafficMetricsAnalyzer(
                camera_id="cam_count",
                camera_profile=self._camera_profile(),
                detector=detector,
                counting_lines=self._camera_profile()["counting_lines"],
            )
            progress_updates = []
            summary = analyzer.analyze_video(
                str(video_path),
                str(output_dir),
                progress_callback=lambda processed, total: progress_updates.append((processed, total)),
            )

            self.assertTrue((output_dir / "annotated.mp4").exists())
            self.assertTrue((output_dir / "summary.json").exists())
            self.assertTrue((output_dir / "metrics.json").exists())
            self.assertTrue((output_dir / "crossings.csv").exists())
            self.assertTrue((output_dir / "tracks.csv").exists())
            self.assertTrue((output_dir / "zebra_occupancy.csv").exists())
            with open(output_dir / "metrics.json", "r") as f:
                metrics = json.load(f)
            self.assertEqual(metrics["counts_by_class"]["car"], 1)
            self.assertEqual(summary["metrics"]["total_crossings"], 1)
            self.assertEqual(progress_updates[-1], (3, 3))


class TestSafetyMeasures(unittest.TestCase):
    VEHICLES = frozenset({"car", "bus", "truck", "motorcycle"})
    PEDESTRIANS = frozenset({"pedestrian"})

    def _tracker(self):
        return SafetyMeasuresTracker(
            camera_id="cam",
            vehicle_classes=self.VEHICLES,
            pedestrian_classes=self.PEDESTRIANS,
        )

    @staticmethod
    def _zstate(zone="z1", near=True, inside=False, dist=1.0):
        return {"zone_id": zone, "near": near, "inside": inside, "distance_m": dist}

    def _ped(self, oid, speed, inside):
        return {
            "object_id": oid, "class": "pedestrian", "is_rider": False,
            "speed_kmh": speed, "_zebra_zone_states": [self._zstate(inside=inside)],
        }

    def _veh(self, oid, speed, inside, cls="car"):
        return {
            "object_id": oid, "class": cls, "is_rider": False,
            "speed_kmh": speed, "_zebra_zone_states": [self._zstate(inside=inside)],
        }

    def test_pedestrian_wait_then_cross_episode(self):
        tracker = self._tracker()
        for e in (0.0, 0.5, 1.0):
            tracker.update(e, [self._ped(1, 1.0, inside=False)])  # waiting
        for e in (1.5, 2.0):
            tracker.update(e, [self._ped(1, 4.0, inside=True)])   # crossing
        tracker.update(2.5, [self._ped(1, 4.0, inside=False)])    # exited far side
        tracker.finalize(3.0)

        self.assertEqual(len(tracker.pedestrian_episode_rows), 1)
        episode = tracker.pedestrian_episode_rows[0]
        self.assertEqual(episode["outcome"], "crossed")
        self.assertAlmostEqual(episode["wait_seconds"], 1.5)
        self.assertGreater(episode["crossing_seconds"], 0.0)
        summary = tracker.metric_summary()["pedestrian_episodes"]
        self.assertEqual(summary["completed"], 1)

    def test_vehicle_yields_versus_does_not_yield(self):
        # Yields: decelerates below the yield threshold before entering.
        yielded = self._tracker()
        for e, spd in ((0.0, 30.0), (0.5, 18.0), (1.0, 6.0)):
            yielded.update(e, [self._ped(9, 1.0, inside=False), self._veh(2, spd, inside=False)])
        yielded.finalize(2.0)
        self.assertEqual(yielded.yielding_event_rows[0]["outcome"], "yielded")
        self.assertEqual(yielded.yielding_event_rows[0]["vehicle_class"], "car")

        # Does not yield: enters the zone still travelling fast.
        ran = self._tracker()
        for e, spd, inside in ((0.0, 30.0, False), (0.5, 29.0, False), (1.0, 28.0, True)):
            ran.update(e, [self._ped(9, 1.0, inside=False), self._veh(3, spd, inside=inside)])
        ran.finalize(2.0)
        self.assertEqual(ran.yielding_event_rows[0]["outcome"], "did_not_yield")
        self.assertEqual(ran.metric_summary()["yielding"]["yielding_rate"], 0.0)

    def test_post_encroachment_time(self):
        tracker = self._tracker()
        tracker.update(0.0, [self._ped(5, 4.0, inside=True)])
        tracker.update(0.5, [self._ped(5, 4.0, inside=True)])
        tracker.update(1.0, [self._veh(6, 20.0, inside=False)])   # pedestrian gone -> exit at 1.0
        tracker.update(2.0, [self._veh(6, 20.0, inside=True)])    # vehicle enters 1s later
        tracker.finalize(3.0)

        self.assertEqual(len(tracker.pet_event_rows), 1)
        pet = tracker.pet_event_rows[0]
        self.assertEqual(pet["encroachment_order"], "pedestrian_first")
        self.assertAlmostEqual(pet["pet_seconds"], 1.0)
        self.assertTrue(pet["critical"])
        self.assertEqual(tracker.metric_summary()["post_encroachment"]["critical_events"], 1)

    def test_analyzer_feeds_safety_measures(self):
        # Drives real detections through the analyzer and confirms the tracker
        # was fed (object categories populated) when a zebra zone is present.
        detector = FakeDetector(
            [
                [
                    {"object_id": 51, "class_name": "car", "bbox": [120.0, 120.0, 160.0, 170.0], "confidence": 0.95},
                    {"object_id": 52, "class_name": "pedestrian", "bbox": [140.0, 120.0, 150.0, 180.0], "confidence": 0.95},
                ]
            ]
        )
        zebra_zones = [
            {
                "id": "zebra_1", "label": "Z1", "category": "zebra_crossing",
                "points": [[100.0, 100.0], [200.0, 100.0], [200.0, 200.0], [100.0, 200.0]],
            }
        ]
        analyzer = TrafficMetricsAnalyzer(
            camera_id="cam_count",
            camera_profile=self._camera_profile_with_limit(),
            detector=detector,
            counting_lines=self._camera_profile_with_limit()["counting_lines"],
            zebra_zones=zebra_zones,
        )
        frame = np.zeros((320, 320, 3), dtype=np.uint8)
        analyzer.analyze_frame(frame, 1, 0.0)
        self.assertIn(51, analyzer.safety_measures._object_categories)
        self.assertIn(52, analyzer.safety_measures._object_categories)
        # metric summary block is present and well-formed
        block = analyzer.safety_measures.metric_summary()
        self.assertIn("yielding", block)
        self.assertIn("post_encroachment", block)

    def _camera_profile_with_limit(self):
        return {
            "pixels_per_meter": 10.0,
            "speed_history_size": 2,
            "speed_limit_kmh": 50.0,
            "zones": [],
            "counting_lines": [
                {
                    "id": "main_gate", "label": "Main Gate",
                    "points": [[100.0, 0.0], [100.0, 240.0]], "enabled": True,
                    "classes": ["car", "pedestrian"], "min_crossing_distance_px": 5.0,
                    "reset_distance_px": 8.0, "min_displacement_px": 10.0, "min_observations": 2,
                }
            ],
        }


if __name__ == "__main__":
    unittest.main()
