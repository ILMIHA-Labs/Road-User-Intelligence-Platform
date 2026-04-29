import argparse
import logging
import json
import os
import requests
import paho.mqtt.client as mqtt
from common.event_schemas import dump_event, parse_event_for_topic

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DataStreamingAgent")

class MQTTForwarder:
    """
    Subscribes to all platform MQTT topics and forwards valid events 
    to the Backend API via authenticated HTTP POST requests.
    """
    def __init__(self, broker_host, broker_port, api_url):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.api_url = api_url.rstrip("/")
        
        # Maps MQTT topic to API endpoint suffix
        self.topic_map = {
            "camera/detections": "/detections",
            "camera/speeds": "/speeds",
            "camera/violations": "/violations",
            "camera/crossings": "/crossings",
            "camera/trajectories": "/trajectories"
        }
        
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, connect_flags, reason_code, properties):
        if reason_code == 0:
            logger.info(f"Connected to MQTT Broker at {self.broker_host}:{self.broker_port}")
            # Subscribe to all required topics
            topics = [(topic, 0) for topic in self.topic_map.keys()]
            self.client.subscribe(topics)
            logger.info(f"Subscribed to: {list(self.topic_map.keys())}")
        else:
            logger.error(f"Failed to connect, return code {reason_code}")

    def on_message(self, client, userdata, msg):
        topic = msg.topic
        endpoint = self.topic_map.get(topic)
        if not endpoint:
            # We received a message on a topic we aren't configured to forward
            return
            
        try:
            event = parse_event_for_topic(topic, msg.payload)
            
            # Forward the payload to the backend HTTP service
            target_url = f"{self.api_url}{endpoint}"
            
            # In MVP, firing an HTTP POST per message can create overhead
            # A stronger implementation would buffer and batch
            response = requests.post(target_url, json=dump_event(event), timeout=2.0)
            
            if response.status_code == 201:
                # Successfully inserted into database
                pass
            else:
                logger.error(f"Failed to forward event to {target_url}: {response.status_code} {response.text}")
                
        except json.JSONDecodeError:
            logger.warning(f"Received invalid JSON on topic {topic}")
        except ValueError as e:
            logger.warning(f"Received invalid event on topic {topic}: {e}")
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP request to backend failed: {e}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")

    def run(self):
        try:
            self.client.connect(self.broker_host, self.broker_port, 60)
            logger.info("Starting MQTT Forwarder loop...")
            self.client.loop_forever()
        except KeyboardInterrupt:
            logger.info("Stopping Data Streaming Agent.")
            self.client.disconnect()
        except Exception as e:
            logger.error(f"Agent failed: {e}")

def main():
    parser = argparse.ArgumentParser(description="Data Streaming Agent")
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
        "--api",
        type=str,
        default=os.getenv("BACKEND_API_URL", "http://localhost:8000"),
        help="Backend API base URL",
    )
    args = parser.parse_args()

    forwarder = MQTTForwarder(
        broker_host=args.broker,
        broker_port=args.port,
        api_url=args.api
    )
    forwarder.run()

if __name__ == "__main__":
    main()
