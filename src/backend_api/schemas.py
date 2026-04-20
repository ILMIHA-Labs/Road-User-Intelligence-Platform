try:
    from common.event_schemas import DetectionEvent, SpeedEvent, TrajectoryEvent, ViolationEvent
except ImportError:
    from src.common.event_schemas import DetectionEvent, SpeedEvent, TrajectoryEvent, ViolationEvent

__all__ = ["DetectionEvent", "SpeedEvent", "ViolationEvent", "TrajectoryEvent"]
