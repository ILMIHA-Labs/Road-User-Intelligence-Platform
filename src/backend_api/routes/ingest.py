"""Event ingest endpoints — single and batch."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ._config import _RETIRED_VIOLATION_TYPES

logger = logging.getLogger(__name__)
router = APIRouter()


def _dispatch_violation_alerts_safe(db: Session, violations: list) -> None:
    """Fire alerts for persisted violations. Best-effort — never breaks ingest."""
    try:
        from ..alerting import dispatch_violation_alerts
        dispatch_violation_alerts(db, violations)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Violation alert dispatch failed: %s", exc)


@router.post("/detections", status_code=201)
def create_detection(event: schemas.DetectionEvent, db: Session = Depends(get_db)):
    data = event.model_dump()
    data["class_name"] = event.class_name
    db.add(models.DBDetection(**data))
    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Failed to insert detection: %s", e)
        raise HTTPException(status_code=500, detail="Database Error")
    return {"message": "Detection stored"}


@router.post("/speeds", status_code=201)
def create_speed(event: schemas.SpeedEvent, db: Session = Depends(get_db)):
    db.add(models.DBSpeed(**event.model_dump()))
    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Failed to insert speed: %s", e)
        raise HTTPException(status_code=500, detail="Database Error")
    return {"message": "Speed stored"}


@router.post("/violations", status_code=201)
def create_violation(event: schemas.ViolationEvent, db: Session = Depends(get_db)):
    if event.violation_type in _RETIRED_VIOLATION_TYPES:
        raise HTTPException(status_code=410, detail="Safety event type is retired")
    db_violation = models.DBViolation(**event.model_dump())
    db.add(db_violation)
    try:
        db.commit()
        db.refresh(db_violation)
        from .violations import _capture_violation_evidence
        evidence_path, evidence_media_type = _capture_violation_evidence(db_violation)
        db_violation.evidence_media_path = evidence_path
        db_violation.evidence_media_type = evidence_media_type
        if evidence_path and evidence_media_type == "image/jpeg":
            db_violation.evidence_image_path = evidence_path
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Failed to insert violation: %s", e)
        raise HTTPException(status_code=500, detail="Database Error")
    _dispatch_violation_alerts_safe(db, [db_violation])
    return {"message": "Violation stored"}


@router.post("/trajectories", status_code=201)
def create_trajectory(event: schemas.TrajectoryEvent, db: Session = Depends(get_db)):
    db.add(models.DBTrajectory(**event.model_dump()))
    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Failed to insert trajectory: %s", e)
        raise HTTPException(status_code=500, detail="Database Error")
    return {"message": "Trajectory stored"}


@router.post("/crossings", status_code=201)
def create_crossing(event: schemas.CrossingEvent, db: Session = Depends(get_db)):
    data = event.model_dump()
    data["class_name"] = event.class_name
    db.add(models.DBCrossing(**data))
    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Failed to insert crossing: %s", e)
        raise HTTPException(status_code=500, detail="Database Error")
    return {"message": "Crossing stored"}


# ---------------------------------------------------------------------------
# Batch endpoints — buffer 100 ms of MQTT events and POST as arrays
# ---------------------------------------------------------------------------

@router.post("/detections/batch", status_code=207)
def create_detections_batch(events: list[schemas.DetectionEvent], db: Session = Depends(get_db)):
    for event in events:
        data = event.model_dump()
        data["class_name"] = event.class_name
        db.add(models.DBDetection(**data))
    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Failed to insert detection batch: %s", e)
        raise HTTPException(status_code=500, detail="Database Error")
    return {"inserted": len(events)}


@router.post("/speeds/batch", status_code=207)
def create_speeds_batch(events: list[schemas.SpeedEvent], db: Session = Depends(get_db)):
    for event in events:
        db.add(models.DBSpeed(**event.model_dump()))
    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Failed to insert speed batch: %s", e)
        raise HTTPException(status_code=500, detail="Database Error")
    return {"inserted": len(events)}


@router.post("/violations/batch", status_code=207)
def create_violations_batch(events: list[schemas.ViolationEvent], db: Session = Depends(get_db)):
    accepted = [e for e in events if e.violation_type not in _RETIRED_VIOLATION_TYPES]
    rows = [models.DBViolation(**event.model_dump()) for event in accepted]
    for row in rows:
        db.add(row)
    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Failed to insert violation batch: %s", e)
        raise HTTPException(status_code=500, detail="Database Error")
    _dispatch_violation_alerts_safe(db, rows)
    return {"inserted": len(accepted), "skipped": len(events) - len(accepted)}


@router.post("/trajectories/batch", status_code=207)
def create_trajectories_batch(events: list[schemas.TrajectoryEvent], db: Session = Depends(get_db)):
    for event in events:
        db.add(models.DBTrajectory(**event.model_dump()))
    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Failed to insert trajectory batch: %s", e)
        raise HTTPException(status_code=500, detail="Database Error")
    return {"inserted": len(events)}


@router.post("/crossings/batch", status_code=207)
def create_crossings_batch(events: list[schemas.CrossingEvent], db: Session = Depends(get_db)):
    for event in events:
        data = event.model_dump()
        data["class_name"] = event.class_name
        db.add(models.DBCrossing(**data))
    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Failed to insert crossing batch: %s", e)
        raise HTTPException(status_code=500, detail="Database Error")
    return {"inserted": len(events)}
