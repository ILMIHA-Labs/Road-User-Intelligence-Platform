"""Module-level constants and path configuration for the backend API."""
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

logger = logging.getLogger(__name__)


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning("Invalid integer for %s=%r. Falling back to %s.", name, value, default)
        return default


_CAMERAS_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "cameras.yaml"
_LIVE_FRAMES_DIR = Path(os.getenv("LIVE_PREVIEW_DIR", str(Path(__file__).resolve().parents[3] / "artifacts" / "live_frames")))
_LIVE_CLIPS_DIR = Path(os.getenv("LIVE_CLIP_DIR", str(Path(__file__).resolve().parents[3] / "artifacts" / "live_clips")))
_VIOLATION_EVIDENCE_DIR = Path(
    os.getenv(
        "VIOLATION_EVIDENCE_DIR",
        str(Path(__file__).resolve().parents[3] / "artifacts" / "violation_evidence"),
    )
)
_SETUP_PREVIEW_DIR = Path(
    os.getenv(
        "SETUP_PREVIEW_DIR",
        str(Path(__file__).resolve().parents[3] / "artifacts" / "setup_previews"),
    )
)
_EVIDENCE_CAPTURE_ENABLED = _env_flag("EVIDENCE_CAPTURE_ENABLED", False)
_VIOLATION_EVIDENCE_RETENTION_SECONDS = _env_int("VIOLATION_EVIDENCE_RETENTION_SECONDS", 7 * 24 * 60 * 60)
_LIVE_PREVIEW_RETENTION_SECONDS = _env_int("LIVE_PREVIEW_RETENTION_SECONDS", 24 * 60 * 60)
_LIVE_CLIP_RETENTION_SECONDS = _env_int("LIVE_CLIP_RETENTION_SECONDS", 24 * 60 * 60)
_SETUP_PREVIEW_RETENTION_SECONDS = _env_int("SETUP_PREVIEW_RETENTION_SECONDS", 24 * 60 * 60)
_VIDEO_ANALYSIS_DIR = Path(
    os.getenv(
        "VIDEO_ANALYSIS_DIR",
        str(Path(__file__).resolve().parents[3] / "artifacts" / "video_analysis_jobs"),
    )
)
_VIDEO_ANALYSIS_RETENTION_SECONDS = _env_int("VIDEO_ANALYSIS_RETENTION_SECONDS", 24 * 60 * 60)
_VIDEO_ANALYSIS_MAX_UPLOAD_MB = _env_int("VIDEO_ANALYSIS_MAX_UPLOAD_MB", 500)
_VIDEO_ANALYSIS_MAX_CONCURRENT_JOBS = max(1, _env_int("VIDEO_ANALYSIS_MAX_CONCURRENT_JOBS", 1))
_VIDEO_ANALYSIS_ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
_VIDEO_ANALYSIS_ARTIFACTS = {
    "annotated_video": ("annotated.mp4", "video/mp4"),
    "summary_json": ("summary.json", "application/json"),
    "metrics_json": ("metrics.json", "application/json"),
    "crossings_csv": ("crossings.csv", "text/csv"),
    "zebra_events_csv": ("zebra_events.csv", "text/csv"),
    "zebra_occupancy_csv": ("zebra_occupancy.csv", "text/csv"),
    "tracks_csv": ("tracks.csv", "text/csv"),
    "pedestrian_episodes_csv": ("pedestrian_episodes.csv", "text/csv"),
    "yielding_events_csv": ("yielding_events.csv", "text/csv"),
    "pet_events_csv": ("pet_events.csv", "text/csv"),
}
_VIDEO_ANALYSIS_EXECUTOR = ThreadPoolExecutor(max_workers=_VIDEO_ANALYSIS_MAX_CONCURRENT_JOBS)
_CAMERA_DEFAULTS_CACHE: dict = {"path": None, "mtime_ns": None, "defaults": {}}
_RETIRED_VIOLATION_TYPES = ("multiple_riders_violation",)
_RETIRED_CAMERA_CONFIG_FIELDS = {
    "max_motorcycle_riders",
    "rider_association_window_seconds",
    "rider_horizontal_margin_ratio",
    "rider_upper_margin_ratio",
    "rider_lower_margin_ratio",
}
