import unittest
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from violation_detection.violation_rules import ViolationRulesEngine
from violation_detection.main import ViolationDetectionService

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

if __name__ == '__main__':
    unittest.main()
