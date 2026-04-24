import logging
from pathlib import Path
from typing import Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


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
        profiles[camera_id] = merged
    return profiles
