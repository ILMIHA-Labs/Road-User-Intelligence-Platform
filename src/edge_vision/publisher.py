import paho.mqtt.client as mqtt
import json
import logging
from datetime import datetime, timezone
from common.event_schemas import DetectionEvent, dump_event

logger = logging.getLogger(__name__)

class MQTTPublisher:
    def __init__(self, broker_host="localhost", broker_port=1883, topic="camera/detections"):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.topic = topic
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)

    def connect(self):
        try:
            logger.info(f"Connecting to MQTT broker at {self.broker_host}:{self.broker_port}")
            self.client.connect(self.broker_host, self.broker_port, 60)
            self.client.loop_start()
            return True
        except Exception as e:
            logger.error(f"MQTT connection failed: {e}")
            return False

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()
        logger.info("Disconnected from MQTT broker")

    def publish_detections(self, camera_id, frame_number, results):
        """
        Formats and publishes detection events according to the global schema.
        """
        if results.boxes is None or results.boxes.id is None:
            return 0 # No tracked objects

        names = results.names
        boxes = results.boxes.xyxy.cpu().numpy()
        track_ids = results.boxes.id.int().cpu().numpy()
        confs = results.boxes.conf.cpu().numpy()
        cls_ids = results.boxes.cls.int().cpu().numpy()

        published_count = 0
        current_time = datetime.now(timezone.utc).isoformat()

        for box, track_id, conf, cls_id in zip(boxes, track_ids, confs, cls_ids):
            class_name = names[cls_id]
            
            # Map COCO classes to our platform classes where applicable
            platform_class = class_name
            if class_name == "person":
                platform_class = "pedestrian"
                
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
