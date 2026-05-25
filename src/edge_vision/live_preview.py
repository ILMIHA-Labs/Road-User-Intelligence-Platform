import logging
import os
import time
from collections import defaultdict, deque
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


class RollingEvidenceClipWriter:
    """Persist the latest rolling annotated clip for evidence capture."""

    def __init__(
        self,
        base_dir="artifacts/live_clips",
        clip_duration_seconds=4.0,
        write_interval_seconds=1.0,
        enabled=True,
        fps=10.0,
    ):
        self.base_dir = Path(base_dir)
        self.clip_duration_seconds = max(float(clip_duration_seconds), 1.0)
        self.write_interval_seconds = max(float(write_interval_seconds), 0.25)
        self.enabled = enabled
        self.default_fps = max(float(fps), 1.0)
        self.last_write_by_camera = {}
        self.frames_by_camera = defaultdict(deque)

    def add_frame(self, camera_id, frame, timestamp_seconds=None, fps=None):
        if not self.enabled or frame is None or not camera_id:
            return None

        now = time.time() if timestamp_seconds is None else float(timestamp_seconds)
        frame_copy = frame.copy()
        frames = self.frames_by_camera[camera_id]
        frames.append((now, frame_copy))

        cutoff = now - self.clip_duration_seconds
        while frames and frames[0][0] < cutoff:
            frames.popleft()

        if now - self.last_write_by_camera.get(camera_id, 0.0) < self.write_interval_seconds:
            return None

        return self._write_clip(camera_id, fps or self.default_fps)

    def _write_clip(self, camera_id, fps):
        frames = self.frames_by_camera.get(camera_id)
        if not frames:
            return None

        first_frame = frames[0][1]
        height, width = first_frame.shape[:2]
        camera_dir = self.base_dir / camera_id
        camera_dir.mkdir(parents=True, exist_ok=True)
        output_path = camera_dir / "latest.mp4"
        temp_path = camera_dir / ".latest.tmp.mp4"

        writer = cv2.VideoWriter(
            str(temp_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            max(float(fps), 1.0),
            (width, height),
        )
        if not writer.isOpened():
            logger.warning("Failed to open evidence clip writer for %s", camera_id)
            return None

        try:
            for _, frame in frames:
                if frame.shape[1] != width or frame.shape[0] != height:
                    frame = cv2.resize(frame, (width, height))
                writer.write(frame)
        finally:
            writer.release()

        os.replace(temp_path, output_path)
        self.last_write_by_camera[camera_id] = frames[-1][0]
        return output_path
