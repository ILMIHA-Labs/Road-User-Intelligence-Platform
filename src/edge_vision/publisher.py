import json
import logging
import time
from datetime import datetime, timezone
from typing import List

import paho.mqtt.client as mqtt
from ultralytics.engine.results import Results

from common.event_schemas import CrossingEvent, DetectionEvent, dump_event

logger = logging.getLogger(__name__)

_MQTT_CONNECT_RETRIES = 3
_MQTT_CONNECT_BACKOFF_SECONDS = [2, 4, 8]


class MQTTPublisher:
    def __init__(
        self,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        topic: str = "camera/detections",
        crossing_topic: str = "camera/crossings",
    ) -> None:
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.topic = topic
        self.crossing_topic = crossing_topic
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)

    def connect(self) -> bool:
        for attempt in range(_MQTT_CONNECT_RETRIES):
            try:
                logger.info(
                    "Connecting to MQTT broker at %s:%s (attempt %d/%d)",
                    self.broker_host, self.broker_port, attempt + 1, _MQTT_CONNECT_RETRIES,
                )
                self.client.connect(self.broker_host, self.broker_port, 60)
                self.client.loop_start()
                return True
            except Exception as e:
                logger.error("MQTT connection failed: %s", e)
                if attempt < _MQTT_CONNECT_RETRIES - 1:
                    delay = _MQTT_CONNECT_BACKOFF_SECONDS[attempt]
                    logger.info("Retrying in %s seconds...", delay)
                    time.sleep(delay)
        logger.critical(
            "Could not connect to MQTT broker at %s:%s after %d attempts. Aborting.",
            self.broker_host, self.broker_port, _MQTT_CONNECT_RETRIES,
        )
        return False

    def disconnect(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()
        logger.info("Disconnected from MQTT broker")

    def publish_detections(self, camera_id: str, frame_number: int, results: Results) -> int:
        """Format and publish detection events from a YOLOv8 Results object."""
        if results.boxes is None or results.boxes.id is None:
            return 0

        names = results.names
        boxes = results.boxes.xyxy.cpu().numpy()
        track_ids = results.boxes.id.int().cpu().numpy()
        confs = results.boxes.conf.cpu().numpy()
        cls_ids = results.boxes.cls.int().cpu().numpy()

        published_count = 0
        current_time = datetime.now(timezone.utc).isoformat()

        for box, track_id, conf, cls_id in zip(boxes, track_ids, confs, cls_ids):
            class_name = names[cls_id]
            platform_class = "pedestrian" if class_name == "person" else class_name

            event = DetectionEvent(
                camera_id=camera_id,
                timestamp=current_time,
                object_id=int(track_id),
                class_name=platform_class,
                helmet_status="unknown",
                bbox=[float(c) for c in box],
                confidence=float(conf),
                frame_number=frame_number,
                source="edge",
            )
            self.client.publish(self.topic, json.dumps(dump_event(event)))
            published_count += 1

        return published_count

    def publish_crossings(self, events: List[CrossingEvent]) -> int:
        published_count = 0
        for event in events:
            if not isinstance(event, CrossingEvent):
                continue
            self.client.publish(self.crossing_topic, json.dumps(dump_event(event)))
            published_count += 1
        return published_count
