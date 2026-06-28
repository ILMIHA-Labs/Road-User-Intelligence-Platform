import argparse
import json
import logging
import os
import time

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
    def __init__(
        self,
        broker_host,
        broker_port,
        speed_limit,
        camera_profiles=None,
        speed_tolerance_kmh=0.0,
        severe_speed_delta_kmh=20.0,
        speed_reset_delta_kmh=5.0,
        stopped_speed_threshold_kmh=3.0,
        stopped_duration_seconds=20,
        stopped_resume_speed_kmh=8.0,
        state_ttl_seconds=120,
        stop_line_min_speed_kmh=5.0,
        pedestrian_crossing_min_speed_kmh=5.0,
        pedestrian_crossing_window_seconds=2.0,
        crossing_min_presence_seconds=0.75,
        crossing_min_observations=2,
        crossing_vehicle_min_displacement_px=12.0,
    ):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.default_speed_limit = speed_limit
        self.camera_profiles = camera_profiles or {}
        self.default_speed_tolerance_kmh = speed_tolerance_kmh
        self.default_severe_speed_delta_kmh = severe_speed_delta_kmh
        self.default_speed_reset_delta_kmh = speed_reset_delta_kmh
        self.default_stopped_speed_threshold_kmh = stopped_speed_threshold_kmh
        self.default_stopped_duration_seconds = stopped_duration_seconds
        self.default_stopped_resume_speed_kmh = stopped_resume_speed_kmh
        self.default_state_ttl_seconds = state_ttl_seconds
        self.default_stop_line_min_speed_kmh = stop_line_min_speed_kmh
        self.default_pedestrian_crossing_min_speed_kmh = pedestrian_crossing_min_speed_kmh
        self.default_pedestrian_crossing_window_seconds = pedestrian_crossing_window_seconds
        self.default_crossing_min_presence_seconds = crossing_min_presence_seconds
        self.default_crossing_min_observations = crossing_min_observations
        self.default_crossing_vehicle_min_displacement_px = (
            crossing_vehicle_min_displacement_px
        )
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

        camera_profile = self.camera_profiles.get(camera_id, {})
        speed_limit = camera_profile.get("speed_limit_kmh", self.default_speed_limit)
        speed_tolerance_kmh = camera_profile.get(
            "speed_tolerance_kmh", self.default_speed_tolerance_kmh
        )
        severe_speed_delta_kmh = camera_profile.get(
            "severe_speed_delta_kmh", self.default_severe_speed_delta_kmh
        )
        speed_reset_delta_kmh = camera_profile.get(
            "speed_reset_delta_kmh", self.default_speed_reset_delta_kmh
        )
        stopped_speed_threshold_kmh = camera_profile.get(
            "stopped_speed_threshold_kmh", self.default_stopped_speed_threshold_kmh
        )
        stopped_duration_seconds = camera_profile.get(
            "stopped_duration_seconds", self.default_stopped_duration_seconds
        )
        stopped_resume_speed_kmh = camera_profile.get(
            "stopped_resume_speed_kmh", self.default_stopped_resume_speed_kmh
        )
        state_ttl_seconds = camera_profile.get(
            "state_ttl_seconds", self.default_state_ttl_seconds
        )
        stop_line_min_speed_kmh = camera_profile.get(
            "stop_line_min_speed_kmh", self.default_stop_line_min_speed_kmh
        )
        pedestrian_crossing_min_speed_kmh = camera_profile.get(
            "pedestrian_crossing_min_speed_kmh",
            self.default_pedestrian_crossing_min_speed_kmh,
        )
        pedestrian_crossing_window_seconds = camera_profile.get(
            "pedestrian_crossing_window_seconds",
            self.default_pedestrian_crossing_window_seconds,
        )
        crossing_min_presence_seconds = camera_profile.get(
            "crossing_min_presence_seconds",
            self.default_crossing_min_presence_seconds,
        )
        crossing_min_observations = camera_profile.get(
            "crossing_min_observations",
            self.default_crossing_min_observations,
        )
        crossing_vehicle_min_displacement_px = camera_profile.get(
            "crossing_vehicle_min_displacement_px",
            self.default_crossing_vehicle_min_displacement_px,
        )
        zones = camera_profile.get("zones", [])
        engine = ViolationRulesEngine(
            speed_limit_kmh=speed_limit,
            speed_tolerance_kmh=speed_tolerance_kmh,
            severe_speed_delta_kmh=severe_speed_delta_kmh,
            speed_reset_delta_kmh=speed_reset_delta_kmh,
            stopped_speed_threshold_kmh=stopped_speed_threshold_kmh,
            stopped_duration_seconds=stopped_duration_seconds,
            stopped_resume_speed_kmh=stopped_resume_speed_kmh,
            state_ttl_seconds=state_ttl_seconds,
            zones=zones,
            stop_line_min_speed_kmh=stop_line_min_speed_kmh,
            pedestrian_crossing_min_speed_kmh=pedestrian_crossing_min_speed_kmh,
            pedestrian_crossing_window_seconds=pedestrian_crossing_window_seconds,
            crossing_min_presence_seconds=crossing_min_presence_seconds,
            crossing_min_observations=crossing_min_observations,
            crossing_vehicle_min_displacement_px=crossing_vehicle_min_displacement_px,
        )
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
                 object_ids = engine.get_related_object_ids(event.object_id)
                 camera_id = event.camera_id
            elif topic == "camera/speeds" and isinstance(event, SpeedEvent):
                 engine = self._get_engine(event.camera_id)
                 engine.update_state(event.object_id, speed_event=dump_event(event))
                 object_ids = [event.object_id]
                 camera_id = event.camera_id
            else:
                 return

            # Evaluate rules
            for object_id in object_ids:
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
        retries = 3
        backoff = [2, 4, 8]
        for attempt in range(retries):
            try:
                self.client.connect(self.broker_host, self.broker_port, 60)
                break
            except Exception as e:
                logger.error("MQTT connection failed (attempt %d/%d): %s", attempt + 1, retries, e)
                if attempt < retries - 1:
                    time.sleep(backoff[attempt])
                else:
                    logger.critical(
                        "Could not connect to MQTT broker at %s:%s after %d attempts. Aborting.",
                        self.broker_host, self.broker_port, retries,
                    )
                    return
        try:
            logger.info("Starting MQTT loop for Violation Detection...")
            self.client.loop_forever()
        except KeyboardInterrupt:
            logger.info("Stopping Violation Detection Agent.")
            self.client.disconnect()
        except Exception as e:
            logger.error("Agent failed: %s", e)

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
        "--speed-tolerance",
        type=float,
        default=float(os.getenv("DEFAULT_SPEED_TOLERANCE_KMH", "0.0")),
        help="Extra tolerance added above the speed limit before a speed violation is triggered",
    )
    parser.add_argument(
        "--severe-speed-delta",
        type=float,
        default=float(os.getenv("SEVERE_SPEED_DELTA_KMH", "20.0")),
        help="Additional speed above the threshold that upgrades a violation to severe speeding",
    )
    parser.add_argument(
        "--speed-reset-delta",
        type=float,
        default=float(os.getenv("SPEED_RESET_DELTA_KMH", "5.0")),
        help="How far below the speed threshold an object must drop before it can trigger again",
    )
    parser.add_argument(
        "--state-ttl-seconds",
        type=int,
        default=int(os.getenv("VIOLATION_STATE_TTL_SECONDS", "120")),
        help="How long to retain stale object state before cleanup",
    )
    parser.add_argument(
        "--stopped-speed-threshold",
        type=float,
        default=float(os.getenv("STOPPED_SPEED_THRESHOLD_KMH", "3.0")),
        help="Maximum speed still treated as stationary for stopped-vehicle rules",
    )
    parser.add_argument(
        "--stopped-duration-seconds",
        type=int,
        default=int(os.getenv("STOPPED_DURATION_SECONDS", "20")),
        help="How long a vehicle must remain stopped before triggering a stopped-vehicle violation",
    )
    parser.add_argument(
        "--stopped-resume-speed",
        type=float,
        default=float(os.getenv("STOPPED_RESUME_SPEED_KMH", "8.0")),
        help="Speed above which a stopped-vehicle state resets",
    )
    parser.add_argument(
        "--stop-line-min-speed",
        type=float,
        default=float(os.getenv("STOP_LINE_MIN_SPEED_KMH", "5.0")),
        help="Minimum speed required before entering a configured stop-line zone is treated as a violation",
    )
    parser.add_argument(
        "--pedestrian-crossing-min-speed",
        type=float,
        default=float(os.getenv("PEDESTRIAN_CROSSING_MIN_SPEED_KMH", "5.0")),
        help="Minimum vehicle speed required before entering a pedestrian-crossing zone is treated as a violation",
    )
    parser.add_argument(
        "--pedestrian-crossing-window-seconds",
        type=float,
        default=float(os.getenv("PEDESTRIAN_CROSSING_WINDOW_SECONDS", "2.0")),
        help="Maximum timestamp gap allowed between a pedestrian and vehicle in the same crossing zone",
    )
    parser.add_argument(
        "--crossing-min-presence-seconds",
        type=float,
        default=float(os.getenv("CROSSING_MIN_PRESENCE_SECONDS", "0.75")),
        help="How long a pedestrian must remain in a crossing zone before crossing-related events can trigger",
    )
    parser.add_argument(
        "--crossing-min-observations",
        type=int,
        default=int(os.getenv("CROSSING_MIN_OBSERVATIONS", "2")),
        help="Minimum tracked observations required before crossing-related events can trigger",
    )
    parser.add_argument(
        "--crossing-vehicle-min-displacement-px",
        type=float,
        default=float(os.getenv("CROSSING_VEHICLE_MIN_DISPLACEMENT_PX", "12.0")),
        help="Minimum per-update vehicle movement in pixels before crossing-related events can trigger",
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
        speed_tolerance_kmh=args.speed_tolerance,
        severe_speed_delta_kmh=args.severe_speed_delta,
        speed_reset_delta_kmh=args.speed_reset_delta,
        stopped_speed_threshold_kmh=args.stopped_speed_threshold,
        stopped_duration_seconds=args.stopped_duration_seconds,
        stopped_resume_speed_kmh=args.stopped_resume_speed,
        state_ttl_seconds=args.state_ttl_seconds,
        stop_line_min_speed_kmh=args.stop_line_min_speed,
        pedestrian_crossing_min_speed_kmh=args.pedestrian_crossing_min_speed,
        pedestrian_crossing_window_seconds=args.pedestrian_crossing_window_seconds,
        crossing_min_presence_seconds=args.crossing_min_presence_seconds,
        crossing_min_observations=args.crossing_min_observations,
        crossing_vehicle_min_displacement_px=args.crossing_vehicle_min_displacement_px,
    )
    service.run()

if __name__ == "__main__":
    main()
