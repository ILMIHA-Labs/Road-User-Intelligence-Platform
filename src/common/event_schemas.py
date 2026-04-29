import json
from datetime import datetime
from typing import Dict, List, Optional, Type, Union

from pydantic import BaseModel, ConfigDict, Field


class PlatformEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class DetectionEvent(PlatformEvent):
    camera_id: str
    timestamp: datetime
    object_id: int
    class_name: str = Field(alias="class")
    helmet_status: str
    bbox: List[float]
    confidence: float
    frame_number: Optional[int] = None
    source: str = "edge"


class SpeedEvent(PlatformEvent):
    camera_id: str
    object_id: int
    speed_kmh: float
    timestamp: datetime
    source: str = "edge"


class ViolationEvent(PlatformEvent):
    violation_type: str
    object_id: int
    camera_id: str
    timestamp: datetime


class CrossingEvent(PlatformEvent):
    camera_id: str
    line_id: str
    line_label: str
    object_id: int
    class_name: str = Field(alias="class")
    direction: str
    timestamp: datetime
    frame_number: Optional[int] = None
    source: str = "edge"


class TrajectoryEvent(PlatformEvent):
    object_id: int
    trajectory: List[List[float]]
    prediction_timestamp: datetime


EventModel = Union[DetectionEvent, SpeedEvent, ViolationEvent, CrossingEvent, TrajectoryEvent]

MQTT_TOPIC_TO_SCHEMA: Dict[str, Type[PlatformEvent]] = {
    "camera/detections": DetectionEvent,
    "camera/speeds": SpeedEvent,
    "camera/violations": ViolationEvent,
    "camera/crossings": CrossingEvent,
    "camera/trajectories": TrajectoryEvent,
}


def parse_event(schema: Type[PlatformEvent], payload: Union[str, bytes, dict]) -> PlatformEvent:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")

    if isinstance(payload, str):
        payload = json.loads(payload)

    return schema.model_validate(payload)


def parse_event_for_topic(topic: str, payload: Union[str, bytes, dict]) -> EventModel:
    schema = MQTT_TOPIC_TO_SCHEMA.get(topic)
    if schema is None:
        raise ValueError(f"No schema registered for topic: {topic}")
    return parse_event(schema, payload)


def dump_event(event: EventModel) -> dict:
    return event.model_dump(mode="json", by_alias=True)
