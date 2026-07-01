import importlib

try:
    _event_schemas = importlib.import_module("common.event_schemas")
except ImportError:
    _event_schemas = importlib.import_module("src.common.event_schemas")

CrossingEvent = _event_schemas.CrossingEvent
DetectionEvent = _event_schemas.DetectionEvent
SpeedEvent = _event_schemas.SpeedEvent
TrajectoryEvent = _event_schemas.TrajectoryEvent
ViolationEvent = _event_schemas.ViolationEvent

__all__ = ["CrossingEvent", "DetectionEvent", "SpeedEvent", "ViolationEvent", "TrajectoryEvent"]
