import time
import logging
from collections import deque
from datetime import datetime

logger = logging.getLogger(__name__)

class SpeedCalculator:
    """
    Tracks object positions over time to estimate speed.
    """
    def __init__(self, calibration, history_size=5):
        self.calibration = calibration
        self.history_size = history_size
        # Dictionary mapping object_id to a deque of (timestamp, (x, y)) tuples
        self.tracks = {}

    def update_position(self, object_id, timestamp_iso, bbox):
        """
        Updates the position history of an object and returns its estimated speed.
        """
        # Parse timestamp
        try:
            dt = datetime.fromisoformat(timestamp_iso)
            timestamp_sec = dt.timestamp()
        except Exception as e:
            logger.error(f"Failed to parse timestamp {timestamp_iso}: {e}")
            timestamp_sec = time.time() # Fallback

        # Use the bottom center of the bounding box as the point of contact
        x1, y1, x2, y2 = bbox
        center_x = (x1 + x2) / 2
        bottom_y = y2 
        point = (center_x, bottom_y)

        if object_id not in self.tracks:
            self.tracks[object_id] = deque(maxlen=self.history_size)
            self.tracks[object_id].append((timestamp_sec, point))
            return None # Not enough history

        history = self.tracks[object_id]
        history.append((timestamp_sec, point))

        # We need at least 2 points to calculate speed
        if len(history) < 2:
            return None

        # Calculate speed between the oldest and newest point in the deque to smooth out frame-by-frame jitter
        old_time, old_pt = history[0]
        new_time, new_pt = history[-1]

        time_diff = new_time - old_time
        if time_diff <= 0:
            return None

        distance_meters = self.calibration.calculate_distance(old_pt, new_pt)
        
        # speed = distance / time (m/s)
        speed_mps = distance_meters / time_diff
        
        # Convert to km/h
        speed_kmh = speed_mps * 3.6
        
        # Basic outlier filtering: cap to realistic speeds (e.g., 200 km/h)
        if speed_kmh > 200:
             logger.debug(f"Cap speed outlier for {object_id}: {speed_kmh:.1f} km/h")
             speed_kmh = 200.0

        return speed_kmh

    def clean_old_tracks(self, current_timestamp_sec, max_age=5.0):
        """
        Removes tracks that haven't been updated recently to free memory.
        """
        keys_to_remove = []
        for obj_id, history in self.tracks.items():
            last_updated = history[-1][0]
            if (current_timestamp_sec - last_updated) > max_age:
                keys_to_remove.append(obj_id)
                
        for key in keys_to_remove:
            del self.tracks[key]
