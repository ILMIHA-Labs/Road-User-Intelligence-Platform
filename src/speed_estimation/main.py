import argparse
import logging
import json
import time
from datetime import datetime
import paho.mqtt.client as mqtt

from calibration import CameraCalibration
from speed_calc import SpeedCalculator

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SpeedEstimationAgent")

class SpeedEstimationService:
    def __init__(self, broker_host, broker_port, pixels_per_meter):
        self.broker_host = broker_host
        self.broker_port = broker_port
        
        self.calibration = CameraCalibration(pixels_per_meter=pixels_per_meter)
        self.calculator = SpeedCalculator(calibration=self.calibration)
        
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        self.in_topic = "camera/detections"
        self.out_topic = "camera/speeds"

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info(f"Connected to MQTT Broker at {self.broker_host}:{self.broker_port}")
            self.client.subscribe(self.in_topic)
            logger.info(f"Subscribed to topic: {self.in_topic}")
        else:
            logger.error(f"Failed to connect, return code {rc}")

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode('utf-8'))
            
            camera_id = payload.get("camera_id")
            object_id = payload.get("object_id")
            timestamp = payload.get("timestamp")
            bbox = payload.get("bbox")
            source = payload.get("source", "unknown")
            
            if None in (camera_id, object_id, timestamp, bbox):
                # Ignore invalid events
                return

            speed_kmh = self.calculator.update_position(object_id, timestamp, bbox)
            
            if speed_kmh is not None:
                # Generate speed event
                speed_event = {
                    "camera_id": camera_id,
                    "object_id": object_id,
                    "speed_kmh": round(speed_kmh, 1),
                    "timestamp": timestamp,
                    "source": source
                }
                
                # Publish event
                self.client.publish(self.out_topic, json.dumps(speed_event))
                logger.debug(f"Published speed event: {speed_event}")

            # Periodically clean up old tracks (approx every few seconds based on messages)
            # In a production system, this would be a separate thread or timer
            if int(time.time()) % 10 == 0:
                 self.calculator.clean_old_tracks(time.time())

        except json.JSONDecodeError:
            logger.warning("Received invalid JSON on detection topic")
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
    parser.add_argument("--broker", type=str, default="localhost", help="MQTT broker host")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--ppm", type=float, default=25.0, help="Pixels per meter for MVP calibration")
    args = parser.parse_args()

    service = SpeedEstimationService(
        broker_host=args.broker,
        broker_port=args.port,
        pixels_per_meter=args.ppm
    )
    service.run()

if __name__ == "__main__":
    main()
