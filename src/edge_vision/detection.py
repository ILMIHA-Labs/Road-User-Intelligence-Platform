import logging
from typing import Dict, Tuple

import numpy as np
from ultralytics import YOLO
from ultralytics.engine.results import Results

from common.constants import DEFAULT_CONFIDENCE_THRESHOLD, YOLO_CLASSES_OF_INTEREST

logger = logging.getLogger(__name__)


class EdgeDetector:
    """YOLOv8 detection and ByteTrack tracking module."""

    def __init__(self, model_path: str = "yolov8n.pt", conf_thresh: float = DEFAULT_CONFIDENCE_THRESHOLD) -> None:
        self.model_path = model_path
        self.conf_thresh = conf_thresh
        logger.info("Loading YOLOv8 model: %s", self.model_path)
        self.model = YOLO(self.model_path)

    @staticmethod
    def _frame_class_counts(results: Results) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        if results.boxes is None or results.boxes.cls is None:
            return counts
        cls_ids = results.boxes.cls.int().cpu().tolist()
        for cls_id in cls_ids:
            class_name = results.names[int(cls_id)]
            counts[class_name] = counts.get(class_name, 0) + 1
        return counts

    def detect_and_track(self, frame: np.ndarray) -> Tuple[Results, np.ndarray, Dict[str, int]]:
        """Run YOLOv8 tracking (ByteTrack).

        Returns the Results object, annotated frame, and per-class counts.
        """
        tracked = self.model.track(
            source=frame,
            conf=self.conf_thresh,
            persist=True,
            tracker="bytetrack.yaml",
            classes=YOLO_CLASSES_OF_INTEREST,
            verbose=False,
        )
        results = tracked[0]
        annotated_frame: np.ndarray = results.plot()
        counts = self._frame_class_counts(results)
        return results, annotated_frame, counts
