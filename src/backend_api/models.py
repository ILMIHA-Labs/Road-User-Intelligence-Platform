from sqlalchemy import Column, Integer, String, Float, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class DBDevice(Base):
    __tablename__ = "devices"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, unique=True, index=True)
    location = Column(String, nullable=True)

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

class DBTrajectory(Base):
    __tablename__ = "trajectories"
    id = Column(Integer, primary_key=True, index=True)
    object_id = Column(Integer, index=True)
    trajectory = Column(JSON) # Store array of points
    prediction_timestamp = Column(DateTime, index=True)
