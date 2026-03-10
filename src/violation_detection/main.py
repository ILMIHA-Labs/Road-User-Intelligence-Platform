import argparse
import logging
import json
import paho.mqtt.client as mqtt

from violation_rules import ViolationRulesEngine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ViolationDetectionAgent")

class ViolationDetectionService:
    def __init__(self, broker_host, broker_port, speed_limit):
        self.broker_host = broker_host
        self.broker_port = broker_port
        
        self.engine = ViolationRulesEngine(speed_limit_kmh=speed_limit)
        
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        # Subscribe to multiple topics
        self.topics = [("camera/detections", 0), ("camera/speeds", 0)]
        self.out_topic = "camera/violations"

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info(f"Connected to MQTT Broker at {self.broker_host}:{self.broker_port}")
            self.client.subscribe(self.topics)
            logger.info("Subscribed to detection and speed topics")
        else:
            logger.error(f"Failed to connect, return code {rc}")

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode('utf-8'))
            topic = msg.topic
            object_id = payload.get("object_id")
            
            if object_id is None:
                return
                
            # Update internal state representation
            if topic == "camera/detections":
                 self.engine.update_state(object_id, detection_event=payload)
            elif topic == "camera/speeds":
                 self.engine.update_state(object_id, speed_event=payload)

            # Evaluate rules
            violation_events = self.engine.generate_violation_events(object_id)
            
            # Emit violations if any
            for event in violation_events:
                 self.client.publish(self.out_topic, json.dumps(event))
                 logger.warning(f"VIOLATION DETECTED: {event}")

        except json.JSONDecodeError:
            logger.warning("Received invalid JSON")
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
    parser.add_argument("--broker", type=str, default="localhost", help="MQTT broker host")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--speed-limit", type=float, default=60.0, help="Speed limit in km/h for violations")
    args = parser.parse_args()

    service = ViolationDetectionService(
        broker_host=args.broker,
        broker_port=args.port,
        speed_limit=args.speed_limit
    )
    service.run()

if __name__ == "__main__":
    main()
