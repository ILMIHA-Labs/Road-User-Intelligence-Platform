import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
import yaml

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from video_analysis.zebra_compliance import (
    TrackObservation,
    ZebraComplianceAnalyzer,
    build_drawn_setup_config,
    load_calibration,
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


class TestZebraComplianceAnalysis(unittest.TestCase):
    def _camera_profile(self):
        return {
            "speed_history_size": 2,
            "speed_max_kmh": 200.0,
            "zones": [
                {
                    "id": "zebra_demo",
                    "label": "Zebra Demo",
                    "category": "zebra_crossing",
                    "points": [[100.0, 100.0], [200.0, 100.0], [200.0, 200.0], [100.0, 200.0]],
                }
            ],
        }

    def test_load_calibration_derives_pixels_per_meter(self):
        config = {
            "camera_id": "cam_a",
            "reference_segments": [
                {
                    "id": "zebra_width",
                    "image_points": [[10, 10], [110, 10]],
                    "real_distance_m": 5.0,
                }
            ],
            "zebra_zones": [
                {
                    "id": "drawn_zebra",
                    "points": [[0, 0], [10, 0], [10, 10], [0, 10]],
                }
            ],
        }

        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            yaml.safe_dump(config, f)
            config_path = f.name

        try:
            calibration = load_calibration(config_path, "cam_a")
        finally:
            os.remove(config_path)

        self.assertEqual(calibration.pixels_per_meter, 20.0)
        self.assertEqual(calibration.source, "reference_segment:zebra_width")
        self.assertEqual(calibration.zebra_zones[0]["id"], "drawn_zebra")

    def test_build_drawn_setup_config(self):
        config = build_drawn_setup_config(
            camera_id="cam_drawn",
            zebra_points=[[10, 10], [110, 10], [110, 60], [10, 60]],
            reference_points=[[10, 10], [110, 10]],
            real_distance_m=5.0,
        )

        self.assertEqual(config["camera_id"], "cam_drawn")
        self.assertEqual(config["zebra_zones"][0]["category"], "zebra_crossing")
        self.assertEqual(config["reference_segments"][0]["real_distance_m"], 5.0)

    def test_yielding_risk_and_violation_events_from_synthetic_tracks(self):
        calibration = type(
            "Calibration",
            (),
            {
                "camera_id": "cam_zebra",
                "pixels_per_meter": 10.0,
                "source": "test",
                "reference_segments": [],
                "approach_speed_threshold_kmh": 15.0,
                "pedestrian_speed_threshold_kmh": 8.0,
                "interaction_window_seconds": 3.0,
                "approach_distance_m": 12.0,
                "pedestrian_near_distance_m": 2.0,
                "zebra_zones": [],
            },
        )()
        detector = FakeDetector(
            [
                [
                    TrackObservation(1, "car", [20.0, 120.0, 60.0, 170.0], 0.95),
                    TrackObservation(2, "pedestrian", [130.0, 120.0, 150.0, 180.0], 0.96),
                ],
                [
                    TrackObservation(1, "car", [70.0, 120.0, 110.0, 170.0], 0.95),
                    TrackObservation(2, "pedestrian", [130.0, 120.0, 150.0, 180.0], 0.96),
                ],
                [
                    TrackObservation(1, "car", [140.0, 120.0, 180.0, 170.0], 0.95),
                    TrackObservation(2, "pedestrian", [130.0, 120.0, 150.0, 180.0], 0.96),
                ],
            ]
        )
        analyzer = ZebraComplianceAnalyzer(
            camera_id="cam_zebra",
            camera_profile=self._camera_profile(),
            calibration=calibration,
            detector=detector,
        )
        frame = np.zeros((240, 320, 3), dtype=np.uint8)

        analyzer.analyze_frame(frame, 1, 0.0)
        analyzer.analyze_frame(frame, 2, 1.0)
        analyzer.analyze_frame(frame, 3, 2.0)

        event_types = [event["event_type"] for event in analyzer.events]
        self.assertIn("zebra_yielding_risk", event_types)
        self.assertIn("zebra_crossing_violation", event_types)

    def test_analyze_video_writes_expected_artifacts_with_fake_detector(self):
        calibration = type(
            "Calibration",
            (),
            {
                "camera_id": "cam_zebra",
                "pixels_per_meter": 10.0,
                "source": "test",
                "reference_segments": [],
                "approach_speed_threshold_kmh": 15.0,
                "pedestrian_speed_threshold_kmh": 8.0,
                "interaction_window_seconds": 3.0,
                "approach_distance_m": 12.0,
                "pedestrian_near_distance_m": 2.0,
                "zebra_zones": [],
            },
        )()
        detector = FakeDetector(
            [
                [
                    TrackObservation(1, "car", [20.0, 120.0, 60.0, 170.0], 0.95),
                    TrackObservation(2, "pedestrian", [130.0, 120.0, 150.0, 180.0], 0.96),
                ],
                [
                    TrackObservation(1, "car", [70.0, 120.0, 110.0, 170.0], 0.95),
                    TrackObservation(2, "pedestrian", [130.0, 120.0, 150.0, 180.0], 0.96),
                ],
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = Path(tmpdir) / "input.mp4"
            writer = cv2.VideoWriter(
                str(video_path),
                cv2.VideoWriter_fourcc(*"mp4v"),
                1.0,
                (320, 240),
            )
            writer.write(np.zeros((240, 320, 3), dtype=np.uint8))
            writer.write(np.zeros((240, 320, 3), dtype=np.uint8))
            writer.release()

            output_dir = Path(tmpdir) / "outputs"
            analyzer = ZebraComplianceAnalyzer(
                camera_id="cam_zebra",
                camera_profile=self._camera_profile(),
                calibration=calibration,
                detector=detector,
            )
            summary = analyzer.analyze_video(str(video_path), str(output_dir))

            self.assertTrue((output_dir / "annotated.mp4").exists())
            self.assertTrue((output_dir / "events.csv").exists())
            self.assertTrue((output_dir / "tracks.csv").exists())
            self.assertTrue((output_dir / "summary.json").exists())
            with open(output_dir / "summary.json", "r") as f:
                disk_summary = json.load(f)
            self.assertEqual(disk_summary["aggregate_counts"]["objects_seen"], 2)
            self.assertEqual(summary["aggregate_counts"]["objects_seen"], 2)


if __name__ == "__main__":
    unittest.main()
