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
        profiles[camera_id] = {
            **defaults,
            **camera,
        }
    return profiles
