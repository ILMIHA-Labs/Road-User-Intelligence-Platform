from ultralytics import YOLO
from ultralytics.solutions import object_counter
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

        # Initialize Object Counter if available in this Ultralytics version.
        # API has changed across versions; runtime compatibility is handled in detect_and_track.
        self.counter = None
        try:
            # Default counting line across the middle of a typical 1080p frame
            self.counter = object_counter.ObjectCounter(
                show=False,
                region=[(0, 500), (1920, 500)],
                classes=self.model.names
            )
        except Exception as e:
            logger.warning(f"ObjectCounter unavailable, continuing without counting: {e}")

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
        Runs YOLOv8 native tracking (ByteTrack by default on ultralytics).
        Returns the Ultralytics Results object.
        """
        # We only want classes like person(0), bicycle(1), car(2), motorcycle(3), bus(5), truck(7)
        # For MVP, we'll track those.
        classes_of_interest = [0, 1, 2, 3, 5, 7]
        
        tracked = self.model.track(
            source=frame,
            conf=self.conf_thresh,
            persist=True,  # Keeps track history
            tracker="bytetrack.yaml", # Native byte track
            classes=classes_of_interest,
            verbose=False
        )

        results = tracked[0]
        annotated_frame = results.plot()
        counts = self._frame_class_counts(results)

        # Try ObjectCounter only when available; preserve pipeline if API differs.
        if self.counter is not None:
            try:
                if hasattr(self.counter, "start_counting"):
                    annotated_frame = self.counter.start_counting(frame, results)
                    if hasattr(self.counter, "class_wise_count"):
                        counts = self.counter.class_wise_count
                    elif hasattr(self.counter, "classwise_count"):
                        counts = self.counter.classwise_count
                elif hasattr(self.counter, "process"):
                    counter_result = self.counter.process(frame)
                    if hasattr(counter_result, "plot_im") and counter_result.plot_im is not None:
                        annotated_frame = counter_result.plot_im
                    if hasattr(counter_result, "classwise_count"):
                        counts = counter_result.classwise_count
            except Exception as e:
                logger.warning(
                    f"ObjectCounter disabled after runtime failure, using detector-only overlays: {e}"
                )
                self.counter = None

        return results, annotated_frame, counts
