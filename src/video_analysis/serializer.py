"""CSV/JSON fieldnames and output helpers for analysis results."""
from typing import List


def crossing_fieldnames() -> List[str]:
    return [
        "camera_id", "line_id", "line_label", "object_id", "class",
        "direction", "timestamp", "frame_number", "elapsed_seconds", "source",
    ]


def zebra_event_fieldnames() -> List[str]:
    return [
        "event_type", "camera_id", "frame_number", "elapsed_seconds",
        "zone_id", "vehicle_object_id", "vehicle_class", "vehicle_speed_kmh",
        "vehicle_distance_to_zebra_m", "pedestrian_object_id", "pedestrian_speed_kmh",
        "pedestrian_distance_to_zebra_m", "vehicle_speed_trend",
        "approach_start_speed_kmh", "approach_end_speed_kmh", "approach_delta_kmh",
        "approach_samples", "rider_filtered_pedestrians_count",
    ]


def zebra_occupancy_fieldnames() -> List[str]:
    return [
        "frame_number", "elapsed_seconds", "zone_id", "objects_in_zone",
        "vehicles_in_zone", "pedestrians_in_zone", "bikes_in_zone", "class_counts_json",
    ]


def track_fieldnames() -> List[str]:
    return [
        "frame_number", "elapsed_seconds", "camera_id", "object_id", "class",
        "confidence", "bbox", "speed_kmh", "is_rider", "associated_vehicle_id",
        "zebra_zone_id", "inside_zebra", "near_zebra", "distance_to_zebra_m",
        "inside_zebra_zone_ids", "near_zebra_zone_ids",
    ]
