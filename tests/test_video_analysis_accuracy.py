import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from speed_estimation.calibration import CameraCalibration
from speed_estimation.speed_calc import SpeedCalculator

# A 10m x 5m ground rectangle imaged at 20 px/m (pure scale, no offset).
IMAGE_RECT = [[0, 0], [200, 0], [200, 100], [0, 100]]
WORLD_RECT = [[0, 0], [10, 0], [10, 5], [0, 5]]


def _iso(base, seconds):
    return (base + timedelta(seconds=seconds)).isoformat()


class TestCalibration(unittest.TestCase):
    def test_homography_recovers_world_metres(self):
        calib = CameraCalibration.from_homography(IMAGE_RECT, WORLD_RECT)
        self.assertEqual(calib.source, "homography")
        wx, wy = calib.image_to_world(100, 50)
        self.assertAlmostEqual(wx, 5.0, places=3)
        self.assertAlmostEqual(wy, 2.5, places=3)
        self.assertAlmostEqual(calib.calculate_distance([0, 0], [200, 0]), 10.0, places=3)

    def test_from_reference_distance(self):
        calib = CameraCalibration.from_reference_distance([0, 0], [200, 0], 10.0)
        self.assertEqual(calib.source, "reference_distance")
        self.assertAlmostEqual(calib.pixels_per_meter, 20.0)
        self.assertAlmostEqual(calib.calculate_distance([0, 0], [0, 100]), 5.0)

    def test_reference_distance_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            CameraCalibration.from_reference_distance([0, 0], [0, 0], 10.0)
        with self.assertRaises(ValueError):
            CameraCalibration.from_reference_distance([0, 0], [10, 0], 0.0)

    def test_default_emits_warning(self):
        calib = CameraCalibration.default()
        self.assertEqual(calib.source, "scalar_default")
        self.assertTrue(calib.warnings)
        self.assertIn("warnings", calib.describe())

    def test_scalar_back_compat(self):
        calib = CameraCalibration(pixels_per_meter=10.0)
        # 30px right, 40px down = 50px hypotenuse / 10 ppm = 5m
        self.assertAlmostEqual(calib.calculate_distance((0, 0), (30, 40)), 5.0)
        self.assertEqual(calib.describe()["pixels_per_meter"], 10.0)

    def test_from_config_dispatch(self):
        self.assertEqual(
            CameraCalibration.from_config({"image_points": IMAGE_RECT, "world_points_m": WORLD_RECT}).source,
            "homography",
        )
        self.assertEqual(
            CameraCalibration.from_config(
                {"reference": {"image_point_a": [0, 0], "image_point_b": [200, 0], "distance_m": 10}}
            ).source,
            "reference_distance",
        )
        self.assertEqual(CameraCalibration.from_config({"pixels_per_meter": 30}).source, "scalar")
        self.assertEqual(CameraCalibration.from_config({}).source, "scalar_default")
        self.assertEqual(CameraCalibration.from_config(None).source, "scalar_default")

    def test_from_config_invalid_falls_back_with_warning(self):
        calib = CameraCalibration.from_config({"image_points": [[0, 0]], "world_points_m": [[0, 0]]})
        self.assertEqual(calib.source, "scalar_default")
        self.assertTrue(any("Invalid calibration" in w for w in calib.warnings))


class TestRobustSpeed(unittest.TestCase):
    def setUp(self):
        self.calib = CameraCalibration(pixels_per_meter=20.0)
        self.base = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    def _run(self, calc, steps):
        # steps: list of (seconds, center_x); bbox is 100px wide, bottom at 200.
        speed = None
        for seconds, cx in steps:
            speed = calc.update_position(1, _iso(self.base, seconds), [cx - 50, 100, cx + 50, 200])
        return speed

    def test_regression_recovers_constant_velocity(self):
        # 100 px/s at 20 px/m = 5 m/s = 18 km/h.
        calc = SpeedCalculator(self.calib, history_size=5, velocity_method="regression", smoothing_alpha=1.0)
        speed = self._run(calc, [(i, 100 + 100 * i) for i in range(5)])
        self.assertAlmostEqual(speed, 18.0, places=1)

    def test_median_recovers_constant_velocity(self):
        calc = SpeedCalculator(self.calib, history_size=5, velocity_method="median", smoothing_alpha=1.0)
        speed = self._run(calc, [(i, 100 + 100 * i) for i in range(5)])
        self.assertAlmostEqual(speed, 18.0, places=1)

    def test_teleport_is_rejected(self):
        calc = SpeedCalculator(
            self.calib, history_size=5, velocity_method="endpoint",
            smoothing_alpha=1.0, outlier_mode="cap", teleport_reject=True, max_speed_kmh=200.0,
        )
        calc.update_position(1, _iso(self.base, 0), [50, 100, 150, 200])
        good = calc.update_position(1, _iso(self.base, 1), [150, 100, 250, 200])  # 18 km/h
        self.assertAlmostEqual(good, 18.0, places=1)
        # Huge jump in one frame -> ID-switch/teleport -> keep previous, don't spike.
        after = calc.update_position(1, _iso(self.base, 2), [20150, 100, 20250, 200])
        self.assertAlmostEqual(after, 18.0, places=1)
        # History stayed clean: a normal step still reads ~18 km/h.
        nxt = calc.update_position(1, _iso(self.base, 3), [250, 100, 350, 200])
        self.assertLess(nxt, 40.0)

    def test_ema_smoothing_dampens_jitter(self):
        calc = SpeedCalculator(self.calib, history_size=2, velocity_method="endpoint", smoothing_alpha=0.5)
        calc.update_position(1, _iso(self.base, 0), [50, 100, 150, 200])
        first = calc.update_position(1, _iso(self.base, 1), [150, 100, 250, 200])  # 18 km/h
        # Next step is faster (200px/s = 36 km/h); EMA(0.5) pulls it toward 18.
        second = calc.update_position(1, _iso(self.base, 2), [350, 100, 450, 200])
        self.assertLess(second, 36.0)
        self.assertGreater(second, first)

    def test_defaults_match_legacy_behaviour(self):
        # Default outlier_mode="cap", no teleport reject -> spike is capped, not dropped.
        calc = SpeedCalculator(self.calib, history_size=3, max_speed_kmh=200.0)
        calc.update_position(1, _iso(self.base, 0), [50, 100, 150, 200])
        calc.update_position(1, _iso(self.base, 1), [150, 100, 250, 200])
        spike = calc.update_position(1, _iso(self.base, 2), [20150, 100, 20250, 200])
        self.assertEqual(spike, 200.0)


if __name__ == "__main__":
    unittest.main()
