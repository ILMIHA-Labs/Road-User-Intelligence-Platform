import logging
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

from . import models, schemas
from .database import engine, get_db, init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BackendAPI")

app = FastAPI(title="Road User Intelligence Platform API")

@app.on_event("startup")
def startup_event():
    init_db()

@app.get("/")
def read_root():
    return {"status": "MVP API is running"}

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
def get_analytics_summary(db: Session = Depends(get_db)):
    """
    Very simple MVP aggregation endpoint.
    """
    detections = db.query(models.DBDetection).count()
    violations = db.query(models.DBViolation).count()
    
    return {
        "total_detections_logged": detections,
        "total_violations_logged": violations
    }
