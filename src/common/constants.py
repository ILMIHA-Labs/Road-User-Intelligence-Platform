# Detection
DEFAULT_CONFIDENCE_THRESHOLD: float = 0.25
YOLO_CLASSES_OF_INTEREST: list[int] = [0, 1, 2, 3, 5, 7]  # person, bicycle, car, motorcycle, bus, truck

# Speed estimation
DEFAULT_MAX_SPEED_KMH: float = 200.0
# Arbitrary fallback scale used only when no real calibration is provided.
# Perspective-blind, so speeds/distances derived from it are approximate.
DEFAULT_PIXELS_PER_METER: float = 25.0
# Default exponential-moving-average factor for pipeline speed smoothing
# (1.0 = no smoothing). Lower = smoother/laggier.
DEFAULT_SPEED_SMOOTHING_ALPHA: float = 0.5
# A per-frame displacement implying a speed this many times the max plausible
# speed is treated as a tracker ID-switch/teleport and rejected.
SPEED_TELEPORT_REJECT_FACTOR: float = 1.5

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

# Privacy redaction (heuristic face/plate blurring on stored imagery)
# Fraction of a person box height, measured from the top, treated as the face.
FACE_REGION_HEIGHT_RATIO: float = 0.4
# Fraction of a vehicle box height, measured from the bottom, treated as the
# plate region, and the horizontal margin trimmed from each side.
PLATE_REGION_HEIGHT_RATIO: float = 0.35
PLATE_REGION_SIDE_MARGIN_RATIO: float = 0.2
# Blur strength: Gaussian kernel size (forced odd) or pixelation block factor.
REDACTION_STRENGTH: int = 25
