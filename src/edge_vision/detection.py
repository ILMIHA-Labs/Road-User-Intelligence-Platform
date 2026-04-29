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

    @staticmethod
    def _frame_class_counts(results):
        counts = {}
        if results.boxes is None or results.boxes.cls is None:
            return counts

        cls_ids = results.boxes.cls.int().cpu().tolist()
        for cls_id in cls_ids:
            class_name = results.names[int(cls_id)]
            counts[class_name] = counts.get(class_name, 0) + 1
        return counts

    def detect_and_track(self, frame):
        """
        Runs YOLOv8 native tracking (ByteTrack).
        Returns the Results object, annotated frame, and per-class counts.
        """
        classes_of_interest = [0, 1, 2, 3, 5, 7]
        tracked = self.model.track(
            source=frame,
            conf=self.conf_thresh,
            persist=True,
            tracker="bytetrack.yaml",
            classes=classes_of_interest,
            verbose=False
        )

        results = tracked[0]
        annotated_frame = results.plot()
        counts = self._frame_class_counts(results)
        return results, annotated_frame, counts
