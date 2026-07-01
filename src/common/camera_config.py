import logging
from typing import Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

DEFAULT_COUNTING_LINE_CLASSES = ["car", "motorcycle", "bus", "truck", "pedestrian", "bicycle"]


def load_camera_config(config_path: str) -> dict:
    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Error loading camera config from {config_path}: {e}")
        return {}


def load_cameras(config_path: str) -> List[dict]:
    return load_camera_config(config_path).get("cameras", [])


def normalize_zone_definitions(zones: Optional[List[dict]]) -> List[dict]:
    normalized = []
    for index, zone in enumerate(zones or []):
        if not isinstance(zone, dict):
            continue
        points = []
        for point in zone.get("points", []):
            if (
                isinstance(point, (list, tuple))
                and len(point) == 2
                and all(isinstance(value, (int, float)) for value in point)
            ):
                points.append([float(point[0]), float(point[1])])
        if len(points) < 3:
            continue
        zone_id = zone.get("id") or f"zone_{index + 1}"
        normalized.append(
            {
                "id": zone_id,
                "label": zone.get("label", zone_id.replace("_", " ").title()),
                "type": zone.get("type", "polygon"),
                "category": zone.get("category", "custom"),
                "points": points,
            }
        )
    return normalized


def normalize_counting_line_definitions(lines: Optional[List[dict]]) -> List[dict]:
    normalized = []
    for index, line in enumerate(lines or []):
        if not isinstance(line, dict):
            continue
        points = []
        for point in line.get("points", []):
            if (
                isinstance(point, (list, tuple))
                and len(point) == 2
                and all(isinstance(value, (int, float)) for value in point)
            ):
                points.append([float(point[0]), float(point[1])])
        if len(points) != 2:
            continue

        line_id = line.get("id") or f"count_line_{index + 1}"
        classes = line.get("classes") or DEFAULT_COUNTING_LINE_CLASSES
        normalized_classes = [
            value for value in classes
            if isinstance(value, str) and value.strip()
        ] or list(DEFAULT_COUNTING_LINE_CLASSES)
        normalized.append(
            {
                "id": line_id,
                "label": line.get("label", line_id.replace("_", " ").title()),
                "points": points,
                "enabled": bool(line.get("enabled", True)),
                "classes": normalized_classes,
                "min_crossing_distance_px": float(line.get("min_crossing_distance_px", 8.0)),
                "reset_distance_px": float(line.get("reset_distance_px", 12.0)),
                "min_displacement_px": float(line.get("min_displacement_px", 12.0)),
                "min_observations": max(2, int(line.get("min_observations", 2))),
            }
        )
    return normalized


def build_camera_profile_map(config_path: Optional[str]) -> Dict[str, dict]:
    if not config_path:
        return {}

    config = load_camera_config(config_path)
    defaults = config.get("defaults", {})
    cameras = config.get("cameras", [])

    profiles = {}
    for camera in cameras:
        camera_id = camera.get("id")
        if not camera_id:
            continue
        merged = {
            **defaults,
            **camera,
        }
        merged["zones"] = normalize_zone_definitions(merged.get("zones"))
        merged["counting_lines"] = normalize_counting_line_definitions(merged.get("counting_lines"))
        profiles[camera_id] = merged
    return profiles
