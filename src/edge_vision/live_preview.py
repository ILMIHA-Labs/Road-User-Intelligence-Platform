import logging
import os
import time
from pathlib import Path

import cv2

logger = logging.getLogger(__name__)


class LivePreviewWriter:
    """Persist the latest annotated frame for dashboard preview."""

    def __init__(self, base_dir="artifacts/live_frames", interval_seconds=1.0, enabled=True):
        self.base_dir = Path(base_dir)
        self.interval_seconds = max(float(interval_seconds), 0.1)
        self.enabled = enabled
        self.last_write_by_camera = {}

    def write_frame(self, camera_id, frame):
        if not self.enabled or frame is None or not camera_id:
            return None

        now = time.time()
        if now - self.last_write_by_camera.get(camera_id, 0.0) < self.interval_seconds:
            return None

        camera_dir = self.base_dir / camera_id
        camera_dir.mkdir(parents=True, exist_ok=True)
        output_path = camera_dir / "latest.jpg"
        temp_path = camera_dir / ".latest.tmp.jpg"

        ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if not ok:
            logger.warning("Failed to encode live preview frame for %s", camera_id)
            return None

        temp_path.write_bytes(encoded.tobytes())
        os.replace(temp_path, output_path)
        self.last_write_by_camera[camera_id] = now
        return output_path
