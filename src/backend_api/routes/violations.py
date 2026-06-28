"""Violation evidence, detail, and review routes."""
import json
import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import cv2
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.responses import FileResponse

from .. import models
from ..database import SessionLocal, get_db
import sys as _sys

from ._shared import _apply_supported_violation_filter, _serialize_dt


def _m():
    """Return the main app module so tests can patch its runtime config."""
    return _sys.modules["backend_api.main"]

logger = logging.getLogger(__name__)
router = APIRouter()


class ViolationReviewUpdateRequest(BaseModel):
    review_status: str
    review_notes: Optional[str] = ""


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _live_snapshot_path(camera_id: str) -> Path:
    return _m()._LIVE_FRAMES_DIR / camera_id / "latest.jpg"


def _live_clip_path(camera_id: str) -> Path:
    return _m()._LIVE_CLIPS_DIR / camera_id / "latest.mp4"


def _live_clip_manifest_path(camera_id: str) -> Path:
    return _m()._LIVE_CLIPS_DIR / camera_id / "latest.json"


def _select_live_clip_source(camera_id: str, violation_timestamp: datetime):
    camera_dir = _m()._LIVE_CLIPS_DIR / camera_id
    if not camera_dir.exists():
        return _live_clip_path(camera_id), _live_clip_manifest_path(camera_id)

    violation_epoch = (
        violation_timestamp.replace(tzinfo=timezone.utc).timestamp()
        if violation_timestamp.tzinfo is None
        else violation_timestamp.timestamp()
    )
    best_match = None
    for manifest_path in sorted(camera_dir.glob("clip_*.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        ts_values = [item.get("timestamp_seconds") for item in manifest if item.get("timestamp_seconds") is not None]
        if not ts_values:
            continue
        if min(ts_values) <= violation_epoch <= max(ts_values):
            distance = abs(max(ts_values) - violation_epoch)
            if best_match is None or distance < best_match[0]:
                best_match = (distance, manifest_path.with_suffix(".mp4"), manifest_path)

    if best_match is not None:
        return best_match[1], best_match[2]

    return _live_clip_path(camera_id), _live_clip_manifest_path(camera_id)


def _violation_evidence_path(camera_id: str, violation_id: int, violation_type: str, timestamp: datetime, extension: str) -> Path:
    safe_type = violation_type.replace("/", "_").replace(" ", "_")
    ts_label = timestamp.strftime("%Y%m%dT%H%M%S")
    normalized_extension = extension if extension.startswith(".") else f".{extension}"
    return _m()._VIOLATION_EVIDENCE_DIR / camera_id / f"{ts_label}_{safe_type}_{violation_id}{normalized_extension}"


# ---------------------------------------------------------------------------
# Evidence capture and rendering
# ---------------------------------------------------------------------------

def _open_video_writer(path: Path, fps: float, width: int, height: int):
    for candidate in ("avc1", "H264", "mp4v"):
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*candidate), max(float(fps), 1.0), (width, height))
        if writer.isOpened():
            return writer
        writer.release()
    return None


def _draw_evidence_box(frame, bbox, object_id):
    if not bbox or len(bbox) != 4:
        return frame
    x1, y1, x2, y2 = [int(round(v)) for v in bbox]
    x1, y1 = max(0, x1), max(0, y1)
    x2 = min(frame.shape[1] - 1, x2)
    y2 = min(frame.shape[0] - 1, y2)
    box_color = (24, 38, 230)
    text_color = (255, 255, 255)
    cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 5)
    label = f"ID {object_id}"
    (text_w, text_h), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)
    label_y1 = max(0, y1 - text_h - baseline - 8)
    label_y2 = max(text_h + baseline + 8, y1)
    label_x2 = min(frame.shape[1] - 1, x1 + text_w + 12)
    cv2.rectangle(frame, (x1, label_y1), (label_x2, label_y2), box_color, -1)
    cv2.putText(frame, label, (x1 + 6, label_y2 - baseline - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.9, text_color, 2, cv2.LINE_AA)
    return frame


def _render_violation_evidence_clip(db_violation: models.DBViolation, clip_path: Path, evidence_path: Path, manifest_path: Path):
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not manifest:
        return None

    frame_numbers = [item.get("frame_number") for item in manifest if item.get("frame_number") is not None]
    timestamp_values = [item.get("timestamp_seconds") for item in manifest if item.get("timestamp_seconds") is not None]
    if not frame_numbers:
        return None

    capture = cv2.VideoCapture(str(clip_path))
    if not capture.isOpened():
        return None

    fps = capture.get(cv2.CAP_PROP_FPS) or 10.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    if width <= 0 or height <= 0:
        capture.release()
        return None

    writer = _open_video_writer(evidence_path, fps, width, height)
    if writer is None:
        capture.release()
        return None

    start_time = datetime.fromtimestamp(min(timestamp_values), tz=timezone.utc).replace(tzinfo=None) if timestamp_values else None
    end_time = datetime.fromtimestamp(max(timestamp_values), tz=timezone.utc).replace(tzinfo=None) if timestamp_values else None
    db = SessionLocal()
    try:
        detection_query = db.query(models.DBDetection).filter(
            models.DBDetection.camera_id == db_violation.camera_id,
            models.DBDetection.object_id == db_violation.object_id,
        )
        if start_time is not None and end_time is not None:
            detection_query = detection_query.filter(
                models.DBDetection.timestamp >= start_time,
                models.DBDetection.timestamp <= end_time,
            )
        else:
            detection_query = detection_query.filter(
                models.DBDetection.frame_number >= min(frame_numbers),
                models.DBDetection.frame_number <= max(frame_numbers),
            )
        detections = detection_query.all()
    finally:
        db.close()

    detections_by_frame = {
        row.frame_number: row
        for row in detections
        if row.frame_number is not None and row.bbox
    }

    matched_frames = 0
    started = False
    try:
        for item in manifest:
            ok, frame = capture.read()
            if not ok or frame is None:
                break
            frame_number = item.get("frame_number")
            detection = detections_by_frame.get(frame_number)
            if detection is not None:
                frame = _draw_evidence_box(frame, detection.bbox, db_violation.object_id)
                matched_frames += 1
                started = True
            if not started:
                continue
            writer.write(frame)
    finally:
        writer.release()
        capture.release()

    if matched_frames <= 0:
        evidence_path.unlink(missing_ok=True)
        return None

    return evidence_path if evidence_path.exists() else None


def _ensure_violation_video_rendered(db_violation: models.DBViolation, evidence_path: Path):
    manifest_path = evidence_path.with_suffix(".json")
    if not manifest_path.exists() or not evidence_path.exists():
        return evidence_path if evidence_path.exists() else None

    temp_path = evidence_path.with_name(f"{evidence_path.stem}.rendering{evidence_path.suffix}")
    temp_path.unlink(missing_ok=True)
    rendered = _render_violation_evidence_clip(db_violation, evidence_path, temp_path, manifest_path)
    if rendered is None:
        temp_path.unlink(missing_ok=True)
        return evidence_path

    temp_path.replace(evidence_path)
    manifest_path.unlink(missing_ok=True)
    return evidence_path


def _violation_evidence_path_and_type(row: models.DBViolation):
    evidence_path_str = row.evidence_media_path or row.evidence_image_path
    if not evidence_path_str:
        return None, None
    evidence_path = Path(evidence_path_str)
    if not evidence_path.exists():
        return None, None
    media_type = row.evidence_media_type
    if not media_type:
        media_type = "video/mp4" if evidence_path.suffix.lower() == ".mp4" else "image/jpeg"
    if media_type == "video/mp4":
        evidence_path = _ensure_violation_video_rendered(row, evidence_path)
        if evidence_path is None or not evidence_path.exists():
            return None, None
    return evidence_path, media_type


def _violation_evidence_url(row: models.DBViolation) -> Optional[str]:
    evidence_path, _ = _violation_evidence_path_and_type(row)
    if evidence_path is None:
        return None
    return f"/violations/{row.id}/evidence"


def _violation_evidence_media_type(row: models.DBViolation) -> Optional[str]:
    _, media_type = _violation_evidence_path_and_type(row)
    return media_type


def _capture_violation_evidence(db_violation: models.DBViolation):
    if not _m()._EVIDENCE_CAPTURE_ENABLED:
        return None, None
    source_path, source_manifest_path = _select_live_clip_source(db_violation.camera_id, db_violation.timestamp)
    media_type = "video/mp4"
    if not source_path.exists():
        source_path = _live_snapshot_path(db_violation.camera_id)
        media_type = "image/jpeg"
    if not source_path.exists():
        return None, None

    evidence_path = _violation_evidence_path(
        camera_id=db_violation.camera_id,
        violation_id=db_violation.id,
        violation_type=db_violation.violation_type,
        timestamp=db_violation.timestamp,
        extension=source_path.suffix or (".mp4" if media_type.startswith("video/") else ".jpg"),
    )
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    if media_type == "video/mp4":
        shutil.copy2(source_path, evidence_path)
        if source_manifest_path.exists():
            shutil.copy2(source_manifest_path, evidence_path.with_suffix(".json"))
        _ensure_violation_video_rendered(db_violation, evidence_path)
        return str(evidence_path), media_type
    shutil.copy2(source_path, evidence_path)
    return str(evidence_path), media_type


def _normalize_review_status(value: str) -> str:
    normalized = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized not in {"needs_review", "confirmed", "false_positive"}:
        raise HTTPException(status_code=400, detail="Invalid review status")
    return normalized


def _get_violation_detail_data(db: Session, violation_id: int):
    from .cameras import _get_camera_profile, _without_retired_camera_fields, _get_camera_defaults
    from ._shared import _serialize_recent_detections, _serialize_recent_speeds, _serialize_recent_crossings

    row = _apply_supported_violation_filter(db.query(models.DBViolation)).filter(
        models.DBViolation.id == violation_id
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Safety event not found")

    camera_defaults = _without_retired_camera_fields(_get_camera_defaults())
    camera_profile = _get_camera_profile(db, row.camera_id)
    timestamp = row.timestamp
    start = timestamp - timedelta(seconds=5)
    end = timestamp + timedelta(seconds=5)

    detections = (
        db.query(models.DBDetection)
        .filter(
            models.DBDetection.camera_id == row.camera_id,
            models.DBDetection.object_id == row.object_id,
            models.DBDetection.timestamp >= start,
            models.DBDetection.timestamp <= end,
        )
        .order_by(models.DBDetection.timestamp.desc())
        .limit(10)
        .all()
    )
    speeds = (
        db.query(models.DBSpeed)
        .filter(
            models.DBSpeed.camera_id == row.camera_id,
            models.DBSpeed.object_id == row.object_id,
            models.DBSpeed.timestamp >= start,
            models.DBSpeed.timestamp <= end,
        )
        .order_by(models.DBSpeed.timestamp.desc())
        .limit(10)
        .all()
    )
    crossings = (
        db.query(models.DBCrossing)
        .filter(
            models.DBCrossing.camera_id == row.camera_id,
            models.DBCrossing.object_id == row.object_id,
            models.DBCrossing.timestamp >= start,
            models.DBCrossing.timestamp <= end,
        )
        .order_by(models.DBCrossing.timestamp.desc())
        .limit(10)
        .all()
    )

    return {
        "id": row.id,
        "violation_type": row.violation_type,
        "object_id": row.object_id,
        "camera_id": row.camera_id,
        "timestamp": row.timestamp,
        "evidence_url": _violation_evidence_url(row),
        "evidence_media_type": _violation_evidence_media_type(row),
        "review_status": row.review_status or "needs_review",
        "review_notes": row.review_notes,
        "reviewed_at": row.reviewed_at,
        "camera_profile": camera_profile,
        "camera_defaults": camera_defaults,
        "related": {
            "detections": _serialize_recent_detections(detections),
            "speeds": _serialize_recent_speeds(speeds),
            "crossings": _serialize_recent_crossings(crossings),
        },
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/violations/{violation_id}/evidence")
def get_violation_evidence(violation_id: int, db: Session = Depends(get_db)):
    row = _apply_supported_violation_filter(db.query(models.DBViolation)).filter(
        models.DBViolation.id == violation_id
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="No evidence available")
    evidence_path, media_type = _violation_evidence_path_and_type(row)
    if evidence_path is None or media_type is None:
        raise HTTPException(status_code=404, detail="No evidence available")
    return FileResponse(evidence_path, media_type=media_type)


@router.get("/violations/detail/{violation_id}")
def get_violation_detail(violation_id: int, db: Session = Depends(get_db)):
    return _get_violation_detail_data(db, violation_id)


@router.patch("/violations/detail/{violation_id}/review")
def update_violation_review(
    violation_id: int,
    request: ViolationReviewUpdateRequest,
    db: Session = Depends(get_db),
):
    row = _apply_supported_violation_filter(db.query(models.DBViolation)).filter(
        models.DBViolation.id == violation_id
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Safety event not found")

    row.review_status = _normalize_review_status(request.review_status)
    row.review_notes = (request.review_notes or "").strip() or None
    row.reviewed_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Failed to update violation review: %s", e)
        raise HTTPException(status_code=500, detail="Database Error")

    return _get_violation_detail_data(db, violation_id)
