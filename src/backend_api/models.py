from datetime import datetime

from sqlalchemy import Boolean, Column, Integer, String, Float, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class DBDevice(Base):
    __tablename__ = "devices"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, unique=True, index=True)
    location = Column(String, nullable=True)


class DBCameraConfig(Base):
    """Persisted control-plane configuration for a single camera node."""

    __tablename__ = "camera_configs"
    camera_id = Column(String, primary_key=True, index=True)
    location = Column(String, nullable=True, index=True)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    profile = Column(JSON, nullable=False)
    source = Column(String, nullable=False, default="api")
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

class DBDetection(Base):
    __tablename__ = "detections"
    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(String, index=True)
    timestamp = Column(DateTime, index=True)
    object_id = Column(Integer, index=True)
    class_name = Column("class", String)
    helmet_status = Column(String)
    bbox = Column(JSON) # Store as JSON array
    confidence = Column(Float)
    frame_number = Column(Integer, nullable=True)
    source = Column(String)

class DBSpeed(Base):
    __tablename__ = "speeds"
    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(String, index=True)
    object_id = Column(Integer, index=True)
    speed_kmh = Column(Float)
    timestamp = Column(DateTime, index=True)
    source = Column(String)

class DBViolation(Base):
    __tablename__ = "violations"
    id = Column(Integer, primary_key=True, index=True)
    violation_type = Column(String, index=True)
    object_id = Column(Integer, index=True)
    camera_id = Column(String, index=True)
    timestamp = Column(DateTime, index=True)
    evidence_image_path = Column(String, nullable=True)
    evidence_media_path = Column(String, nullable=True)
    evidence_media_type = Column(String, nullable=True)
    review_status = Column(String, nullable=True, index=True)
    review_notes = Column(String, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

class DBTrajectory(Base):
    __tablename__ = "trajectories"
    id = Column(Integer, primary_key=True, index=True)
    object_id = Column(Integer, index=True)
    trajectory = Column(JSON) # Store array of points
    prediction_timestamp = Column(DateTime, index=True)


class DBCrossing(Base):
    __tablename__ = "crossings"
    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(String, index=True)
    line_id = Column(String, index=True)
    line_label = Column(String)
    object_id = Column(Integer, index=True)
    class_name = Column("class", String, index=True)
    direction = Column(String, index=True)
    timestamp = Column(DateTime, index=True)
    frame_number = Column(Integer, nullable=True)
    source = Column(String)
