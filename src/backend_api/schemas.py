from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class DetectionEvent(BaseModel):
    camera_id: str
    timestamp: datetime
    object_id: int
    class_name: str = Field(alias="class")
    helmet_status: str
    bbox: List[float]
    confidence: float
    frame_number: Optional[int] = None
    source: Optional[str] = "edge"

class SpeedEvent(BaseModel):
    camera_id: str
    object_id: int
    speed_kmh: float
    timestamp: datetime
    source: Optional[str] = "edge"

class ViolationEvent(BaseModel):
    violation_type: str
    object_id: int
    camera_id: str
    timestamp: datetime

class TrajectoryEvent(BaseModel):
    object_id: int
    trajectory: List[List[float]]
    prediction_timestamp: datetime
