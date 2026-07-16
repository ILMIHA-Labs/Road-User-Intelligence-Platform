import os
import sys
import unittest

import numpy as np

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from common import redaction as R


class TestRegionGeometry(unittest.TestCase):
    def test_face_region_is_upper_portion(self):
        self.assertEqual(R.face_region([10, 10, 50, 110]), (10, 10, 50, 50))

    def test_plate_region_is_lower_central(self):
        # 100x100 box: bottom 35% high, 20% side margins.
        self.assertEqual(R.plate_region([0, 0, 100, 100]), (20, 65, 80, 100))

    def test_invalid_boxes_return_none(self):
        self.assertIsNone(R.face_region([1, 2, 3]))
        self.assertIsNone(R.plate_region([50, 50, 10, 10]))  # inverted


class TestRedactFrame(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(0)
        self.image = rng.integers(0, 255, (120, 120, 3)).astype(np.uint8)

    def test_person_face_is_blurred_background_untouched(self):
        before = self.image.copy()
        R.redact_frame(self.image, [("pedestrian", [10, 10, 50, 110])], R.RedactionConfig(enabled=True))
        fx1, fy1, fx2, fy2 = R.face_region([10, 10, 50, 110])
        self.assertFalse(np.array_equal(before[fy1:fy2, fx1:fx2], self.image[fy1:fy2, fx1:fx2]))
        self.assertTrue(np.array_equal(before[0:5, 60:65], self.image[0:5, 60:65]))

    def test_vehicle_plate_is_pixelated(self):
        before = self.image.copy()
        R.redact_frame(self.image, [("car", [0, 0, 100, 100])], R.RedactionConfig(enabled=True, method="pixelate", strength=8))
        px1, py1, px2, py2 = R.plate_region([0, 0, 100, 100])
        self.assertFalse(np.array_equal(before[py1:py2, px1:px2], self.image[py1:py2, px1:px2]))

    def test_disabled_is_noop(self):
        before = self.image.copy()
        R.redact_frame(self.image, [("pedestrian", [10, 10, 50, 110])], R.RedactionConfig(enabled=False))
        self.assertTrue(np.array_equal(before, self.image))

    def test_faces_only_leaves_vehicle_plate_untouched(self):
        before = self.image.copy()
        cfg = R.RedactionConfig(enabled=True, redact_faces=True, redact_plates=False)
        R.redact_frame(self.image, [("car", [0, 0, 100, 100])], cfg)
        self.assertTrue(np.array_equal(before, self.image))


class TestSuppression(unittest.TestCase):
    def test_suppress_value(self):
        self.assertIsNone(R.suppress_value(3, 5))
        self.assertEqual(R.suppress_value(5, 5), 5)
        self.assertEqual(R.suppress_value(0, 5), 0)
        self.assertEqual(R.suppress_value(3, 0), 3)  # k<2 disables

    def test_suppress_map_and_list(self):
        self.assertEqual(R.suppress_small_counts({"a": 1, "b": 5, "c": 0}, 5), {"a": None, "b": 5, "c": 0})
        self.assertEqual(R.suppress_small_counts_list([0, 1, 4, 5], 5), [0, None, None, 5])

    def test_disabled_returns_copy_unchanged(self):
        self.assertEqual(R.suppress_small_counts({"a": 1}, 0), {"a": 1})
        self.assertEqual(R.suppress_small_counts_list([1, 2], 1), [1, 2])


if __name__ == "__main__":
    unittest.main()
