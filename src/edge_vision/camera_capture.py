import cv2
import logging

logger = logging.getLogger(__name__)

class CameraCapture:
    """
    Handles reading frames from a local edge camera or a video file.
    """
    def __init__(self, source):
        self.source = source
        self.cap = None
        self.frame_count = 0

    def connect(self):
        logger.info(f"Connecting to camera source: {self.source}")
        if str(self.source).isdigit():
            self.source = int(self.source)
        
        self.cap = cv2.VideoCapture(self.source)
        if not self.cap.isOpened():
            logger.error(f"Failed to open source {self.source}")
            return False
        return True

    def read_frame(self):
        if self.cap is None or not self.cap.isOpened():
            return None, 0

        ret, frame = self.cap.read()
        if not ret:
            logger.warning("Failed to read frame or end of stream")
            return None, self.frame_count
            
        self.frame_count += 1
        return frame, self.frame_count

    def release(self):
        if self.cap:
            self.cap.release()
            logger.info("Camera released")
