"""YOLOv8 detector and tracker wrapper."""
import logging
from typing import List

logger = logging.getLogger(__name__)


class YoloTrackDetector:
    def __init__(self, model_path: str = "yolov8l.pt", confidence: float = 0.25):
        from ultralytics import YOLO

        self.model = YOLO(model_path)
        self.confidence = confidence

    def detect(self, frame) -> List[dict]:
        tracked = self.model.track(
            source=frame,
            conf=self.confidence,
            persist=True,
            tracker="bytetrack.yaml",
            classes=[0, 1, 2, 3, 5, 7],
            verbose=False,
        )
        results = tracked[0]
        if results.boxes is None or results.boxes.id is None:
            return []

        observations = []
        for box, track_id, conf, cls_id in zip(
            results.boxes.xyxy.cpu().numpy(),
            results.boxes.id.int().cpu().numpy(),
            results.boxes.conf.cpu().numpy(),
            results.boxes.cls.int().cpu().numpy(),
        ):
            class_name = results.names[int(cls_id)]
            if class_name == "person":
                class_name = "pedestrian"
            observations.append(
                {
                    "object_id": int(track_id),
                    "class_name": class_name,
                    "bbox": [float(value) for value in box],
                    "confidence": float(conf),
                }
            )
        return observations
