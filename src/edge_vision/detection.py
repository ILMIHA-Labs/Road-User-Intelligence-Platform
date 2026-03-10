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
        
        # Initialize Object Counter
        # Default counting line across the middle of a typical 1080p frame
        self.counter = object_counter.ObjectCounter(
            show=False,
            region=[(0, 500), (1920, 500)],
            classes=self.model.names
        )
        
    def detect_and_track(self, frame):
        """
        Runs YOLOv8 native tracking (ByteTrack by default on ultralytics).
        Returns the Ultralytics Results object.
        """
        # We only want classes like person(0), bicycle(1), car(2), motorcycle(3), bus(5), truck(7)
        # For MVP, we'll track those.
        classes_of_interest = [0, 1, 2, 3, 5, 7]
        
        results = self.model.track(
            source=frame,
            conf=self.conf_thresh,
            persist=True,  # Keeps track history
            tracker="bytetrack.yaml", # Native byte track
            classes=classes_of_interest,
            verbose=False
        )
        
        # Pass the tracked frame to the counter
        annotated_frame = self.counter.start_counting(frame, results[0])
        
        return results[0], annotated_frame, self.counter.class_wise_count
