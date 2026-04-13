import os
import sys
import tempfile
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from common.camera_config import build_camera_profile_map


class TestCameraConfig(unittest.TestCase):
    def test_camera_profiles_merge_defaults(self):
        config_text = """
defaults:
  pixels_per_meter: 25.0
  speed_limit_kmh: 60.0
cameras:
  - id: cam_a
    pixels_per_meter: 20.0
  - id: cam_b
    speed_limit_kmh: 45.0
"""

        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write(config_text)
            config_path = f.name

        try:
            profiles = build_camera_profile_map(config_path)
        finally:
            os.remove(config_path)

        self.assertEqual(profiles["cam_a"]["pixels_per_meter"], 20.0)
        self.assertEqual(profiles["cam_a"]["speed_limit_kmh"], 60.0)
        self.assertEqual(profiles["cam_b"]["pixels_per_meter"], 25.0)
        self.assertEqual(profiles["cam_b"]["speed_limit_kmh"], 45.0)


if __name__ == "__main__":
    unittest.main()
