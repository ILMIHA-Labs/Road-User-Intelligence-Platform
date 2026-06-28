import logging
import threading
import time
from collections import deque
from datetime import datetime

from common.constants import DEFAULT_MAX_SPEED_KMH

logger = logging.getLogger(__name__)

class SpeedCalculator:
    """
    Tracks object positions over time to estimate speed.
    """
    def __init__(
        self,
        calibration,
        history_size=5,
        max_speed_kmh=DEFAULT_MAX_SPEED_KMH,
        min_time_delta_seconds=0.0,
        smoothing_alpha=1.0,
        outlier_mode="cap",
    ):
        self.calibration = calibration
        self.history_size = history_size
        self.max_speed_kmh = max_speed_kmh
        self.min_time_delta_seconds = min_time_delta_seconds
        self.smoothing_alpha = smoothing_alpha
        self.outlier_mode = outlier_mode
        self._lock = threading.Lock()
        # Dictionary mapping object_id to a deque of (timestamp, (x, y)) tuples
        self.tracks = {}
        self.last_speeds = {}

    def update_position(self, object_id, timestamp_iso, bbox):
        """
        Updates the position history of an object and returns its estimated speed.
        """
        # Parse timestamp
        try:
            dt = datetime.fromisoformat(timestamp_iso)
            timestamp_sec = dt.timestamp()
        except Exception as e:
            logger.error("Failed to parse timestamp %s: %s", timestamp_iso, e)
            timestamp_sec = time.time()

        x1, y1, x2, y2 = bbox
        center_x = (x1 + x2) / 2
        bottom_y = y2
        point = (center_x, bottom_y)

        with self._lock:
            if object_id not in self.tracks:
                self.tracks[object_id] = deque(maxlen=self.history_size)
                self.tracks[object_id].append((timestamp_sec, point))
                return None

            history = self.tracks[object_id]
            history.append((timestamp_sec, point))

            if len(history) < 2:
                return None

            old_time, old_pt = history[0]
            new_time, new_pt = history[-1]

            time_diff = new_time - old_time
            if time_diff <= self.min_time_delta_seconds:
                return None

            distance_meters = self.calibration.calculate_distance(old_pt, new_pt)
            speed_mps = distance_meters / time_diff
            speed_kmh = speed_mps * 3.6

            if speed_kmh > self.max_speed_kmh:
                logger.debug("Speed outlier for %s: %.1f km/h", object_id, speed_kmh)
                if self.outlier_mode == "ignore":
                    return None
                speed_kmh = self.max_speed_kmh

            previous_speed = self.last_speeds.get(object_id)
            if previous_speed is not None and self.smoothing_alpha < 1.0:
                speed_kmh = (self.smoothing_alpha * speed_kmh) + ((1.0 - self.smoothing_alpha) * previous_speed)
            self.last_speeds[object_id] = speed_kmh

        return speed_kmh

    def clean_old_tracks(self, current_timestamp_sec, max_age=5.0):
        """
        Removes tracks that haven't been updated recently to free memory.
        """
        with self._lock:
            keys_to_remove = [
                obj_id for obj_id, history in self.tracks.items()
                if (current_timestamp_sec - history[-1][0]) > max_age
            ]
            for key in keys_to_remove:
                del self.tracks[key]
                self.last_speeds.pop(key, None)
