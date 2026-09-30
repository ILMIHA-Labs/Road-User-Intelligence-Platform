import logging
import threading
import time
from collections import deque
from datetime import datetime
from statistics import median

from common.constants import DEFAULT_MAX_SPEED_KMH, SPEED_TELEPORT_REJECT_FACTOR

logger = logging.getLogger(__name__)


class SpeedCalculator:
    """Tracks object positions over time to estimate speed.

    Defaults reproduce the original behaviour (endpoint difference over the
    window, no smoothing, outliers capped) so existing callers are unchanged.
    The video-analysis pipeline opts into the robust settings:
    ``velocity_method="regression"`` (or ``"median"``), EMA smoothing,
    ``outlier_mode="ignore"`` and ``teleport_reject=True``.
    """

    def __init__(
        self,
        calibration,
        history_size=5,
        max_speed_kmh=DEFAULT_MAX_SPEED_KMH,
        min_time_delta_seconds=0.0,
        smoothing_alpha=1.0,
        outlier_mode="cap",
        velocity_method="endpoint",
        teleport_reject=False,
        teleport_factor=SPEED_TELEPORT_REJECT_FACTOR,
    ):
        self.calibration = calibration
        self.history_size = history_size
        self.max_speed_kmh = max_speed_kmh
        self.min_time_delta_seconds = min_time_delta_seconds
        self.smoothing_alpha = smoothing_alpha
        self.outlier_mode = outlier_mode
        self.velocity_method = velocity_method
        self.teleport_reject = teleport_reject
        self.teleport_factor = teleport_factor
        self._lock = threading.Lock()
        # object_id -> deque of (timestamp_sec, (x, y)) tuples
        self.tracks = {}
        self.last_speeds = {}

    def update_position(self, object_id, timestamp_iso, bbox):
        """Update an object's position history and return its estimated speed."""
        try:
            timestamp_sec = datetime.fromisoformat(timestamp_iso).timestamp()
        except Exception as e:  # noqa: BLE001 - defensive: fall back to wall clock
            logger.error("Failed to parse timestamp %s: %s", timestamp_iso, e)
            timestamp_sec = time.time()

        x1, y1, x2, y2 = bbox
        # Ground-contact point (bottom centre) is the most stable anchor for
        # ground-plane motion.
        point = ((x1 + x2) / 2, y2)

        with self._lock:
            if object_id not in self.tracks:
                self.tracks[object_id] = deque(maxlen=self.history_size)
                self.tracks[object_id].append((timestamp_sec, point))
                return None

            history = self.tracks[object_id]

            # Reject an ID-switch/teleport: a single step implying an impossible
            # speed usually means the tracker reused this id for a new object.
            if self.teleport_reject and history:
                prev_time, prev_point = history[-1]
                step_dt = timestamp_sec - prev_time
                if step_dt > 0:
                    step_speed = (self.calibration.calculate_distance(prev_point, point) / step_dt) * 3.6
                    if step_speed > self.max_speed_kmh * self.teleport_factor:
                        logger.debug("Rejecting teleport for %s: %.1f km/h", object_id, step_speed)
                        return self.last_speeds.get(object_id)

            history.append((timestamp_sec, point))
            if len(history) < 2:
                return None

            old_time, _ = history[0]
            new_time, _ = history[-1]
            time_diff = new_time - old_time
            if time_diff <= self.min_time_delta_seconds:
                return None

            speed_kmh = self._estimate_speed_kmh(history, time_diff)
            if speed_kmh is None:
                return None

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

    def _estimate_speed_kmh(self, history, time_diff):
        """Estimate speed (km/h) from the position window per ``velocity_method``."""
        if self.velocity_method == "median":
            pairwise = []
            for (t0, p0), (t1, p1) in zip(history, list(history)[1:]):
                dt = t1 - t0
                if dt > 0:
                    pairwise.append(self.calibration.calculate_distance(p0, p1) / dt)
            if not pairwise:
                return None
            return median(pairwise) * 3.6

        if self.velocity_method == "regression":
            speed_mps = self._regression_speed_mps(history)
            if speed_mps is not None:
                return speed_mps * 3.6
            # Fall through to endpoint if regression is degenerate.

        # Endpoint (default): distance between oldest and newest sample.
        _, old_pt = history[0]
        _, new_pt = history[-1]
        return (self.calibration.calculate_distance(old_pt, new_pt) / time_diff) * 3.6

    def _regression_speed_mps(self, history):
        """Least-squares velocity magnitude over the window in world metres."""
        times = [t for t, _ in history]
        world = [self.calibration.image_to_world(px, py) for _, (px, py) in history]
        n = len(times)
        if n < 2:
            return None
        t0 = times[0]
        ts = [t - t0 for t in times]
        mean_t = sum(ts) / n
        var_t = sum((t - mean_t) ** 2 for t in ts)
        if var_t <= 0:
            return None
        mean_x = sum(w[0] for w in world) / n
        mean_y = sum(w[1] for w in world) / n
        slope_x = sum((ts[i] - mean_t) * (world[i][0] - mean_x) for i in range(n)) / var_t
        slope_y = sum((ts[i] - mean_t) * (world[i][1] - mean_y) for i in range(n)) / var_t
        return (slope_x ** 2 + slope_y ** 2) ** 0.5

    def clean_old_tracks(self, current_timestamp_sec, max_age=5.0):
        """Remove tracks not updated recently to free memory."""
        with self._lock:
            keys_to_remove = [
                obj_id for obj_id, history in self.tracks.items()
                if (current_timestamp_sec - history[-1][0]) > max_age
            ]
            for key in keys_to_remove:
                del self.tracks[key]
                self.last_speeds.pop(key, None)
