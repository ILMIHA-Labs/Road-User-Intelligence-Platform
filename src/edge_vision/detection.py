from ultralytics import YOLO
import logging

logger = logging.getLogger(__name__)

class EdgeDetector:
    """
    YOLOv8 Nano detection and tracking module
    """
    def __init__(self, model_path="yolov8n.pt", conf_thresh=0.25):
        self.model_path = model_path
        self.conf_thresh = conf_thresh
        logger.info(f"Loading YOLOv8 model: {self.model_path}")
        self.model = YOLO(self.model_path)

    def detect_and_track(self, frame):
        """
        Runs YOLOv8 native tracking (ByteTrack).
        Returns the Results object, annotated frame, and per-class counts.
        """
        classes_of_interest = [0, 1, 2, 3, 5, 7]

        results = self.model.track(
            source=frame,
            conf=self.conf_thresh,
            persist=True,
            tracker="bytetrack.yaml",
            classes=classes_of_interest,
            verbose=False
        )

        annotated_frame = results[0].plot()

        # Build class-wise count from boxes
        counts = {}
        if results[0].boxes is not None and len(results[0].boxes):
            for cls_id in results[0].boxes.cls.int().cpu().tolist():
                name = self.model.names[cls_id]
                counts[name] = counts.get(name, 0) + 1

        return results[0], annotated_frame, counts
