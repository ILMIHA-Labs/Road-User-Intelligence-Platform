import argparse
import json
import logging
import os
import threading
import time
from collections import defaultdict

import paho.mqtt.client as mqtt
import requests

from common.event_schemas import dump_event, parse_event_for_topic

logger = logging.getLogger(__name__)

_BATCH_INTERVAL_SECONDS = float(os.getenv("FORWARDER_BATCH_INTERVAL_SECONDS", "0.1"))
_MQTT_CONNECT_RETRIES = 3
_MQTT_CONNECT_BACKOFF = [2, 4, 8]


class MQTTForwarder:
    """
    Subscribes to all platform MQTT topics and forwards events to the Backend API.
    Events are buffered for FORWARDER_BATCH_INTERVAL_SECONDS (default 100 ms) and
    sent as JSON arrays to reduce per-event HTTP overhead at high frame rates.
    """

    def __init__(self, broker_host, broker_port, api_url):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.api_url = api_url.rstrip("/")

        # Maps MQTT topic → API endpoint suffix
        self.topic_map = {
            "camera/detections": "/detections",
            "camera/speeds": "/speeds",
            "camera/violations": "/violations",
            "camera/crossings": "/crossings",
            "camera/trajectories": "/trajectories",
        }

        # Pending events keyed by endpoint, drained by the flush thread
        self._buffer: dict[str, list] = defaultdict(list)
        self._buffer_lock = threading.Lock()
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)

        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    # ------------------------------------------------------------------
    # MQTT callbacks
    # ------------------------------------------------------------------

    def on_connect(self, client, userdata, connect_flags, reason_code, properties):
        if reason_code == 0:
            logger.info("Connected to MQTT broker at %s:%s", self.broker_host, self.broker_port)
            topics = [(topic, 0) for topic in self.topic_map]
            self.client.subscribe(topics)
            logger.info("Subscribed to: %s", list(self.topic_map))
        else:
            logger.error("MQTT connect failed, reason code %s", reason_code)

    def on_message(self, client, userdata, msg):
        topic = msg.topic
        endpoint = self.topic_map.get(topic)
        if not endpoint:
            return
        try:
            event = parse_event_for_topic(topic, msg.payload)
            with self._buffer_lock:
                self._buffer[endpoint].append(dump_event(event))
        except json.JSONDecodeError:
            logger.warning("Invalid JSON on topic %s", topic)
        except ValueError as e:
            logger.warning("Invalid event on topic %s: %s", topic, e)
        except Exception as e:
            logger.error("Error buffering message from %s: %s", topic, e)
            return
        self._flush_all()

    # ------------------------------------------------------------------
    # Batch flush
    # ------------------------------------------------------------------

    def _flush_loop(self):
        while True:
            time.sleep(_BATCH_INTERVAL_SECONDS)
            self._flush_all()

    def _flush_all(self):
        with self._buffer_lock:
            snapshot = {ep: events for ep, events in self._buffer.items() if events}
            self._buffer.clear()

        for endpoint, events in snapshot.items():
            self._post_batch(endpoint, events)

    def _post_batch(self, endpoint: str, events: list):
        target_url = f"{self.api_url}{endpoint}/batch"
        try:
            response = requests.post(target_url, json=events, timeout=5.0)
            if response.status_code not in (200, 201, 207):
                logger.error(
                    "Batch POST to %s returned %s — falling back to individual POSTs",
                    target_url, response.status_code,
                )
                self._post_individually(endpoint, events)
        except requests.exceptions.RequestException as e:
            logger.error("Batch POST to %s failed: %s — falling back to individual POSTs", target_url, e)
            self._post_individually(endpoint, events)

    def _post_individually(self, endpoint: str, events: list):
        target_url = f"{self.api_url}{endpoint}"
        for event in events:
            try:
                response = requests.post(target_url, json=event, timeout=2.0)
                if response.status_code != 201:
                    logger.error("POST to %s failed: %s %s", target_url, response.status_code, response.text)
            except requests.exceptions.RequestException as e:
                logger.error("POST to %s failed: %s", target_url, e)

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self):
        for attempt in range(_MQTT_CONNECT_RETRIES):
            try:
                self.client.connect(self.broker_host, self.broker_port, 60)
                break
            except Exception as e:
                logger.error(
                    "MQTT connection failed (attempt %d/%d): %s",
                    attempt + 1, _MQTT_CONNECT_RETRIES, e,
                )
                if attempt < _MQTT_CONNECT_RETRIES - 1:
                    time.sleep(_MQTT_CONNECT_BACKOFF[attempt])
                else:
                    logger.critical(
                        "Could not connect to MQTT broker at %s:%s after %d attempts. Aborting.",
                        self.broker_host, self.broker_port, _MQTT_CONNECT_RETRIES,
                    )
                    return

        self._flush_thread.start()
        try:
            logger.info("Starting MQTT Forwarder loop (batch interval: %.0f ms)...", _BATCH_INTERVAL_SECONDS * 1000)
            self.client.loop_forever()
        except KeyboardInterrupt:
            logger.info("Stopping Data Streaming Agent.")
            self._flush_all()
            self.client.disconnect()
        except Exception as e:
            logger.error("Agent failed: %s", e)


def main():
    parser = argparse.ArgumentParser(description="Data Streaming Agent")
    parser.add_argument("--broker", type=str, default=os.getenv("MQTT_BROKER_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MQTT_BROKER_PORT", "1883")))
    parser.add_argument("--api", type=str, default=os.getenv("BACKEND_API_URL", "http://localhost:8000"))
    args = parser.parse_args()

    forwarder = MQTTForwarder(
        broker_host=args.broker,
        broker_port=args.port,
        api_url=args.api,
    )
    forwarder.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    main()
