import asyncio
import csv
import json
import logging
import math
import os
import shutil
from io import StringIO
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

import cv2
import yaml
from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import func, case
from sqlalchemy.orm import Session
from starlette.responses import FileResponse, StreamingResponse
from starlette.staticfiles import StaticFiles

from . import models, schemas
from .database import engine, get_db, init_db, SessionLocal
from common.camera_config import normalize_counting_line_definitions, normalize_zone_definitions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BackendAPI")

app = FastAPI(title="Road User Intelligence Platform API")


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

_CAMERAS_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "cameras.yaml"
_LIVE_FRAMES_DIR = Path(os.getenv("LIVE_PREVIEW_DIR", str(Path(__file__).resolve().parents[2] / "artifacts" / "live_frames")))
_VIOLATION_EVIDENCE_DIR = Path(
    os.getenv(
        "VIOLATION_EVIDENCE_DIR",
        str(Path(__file__).resolve().parents[2] / "artifacts" / "violation_evidence"),
    )
)
_SETUP_PREVIEW_DIR = Path(
    os.getenv(
        "SETUP_PREVIEW_DIR",
        str(Path(__file__).resolve().parents[2] / "artifacts" / "setup_previews"),
    )
)
_EVIDENCE_CAPTURE_ENABLED = _env_flag("EVIDENCE_CAPTURE_ENABLED", False)
_VIOLATION_EVIDENCE_RETENTION_SECONDS = _env_int("VIOLATION_EVIDENCE_RETENTION_SECONDS", 7 * 24 * 60 * 60)
_LIVE_PREVIEW_RETENTION_SECONDS = _env_int("LIVE_PREVIEW_RETENTION_SECONDS", 24 * 60 * 60)
_SETUP_PREVIEW_RETENTION_SECONDS = _env_int("SETUP_PREVIEW_RETENTION_SECONDS", 24 * 60 * 60)

dashboard_dir = Path(__file__).resolve().parents[1] / "dashboard" / "app"
if dashboard_dir.exists():
    app.mount("/dashboard", StaticFiles(directory=dashboard_dir, html=True), name="dashboard")

@app.on_event("startup")
def startup_event():
    init_db()
    _cleanup_runtime_artifacts()

@app.get("/")
def read_root():
    return {"status": "MVP API is running"}


class SetupPreviewRequest(BaseModel):
    source: str
    camera_id: Optional[str] = None


class SetupCountingLineInput(BaseModel):
    id: Optional[str] = None
    label: Optional[str] = None
    points: List[List[float]]


class SetupZebraZoneInput(BaseModel):
    id: Optional[str] = None
    label: Optional[str] = None
    points: List[List[float]]


class CameraSetupSaveRequest(BaseModel):
    camera_id: str
    source: str
    location: Optional[str] = ""
    target_fps: Optional[int] = None
    pixels_per_meter: Optional[float] = None
    speed_limit_kmh: Optional[float] = None
    live_feed_type: Optional[str] = None
    live_feed_url: Optional[str] = None
    preview_image_url: Optional[str] = None
    preview_frame_width: Optional[int] = None
    preview_frame_height: Optional[int] = None
    counting_lines: List[SetupCountingLineInput] = Field(default_factory=list)
    zebra_zones: List[SetupZebraZoneInput] = Field(default_factory=list)


class ViolationReviewUpdateRequest(BaseModel):
    review_status: str
    review_notes: Optional[str] = ""


@app.get("/cameras/config")
def get_cameras_config():
    """Return merged camera profiles from cameras.yaml (defaults + per-camera overrides)."""
    try:
        with open(_CAMERAS_CONFIG_PATH, "r") as f:
            raw = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {"defaults": {}, "cameras": []}
    defaults = raw.get("defaults", {})
    cameras = raw.get("cameras", [])
    merged = []
    for cam in cameras:
        profile = {**defaults, **cam}
        profile["zones"] = normalize_zone_definitions(profile.get("zones"))
        profile["counting_lines"] = normalize_counting_line_definitions(profile.get("counting_lines"))
        merged.append(profile)
    return {"defaults": defaults, "cameras": merged}


@app.post("/setup/preview-frame")
def create_setup_preview(request: SetupPreviewRequest):
    camera_id = _sanitize_camera_id(request.camera_id or Path(request.source).stem or "camera_setup")
    frame, resolved_source = _extract_preview_frame(request.source)
    preview_path = _setup_preview_path(camera_id)
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(preview_path), frame):
        raise HTTPException(status_code=500, detail="Failed to write preview frame")

    height, width = frame.shape[:2]
    return {
        "camera_id": camera_id,
        "source": request.source,
        "resolved_source": resolved_source,
        "preview_url": f"/setup/previews/{camera_id}/frame",
        "width": int(width),
        "height": int(height),
    }


@app.get("/setup/previews/{camera_id}/frame")
def get_setup_preview(camera_id: str):
    preview_path = _setup_preview_path(camera_id)
    if not preview_path.exists():
        raise HTTPException(status_code=404, detail="No setup preview available")
    return FileResponse(preview_path, media_type="image/jpeg")


@app.post("/setup/camera-config")
def save_camera_setup(request: CameraSetupSaveRequest):
    preview_camera_id = _sanitize_camera_id(request.camera_id)
    raw = _read_raw_camera_config()
    defaults = raw.get("defaults", {})
    cameras = raw.get("cameras", [])

    normalized_lines = _normalize_setup_counting_lines(request.counting_lines)
    normalized_zebra_zones = _normalize_setup_zebra_zones(request.zebra_zones)

    existing_index = next((index for index, camera in enumerate(cameras) if camera.get("id") == request.camera_id), None)
    existing_camera = cameras[existing_index] if existing_index is not None else {}
    existing_zones = normalize_zone_definitions(existing_camera.get("zones"))
    retained_non_zebra_zones = [zone for zone in existing_zones if zone.get("category") != "zebra_crossing"]

    camera_payload = {
        **existing_camera,
        "id": request.camera_id,
        "url": request.source,
        "location": request.location or existing_camera.get("location") or "",
        "target_fps": request.target_fps if request.target_fps is not None else existing_camera.get("target_fps", 15),
        "pixels_per_meter": request.pixels_per_meter if request.pixels_per_meter is not None else existing_camera.get("pixels_per_meter", defaults.get("pixels_per_meter", 25.0)),
        "speed_limit_kmh": request.speed_limit_kmh if request.speed_limit_kmh is not None else existing_camera.get("speed_limit_kmh", defaults.get("speed_limit_kmh", 60.0)),
        "live_feed_type": request.live_feed_type if request.live_feed_type is not None else existing_camera.get("live_feed_type", "preview"),
        "live_feed_url": request.live_feed_url if request.live_feed_url is not None else existing_camera.get("live_feed_url"),
        "preview_image_url": request.preview_image_url if request.preview_image_url is not None else existing_camera.get("preview_image_url", f"/setup/previews/{preview_camera_id}/frame"),
        "preview_frame_width": request.preview_frame_width if request.preview_frame_width is not None else existing_camera.get("preview_frame_width"),
        "preview_frame_height": request.preview_frame_height if request.preview_frame_height is not None else existing_camera.get("preview_frame_height"),
        "counting_lines": normalized_lines,
        "zones": retained_non_zebra_zones + normalized_zebra_zones,
    }

    if existing_index is not None:
        cameras[existing_index] = camera_payload
    else:
        cameras.append(camera_payload)

    raw["cameras"] = cameras
    _write_raw_camera_config(raw)

    profile = {**defaults, **camera_payload}
    profile["zones"] = normalize_zone_definitions(profile.get("zones"))
    profile["counting_lines"] = normalize_counting_line_definitions(profile.get("counting_lines"))
    return {"message": "Camera setup saved", "camera": profile}


def _resolve_source_path(source: str) -> Path:
    source_path = Path(source)
    if source_path.is_absolute():
        return source_path
    return (_CAMERAS_CONFIG_PATH.parent.parent / source).resolve()


def _setup_preview_path(camera_id: str) -> Path:
    return _SETUP_PREVIEW_DIR / camera_id / "frame.jpg"


def _sanitize_camera_id(camera_id: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in camera_id.strip())
    return safe or "camera_setup"


def _extract_preview_frame(source: str):
    image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    resolved_source = _resolve_source_path(source)
    frame = None

    if resolved_source.exists() and resolved_source.suffix.lower() in image_extensions:
        frame = cv2.imread(str(resolved_source))
    else:
        capture_source = str(resolved_source) if resolved_source.exists() else source
        capture = cv2.VideoCapture(capture_source)
        try:
            ok, frame = capture.read()
        finally:
            capture.release()
        if not ok:
            frame = None

    if frame is None:
        raise HTTPException(status_code=400, detail="Unable to read preview frame from source")
    return frame, str(resolved_source if resolved_source.exists() else source)


def _read_raw_camera_config():
    try:
        with open(_CAMERAS_CONFIG_PATH, "r") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def _write_raw_camera_config(raw_config: dict):
    _CAMERAS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_CAMERAS_CONFIG_PATH, "w") as f:
        yaml.safe_dump(raw_config, f, sort_keys=False)


def _normalize_setup_counting_lines(lines: List[SetupCountingLineInput]):
    payload = []
    for index, line in enumerate(lines or [], start=1):
        payload.append(
            {
                "id": line.id or f"count_line_{index}",
                "label": line.label or f"Count Line {index}",
                "points": line.points,
                "enabled": True,
            }
        )
    return normalize_counting_line_definitions(payload)


def _normalize_setup_zebra_zones(zones: List[SetupZebraZoneInput]):
    payload = []
    for index, zone in enumerate(zones or [], start=1):
        payload.append(
            {
                "id": zone.id or f"zebra_crossing_{index}",
                "label": zone.label or f"Zebra Crossing {index}",
                "type": "polygon",
                "category": "zebra_crossing",
                "points": zone.points,
            }
        )
    return normalize_zone_definitions(payload)


def _live_snapshot_path(camera_id: str) -> Path:
    return _LIVE_FRAMES_DIR / camera_id / "latest.jpg"


def _violation_evidence_path(camera_id: str, violation_id: int, violation_type: str, timestamp: datetime) -> Path:
    safe_type = violation_type.replace("/", "_").replace(" ", "_")
    ts_label = timestamp.strftime("%Y%m%dT%H%M%S")
    return _VIOLATION_EVIDENCE_DIR / camera_id / f"{ts_label}_{safe_type}_{violation_id}.jpg"


def _iter_retention_targets(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return (path for path in root.rglob("*") if path.is_file())


def _cleanup_dir_older_than(root: Path, retention_seconds: int, label: str):
    if retention_seconds <= 0:
        return
    now = datetime.now(timezone.utc).timestamp()
    removed = 0
    for path in _iter_retention_targets(root):
        try:
            if now - path.stat().st_mtime > retention_seconds:
                path.unlink(missing_ok=True)
                removed += 1
        except FileNotFoundError:
            continue
    if removed:
        logger.info("Removed %s expired %s file(s) from %s", removed, label, root)


def _cleanup_runtime_artifacts():
    _cleanup_dir_older_than(_VIOLATION_EVIDENCE_DIR, _VIOLATION_EVIDENCE_RETENTION_SECONDS, "evidence")
    _cleanup_dir_older_than(_LIVE_FRAMES_DIR, _LIVE_PREVIEW_RETENTION_SECONDS, "live preview")
    _cleanup_dir_older_than(_SETUP_PREVIEW_DIR, _SETUP_PREVIEW_RETENTION_SECONDS, "setup preview")


def _capture_violation_evidence(db_violation: models.DBViolation) -> Optional[str]:
    if not _EVIDENCE_CAPTURE_ENABLED:
        return None
    source_path = _live_snapshot_path(db_violation.camera_id)
    if not source_path.exists():
        return None

    evidence_path = _violation_evidence_path(
        camera_id=db_violation.camera_id,
        violation_id=db_violation.id,
        violation_type=db_violation.violation_type,
        timestamp=db_violation.timestamp,
    )
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, evidence_path)
    return str(evidence_path)


def _violation_evidence_url(row: models.DBViolation) -> Optional[str]:
    if not row.evidence_image_path:
        return None
    evidence_path = Path(row.evidence_image_path)
    if not evidence_path.exists():
        return None
    return f"/violations/{row.id}/evidence"


def _normalize_review_status(value: str) -> str:
    normalized = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    allowed = {"needs_review", "confirmed", "false_positive"}
    if normalized not in allowed:
        raise HTTPException(status_code=400, detail="Invalid review status")
    return normalized


def _serialize_dt(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _camera_health_snapshot(camera_id: str, db: Session):
    snapshot_path = _live_snapshot_path(camera_id)
    snapshot_available = snapshot_path.exists()
    snapshot_updated_at = None
    snapshot_age_seconds = None
    snapshot_fresh = False

    if snapshot_available:
        snapshot_updated = datetime.fromtimestamp(snapshot_path.stat().st_mtime, tz=timezone.utc)
        snapshot_updated_at = snapshot_updated.isoformat()
        snapshot_age_seconds = max(0, int((datetime.now(timezone.utc) - snapshot_updated).total_seconds()))
        snapshot_fresh = snapshot_age_seconds <= 10

    last_detection = db.query(func.max(models.DBDetection.timestamp)).filter(
        models.DBDetection.camera_id == camera_id
    ).scalar()
    last_speed = db.query(func.max(models.DBSpeed.timestamp)).filter(
        models.DBSpeed.camera_id == camera_id
    ).scalar()
    last_violation = db.query(func.max(models.DBViolation.timestamp)).filter(
        models.DBViolation.camera_id == camera_id
    ).scalar()
    last_crossing = db.query(func.max(models.DBCrossing.timestamp)).filter(
        models.DBCrossing.camera_id == camera_id
    ).scalar()

    recent_activity = [value for value in (last_detection, last_speed, last_violation, last_crossing) if value is not None]
    last_activity = max(recent_activity) if recent_activity else None
    last_activity_iso = _serialize_dt(last_activity)
    activity_age_seconds = None
    if last_activity is not None:
        if last_activity.tzinfo is None:
            last_activity = last_activity.replace(tzinfo=timezone.utc)
        activity_age_seconds = max(0, int((datetime.now(timezone.utc) - last_activity).total_seconds()))

    if snapshot_fresh or (activity_age_seconds is not None and activity_age_seconds <= 15):
        health = "online"
    elif snapshot_available or last_activity_iso:
        health = "idle"
    else:
        health = "offline"

    return {
        "camera_id": camera_id,
        "snapshot_available": snapshot_available,
        "snapshot_url": f"/live/cameras/{camera_id}/snapshot" if snapshot_available else None,
        "snapshot_updated_at": snapshot_updated_at,
        "snapshot_age_seconds": snapshot_age_seconds,
        "snapshot_fresh": snapshot_fresh,
        "last_detection_at": _serialize_dt(last_detection),
        "last_speed_at": _serialize_dt(last_speed),
        "last_violation_at": _serialize_dt(last_violation),
        "last_crossing_at": _serialize_dt(last_crossing),
        "last_activity_at": last_activity_iso,
        "activity_age_seconds": activity_age_seconds,
        "health": health,
    }


def _read_camera_profiles():
    try:
        with open(_CAMERAS_CONFIG_PATH, "r") as f:
            raw = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}, []
    defaults = raw.get("defaults", {})
    cameras = raw.get("cameras", [])
    merged = []
    for cam in cameras:
        profile = {**defaults, **cam}
        profile["zones"] = normalize_zone_definitions(profile.get("zones"))
        profile["counting_lines"] = normalize_counting_line_definitions(profile.get("counting_lines"))
        merged.append(profile)
    return defaults, merged


@app.get("/live/cameras")
def get_live_camera_statuses(db: Session = Depends(get_db)):
    _, cameras = _read_camera_profiles()
    statuses = []
    for camera in cameras:
        camera_id = camera.get("id")
        if not camera_id:
            continue
        statuses.append(_camera_health_snapshot(camera_id, db))
    return {"cameras": statuses}


@app.get("/live/cameras/{camera_id}")
def get_live_camera_status(camera_id: str, db: Session = Depends(get_db)):
    return _camera_health_snapshot(camera_id, db)


@app.get("/live/cameras/{camera_id}/snapshot")
def get_live_camera_snapshot(camera_id: str):
    snapshot_path = _live_snapshot_path(camera_id)
    if not snapshot_path.exists():
        raise HTTPException(status_code=404, detail="No live snapshot available")
    return FileResponse(snapshot_path, media_type="image/jpeg")


@app.get("/violations/{violation_id}/evidence")
def get_violation_evidence(violation_id: int, db: Session = Depends(get_db)):
    row = db.query(models.DBViolation).filter(models.DBViolation.id == violation_id).first()
    if row is None or not row.evidence_image_path:
        raise HTTPException(status_code=404, detail="No evidence available")

    evidence_path = Path(row.evidence_image_path)
    if not evidence_path.exists():
        raise HTTPException(status_code=404, detail="No evidence available")
    return FileResponse(evidence_path, media_type="image/jpeg")


@app.get("/violations/detail/{violation_id}")
def get_violation_detail(violation_id: int, db: Session = Depends(get_db)):
    return _get_violation_detail_data(db, violation_id)


def _apply_time_filters(query, model, start: datetime = None, end: datetime = None):
    if start is not None:
        query = query.filter(model.timestamp >= start)
    if end is not None:
        query = query.filter(model.timestamp <= end)
    return query


def _apply_camera_filter(query, model, camera_id: str = None):
    if camera_id:
        query = query.filter(model.camera_id == camera_id)
    return query


def _serialize_detection_class_rows(rows):
    items = [
        {"class": row.class_name, "count": row.count}
        for row in rows
    ]
    return sorted(items, key=lambda item: (-item["count"], item["class"]))


def _serialize_recent_detections(rows):
    return [
        {
            "camera_id": row.camera_id,
            "timestamp": row.timestamp,
            "object_id": row.object_id,
            "class": row.class_name,
            "helmet_status": row.helmet_status,
            "bbox": row.bbox,
            "confidence": row.confidence,
            "frame_number": row.frame_number,
            "source": row.source,
        }
        for row in rows
    ]


def _serialize_recent_speeds(rows):
    return [
        {
            "camera_id": row.camera_id,
            "object_id": row.object_id,
            "speed_kmh": row.speed_kmh,
            "timestamp": row.timestamp,
            "source": row.source,
        }
        for row in rows
    ]


def _serialize_recent_violations(rows):
    return [
        {
            "id": row.id,
            "violation_type": row.violation_type,
            "object_id": row.object_id,
            "camera_id": row.camera_id,
            "timestamp": row.timestamp,
            "evidence_url": _violation_evidence_url(row),
            "review_status": row.review_status or "needs_review",
            "review_notes": row.review_notes,
            "reviewed_at": row.reviewed_at,
        }
        for row in rows
    ]


def _serialize_recent_crossings(rows):
    return [
        {
            "id": row.id,
            "camera_id": row.camera_id,
            "line_id": row.line_id,
            "line_label": row.line_label,
            "object_id": row.object_id,
            "class": row.class_name,
            "direction": row.direction,
            "timestamp": row.timestamp,
            "frame_number": row.frame_number,
            "source": row.source,
        }
        for row in rows
    ]


def _build_export_filename(prefix: str, extension: str, camera_id: str = None, start: datetime = None, end: datetime = None):
    parts = [prefix]
    if camera_id:
        parts.append(camera_id)
    if start:
        parts.append(start.strftime("%Y%m%dT%H%M%S"))
    if end:
        parts.append(end.strftime("%Y%m%dT%H%M%S"))
    return f"{'_'.join(parts)}.{extension}"


def _csv_download_response(filename: str, fieldnames: List[str], rows: List[dict]):
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    content = buffer.getvalue()
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(iter([content]), media_type="text/csv", headers=headers)


def _json_download_response(filename: str, payload: dict):
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    content = json.dumps(jsonable_encoder(payload), indent=2)
    return StreamingResponse(iter([content]), media_type="application/json", headers=headers)


def _get_violation_detail_data(db: Session, violation_id: int):
    row = db.query(models.DBViolation).filter(models.DBViolation.id == violation_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Safety event not found")

    camera_defaults, camera_profiles = _read_camera_profiles()
    camera_profile = next((camera for camera in camera_profiles if camera.get("id") == row.camera_id), None)
    from datetime import timedelta
    timestamp = row.timestamp
    start = timestamp - timedelta(seconds=5)
    end = timestamp + timedelta(seconds=5)

    detections_query = db.query(models.DBDetection).filter(
        models.DBDetection.camera_id == row.camera_id,
        models.DBDetection.object_id == row.object_id,
        models.DBDetection.timestamp >= start,
        models.DBDetection.timestamp <= end,
    ).order_by(models.DBDetection.timestamp.desc())

    speeds_query = db.query(models.DBSpeed).filter(
        models.DBSpeed.camera_id == row.camera_id,
        models.DBSpeed.object_id == row.object_id,
        models.DBSpeed.timestamp >= start,
        models.DBSpeed.timestamp <= end,
    ).order_by(models.DBSpeed.timestamp.desc())

    crossings_query = db.query(models.DBCrossing).filter(
        models.DBCrossing.camera_id == row.camera_id,
        models.DBCrossing.object_id == row.object_id,
        models.DBCrossing.timestamp >= start,
        models.DBCrossing.timestamp <= end,
    ).order_by(models.DBCrossing.timestamp.desc())

    return {
        "id": row.id,
        "violation_type": row.violation_type,
        "object_id": row.object_id,
        "camera_id": row.camera_id,
        "timestamp": row.timestamp,
        "evidence_url": _violation_evidence_url(row),
        "review_status": row.review_status or "needs_review",
        "review_notes": row.review_notes,
        "reviewed_at": row.reviewed_at,
        "camera_profile": camera_profile,
        "camera_defaults": camera_defaults,
        "related": {
            "detections": _serialize_recent_detections(detections_query.limit(10).all()),
            "speeds": _serialize_recent_speeds(speeds_query.limit(10).all()),
            "crossings": _serialize_recent_crossings(crossings_query.limit(10).all()),
        },
    }


def _build_counts_map(items, key_field="count", label_field=None):
    counts = {}
    for item in items:
        label = item.get(label_field or "class") or item.get("direction") or item.get("line_id")
        if label:
            counts[label] = item.get(key_field, 0)
    return counts


def _p85(values):
    if not values:
        return None
    sorted_values = sorted(values)
    index = min(len(sorted_values) - 1, int(round((len(sorted_values) - 1) * 0.85)))
    return sorted_values[index]


def _resolve_flow_rate_per_minute(start, end, min_timestamp, max_timestamp, total_crossings):
    if total_crossings <= 0:
        return 0.0
    if start is not None and end is not None and end > start:
        duration_seconds = (end - start).total_seconds()
    elif min_timestamp is not None and max_timestamp is not None and max_timestamp > min_timestamp:
        duration_seconds = (max_timestamp - min_timestamp).total_seconds()
    else:
        return 0.0

    duration_minutes = duration_seconds / 60.0
    if duration_minutes <= 0:
        return 0.0
    return round(total_crossings / duration_minutes, 2)


def _get_analytics_summary_data(db: Session, camera_id: str = None, start: datetime = None, end: datetime = None):
    detection_query = db.query(models.DBDetection)
    detection_query = _apply_camera_filter(detection_query, models.DBDetection, camera_id)
    detection_query = _apply_time_filters(detection_query, models.DBDetection, start, end)

    violation_query = db.query(models.DBViolation)
    violation_query = _apply_camera_filter(violation_query, models.DBViolation, camera_id)
    violation_query = _apply_time_filters(violation_query, models.DBViolation, start, end)

    speed_query = db.query(models.DBSpeed)
    speed_query = _apply_camera_filter(speed_query, models.DBSpeed, camera_id)
    speed_query = _apply_time_filters(speed_query, models.DBSpeed, start, end)

    crossing_query = db.query(models.DBCrossing)
    crossing_query = _apply_camera_filter(crossing_query, models.DBCrossing, camera_id)
    crossing_query = _apply_time_filters(crossing_query, models.DBCrossing, start, end)

    detection_class_rows = (
        detection_query.with_entities(
            models.DBDetection.class_name,
            func.count(models.DBDetection.id).label("count"),
        )
        .group_by(models.DBDetection.class_name)
        .all()
    )

    return {
        "camera_id": camera_id,
        "start": start,
        "end": end,
        "total_detections_logged": detection_query.count(),
        "total_speeds_logged": speed_query.count(),
        "total_violations_logged": violation_query.count(),
        "total_crossings_logged": crossing_query.count(),
        "detection_classes": _serialize_detection_class_rows(detection_class_rows),
    }


def _get_detection_analytics_data(db: Session, camera_id: str = None, start: datetime = None, end: datetime = None):
    query = db.query(models.DBDetection)
    query = _apply_camera_filter(query, models.DBDetection, camera_id)
    query = _apply_time_filters(query, models.DBDetection, start, end)

    class_rows = (
        query.with_entities(
            models.DBDetection.class_name,
            func.count(models.DBDetection.id).label("count"),
        )
        .group_by(models.DBDetection.class_name)
        .all()
    )
    camera_rows = (
        query.with_entities(
            models.DBDetection.camera_id,
            models.DBDetection.class_name,
            func.count(models.DBDetection.id).label("count"),
        )
        .group_by(models.DBDetection.camera_id, models.DBDetection.class_name)
        .all()
    )

    cameras = {}
    for row in camera_rows:
        camera = cameras.setdefault(
            row.camera_id,
            {
                "camera_id": row.camera_id,
                "total_detections": 0,
                "classes": [],
            },
        )
        camera["classes"].append({"class": row.class_name, "count": row.count})
        camera["total_detections"] += row.count

    for camera in cameras.values():
        camera["classes"].sort(key=lambda item: (-item["count"], item["class"]))

    return {
        "camera_id": camera_id,
        "start": start,
        "end": end,
        "total_detections": query.count(),
        "classes": _serialize_detection_class_rows(class_rows),
        "cameras": sorted(cameras.values(), key=lambda item: item["camera_id"]),
    }


def _get_analytics_by_camera_data(db: Session, start: datetime = None, end: datetime = None):
    detection_query = db.query(
        models.DBDetection.camera_id,
        func.count(models.DBDetection.id).label("detections"),
    )
    detection_query = _apply_time_filters(detection_query, models.DBDetection, start, end)
    detection_rows = detection_query.group_by(models.DBDetection.camera_id).all()

    speed_query = db.query(
        models.DBSpeed.camera_id,
        func.count(models.DBSpeed.id).label("speeds"),
    )
    speed_query = _apply_time_filters(speed_query, models.DBSpeed, start, end)
    speed_rows = speed_query.group_by(models.DBSpeed.camera_id).all()

    violation_query = db.query(
        models.DBViolation.camera_id,
        func.count(models.DBViolation.id).label("violations"),
    )
    violation_query = _apply_time_filters(violation_query, models.DBViolation, start, end)
    violation_rows = violation_query.group_by(models.DBViolation.camera_id).all()

    crossing_query = db.query(
        models.DBCrossing.camera_id,
        func.count(models.DBCrossing.id).label("crossings"),
    )
    crossing_query = _apply_time_filters(crossing_query, models.DBCrossing, start, end)
    crossing_rows = crossing_query.group_by(models.DBCrossing.camera_id).all()

    summary = {}
    for row in detection_rows:
        summary.setdefault(row.camera_id, {"camera_id": row.camera_id, "detections": 0, "speeds": 0, "violations": 0, "crossings": 0})
        summary[row.camera_id]["detections"] = row.detections
    for row in speed_rows:
        summary.setdefault(row.camera_id, {"camera_id": row.camera_id, "detections": 0, "speeds": 0, "violations": 0, "crossings": 0})
        summary[row.camera_id]["speeds"] = row.speeds
    for row in violation_rows:
        summary.setdefault(row.camera_id, {"camera_id": row.camera_id, "detections": 0, "speeds": 0, "violations": 0, "crossings": 0})
        summary[row.camera_id]["violations"] = row.violations
    for row in crossing_rows:
        summary.setdefault(row.camera_id, {"camera_id": row.camera_id, "detections": 0, "speeds": 0, "violations": 0, "crossings": 0})
        summary[row.camera_id]["crossings"] = row.crossings

    return {
        "start": start,
        "end": end,
        "cameras": sorted(summary.values(), key=lambda item: item["camera_id"]),
    }


def _get_violation_breakdown_data(db: Session, camera_id: str = None, start: datetime = None, end: datetime = None):
    query = db.query(
        models.DBViolation.violation_type,
        func.count(models.DBViolation.id).label("count"),
    )
    query = _apply_camera_filter(query, models.DBViolation, camera_id)
    query = _apply_time_filters(query, models.DBViolation, start, end)
    rows = query.group_by(models.DBViolation.violation_type).all()

    return {
        "camera_id": camera_id,
        "start": start,
        "end": end,
        "violations": [
            {"violation_type": row.violation_type, "count": row.count}
            for row in rows
        ],
    }


def _get_crossing_analytics_data(db: Session, camera_id: str = None, start: datetime = None, end: datetime = None):
    query = db.query(models.DBCrossing)
    query = _apply_camera_filter(query, models.DBCrossing, camera_id)
    query = _apply_time_filters(query, models.DBCrossing, start, end)

    total_crossings = query.count()
    min_timestamp, max_timestamp = query.with_entities(
        func.min(models.DBCrossing.timestamp),
        func.max(models.DBCrossing.timestamp),
    ).one()

    direction_rows = (
        query.with_entities(models.DBCrossing.direction, func.count(models.DBCrossing.id).label("count"))
        .group_by(models.DBCrossing.direction)
        .all()
    )
    class_rows = (
        query.with_entities(models.DBCrossing.class_name, func.count(models.DBCrossing.id).label("count"))
        .group_by(models.DBCrossing.class_name)
        .all()
    )
    line_rows = (
        query.with_entities(
            models.DBCrossing.line_id,
            models.DBCrossing.line_label,
            models.DBCrossing.direction,
            func.count(models.DBCrossing.id).label("count"),
        )
        .group_by(models.DBCrossing.line_id, models.DBCrossing.line_label, models.DBCrossing.direction)
        .all()
    )

    lines = {}
    for row in line_rows:
        line = lines.setdefault(
            row.line_id,
            {
                "line_id": row.line_id,
                "line_label": row.line_label,
                "count": 0,
                "directions": {},
            },
        )
        line["directions"][row.direction] = row.count
        line["count"] += row.count

    crossing_objects = {}
    for row in query.with_entities(
        models.DBCrossing.camera_id,
        models.DBCrossing.object_id,
        models.DBCrossing.class_name,
    ).all():
        crossing_objects[(row.camera_id, row.object_id)] = row.class_name

    speed_query = db.query(models.DBSpeed)
    speed_query = _apply_camera_filter(speed_query, models.DBSpeed, camera_id)
    speed_query = _apply_time_filters(speed_query, models.DBSpeed, start, end)
    speed_rows = speed_query.all()

    speeds_by_class = {}
    for row in speed_rows:
        class_name = crossing_objects.get((row.camera_id, row.object_id))
        if not class_name:
            continue
        speeds_by_class.setdefault(class_name, []).append(float(row.speed_kmh))

    speed_metrics_by_class = {}
    for class_name, values in sorted(speeds_by_class.items()):
        speed_metrics_by_class[class_name] = {
            "avg_speed_kmh": round(sum(values) / len(values), 2),
            "max_speed_kmh": round(max(values), 2),
            "p85_speed_kmh": round(_p85(values), 2) if _p85(values) is not None else None,
            "samples": len(values),
        }

    directions = [
        {"direction": row.direction, "count": row.count}
        for row in direction_rows
    ]
    classes = [
        {"class": row.class_name, "count": row.count}
        for row in class_rows
    ]
    sorted_lines = sorted(lines.values(), key=lambda item: (-item["count"], item["line_id"]))

    return {
        "camera_id": camera_id,
        "start": start,
        "end": end,
        "total_crossings": total_crossings,
        "directions": directions,
        "classes": classes,
        "lines": sorted_lines,
        "counts_by_direction": {item["direction"]: item["count"] for item in directions},
        "counts_by_class": {item["class"]: item["count"] for item in classes},
        "counts_by_line": {item["line_id"]: item["count"] for item in sorted_lines},
        "flow_rate_per_minute": _resolve_flow_rate_per_minute(start, end, min_timestamp, max_timestamp, total_crossings),
        "speed_metrics_by_class": speed_metrics_by_class,
    }


def _get_recent_events_data(
    db: Session,
    camera_id: str = None,
    start: datetime = None,
    end: datetime = None,
    limit: int = 10,
    offset: int = 0,
):
    detections_query = db.query(models.DBDetection)
    detections_query = _apply_camera_filter(detections_query, models.DBDetection, camera_id)
    detections_query = _apply_time_filters(detections_query, models.DBDetection, start, end)
    detections = detections_query.order_by(models.DBDetection.timestamp.desc()).offset(offset).limit(limit).all()

    speeds_query = db.query(models.DBSpeed)
    speeds_query = _apply_camera_filter(speeds_query, models.DBSpeed, camera_id)
    speeds_query = _apply_time_filters(speeds_query, models.DBSpeed, start, end)
    speeds = speeds_query.order_by(models.DBSpeed.timestamp.desc()).offset(offset).limit(limit).all()

    violations_query = db.query(models.DBViolation)
    violations_query = _apply_camera_filter(violations_query, models.DBViolation, camera_id)
    violations_query = _apply_time_filters(violations_query, models.DBViolation, start, end)
    violations = violations_query.order_by(models.DBViolation.timestamp.desc()).offset(offset).limit(limit).all()

    crossings_query = db.query(models.DBCrossing)
    crossings_query = _apply_camera_filter(crossings_query, models.DBCrossing, camera_id)
    crossings_query = _apply_time_filters(crossings_query, models.DBCrossing, start, end)
    crossings = crossings_query.order_by(models.DBCrossing.timestamp.desc()).offset(offset).limit(limit).all()

    return {
        "camera_id": camera_id,
        "start": start,
        "end": end,
        "detections": _serialize_recent_detections(detections),
        "speeds": _serialize_recent_speeds(speeds),
        "violations": _serialize_recent_violations(violations),
        "crossings": _serialize_recent_crossings(crossings),
    }


def _get_speed_distribution_data(db: Session, camera_id: str = None, start: datetime = None, end: datetime = None):
    bands = [
        (0, 20, "0–20"),
        (20, 40, "20–40"),
        (40, 60, "40–60"),
        (60, 80, "60–80"),
        (80, 100, "80–100"),
        (100, 120, "100–120"),
        (120, None, "120+"),
    ]

    bucket_expr = case(
        *[
            (
                (models.DBSpeed.speed_kmh >= lo) & (models.DBSpeed.speed_kmh < hi),
                label,
            )
            for lo, hi, label in bands
            if hi is not None
        ],
        else_="120+",
    )

    query = db.query(bucket_expr.label("band"), func.count(models.DBSpeed.id).label("count"))
    query = _apply_camera_filter(query, models.DBSpeed, camera_id)
    query = _apply_time_filters(query, models.DBSpeed, start, end)
    rows = query.group_by(bucket_expr).all()

    counts = {row.band: row.count for row in rows}
    return {
        "camera_id": camera_id,
        "start": start,
        "end": end,
        "buckets": [
            {"band": label, "count": counts.get(label, 0)}
            for _, _, label in bands
        ],
    }


def _get_violation_log_data(
    db: Session,
    camera_id: str = None,
    violation_type: str = None,
    start: datetime = None,
    end: datetime = None,
    page: int = 1,
    page_size: int = 25,
):
    query = db.query(models.DBViolation)
    if camera_id:
        query = query.filter(models.DBViolation.camera_id == camera_id)
    if violation_type:
        query = query.filter(models.DBViolation.violation_type == violation_type)
    query = _apply_time_filters(query, models.DBViolation, start, end)

    total = query.count()
    offset = (page - 1) * page_size
    rows = query.order_by(models.DBViolation.timestamp.desc()).offset(offset).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total else 0,
        "items": _serialize_recent_violations(rows),
    }


def _get_dashboard_snapshot_data(
    db: Session,
    camera_id: str = None,
    start: datetime = None,
    end: datetime = None,
    detail_camera_id: str = None,
):
    camera_defaults, camera_profiles = _read_camera_profiles()
    live_feeds = {"cameras": [_camera_health_snapshot(camera["id"], db) for camera in camera_profiles if camera.get("id")]}
    snapshot = {
        "summary": _get_analytics_summary_data(db, camera_id, start, end),
        "by_camera": _get_analytics_by_camera_data(db, start, end),
        "violations": _get_violation_breakdown_data(db, camera_id, start, end),
        "detections": _get_detection_analytics_data(db, camera_id, start, end),
        "crossings": _get_crossing_analytics_data(db, camera_id, start, end),
        "recent": _get_recent_events_data(db, camera_id, start, end, limit=20, offset=0),
        "speed_distribution": _get_speed_distribution_data(db, camera_id, start, end),
        "camera_configs": {
            "defaults": camera_defaults,
            "cameras": camera_profiles,
        },
        "live_feeds": live_feeds,
        "stream": {
            "status": "live",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }

    if detail_camera_id:
        camera_stats = next(
            (item for item in snapshot["by_camera"]["cameras"] if item["camera_id"] == detail_camera_id),
            {"camera_id": detail_camera_id, "detections": 0, "speeds": 0, "violations": 0, "crossings": 0},
        )
        snapshot["camera_detail"] = {
            "camera_id": detail_camera_id,
            "camera_stats": camera_stats,
            "recent": _get_recent_events_data(db, detail_camera_id, start, end, limit=20, offset=0),
            "violations": _get_violation_breakdown_data(db, detail_camera_id, start, end),
            "crossings": _get_crossing_analytics_data(db, detail_camera_id, start, end),
            "detections": _get_detection_analytics_data(db, detail_camera_id, start, end),
        }

    return snapshot


def _get_safety_event_export_rows(
    db: Session,
    camera_id: str = None,
    violation_type: str = None,
    start: datetime = None,
    end: datetime = None,
):
    query = db.query(models.DBViolation)
    if camera_id:
        query = query.filter(models.DBViolation.camera_id == camera_id)
    if violation_type:
        query = query.filter(models.DBViolation.violation_type == violation_type)
    query = _apply_time_filters(query, models.DBViolation, start, end)
    rows = query.order_by(models.DBViolation.timestamp.desc()).all()

    return [
        {
            "id": row.id,
            "timestamp": _serialize_dt(row.timestamp),
            "camera_id": row.camera_id,
            "violation_type": row.violation_type,
            "object_id": row.object_id,
            "evidence_url": _violation_evidence_url(row) or "",
        }
        for row in rows
    ]


def _get_crossing_export_rows(
    db: Session,
    camera_id: str = None,
    start: datetime = None,
    end: datetime = None,
):
    query = db.query(models.DBCrossing)
    query = _apply_camera_filter(query, models.DBCrossing, camera_id)
    query = _apply_time_filters(query, models.DBCrossing, start, end)
    rows = query.order_by(models.DBCrossing.timestamp.desc()).all()

    return [
        {
            "id": row.id,
            "timestamp": _serialize_dt(row.timestamp),
            "camera_id": row.camera_id,
            "line_id": row.line_id,
            "line_label": row.line_label,
            "direction": row.direction,
            "class": row.class_name,
            "object_id": row.object_id,
            "frame_number": row.frame_number if row.frame_number is not None else "",
            "source": row.source or "",
        }
        for row in rows
    ]


def _get_traffic_flow_export_data(
    db: Session,
    camera_id: str = None,
    start: datetime = None,
    end: datetime = None,
):
    return {
        "generated_at": datetime.now(timezone.utc),
        "scope": {
            "camera_id": camera_id,
            "start": start,
            "end": end,
        },
        "summary": _get_analytics_summary_data(db, camera_id, start, end),
        "crossings": _get_crossing_analytics_data(db, camera_id, start, end),
        "detections": _get_detection_analytics_data(db, camera_id, start, end),
        "violations": _get_violation_breakdown_data(db, camera_id, start, end),
        "speed_distribution": _get_speed_distribution_data(db, camera_id, start, end),
    }

@app.post("/detections", status_code=201)
def create_detection(event: schemas.DetectionEvent, db: Session = Depends(get_db)):
    data = event.model_dump()
    data['class_name'] = event.class_name
    db_detection = models.DBDetection(**data)
    db.add(db_detection)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to insert detection: {e}")
        raise HTTPException(status_code=500, detail="Database Error")
    return {"message": "Detection stored"}

@app.post("/speeds", status_code=201)
def create_speed(event: schemas.SpeedEvent, db: Session = Depends(get_db)):
    db_speed = models.DBSpeed(**event.model_dump())
    db.add(db_speed)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to insert speed: {e}")
        raise HTTPException(status_code=500, detail="Database Error")
    return {"message": "Speed stored"}

@app.post("/violations", status_code=201)
def create_violation(event: schemas.ViolationEvent, db: Session = Depends(get_db)):
    db_violation = models.DBViolation(**event.model_dump())
    db.add(db_violation)
    try:
        db.commit()
        db.refresh(db_violation)
        db_violation.evidence_image_path = _capture_violation_evidence(db_violation)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to insert violation: {e}")
        raise HTTPException(status_code=500, detail="Database Error")
    return {"message": "Violation stored"}


@app.patch("/violations/detail/{violation_id}/review")
def update_violation_review(
    violation_id: int,
    request: ViolationReviewUpdateRequest,
    db: Session = Depends(get_db),
):
    row = db.query(models.DBViolation).filter(models.DBViolation.id == violation_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Safety event not found")

    row.review_status = _normalize_review_status(request.review_status)
    row.review_notes = (request.review_notes or "").strip() or None
    row.reviewed_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update violation review: {e}")
        raise HTTPException(status_code=500, detail="Database Error")

    return _get_violation_detail_data(db, violation_id)

@app.post("/trajectories", status_code=201)
def create_trajectory(event: schemas.TrajectoryEvent, db: Session = Depends(get_db)):
    db_traj = models.DBTrajectory(**event.model_dump())
    db.add(db_traj)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to insert trajectory: {e}")
        raise HTTPException(status_code=500, detail="Database Error")
    return {"message": "Trajectory stored"}


@app.post("/crossings", status_code=201)
def create_crossing(event: schemas.CrossingEvent, db: Session = Depends(get_db)):
    data = event.model_dump()
    data["class_name"] = event.class_name
    db_crossing = models.DBCrossing(**data)
    db.add(db_crossing)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to insert crossing: {e}")
        raise HTTPException(status_code=500, detail="Database Error")
    return {"message": "Crossing stored"}

@app.get("/analytics/summary")
def get_analytics_summary(
    camera_id: str = Query(default=None),
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    db: Session = Depends(get_db),
):
    return _get_analytics_summary_data(db, camera_id, start, end)


@app.get("/analytics/detections")
def get_detection_analytics(
    camera_id: str = Query(default=None),
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    db: Session = Depends(get_db),
):
    return _get_detection_analytics_data(db, camera_id, start, end)


@app.get("/analytics/by-camera")
def get_analytics_by_camera(
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    db: Session = Depends(get_db),
):
    return _get_analytics_by_camera_data(db, start, end)


@app.get("/analytics/violations")
def get_violation_breakdown(
    camera_id: str = Query(default=None),
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    db: Session = Depends(get_db),
):
    return _get_violation_breakdown_data(db, camera_id, start, end)


@app.get("/analytics/crossings")
def get_crossing_analytics(
    camera_id: str = Query(default=None),
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    db: Session = Depends(get_db),
):
    return _get_crossing_analytics_data(db, camera_id, start, end)


@app.get("/events/recent")
def get_recent_events(
    camera_id: str = Query(default=None),
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return _get_recent_events_data(db, camera_id, start, end, limit, offset)


@app.get("/analytics/speed-distribution")
def get_speed_distribution(
    camera_id: str = Query(default=None),
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    db: Session = Depends(get_db),
):
    return _get_speed_distribution_data(db, camera_id, start, end)


@app.get("/violations/log")
def get_violations_log(
    camera_id: str = Query(default=None),
    violation_type: str = Query(default=None),
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return _get_violation_log_data(db, camera_id, violation_type, start, end, page, page_size)


@app.get("/exports/safety-events.csv")
def export_safety_events_csv(
    camera_id: str = Query(default=None),
    violation_type: str = Query(default=None),
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    db: Session = Depends(get_db),
):
    rows = _get_safety_event_export_rows(db, camera_id, violation_type, start, end)
    filename = _build_export_filename("safety_events", "csv", camera_id, start, end)
    return _csv_download_response(
        filename,
        ["id", "timestamp", "camera_id", "violation_type", "object_id", "evidence_url"],
        rows,
    )


@app.get("/exports/crossings.csv")
def export_crossings_csv(
    camera_id: str = Query(default=None),
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    db: Session = Depends(get_db),
):
    rows = _get_crossing_export_rows(db, camera_id, start, end)
    filename = _build_export_filename("crossings", "csv", camera_id, start, end)
    return _csv_download_response(
        filename,
        ["id", "timestamp", "camera_id", "line_id", "line_label", "direction", "class", "object_id", "frame_number", "source"],
        rows,
    )


@app.get("/exports/traffic-flow.json")
def export_traffic_flow_json(
    camera_id: str = Query(default=None),
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    db: Session = Depends(get_db),
):
    payload = _get_traffic_flow_export_data(db, camera_id, start, end)
    filename = _build_export_filename("traffic_flow", "json", camera_id, start, end)
    return _json_download_response(filename, payload)


@app.get("/live/dashboard")
async def stream_dashboard_state(
    request: Request,
    camera_id: str = Query(default=None),
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    detail_camera_id: str = Query(default=None),
    once: bool = Query(default=False),
):
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            db = SessionLocal()
            try:
                payload = _get_dashboard_snapshot_data(
                    db,
                    camera_id=camera_id,
                    start=start,
                    end=end,
                    detail_camera_id=detail_camera_id,
                )
                encoded = json.dumps(jsonable_encoder(payload))
                yield f"event: snapshot\ndata: {encoded}\n\n"
            finally:
                db.close()
            if once:
                break
            await asyncio.sleep(2.0)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)
