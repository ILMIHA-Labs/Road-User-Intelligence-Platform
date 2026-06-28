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
