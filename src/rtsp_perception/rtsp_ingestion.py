import cv2
import time
import logging

logger = logging.getLogger(__name__)

class RTSPIngestion:
    """
    Handles connecting to an RTSP stream, decoding frames, 
    and managing reconnections or frame skipping for performance.
    """
    def __init__(self, camera_config):
        self.camera_id = camera_config.get("id")
        self.url = camera_config.get("url")
        self.location = camera_config.get("location", "unknown")
        # Target FPS processing rate (to save compute)
        self.target_fps = camera_config.get("target_fps", 10) 
        
        self.cap = None
        self.frame_count = 0
        self.last_frame_time = 0

    def connect(self):
        logger.info(f"Connecting to RTSP stream {self.camera_id} at {self.url}")
        self.cap = cv2.VideoCapture(self.url)
        # Using FFMPEG backend is typical for RTSP
        if not self.cap.isOpened():
            logger.error(f"Failed to open RTSP stream for {self.camera_id}")
            return False
        return True

    def read_frame(self):
        """
        Reads a frame from the stream.
        Implements frame skipping to adhere roughly to target_fps.
        """
        if self.cap is None or not self.cap.isOpened():
            # Try reconnecting
            logger.warning(f"Reconnecting to {self.camera_id}...")
            if not self.connect():
                time.sleep(2)
                return None, 0

        # Read frames as fast as possible to clear the buffer
        # But only return a frame when it's time according to target_fps
        ret, frame = self.cap.read()
        
        if not ret:
            logger.error(f"Stream interrupted for {self.camera_id}")
            self.cap.release()
            return None, self.frame_count
            
        current_time = time.time()
        time_elapsed = current_time - self.last_frame_time
        
        # Skip frames to match target FPS
        if time_elapsed < (1.0 / self.target_fps):
            return None, self.frame_count # Skip frame
            
        self.last_frame_time = current_time
        self.frame_count += 1
        
        return frame, self.frame_count

    def release(self):
        if self.cap:
            self.cap.release()
            logger.info(f"RTSP stream {self.camera_id} released")
