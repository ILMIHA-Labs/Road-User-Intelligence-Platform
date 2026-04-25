import logging
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml
from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy import func, case
from sqlalchemy.orm import Session
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles

from . import models, schemas
from .database import engine, get_db, init_db
from common.camera_config import normalize_zone_definitions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BackendAPI")

app = FastAPI(title="Road User Intelligence Platform API")

_CAMERAS_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "cameras.yaml"
_LIVE_FRAMES_DIR = Path(os.getenv("LIVE_PREVIEW_DIR", str(Path(__file__).resolve().parents[2] / "artifacts" / "live_frames")))

dashboard_dir = Path(__file__).resolve().parents[1] / "dashboard" / "app"
if dashboard_dir.exists():
    app.mount("/dashboard", StaticFiles(directory=dashboard_dir, html=True), name="dashboard")

@app.on_event("startup")
def startup_event():
    init_db()

@app.get("/")
def read_root():
    return {"status": "MVP API is running"}


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
        merged.append(profile)
    return {"defaults": defaults, "cameras": merged}


def _live_snapshot_path(camera_id: str) -> Path:
    return _LIVE_FRAMES_DIR / camera_id / "latest.jpg"


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

    recent_activity = [value for value in (last_detection, last_speed, last_violation) if value is not None]
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
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to insert violation: {e}")
        raise HTTPException(status_code=500, detail="Database Error")
    return {"message": "Violation stored"}

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

@app.get("/analytics/summary")
def get_analytics_summary(
    camera_id: str = Query(default=None),
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    db: Session = Depends(get_db),
):
    detection_query = db.query(models.DBDetection)
    detection_query = _apply_camera_filter(detection_query, models.DBDetection, camera_id)
    detection_query = _apply_time_filters(detection_query, models.DBDetection, start, end)

    violation_query = db.query(models.DBViolation)
    violation_query = _apply_camera_filter(violation_query, models.DBViolation, camera_id)
    violation_query = _apply_time_filters(violation_query, models.DBViolation, start, end)

    speed_query = db.query(models.DBSpeed)
    speed_query = _apply_camera_filter(speed_query, models.DBSpeed, camera_id)
    speed_query = _apply_time_filters(speed_query, models.DBSpeed, start, end)

    detections = detection_query.count()
    violations = violation_query.count()
    speeds = speed_query.count()
    
    return {
        "camera_id": camera_id,
        "start": start,
        "end": end,
        "total_detections_logged": detections,
        "total_speeds_logged": speeds,
        "total_violations_logged": violations
    }


@app.get("/analytics/by-camera")
def get_analytics_by_camera(
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    db: Session = Depends(get_db),
):
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

    summary = {}
    for row in detection_rows:
        summary.setdefault(row.camera_id, {"camera_id": row.camera_id, "detections": 0, "speeds": 0, "violations": 0})
        summary[row.camera_id]["detections"] = row.detections
    for row in speed_rows:
        summary.setdefault(row.camera_id, {"camera_id": row.camera_id, "detections": 0, "speeds": 0, "violations": 0})
        summary[row.camera_id]["speeds"] = row.speeds
    for row in violation_rows:
        summary.setdefault(row.camera_id, {"camera_id": row.camera_id, "detections": 0, "speeds": 0, "violations": 0})
        summary[row.camera_id]["violations"] = row.violations

    return {
        "start": start,
        "end": end,
        "cameras": sorted(summary.values(), key=lambda item: item["camera_id"]),
    }


@app.get("/analytics/violations")
def get_violation_breakdown(
    camera_id: str = Query(default=None),
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    db: Session = Depends(get_db),
):
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


@app.get("/events/recent")
def get_recent_events(
    camera_id: str = Query(default=None),
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
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

    return {
        "camera_id": camera_id,
        "start": start,
        "end": end,
        "detections": [
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
            for row in detections
        ],
        "speeds": [
            {
                "camera_id": row.camera_id,
                "object_id": row.object_id,
                "speed_kmh": row.speed_kmh,
                "timestamp": row.timestamp,
                "source": row.source,
            }
            for row in speeds
        ],
        "violations": [
            {
                "violation_type": row.violation_type,
                "object_id": row.object_id,
                "camera_id": row.camera_id,
                "timestamp": row.timestamp,
            }
            for row in violations
        ],
    }


@app.get("/analytics/speed-distribution")
def get_speed_distribution(
    camera_id: str = Query(default=None),
    start: datetime = Query(default=None),
    end: datetime = Query(default=None),
    db: Session = Depends(get_db),
):
    """Return speed counts bucketed into 20 km/h bands."""
    BANDS = [
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
            for lo, hi, label in BANDS
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
            for _, _, label in BANDS
        ],
    }


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
    """Paginated, filterable violations list with total count."""
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
        "items": [
            {
                "id": row.id,
                "violation_type": row.violation_type,
                "object_id": row.object_id,
                "camera_id": row.camera_id,
                "timestamp": row.timestamp,
            }
            for row in rows
        ],
    }
