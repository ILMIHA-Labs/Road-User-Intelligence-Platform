import json
import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from common.event_schemas import DetectionEvent, SpeedEvent, dump_event, parse_event_for_topic


class TestEventSchemas(unittest.TestCase):
    def test_detection_round_trip_uses_aliases(self):
        event = DetectionEvent(
            camera_id="cam-1",
            timestamp="2025-01-01T12:00:00+00:00",
            object_id=7,
            class_name="motorcycle",
            helmet_status="unknown",
            bbox=[1.0, 2.0, 3.0, 4.0],
            confidence=0.9,
            frame_number=12,
            source="edge",
        )

        payload = dump_event(event)
        self.assertEqual(payload["class"], "motorcycle")
        self.assertNotIn("class_name", payload)

        reparsed = parse_event_for_topic("camera/detections", json.dumps(payload))
        self.assertIsInstance(reparsed, DetectionEvent)
        self.assertEqual(reparsed.class_name, "motorcycle")

    def test_topic_parsing_rejects_unknown_topics(self):
        with self.assertRaises(ValueError):
            parse_event_for_topic("camera/unknown", {})

    def test_speed_event_defaults_source(self):
        event = parse_event_for_topic(
            "camera/speeds",
            {
                "camera_id": "cam-1",
                "object_id": 3,
                "speed_kmh": 44.2,
                "timestamp": "2025-01-01T12:00:01+00:00",
            },
        )
        self.assertIsInstance(event, SpeedEvent)
        self.assertEqual(event.source, "edge")


if __name__ == "__main__":
    unittest.main()
