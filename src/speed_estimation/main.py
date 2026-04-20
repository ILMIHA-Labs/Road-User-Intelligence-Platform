import argparse
import logging
import json
import os
import time
import paho.mqtt.client as mqtt

from speed_estimation.calibration import CameraCalibration
from speed_estimation.speed_calc import SpeedCalculator
from common.event_schemas import DetectionEvent, SpeedEvent, dump_event, parse_event_for_topic
from common.camera_config import build_camera_profile_map

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SpeedEstimationAgent")

class SpeedEstimationService:
    def __init__(self, broker_host, broker_port, pixels_per_meter, camera_profiles=None):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.default_pixels_per_meter = pixels_per_meter
        self.camera_profiles = camera_profiles or {}
        self.calculators = {}
        
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        self.in_topic = "camera/detections"
        self.out_topic = "camera/speeds"

    def _get_calculator(self, camera_id):
        calculator = self.calculators.get(camera_id)
        if calculator is not None:
            return calculator

        pixels_per_meter = self.camera_profiles.get(camera_id, {}).get(
            "pixels_per_meter", self.default_pixels_per_meter
        )
        calibration = CameraCalibration(pixels_per_meter=pixels_per_meter)
        calculator = SpeedCalculator(calibration=calibration)
        self.calculators[camera_id] = calculator
        logger.info(
            f"Initialized speed estimator for {camera_id} with {pixels_per_meter} pixels/meter"
        )
        return calculator

    def on_connect(self, client, userdata, connect_flags, reason_code, properties):
        if reason_code == 0:
            logger.info(f"Connected to MQTT Broker at {self.broker_host}:{self.broker_port}")
            self.client.subscribe(self.in_topic)
            logger.info(f"Subscribed to topic: {self.in_topic}")
        else:
            logger.error(f"Failed to connect, return code {reason_code}")

    def on_message(self, client, userdata, msg):
        try:
            detection_event = parse_event_for_topic(msg.topic, msg.payload)
            if not isinstance(detection_event, DetectionEvent):
                return

            calculator = self._get_calculator(detection_event.camera_id)
            speed_kmh = calculator.update_position(
                detection_event.object_id,
                detection_event.timestamp.isoformat(),
                detection_event.bbox,
            )
            
            if speed_kmh is not None:
                speed_event = SpeedEvent(
                    camera_id=detection_event.camera_id,
                    object_id=detection_event.object_id,
                    speed_kmh=round(speed_kmh, 1),
                    timestamp=detection_event.timestamp,
                    source=detection_event.source,
                )

                self.client.publish(self.out_topic, json.dumps(dump_event(speed_event)))
                logger.debug(f"Published speed event: {dump_event(speed_event)}")

            # Periodically clean up old tracks (approx every few seconds based on messages)
            # In a production system, this would be a separate thread or timer
            if int(time.time()) % 10 == 0:
                 for calculator in self.calculators.values():
                     calculator.clean_old_tracks(time.time())

        except json.JSONDecodeError:
            logger.warning("Received invalid JSON on detection topic")
        except ValueError as e:
            logger.warning(f"Received invalid detection event: {e}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")

    def run(self):
        try:
            self.client.connect(self.broker_host, self.broker_port, 60)
            logger.info("Starting MQTT loop...")
            self.client.loop_forever()
        except KeyboardInterrupt:
            logger.info("Stopping Speed Estimation Agent.")
            self.client.disconnect()
        except Exception as e:
            logger.error(f"Agent failed: {e}")

def main():
    parser = argparse.ArgumentParser(description="Speed Estimation Agent")
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
        "--ppm",
        type=float,
        default=float(os.getenv("DEFAULT_PIXELS_PER_METER", "25.0")),
        help="Pixels per meter for MVP calibration",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=os.getenv("CAMERA_CONFIG_PATH", "config/cameras.yaml"),
        help="Path to camera config with per-camera calibration values",
    )
    args = parser.parse_args()

    service = SpeedEstimationService(
        broker_host=args.broker,
        broker_port=args.port,
        pixels_per_meter=args.ppm,
        camera_profiles=build_camera_profile_map(args.config),
    )
    service.run()

if __name__ == "__main__":
    main()
