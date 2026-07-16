# Detection
DEFAULT_CONFIDENCE_THRESHOLD: float = 0.25
YOLO_CLASSES_OF_INTEREST: list[int] = [0, 1, 2, 3, 5, 7]  # person, bicycle, car, motorcycle, bus, truck

# Speed estimation
DEFAULT_MAX_SPEED_KMH: float = 200.0

# Violation detection — time windows and thresholds
STOPPED_SPEED_THRESHOLD_KMH: float = 3.0
PEDESTRIAN_CROSSING_WINDOW_SECONDS: float = 2.0
CROSSING_MIN_PRESENCE_SECONDS: float = 0.75
CROSSING_VEHICLE_MIN_DISPLACEMENT_PX: float = 12.0

# Crossing-safety research measures
# A pedestrian moving at or below this speed near a crossing is treated as
# waiting at the kerb.
PEDESTRIAN_WAITING_SPEED_KMH: float = 3.0
# A vehicle whose approach speed drops to or below this is treated as having
# yielded to a waiting pedestrian.
YIELD_SPEED_THRESHOLD_KMH: float = 8.0
# Maximum gap between one road user leaving a crossing and the next entering
# it for the pair to count as a post-encroachment-time (PET) conflict.
PET_WINDOW_SECONDS: float = 5.0
# PET below this threshold is considered a critical near-miss.
PET_CRITICAL_SECONDS: float = 1.5

# Alerting and camera-health monitoring
# Minimum seconds between two alerts sharing the same dedup key.
ALERT_DEBOUNCE_SECONDS: float = 60.0
# A camera with no recorded activity for longer than this is treated as
# having gone offline.
CAMERA_OFFLINE_AFTER_SECONDS: float = 60.0
# How often the background monitor re-checks camera health.
CAMERA_HEALTH_POLL_SECONDS: float = 30.0
