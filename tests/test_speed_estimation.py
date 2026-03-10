import unittest
import time
from datetime import datetime, timezone
import sys
import os

# Add src to path so we can import internal modules easily
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from speed_estimation.calibration import CameraCalibration
from speed_estimation.speed_calc import SpeedCalculator

class TestSpeedEstimation(unittest.TestCase):
    
    def test_calibration_distance(self):
        calib = CameraCalibration(pixels_per_meter=10.0)
        # 30 pixels right, 40 pixels down = 50 pixel hypotenuse
        # 50 pixels / 10 ppm = 5 meters
        dist = calib.calculate_distance((0,0), (30,40))
        self.assertAlmostEqual(dist, 5.0)

    def test_speed_calculation(self):
        calib = CameraCalibration(pixels_per_meter=20.0)
        calc = SpeedCalculator(calibration=calib, history_size=3)
        
        obj_id = 1
        
        # Frame 1: center=100, bottom=200 -> bbox = (50, 100, 150, 200)
        t1 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat()
        speed1 = calc.update_position(obj_id, t1, [50, 100, 150, 200])
        self.assertIsNone(speed1) # Need >= 2 frames
        
        # Frame 2: Exactly 1 second later. 
        # Moves 100 pixels in X (no Y movement) -> distance = 100 px = 5 meters in 1 second
        # 5 m/s = 18 km/h
        t2 = datetime(2025, 1, 1, 12, 0, 1, tzinfo=timezone.utc).isoformat()
        speed2 = calc.update_position(obj_id, t2, [150, 100, 250, 200])
        
        self.assertIsNotNone(speed2)
        self.assertAlmostEqual(speed2, 18.0)
        
        # Test extreme outlier clipping (moves 20,000 pixels = 1000 meters in 1 sec -> 3600 km/h)
        t3 = datetime(2025, 1, 1, 12, 0, 2, tzinfo=timezone.utc).isoformat()
        speed3 = calc.update_position(obj_id, t3, [20150, 100, 20250, 200])
        self.assertEqual(speed3, 200.0) # Our outlier cap

if __name__ == '__main__':
    unittest.main()
