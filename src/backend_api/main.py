import logging
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.staticfiles import StaticFiles

from . import models, schemas
from .database import engine, get_db, init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BackendAPI")

app = FastAPI(title="Road User Intelligence Platform API")

dashboard_dir = Path(__file__).resolve().parents[1] / "dashboard" / "app"
if dashboard_dir.exists():
    app.mount("/dashboard", StaticFiles(directory=dashboard_dir, html=True), name="dashboard")

@app.on_event("startup")
def startup_event():
    init_db()

@app.get("/")
def read_root():
    return {"status": "MVP API is running"}


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
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    detections_query = db.query(models.DBDetection)
    detections_query = _apply_camera_filter(detections_query, models.DBDetection, camera_id)
    detections = detections_query.order_by(models.DBDetection.timestamp.desc()).limit(limit).all()

    speeds_query = db.query(models.DBSpeed)
    speeds_query = _apply_camera_filter(speeds_query, models.DBSpeed, camera_id)
    speeds = speeds_query.order_by(models.DBSpeed.timestamp.desc()).limit(limit).all()

    violations_query = db.query(models.DBViolation)
    violations_query = _apply_camera_filter(violations_query, models.DBViolation, camera_id)
    violations = violations_query.order_by(models.DBViolation.timestamp.desc()).limit(limit).all()

    return {
        "camera_id": camera_id,
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
