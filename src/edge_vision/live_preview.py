import logging
import os
import time
import json
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
        self._codec_by_camera = {}

    def add_frame(self, camera_id, frame, timestamp_seconds=None, fps=None, frame_number=None):
        if not self.enabled or frame is None or not camera_id:
            return None

        now = time.time() if timestamp_seconds is None else float(timestamp_seconds)
        frame_copy = frame.copy()
        frames = self.frames_by_camera[camera_id]
        frames.append((now, frame_number, frame_copy))

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

        first_frame = frames[0][2]
        height, width = first_frame.shape[:2]
        camera_dir = self.base_dir / camera_id
        camera_dir.mkdir(parents=True, exist_ok=True)
        output_path = camera_dir / "latest.mp4"
        temp_path = camera_dir / ".latest.tmp.mp4"
        manifest_path = camera_dir / "latest.json"
        temp_manifest_path = camera_dir / ".latest.tmp.json"
        end_timestamp = frames[-1][0]
        clip_stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime(end_timestamp))
        clip_millis = int((end_timestamp % 1) * 1000)
        window_output_path = camera_dir / f"clip_{clip_stamp}{clip_millis:03d}.mp4"
        window_temp_path = camera_dir / f".clip_{clip_stamp}{clip_millis:03d}.tmp.mp4"
        window_manifest_path = camera_dir / f"clip_{clip_stamp}{clip_millis:03d}.json"
        window_temp_manifest_path = camera_dir / f".clip_{clip_stamp}{clip_millis:03d}.tmp.json"

        def open_writer(path):
            codec = self._codec_by_camera.get(camera_id)
            writer = None
            if codec is not None:
                writer = cv2.VideoWriter(
                    str(path),
                    cv2.VideoWriter_fourcc(*codec),
                    max(float(fps), 1.0),
                    (width, height),
                )
                if not writer.isOpened():
                    writer.release()
                    writer = None
                    self._codec_by_camera.pop(camera_id, None)

            if writer is None:
                for candidate in ("avc1", "H264", "mp4v"):
                    candidate_writer = cv2.VideoWriter(
                        str(path),
                        cv2.VideoWriter_fourcc(*candidate),
                        max(float(fps), 1.0),
                        (width, height),
                    )
                    if candidate_writer.isOpened():
                        writer = candidate_writer
                        self._codec_by_camera[camera_id] = candidate
                        logger.info("Using %s codec for rolling evidence clips on %s", candidate, camera_id)
                        break
                    candidate_writer.release()
            return writer

        writer = open_writer(temp_path)
        window_writer = open_writer(window_temp_path)
        if window_writer is None and writer is not None:
            writer.release()
            writer = None

        if writer is None or not writer.isOpened() or window_writer is None or not window_writer.isOpened():
            logger.warning("Failed to open evidence clip writer for %s", camera_id)
            return None

        try:
            manifest_entries = []
            for ts, frame_number, frame in frames:
                if frame.shape[1] != width or frame.shape[0] != height:
                    frame = cv2.resize(frame, (width, height))
                writer.write(frame)
                window_writer.write(frame)
                manifest_entries.append(
                    {
                        "timestamp_seconds": ts,
                        "frame_number": frame_number,
                    }
                )
        finally:
            writer.release()
            window_writer.release()

        os.replace(temp_path, output_path)
        temp_manifest_path.write_text(json.dumps(manifest_entries), encoding="utf-8")
        os.replace(temp_manifest_path, manifest_path)
        os.replace(window_temp_path, window_output_path)
        window_temp_manifest_path.write_text(json.dumps(manifest_entries), encoding="utf-8")
        os.replace(window_temp_manifest_path, window_manifest_path)
        self.last_write_by_camera[camera_id] = frames[-1][0]
        return output_path
