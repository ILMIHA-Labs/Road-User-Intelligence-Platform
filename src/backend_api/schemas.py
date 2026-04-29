try:
    from common.event_schemas import CrossingEvent, DetectionEvent, SpeedEvent, TrajectoryEvent, ViolationEvent
except ImportError:
    from src.common.event_schemas import CrossingEvent, DetectionEvent, SpeedEvent, TrajectoryEvent, ViolationEvent

__all__ = ["CrossingEvent", "DetectionEvent", "SpeedEvent", "ViolationEvent", "TrajectoryEvent"]
