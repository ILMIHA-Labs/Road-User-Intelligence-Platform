import argparse
import logging
import json
import os
import paho.mqtt.client as mqtt

from violation_detection.violation_rules import ViolationRulesEngine
from common.camera_config import build_camera_profile_map
from common.event_schemas import (
    DetectionEvent,
    SpeedEvent,
    ViolationEvent,
    dump_event,
    parse_event_for_topic,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ViolationDetectionAgent")

class ViolationDetectionService:
    def __init__(self, broker_host, broker_port, speed_limit, camera_profiles=None):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.default_speed_limit = speed_limit
        self.camera_profiles = camera_profiles or {}
        self.engines = {}
        
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        # Subscribe to multiple topics
        self.topics = [("camera/detections", 0), ("camera/speeds", 0)]
        self.out_topic = "camera/violations"

    def _get_engine(self, camera_id):
        engine = self.engines.get(camera_id)
        if engine is not None:
            return engine

        speed_limit = self.camera_profiles.get(camera_id, {}).get(
            "speed_limit_kmh", self.default_speed_limit
        )
        engine = ViolationRulesEngine(speed_limit_kmh=speed_limit)
        self.engines[camera_id] = engine
        logger.info(
            f"Initialized violation rules for {camera_id} with speed limit {speed_limit} km/h"
        )
        return engine

    def on_connect(self, client, userdata, connect_flags, reason_code, properties):
        if reason_code == 0:
            logger.info(f"Connected to MQTT Broker at {self.broker_host}:{self.broker_port}")
            self.client.subscribe(self.topics)
            logger.info("Subscribed to detection and speed topics")
        else:
            logger.error(f"Failed to connect, return code {reason_code}")

    def on_message(self, client, userdata, msg):
        try:
            topic = msg.topic
            event = parse_event_for_topic(topic, msg.payload)
                
            # Update internal state representation
            if topic == "camera/detections" and isinstance(event, DetectionEvent):
                 engine = self._get_engine(event.camera_id)
                 engine.update_state(event.object_id, detection_event=dump_event(event))
                 object_id = event.object_id
                 camera_id = event.camera_id
            elif topic == "camera/speeds" and isinstance(event, SpeedEvent):
                 engine = self._get_engine(event.camera_id)
                 engine.update_state(event.object_id, speed_event=dump_event(event))
                 object_id = event.object_id
                 camera_id = event.camera_id
            else:
                 return

            # Evaluate rules
            violation_events = self.engines[camera_id].generate_violation_events(object_id)
            
            # Emit violations if any
            for event in violation_events:
                 payload = dump_event(event)
                 self.client.publish(self.out_topic, json.dumps(payload))
                 logger.warning(f"VIOLATION DETECTED: {payload}")

        except json.JSONDecodeError:
            logger.warning("Received invalid JSON")
        except ValueError as e:
            logger.warning(f"Received invalid event: {e}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")

    def run(self):
        try:
            self.client.connect(self.broker_host, self.broker_port, 60)
            logger.info("Starting MQTT loop for Violation Detection...")
            self.client.loop_forever()
        except KeyboardInterrupt:
            logger.info("Stopping Violation Detection Agent.")
            self.client.disconnect()
        except Exception as e:
            logger.error(f"Agent failed: {e}")

def main():
    parser = argparse.ArgumentParser(description="Violation Detection Agent")
    parser.add_argument(
        "--broker",
        type=str,
        default=os.getenv("MQTT_BROKER_HOST", "localhost"),
        help="MQTT broker host",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MQTT_BROKER_PORT", "1883")),
        help="MQTT broker port",
    )
    parser.add_argument(
        "--speed-limit",
        type=float,
        default=float(os.getenv("DEFAULT_SPEED_LIMIT_KMH", "60.0")),
        help="Speed limit in km/h for violations",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=os.getenv("CAMERA_CONFIG_PATH", "config/cameras.yaml"),
        help="Path to camera config with per-camera rule thresholds",
    )
    args = parser.parse_args()

    service = ViolationDetectionService(
        broker_host=args.broker,
        broker_port=args.port,
        speed_limit=args.speed_limit,
        camera_profiles=build_camera_profile_map(args.config),
    )
    service.run()

if __name__ == "__main__":
    main()
